from re import compile as compile_re
from re import escape
from shlex import split
from typing import List, Union

from pyrogram.enums import ChatMemberStatus as CMS
from pyrogram.enums import ChatType
from pyrogram.errors import RPCError, UserNotParticipant
from pyrogram.filters import create
from pyrogram.types import CallbackQuery, Message

from Powers import DEV_LEVEL, OWNER_ID, SUDO_LEVEL
from Powers.database.disable_db import Disabling
from Powers.utils.disable_control import should_block_command
from Powers.utils.permissions import PERMISSION_ATTRIBUTES, has_permission
from Powers.vars import Config


def command(
    commands: Union[str, List[str]],
    case_sensitive: bool = False,
    owner_cmd: bool = False,
    dev_cmd: bool = False,
    sudo_cmd: bool = False,
):
    async def func(flt, _, m: Message):
        if not m:
            return

        date = m.edit_date
        if date:
            return  # reaction

        if m.chat and m.chat.type == ChatType.CHANNEL:
            return

        if m and not m.from_user:
            return False

        if m.from_user.is_bot:
            return False

        if any([m.forward_from_chat, m.forward_from]):
            return False

        if owner_cmd and (m.from_user.id != OWNER_ID):
            # Only owner allowed to use this...!
            return False

        if dev_cmd and (m.from_user.id not in DEV_LEVEL):
            # Only devs allowed to use this...!
            return False

        if sudo_cmd and (m.from_user.id not in SUDO_LEVEL):
            # Only sudos and above allowed to use it
            return False

        text: str = m.text or m.caption
        if not text:
            return False
        regex = r"^[{prefix}](\w+)(@{bot_name})?(?: |$)(.*)".format(
            prefix="|".join(escape(x) for x in Config.PREFIX_HANDLER),
            bot_name=Config.BOT_USERNAME,
        )
        matches = compile_re(regex).search(text)
        if matches:
            m.command = [matches.group(1)]
            if matches.group(1) not in flt.commands:
                return False
            if bool(m.chat and m.chat.type in {ChatType.SUPERGROUP, ChatType.GROUP}):
                is_admin = await has_permission(m, "admin")
                ddb = Disabling(m.chat.id)
                command_name = str(matches.group(1)).lower()
                if should_block_command(command_name, ddb.get_disabled(), is_admin):
                    if ddb.get_action() == "del":
                        try:
                            await m.delete()
                        except RPCError:
                            pass
                    return False
            if matches.group(3) == "":
                return True
            try:
                for arg in split(matches.group(3)):
                    m.command.append(arg)
            except ValueError:
                pass
            return True
        return False

    commands = commands if isinstance(commands, list) else [commands]
    commands = {c if case_sensitive else c.lower() for c in commands}

    return create(
        func,
        "NormalCommandFilter",
        commands=commands,
        case_sensitive=case_sensitive,
    )


def _member_allows(member, permission: str) -> bool:
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


async def _callback_has_permission(query: CallbackQuery, permission: str) -> bool:
    """Check the user who tapped, not the author of the attached message."""
    user = getattr(query, "from_user", None)
    if user is None or getattr(user, "id", None) is None:
        return False
    message = getattr(query, "message", None)
    chat = getattr(message, "chat", None) if message is not None else None
    if chat is None:
        return False
    try:
        member = await chat.get_member(user.id)
    except (UserNotParticipant, ValueError):
        return False
    return _member_allows(member, permission)


async def bot_admin_check_func(_, __, m: Message or CallbackQuery):
    """Check if the bot is an admin in the target group."""
    if isinstance(m, CallbackQuery):
        m = m.message
    if m is None:
        return False

    allowed = await has_permission(m, "bot_admin", Config.BOT_ID)
    if not allowed:
        await m.reply_text(
            "I am not an admin to receive updates in this group; Mind Promoting?",
        )
    return allowed


async def admin_check_func(_, __, m: Message or CallbackQuery):
    """Check if the user is an admin in the target group."""
    if isinstance(m, CallbackQuery):
        allowed = await _callback_has_permission(m, "admin")
        if not allowed and getattr(m, "message", None) is not None:
            await m.message.reply_text(text="You cannot use an admin command!")
        return allowed

    allowed = await has_permission(m, "admin")
    if not allowed:
        await m.reply_text(text="You cannot use an admin command!")
    return allowed


async def owner_check_func(_, __, m: Message or CallbackQuery):
    """Check if the user is the group owner."""
    if isinstance(m, CallbackQuery):
        allowed = await _callback_has_permission(m, "owner")
        if not allowed and getattr(m, "message", None) is not None:
            await m.message.reply_text("You must be the group owner to use this command!")
        return allowed

    allowed = await has_permission(m, "owner")
    if not allowed:
        await m.reply_text("You must be the group owner to use this command!")
    return allowed


async def restrict_check_func(_, __, m: Message or CallbackQuery):
    """Check if the user can restrict members."""
    if isinstance(m, CallbackQuery):
        allowed = await _callback_has_permission(m, "restrict")
        if not allowed and getattr(m, "message", None) is not None:
            await m.message.reply_text(text="You don't have permissions to restrict members!")
        return allowed

    allowed = await has_permission(m, "restrict")
    if not allowed:
        await m.reply_text(text="You don't have permissions to restrict members!")
    return allowed


async def promote_check_func(_, __, m):
    """Check if the user can promote members."""
    if isinstance(m, CallbackQuery):
        allowed = await _callback_has_permission(m, "promote")
        if not allowed and getattr(m, "message", None) is not None:
            await m.message.reply_text(text="You don't have permission to promote members!")
        return allowed

    allowed = await has_permission(m, "promote")
    if not allowed:
        await m.reply_text(text="You don't have permission to promote members!")
    return allowed


async def changeinfo_check_func(_, __, m):
    """Check if the user can change group info."""
    if isinstance(m, CallbackQuery):
        allowed = await _callback_has_permission(m, "change_info")
        if not allowed and getattr(m, "message", None) is not None:
            await m.message.reply_text("You don't have: can_change_info permission!")
        return allowed

    allowed = await has_permission(m, "change_info")
    if not allowed:
        await m.reply_text("You don't have: can_change_info permission!")
    return allowed


async def can_pin_message_func(_, __, m):
    """Check if the user can pin messages."""
    if isinstance(m, CallbackQuery):
        user = getattr(m, "from_user", None)
        if user is not None and user.id in SUDO_LEVEL:
            return True
        allowed = await _callback_has_permission(m, "pin")
        if not allowed and getattr(m, "message", None) is not None:
            await m.message.reply_text("You don't have: can_pin_messages permission!")
        return allowed

    # Preserve the existing developer/sudo/owner bypass.
    if getattr(m, "from_user", None) and m.from_user.id in SUDO_LEVEL:
        return True

    allowed = await has_permission(m, "pin")
    if not allowed:
        await m.reply_text("You don't have: can_pin_messages permission!")
    return allowed


admin_filter = create(admin_check_func)
owner_filter = create(owner_check_func)
restrict_filter = create(restrict_check_func)
promote_filter = create(promote_check_func)
bot_admin_filter = create(bot_admin_check_func)
can_change_filter = create(changeinfo_check_func)
can_pin_filter = create(can_pin_message_func)
