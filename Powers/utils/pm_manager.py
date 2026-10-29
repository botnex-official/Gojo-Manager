import importlib
import inspect
import pkgutil
import re
import shlex
import sys
from dataclasses import dataclass
from typing import Dict, Optional, Set

from pyrogram.enums import ChatMemberStatus as CMS, ChatType
from pyrogram.types import InlineKeyboardMarkup, Message

from Powers import LOGGER
from Powers.database.pm_connection_db import PMConnectionDB
from Powers.vars import Config
from Powers.utils.permissions import PERMISSION_ATTRIBUTES

PM_DB = PMConnectionDB()

# Commands that are deliberately never exposed through the PM management bridge.
# These are bot-global/dev operations rather than connected-group administration.
BLOCKED_PM_MODULES = {
    "dev",
    "devs",
    "botstaff",
    "stats",
    "chat_blacklist",
    "antispam",  # Global Ban plugin, not the per-group advanced anti-spam plugin.
    "birthday",
    "fun",
    "formatting",
    "stickers",
}

BLOCKED_PM_COMMANDS = {
    "help",
    "adddev",
    "rmdev",
    "gban",
    "globalban",
    "stats",
    "blchat",
    "botstaff",
}

PRIVILEGE_FILTERS = {
    "admin_check_func": "admin",
    "restrict_check_func": "restrict",
    "promote_check_func": "promote",
    "changeinfo_check_func": "change_info",
    "can_pin_message_func": "pin",
    "bot_admin_check_func": "bot_admin",
    "owner_check_func": "owner",
}

_PLUGINS_BOOTSTRAPPED = False


def _ensure_plugins_loaded():
    """Ensure every normal plugin is imported before command discovery."""
    global _PLUGINS_BOOTSTRAPPED
    if _PLUGINS_BOOTSTRAPPED:
        return

    import Powers.plugins as plugins_package

    for module_info in pkgutil.iter_modules(plugins_package.__path__):
        module_name = module_info.name
        if module_name.startswith("_") or module_name in BLOCKED_PM_MODULES:
            continue
        try:
            importlib.import_module(f"Powers.plugins.{module_name}")
        except Exception as exc:
            LOGGER.warning(
                "PM manager could not load plugin %s for command discovery: %s",
                module_name,
                exc,
            )

    _PLUGINS_BOOTSTRAPPED = True

PREFIX_RE = re.compile(
    r"^(?P<prefix>[/!$])(?P<command>[A-Za-z0-9_]+)(?:@(?P<bot>[A-Za-z0-9_]+))?(?:\s+(?P<args>.*))?$",
    re.S,
)


@dataclass(frozen=True)
class HandlerSpec:
    callback: object
    requirements: frozenset
    module_name: str


class PMMessageProxy:
    """Make a PM command look like a group command while sending replies back to PM."""

    def __init__(self, client, pm_message: Message, target_chat, command_parts):
        self._client = client
        self._pm_message = pm_message
        self.chat = target_chat
        self.from_user = pm_message.from_user
        self.sender_chat = None
        self.text = pm_message.text
        self.caption = pm_message.caption
        self.id = pm_message.id
        self.command = command_parts
        self.reply_to_message = None
        self.reply_to_message_id = None
        self.matches = getattr(pm_message, "matches", None)

    def __getattr__(self, name):
        return getattr(self._pm_message, name)

    async def reply_text(self, text, **kwargs):
        return await self._client.send_message(
            self._pm_message.chat.id,
            text,
            **_clean_reply_kwargs(kwargs),
        )

    async def reply_animation(self, animation, **kwargs):
        return await self._client.send_animation(
            self._pm_message.chat.id,
            animation,
            **_clean_reply_kwargs(kwargs),
        )

    async def reply_photo(self, photo, **kwargs):
        return await self._client.send_photo(
            self._pm_message.chat.id,
            photo,
            **_clean_reply_kwargs(kwargs),
        )

    async def reply_document(self, document, **kwargs):
        return await self._client.send_document(
            self._pm_message.chat.id,
            document,
            **_clean_reply_kwargs(kwargs),
        )

    async def reply_video(self, video, **kwargs):
        return await self._client.send_video(
            self._pm_message.chat.id,
            video,
            **_clean_reply_kwargs(kwargs),
        )

    async def reply_audio(self, audio, **kwargs):
        return await self._client.send_audio(
            self._pm_message.chat.id,
            audio,
            **_clean_reply_kwargs(kwargs),
        )

    async def reply_voice(self, voice, **kwargs):
        return await self._client.send_voice(
            self._pm_message.chat.id,
            voice,
            **_clean_reply_kwargs(kwargs),
        )

    async def reply_sticker(self, sticker, **kwargs):
        return await self._client.send_sticker(
            self._pm_message.chat.id,
            sticker,
            **_clean_reply_kwargs(kwargs),
        )

    async def reply_video_note(self, video_note, **kwargs):
        return await self._client.send_video_note(
            self._pm_message.chat.id,
            video_note,
            **_clean_reply_kwargs(kwargs),
        )

    async def reply(self, text=None, **kwargs):
        if text is not None:
            return await self.reply_text(text, **kwargs)
        return await self._pm_message.reply(**kwargs)


_PM_SEND_METHODS = {
    "send_message",
    "send_photo",
    "send_document",
    "send_animation",
    "send_video",
    "send_audio",
    "send_voice",
    "send_sticker",
    "send_video_note",
}


def _same_chat(value, chat_id):
    if value is None:
        return False
    return getattr(value, "id", value) == chat_id


class PMClientProxy:
    """Client wrapper used while executing a command through the PM bridge.

    Everything delegates to the real client EXCEPT content sends addressed
    to the connected group. Some handlers post their result with
    ``client.send_message(message.chat.id, ...)`` instead of ``reply_*``
    (greetings /welcome and /goodbye are the known cases). Through the
    bridge ``message.chat.id`` is the connected group, so those posts
    leaked INTO the group — querying /welcome in PM posted the welcome
    text into the group itself. Sends targeting the connected chat are
    delivered to the admin's PM instead; sends to any other chat (log
    channels, dumps) and every non-send call (member lookups, bans,
    permission changes) pass through untouched.
    """

    def __init__(self, client, pm_chat_id, target_chat_id):
        self._client = client
        self._pm_chat_id = pm_chat_id
        self._target_chat_id = target_chat_id

    def __getattr__(self, name):
        attr = getattr(self._client, name)
        if name not in _PM_SEND_METHODS or not callable(attr):
            return attr

        async def _send_as_pm(*args, **kwargs):
            args, kwargs = self._redirect(args, kwargs)
            return await attr(*args, **kwargs)

        return _send_as_pm

    def _redirect(self, args, kwargs):
        kwargs = dict(kwargs)
        if args:
            if _same_chat(args[0], self._target_chat_id):
                args = (self._pm_chat_id,) + tuple(args[1:])
                kwargs = _clean_reply_kwargs(kwargs)
        elif _same_chat(kwargs.get("chat_id"), self._target_chat_id):
            kwargs["chat_id"] = self._pm_chat_id
            kwargs = _clean_reply_kwargs(kwargs)
        return args, kwargs


def _clean_reply_kwargs(kwargs):
    kwargs = dict(kwargs)
    # Group message IDs have no meaning in the user's PM.
    kwargs.pop("reply_to_message_id", None)
    kwargs.pop("quote", None)
    markup = kwargs.get("reply_markup")
    if isinstance(markup, InlineKeyboardMarkup):
        # Confirmation prompts (clear rules, clear all notes/filters/
        # blacklists, unapprove all, unpin all, and their shared Cancel
        # button) must keep their buttons in PM: without them the admin
        # can neither confirm nor cancel, so the action is impossible
        # from the connected group — the same failure the gsettings:
        # allowlist fixed for the settings panel. The plugin callbacks
        # resolve the PM-connected chat themselves (resolve_confirm_chat).
        safe_callback_data = {
            "clear_rules",
            "close_admin",
            "clear_notes",
            "rm_allfilters",
            "rm_allblacklist",
            "unapprove_all",
            "unpin all in this chat",
        }
        rows = []
        for row in markup.inline_keyboard:
            safe_row = [
                button for button in row
                if button.url
                or button.switch_inline_query
                or button.switch_inline_query_current_chat
                or (
                    button.callback_data
                    and (
                        str(button.callback_data).startswith("gsettings:")
                        or str(button.callback_data) in safe_callback_data
                    )
                )
            ]
            if safe_row:
                rows.append(safe_row)
        kwargs["reply_markup"] = InlineKeyboardMarkup(rows) if rows else None
    return kwargs


def _walk_filters(filter_obj):
    if filter_obj is None:
        return

    name = type(filter_obj).__name__
    if name in PRIVILEGE_FILTERS:
        yield PRIVILEGE_FILTERS[name]

    commands = getattr(filter_obj, "commands", None)
    if name == "NormalCommandFilter" and commands:
        yield ("commands", {str(c).lower() for c in commands})

    data = getattr(filter_obj, "__dict__", {})
    for key in ("base", "other"):
        child = data.get(key)
        if child is not None:
            yield from _walk_filters(child)


def _discover_handlers() -> Dict[str, HandlerSpec]:
    discovered = {}

    for module_name, module in sorted(sys.modules.items()):
        if not module_name.startswith("Powers.plugins."):
            continue

        short_name = module_name.rsplit(".", 1)[-1].lower()
        if short_name in BLOCKED_PM_MODULES:
            continue

        for _, callback in inspect.getmembers(module, inspect.iscoroutinefunction):
            for handler_entry in getattr(callback, "handlers", []):
                handler = handler_entry[0]
                if not handler.__class__.__name__.lower().endswith("messagehandler"):
                    continue

                commands: Set[str] = set()
                requirements: Set[str] = set()
                for item in _walk_filters(getattr(handler, "filters", None)):
                    if isinstance(item, tuple) and item and item[0] == "commands":
                        commands.update(item[1])
                    elif isinstance(item, str):
                        requirements.add(item)

                if not commands:
                    continue

                # Prefer the real group handler over a PM-only bridge handler.
                for command_name in sorted(commands):
                    if command_name in BLOCKED_PM_COMMANDS:
                        continue
                    spec = HandlerSpec(
                        callback=callback,
                        requirements=frozenset(requirements),
                        module_name=short_name,
                    )
                    current = discovered.get(command_name)
                    if current is None:
                        discovered[command_name] = spec
                    elif "admin" in spec.requirements and "admin" not in current.requirements:
                        discovered[command_name] = spec

    return discovered


def _parse_pm_command(message):
    text = message.text or ""
    match = PREFIX_RE.match(text.strip())
    if not match:
        return None

    bot_name = (match.group("bot") or "").lower()
    configured_bot = str(Config.BOT_USERNAME).lstrip("@").lower()
    if bot_name and bot_name != configured_bot:
        return None

    command_name = match.group("command").lower()
    args = match.group("args") or ""
    try:
        arg_list = shlex.split(args)
    except ValueError:
        arg_list = args.split()

    return [command_name, *arg_list]


def _is_permanent_connection_error(exc):
    """Return True only for errors that invalidate a saved chat connection."""
    return type(exc).__name__ in {
        "PeerIdInvalid",
        "ChatIdInvalid",
        "ChannelInvalid",
        "UserNotParticipant",
    }


async def _connected_chat(client, user_id):
    connection = PM_DB.get(user_id)
    if not connection:
        return None, "❌ No group is connected to your PM. Open the group's /start message and tap <b>Connect me to pm</b>."

    chat_id = connection.get("chat_id")
    if not isinstance(chat_id, int) or chat_id >= 0:
        return None, "❌ Saved PM connection is invalid. Please reconnect the group."

    try:
        member = await client.get_chat_member(chat_id, user_id)
    except Exception as exc:
        if _is_permanent_connection_error(exc):
            PM_DB.disconnect(user_id)
            return None, (
                "❌ The connected group is no longer available. "
                "The PM connection has been removed; please reconnect it."
            )
        return None, (
            "❌ I cannot access the connected group right now. "
            "Please try again in a moment."
        )

    if member.status not in {CMS.OWNER, CMS.ADMINISTRATOR}:
        PM_DB.disconnect(user_id)
        return None, "❌ You are no longer an admin of the connected group. The PM connection has been removed."

    try:
        chat = await client.get_chat(chat_id)
    except Exception as exc:
        if _is_permanent_connection_error(exc):
            PM_DB.disconnect(user_id)
            return None, (
                "❌ The connected group is no longer available. "
                "The PM connection has been removed; please reconnect it."
            )
        return None, "❌ I could not load the connected group right now. Please try again."

    return (chat, member), None


async def resolve_confirm_chat(client, query):
    """Resolve the chat a confirmation-style callback acts on.

    Confirmation prompts (clear rules, clear all notes/filters/
    blacklists, unapprove all, unpin all, and their shared Cancel
    button) are answered by plugin callback handlers, not by the PM
    router, so the bridge cannot rewrite their message context. In a
    group, the callback message's own chat is the target and the
    clicker's status comes from that chat — the historical behaviour.
    In a private chat the prompt was delivered through this bridge, so
    the target is the clicker's PM-connected group and their status is
    resolved there instead; without this, the handlers read membership
    of (and acted on) the private chat itself, which either crashed on
    the user-peer or silently targeted the wrong chat. Returns
    (chat_id, status), or (None, None) when no target can be resolved
    (no connection, or the clicker is not a member of the connected
    group).
    """
    message = getattr(query, "message", None)
    chat = getattr(message, "chat", None)
    if chat is None:
        return None, None
    if chat.type != ChatType.PRIVATE:
        try:
            member = await chat.get_member(query.from_user.id)
        except Exception:
            return None, None
        return chat.id, member.status
    connection = PM_DB.get(query.from_user.id)
    if not connection:
        return None, None
    chat_id = connection.get("chat_id")
    if not isinstance(chat_id, int) or chat_id >= 0:
        return None, None
    try:
        member = await client.get_chat_member(chat_id, query.from_user.id)
    except Exception:
        return None, None
    return chat_id, member.status


def _member_allows(member, permission):
    """Privilege test against an already-resolved ChatMember.

    Mirrors the semantics of Powers.utils.custom_filters._member_allows,
    but takes the member object directly so the PM bridge never has to
    re-resolve membership through the (PM-context) message.
    """
    if not member:
        return False
    if permission == "admin":
        return member.status in {CMS.OWNER, CMS.ADMINISTRATOR}
    if permission == "owner":
        return member.status == CMS.OWNER
    attribute = PERMISSION_ATTRIBUTES.get(permission)
    if attribute is None or member.status not in {CMS.OWNER, CMS.ADMINISTRATOR}:
        return False
    return bool(getattr(getattr(member, "privileges", None), attribute, False))


async def _check_requirements(client, chat_id, member, requirements):
    """Validate command privileges against the CONNECTED chat.

    Authorization is evaluated exactly where the command will act:
    (1) the sender's status and fine-grained rights come from `member`,
    the sender's ChatMember of the connected group that _connected_chat
    already resolved (and admin-verified); (2) bot_admin is checked
    against the BOT's membership of the connected group. Nothing is
    resolved against the PM chat — a private chat has no members, so
    checks aimed at it can only ever fail or blow up, which is how
    typed PM admin commands used to die even for the group's owner.
    """
    if "owner" in requirements and not _member_allows(member, "owner"):
        return "❌ This command requires the group owner."

    checks = {
        "admin": "admin",
        "restrict": "restrict",
        "promote": "promote",
        "change_info": "change_info",
        "pin": "pin",
        "bot_admin": "bot_admin",
    }
    errors = {
        "admin": "❌ You need to be a group admin for this command.",
        "restrict": "❌ You need the <b>Restrict Members</b> admin right for this command.",
        "promote": "❌ You need the <b>Add New Admins</b> admin right for this command.",
        "change_info": "❌ You need the <b>Change Group Info</b> admin right for this command.",
        "pin": "❌ You need the <b>Pin Messages</b> admin right for this command.",
        "bot_admin": "❌ I am not an admin in the connected group.",
    }

    for requirement in requirements:
        permission = checks.get(requirement)
        if not permission:
            continue
        if permission == "bot_admin":
            try:
                bot_member = await client.get_chat_member(chat_id, Config.BOT_ID)
            except Exception:
                bot_member = None
            allowed = bool(
                bot_member
                and bot_member.status in {CMS.OWNER, CMS.ADMINISTRATOR}
            )
        else:
            allowed = _member_allows(member, permission)
        if not allowed:
            return errors[requirement]

    return None


async def pm_management_router(client, message):
    command_parts = _parse_pm_command(message)
    if not command_parts:
        return

    command_name = command_parts[0]

    if command_name == "pmstatus":
        connected, error = await _connected_chat(client, message.from_user.id)
        if error:
            await message.reply_text(error)
        else:
            chat, member = connected
            role = "Owner" if member.status == CMS.OWNER else "Admin"
            await message.reply_text(
                f"🔗 <b>PM Management Connected</b>\n\n"
                f"Group: <b>{chat.title}</b>\n"
                f"Group ID: <code>{chat.id}</code>\n"
                f"Your role: <b>{role}</b>\n\n"
                "You can now manage this group directly from PM."
            )
        await message.stop_propagation()
        return

    if command_name == "disconnect":
        connection = PM_DB.get(message.from_user.id)
        if not connection:
            await message.reply_text("ℹ️ No group is connected to your PM.")
        else:
            PM_DB.disconnect(message.from_user.id)
            await message.reply_text("✅ PM management disconnected for the current group.")
        await message.stop_propagation()
        return

    if command_name in {"connections", "connection"}:
        connected, error = await _connected_chat(client, message.from_user.id)
        if error:
            await message.reply_text(error)
        else:
            chat, member = connected
            role = "Owner" if member.status == CMS.OWNER else "Admin"
            await message.reply_text(
                f"🔗 <b>Your PM connections</b>\n\n"
                f"Group: <b>{chat.title}</b>\n"
                f"Group ID: <code>{chat.id}</code>\n"
                f"Your role: <b>{role}</b>\n\n"
                "Only one group can be connected at a time. "
                "Use /disconnect to remove it, or /connect in another "
                "group to replace it."
            )
        await message.stop_propagation()
        return

    # /start must always reach the normal start plugin. PM linking is
    # initiated from the group with /connect; the deep-link payload is then
    # handled by the existing /start handler in PM.
    if command_name == "start":
        message.continue_propagation()
        return

    if command_name in BLOCKED_PM_COMMANDS:
        # Bot-global commands must keep their normal PM behaviour. The PM
        # bridge only owns connected-group management commands.
        message.continue_propagation()
        return

    # Keep normal PM commands such as /start, /help and plugin utilities untouched.
    _ensure_plugins_loaded()
    handlers = _discover_handlers()
    spec = handlers.get(command_name)
    if spec is None:
        # Do not swallow unrelated/private bot commands. If the command is
        # not part of the connected-group management surface, let its normal
        # handler (if any) process it.
        message.continue_propagation()
        return

    connected, error = await _connected_chat(client, message.from_user.id)
    if error:
        await message.reply_text(error)
        await message.stop_propagation()
        return

    chat, member = connected
    proxy = PMMessageProxy(client, message, chat, command_parts)
    try:
        permission_error = await _check_requirements(
            client, chat.id, member, spec.requirements
        )
    except Exception:
        # The bridge owns this update (a discovered command with an
        # active connection): a failing check must surface as an error
        # in PM, never escape and let the raw update fall through to
        # the plugin handlers in the DM context, where their own
        # privilege filters misfire with misleading refusals.
        LOGGER.exception(
            "PM management permission check failed: /%s for user %s in chat %s",
            command_name,
            message.from_user.id,
            chat.id,
        )
        await message.reply_text(
            "❌ Command failed while managing the connected group."
        )
        await message.stop_propagation()
        return
    if permission_error:
        await message.reply_text(permission_error)
        await message.stop_propagation()
        return

    # Commands which fundamentally require a replied group message cannot be
    # executed safely from PM without a message ID. Tell the user how to use
    # the command rather than silently targeting the wrong message.
    callback_source = inspect.getsource(spec.callback)
    if "reply_to_message" in callback_source and command_name in {
        "pin", "dtban", "dtmute", "dban", "sban", "skick", "dkick",
        "dmute", "smute", "unpinall", "purge", "spurge", "del",
    }:
        # User-target forms are still valid for ban/mute/kick commands when
        # supplied as arguments. Only reject when no argument can identify a
        # target and the callback is known to depend on replies.
        if command_name in {"ban", "tban", "stban", "unban", "kick", "mute", "tmute", "stmute", "unmute"}:
            pass
        elif len(command_parts) == 1:
            await message.reply_text(
                f"❌ <code>/{command_name}</code> normally requires a replied group message. "
                "From PM, use the command with a target/message ID where supported."
            )
            await message.stop_propagation()
            return

    target_message = None
    if command_name in {"pin", "purge", "spurge", "del"} and len(command_parts) >= 2:
        try:
            target_id = int(command_parts[1])
        except (TypeError, ValueError):
            target_id = None
        if target_id is not None:
            try:
                target_message = await client.get_messages(chat.id, target_id)
            except Exception:
                target_message = None
            if target_message is None or getattr(target_message, "empty", False):
                await message.reply_text(
                    f"❌ I could not find message <code>{target_id}</code> in the connected group."
                )
                await message.stop_propagation()
                return

    proxy.reply_to_message = target_message
    proxy.reply_to_message_id = getattr(target_message, "id", None)
    try:
        await spec.callback(
            PMClientProxy(client, message.chat.id, chat.id), proxy
        )
    except Exception as exc:
        LOGGER.exception(
            "PM management command failed: /%s for user %s in chat %s",
            command_name,
            message.from_user.id,
            chat.id,
        )
        await message.reply_text(
            "❌ Command failed while managing the connected group.\n"
            f"<code>{type(exc).__name__}: {exc}</code>"
        )

    await message.stop_propagation()

__all__ = [
    "pm_management_router",
    "PMClientProxy",
    "PMMessageProxy",
    "resolve_confirm_chat",
]
