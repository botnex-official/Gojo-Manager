from asyncio import sleep
from traceback import format_exc
import re

from pyrogram import filters
from pyrogram.enums import MessageEntityType as MET
from pyrogram.errors import ChatAdminRequired, ChatNotModified, RPCError
from pyrogram.types import ChatPermissions, Message

from Powers import LOGGER
from Powers.bot_class import Gojo
from Powers.database.approve_db import Approve
from Powers.database.granular_lock_db import GranularLocks
from Powers.database.message_lock_db import FLAG_FIELDS, MessageLocks
from Powers.utils.caching import ADMIN_CACHE, admin_cache_reload
from Powers.utils.custom_filters import command, restrict_filter
from Powers.utils.lock_control import (
    GRANULAR_LOCK_TYPES,
    add_lock,
    is_granular_lock,
    is_locked,
    normalize_lock_type,
    remove_lock,
)
from Powers.vars import Config


class _FlagView:
    """`chat_id in anti_links` reads Mongo. It never inserts a document."""

    def __init__(self, field):
        self.field = field

    def __contains__(self, chat_id):
        return MessageLocks().get_flag(int(chat_id), self.field)


anti_links = _FlagView("links")
anti_forward = _FlagView("forward_all")
anti_forward_u = _FlagView("forward_users")
anti_forward_c = _FlagView("forward_channels")
anti_c_send = _FlagView("anon_channel")

# Message-level locks extend Telegram's broad ChatPermissions with per-media controls.


PLAIN_URL_RE = re.compile(
    r"(?i)(?:https?://|www\.)[^\s<>]+|"
    r"(?<![\w.-])(?:t\.me|telegram\.me|telegram\.dog)/[^\s<>]+"
)


def is_granular_locked(lock_type, locked_types):
    return is_locked(lock_type, locked_types)


def message_contains_link(message):
    """Return True for URL/text-link entities or plain-text web/Telegram URLs."""
    entities = message.entities if message.text else message.caption_entities
    if any(entity.type in (MET.URL, MET.TEXT_LINK) for entity in (entities or [])):
        return True
    content = message.text or message.caption or ""
    return bool(PLAIN_URL_RE.search(content))


@Gojo.on_message(command("locktypes"))
async def lock_types(_, m: Message):
    await m.reply_text(
        (
            "**Lock Types:**\n"
            " - `all` = Everything\n"
            " - `msg` = Messages\n"
            " - `media` = Media, such as Photo and Video.\n"
            " - `polls` = Polls\n"
            " - `invite` = Add users to Group\n"
            " - `pin` = Pin Messages\n"
            " - `info` = Change Group Info\n"
            " - `webprev` = Web Page Previews\n"
            " - `inlinebots`, `inline` = Inline bots\n"
            " - `animations` = Animations\n"
            " - `games` = Game Bots\n"
            " - `stickers` = Stickers\n"
            " - `anonchannel` = Send as chat will be locked\n"
            " - `forwardall` = Forwarding from channel and user\n"
            " - `forwardu` = Forwarding from user\n"
            " - `forwardc` = Forwarding from channel\n"
            " - `links | url` = Block URLs, Telegram/t.me links and text links\n"
            "\n**Granular message locks:**\n"
            " - `photo` = Photos\n"
            " - `video` = Videos\n"
            " - `document` = Documents/files\n"
            " - `audio` = Audio files\n"
            " - `voice` = Voice messages\n"
            " - `video_note` = Video notes\n"
            " - `sticker` = Stickers\n"
            " - `animation | gif` = GIFs/animations\n"
            " - `contact` = Contacts\n"
            " - `location` = Locations"
        ),
    )
    return


@Gojo.on_message(command("lock") & restrict_filter)
async def lock_perm(c: Gojo, m: Message):
    if len(m.text.split()) < 2:
        await m.reply_text("Please enter a permission to lock!")
        return
    lock_type = m.text.split(None, 1)[1].strip().lower()
    chat_id = m.chat.id

    if not lock_type:
        await m.reply_text(text="Specify a permission to lock!")
        return

    # Message-level locks do not require Telegram ChatPermissions.
    # Handle them before reading m.chat.permissions so the PM management
    # bridge can safely execute /lock url and granular locks.
    if lock_type in ("links", "url"):
        db = MessageLocks()
        if db.enabled_links(chat_id):
            await m.reply_text("It is already on")
            return
        db.set_links(chat_id, True)
        await m.reply_text(
            "🔒 Locked links in the chat. URLs, Telegram/t.me links and text links will be deleted."
        )
        return

    get_perm = m.chat.permissions

    msg = get_perm.can_send_messages
    media = get_perm.can_send_media_messages
    webprev = get_perm.can_add_web_page_previews
    polls = get_perm.can_send_polls
    info = get_perm.can_change_info
    invite = get_perm.can_invite_users
    pin = get_perm.can_pin_messages
    stickers = animations = games = inlinebots = None

    if lock_type == "all":
        # "all" also covers message-level locks that Telegram's broad
        # ChatPermissions cannot represent.
        db = MessageLocks()
        for field in FLAG_FIELDS:
            db.set_flag(chat_id, field, True)
        GranularLocks(chat_id).clear()
        try:
            await c.set_chat_permissions(chat_id, ChatPermissions())
            LOGGER.info(f"{m.from_user.id} locked all permissions in {m.chat.id}")
        except ChatNotModified:
            pass
        except ChatAdminRequired:
            await m.reply_text(text="I don't have permission to do that")
        await m.reply_text("🔒 " + "Locked <b>all</b> permission from this Chat!")
        await prevent_approved(m)
        return

    granular_type = normalize_lock_type(lock_type)
    if is_granular_lock(granular_type):
        granular_db = GranularLocks(chat_id)
        if granular_db.is_locked(granular_type):
            await m.reply_text(f"🔒 <b>{lock_type}</b> is already locked.")
            return
        granular_db.add(granular_type)
        LOGGER.info(f"{m.from_user.id} locked {granular_type} messages in {chat_id}")
        await m.reply_text(f"🔒 Locked <b>{granular_type}</b> messages in this Chat.")
        return

    if lock_type == "msg":
        msg = False
        perm = "messages"

    elif lock_type == "media":
        media = False
        perm = "audios, documents, photos, videos, video notes, voice notes"

    elif lock_type == "stickers":
        stickers = False
        perm = "stickers"

    elif lock_type == "animations":
        animations = False
        perm = "animations"

    elif lock_type == "games":
        games = False
        perm = "games"

    elif lock_type in ("inlinebots", "inline"):
        inlinebots = False
        perm = "inline bots"

    elif lock_type == "webprev":
        webprev = False
        perm = "web page previews"

    elif lock_type == "polls":
        polls = False
        perm = "polls"

    elif lock_type == "info":
        info = False
        perm = "info"

    elif lock_type == "invite":
        invite = False
        perm = "invite"

    elif lock_type == "pin":
        pin = False
        perm = "pin"
    elif lock_type == "anonchannel":
        db = MessageLocks()
        if db.get_flag(chat_id, "anon_channel"):
            await m.reply_text("It is already on")
            return
        db.set_flag(chat_id, "anon_channel", True)
        await m.reply_text("Locked Send As Chat")
        return
    elif lock_type == "forwardall":
        db = MessageLocks()
        if db.get_flag(chat_id, "forward_all"):
            await m.reply_text("It is already on")
            return
        db.set_flag(chat_id, "forward_all", True)
        await m.reply_text("Locked Forward from user as well as channel")
        return
    elif lock_type == "forwardu":
        db = MessageLocks()
        if db.get_flag(chat_id, "forward_users"):
            await m.reply_text("It is already on")
            return
        db.set_flag(chat_id, "forward_users", True)
        await m.reply_text("Locked Forward message from user")
        return
    elif lock_type == "forwardc":
        db = MessageLocks()
        if db.get_flag(chat_id, "forward_channels"):
            await m.reply_text("It is already on")
            return
        db.set_flag(chat_id, "forward_channels", True)
        await m.reply_text("Locked Forward message from channel")
        return
    else:
        await m.reply_text(
            text=""" Invalid Lock Type!

Use /locktypes to get the lock types"""
        )
        return

    try:
        await c.set_chat_permissions(
            chat_id,
            ChatPermissions(
                can_send_messages=msg,
                can_send_media_messages=media,
                can_send_other_messages=any([stickers, animations, games, inlinebots]),
                can_add_web_page_previews=webprev,
                can_send_polls=polls,
                can_change_info=info,
                can_invite_users=invite,
                can_pin_messages=pin,
            ),
        )
        LOGGER.info(f"{m.from_user.id} locked selected permissions in {m.chat.id}")
    except ChatNotModified:
        pass
    except ChatAdminRequired:
        await m.reply_text(text="I don't have permission to do that")
    await m.reply_text(
        "🔒 " + f"Locked <b>{perm}</b> for this Chat.",
    )
    await prevent_approved(m)
    return


@Gojo.on_message(command("locks") & restrict_filter)
async def view_locks(c: Gojo, m: Message):
    chkmsg = await m.reply_text(text="Checking Chat permissions...")
    # The chat object carried by a message can hold stale or default
    # permissions — through the PM bridge it described the wrong chat
    # entirely (an all-allowed default set instead of the connected
    # group's real permissions). Always fetch the target chat fresh at
    # answer time and report its actual permissions.
    chat = m.chat
    v_perm = m.chat.permissions
    try:
        fresh_chat = await c.get_chat(m.chat.id)
    except RPCError:
        fresh_chat = None
    if fresh_chat is not None:
        chat = fresh_chat
        if fresh_chat.permissions is not None:
            v_perm = fresh_chat.permissions
    if v_perm is None:
        await chkmsg.edit_text("I could not fetch this chat's permissions.")
        return

    async def convert_to_emoji(val: bool):
        if val:
            return "✅"
        return "❌"
    anon = False
    message_locks = MessageLocks()
    if message_locks.get_flag(m.chat.id, "anon_channel"):
        anon = True
    anti_f, anti_f_u, anti_f_c = message_locks.forward_mode_flags(m.chat.id)
    antil = message_locks.enabled_links(m.chat.id)
    vmsg = await convert_to_emoji(v_perm.can_send_messages)
    vmedia = await convert_to_emoji(v_perm.can_send_media_messages)
    vother = await convert_to_emoji(v_perm.can_send_other_messages)
    vwebprev = await convert_to_emoji(v_perm.can_add_web_page_previews)
    vpolls = await convert_to_emoji(v_perm.can_send_polls)
    vinfo = await convert_to_emoji(v_perm.can_change_info)
    vinvite = await convert_to_emoji(v_perm.can_invite_users)
    vpin = await convert_to_emoji(v_perm.can_pin_messages)
    vanon = await convert_to_emoji(anon)
    vanti = await convert_to_emoji(anti_f)
    vantiu = await convert_to_emoji(anti_f_u)
    vantic = await convert_to_emoji(anti_f_c)
    vantil = await convert_to_emoji(antil)

    if v_perm is not None:
        try:
            permission_view_str = f"""<b>Chat Permissions:</b> <b>{chat.title}</b>

      <b>Send Messages:</b> {vmsg}
      <b>Send Media:</b> {vmedia}
      <b>Send Stickers:</b> {vother}
      <b>Send Animations:</b> {vother}
      <b>Can Play Games:</b> {vother}
      <b>Can Use Inline Bots:</b> {vother}
      <b>Webpage Preview:</b> {vwebprev}
      <b>Send Polls:</b> {vpolls}
      <b>Change Info:</b> {vinfo}
      <b>Invite Users:</b> {vinvite}
      <b>Pin Messages:</b> {vpin}
      <b>Send as chat:</b> {vanon}
      <b>Can forward:</b> {vanti}
      <b>Can forward from user:</b> {vantiu}
      <b>Can forward from channel and chats:</b> {vantic}
      <b>Can send links:</b> {antil}
      <b>Granular message locks:</b> {", ".join(sorted(GranularLocks(m.chat.id).get_locked())) or "None"}
      """
            LOGGER.info(f"{m.from_user.id} used locks cmd in {m.chat.id}")
            await chkmsg.edit_text(permission_view_str)

        except RPCError as e_f:
            await chkmsg.edit_text(text="Something went wrong!")
            await m.reply_text(e_f)
    return


@Gojo.on_message(command("unlock") & restrict_filter)
async def unlock_perm(c: Gojo, m: Message):
    if len(m.text.split()) < 2:
        await m.reply_text("Please enter a permission to unlock!")
        return
    unlock_type = m.text.split(None, 1)[1].strip().lower()
    chat_id = m.chat.id

    if not unlock_type:
        await m.reply_text(text="Specify a permission to unlock!")
        return

    if unlock_type == "all":
        try:
            await c.set_chat_permissions(
                chat_id,
                ChatPermissions(
                    can_send_messages=True,
                    can_send_media_messages=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True,
                    can_send_polls=True,
                    can_change_info=True,
                    can_invite_users=True,
                    can_pin_messages=True,
                ),
            )
            LOGGER.info(f"{m.from_user.id} unlocked all permissions in {m.chat.id}")
        except ChatNotModified:
            pass
        except ChatAdminRequired:
            await m.reply_text(text="I don't have permission to do that")
        GranularLocks(chat_id).clear()
        db = MessageLocks()
        for field in FLAG_FIELDS:
            db.set_flag(chat_id, field, False)
        await m.reply_text("🔓 " + "Unlocked <b>all</b> permission from this Chat!")
        await prevent_approved(m)
        return

    granular_type = normalize_lock_type(unlock_type)
    if is_granular_lock(granular_type):
        granular_db = GranularLocks(chat_id)
        if not granular_db.is_locked(granular_type):
            await m.reply_text(f"🔓 <b>{unlock_type}</b> is already unlocked.")
            return
        granular_db.remove(granular_type)
        LOGGER.info(f"{m.from_user.id} unlocked {granular_type} messages in {chat_id}")
        await m.reply_text(f"🔓 Unlocked <b>{granular_type}</b> messages in this Chat.")
        return

    get_uperm = m.chat.permissions

    umsg = get_uperm.can_send_messages
    umedia = get_uperm.can_send_media_messages
    uwebprev = get_uperm.can_add_web_page_previews
    upolls = get_uperm.can_send_polls
    uinfo = get_uperm.can_change_info
    uinvite = get_uperm.can_invite_users
    upin = get_uperm.can_pin_messages
    ustickers = uanimations = ugames = uinlinebots = None

    if unlock_type == "msg":
        umsg = True
        uperm = "messages"

    elif unlock_type == "media":
        umedia = True
        uperm = "audios, documents, photos, videos, video notes, voice notes"

    elif unlock_type == "stickers":
        ustickers = True
        uperm = "stickers"

    elif unlock_type == "animations":
        uanimations = True
        uperm = "animations"

    elif unlock_type == "games":
        ugames = True
        uperm = "games"

    elif unlock_type in ("inlinebots", "inline"):
        uinlinebots = True
        uperm = "inline bots"

    elif unlock_type == "webprev":
        uwebprev = True
        uperm = "web page previews"

    elif unlock_type == "polls":
        upolls = True
        uperm = "polls"

    elif unlock_type == "info":
        uinfo = True
        uperm = "info"

    elif unlock_type == "invite":
        uinvite = True
        uperm = "invite"

    elif unlock_type == "pin":
        upin = True
        uperm = "pin"
    elif unlock_type == "anonchannel":
        db = MessageLocks()
        if not db.get_flag(chat_id, "anon_channel"):
            await m.reply_text("Already off")
            return
        db.set_flag(chat_id, "anon_channel", False)
        await m.reply_text("Send as chat is now enabled for this chat")
        return
    elif unlock_type in ["links", "url"]:
        db = MessageLocks()
        if not db.enabled_links(chat_id):
            await m.reply_text("Already allowed")
            return
        db.set_links(chat_id, False)
        await m.reply_text("Sending link is now allowed")
        return
    elif unlock_type == "forwardall":
        db = MessageLocks()
        if not db.get_flag(chat_id, "forward_all"):
            await m.reply_text("Already off")
            return
        db.set_flag(chat_id, "forward_all", False)
        await m.reply_text("Forwarding content is now enabled for this chat")
        return
    elif unlock_type == "forwardu":
        db = MessageLocks()
        if not db.get_flag(chat_id, "forward_users"):
            await m.reply_text("Already off")
            return
        db.set_flag(chat_id, "forward_users", False)
        await m.reply_text("Forwarding content is now enabled for this chat")
        return
    elif unlock_type == "forwardc":
        db = MessageLocks()
        if not db.get_flag(chat_id, "forward_channels"):
            await m.reply_text("Already off")
            return
        db.set_flag(chat_id, "forward_channels", False)
        await m.reply_text("Forwarding content is now enabled for this chat")
        return
    else:
        await m.reply_text(
            text="""Invalid Lock Type!

      Use /locktypes to get the lock types"""
        )
        return

    try:
        LOGGER.info(f"{m.from_user.id} unlocked selected permissions in {m.chat.id}")
        await c.set_chat_permissions(
            chat_id,
            ChatPermissions(
                can_send_messages=umsg,
                can_send_media_messages=umedia,
                can_send_other_messages=any(
                    [ustickers, uanimations, ugames, uinlinebots],
                ),
                can_add_web_page_previews=uwebprev,
                can_send_polls=upolls,
                can_change_info=uinfo,
                can_invite_users=uinvite,
                can_pin_messages=upin,
            ),
        )
    except ChatNotModified:
        pass
    except ChatAdminRequired:
        await m.reply_text(text="I don't have permission to do that")
    await m.reply_text(
        "🔓 " + f"Unlocked <b>{uperm}</b> for this Chat.",
    )
    await prevent_approved(m)
    return

async def delete_messages(c:Gojo, m: Message):
    try:
        await m.delete()
        return
    except RPCError as rp:
        LOGGER.error(rp)
        LOGGER.error(format_exc())
        return

async def is_approved_user(c:Gojo, m: Message):
    from Powers import DEV_USERS, OWNER_ID, SUDO_USERS

    sudo_level = {int(x) for x in list(SUDO_USERS) + list(DEV_USERS) + [int(OWNER_ID)]}
    approved_users = Approve(m.chat.id).list_approved()
    ul = [user[0] for user in approved_users]
    try:
        admins_group = {i[0] for i in ADMIN_CACHE[m.chat.id]}
    except KeyError:
        admins_group = await admin_cache_reload(m, "lock")
    
    if m.forward_from:
        if m.from_user.id in ul or m.from_user.id in sudo_level or m.from_user.id in admins_group or m.from_user.id == Config.BOT_ID:
            return True
        return False
    elif m.forward_from_chat:
        x_chat = (await c.get_chat(m.forward_from_chat.id)).linked_chat
        if not x_chat:
            return False
        elif x_chat and x_chat.id == m.chat.id:
            return True
        return False
    elif m.from_user:
        if m.from_user.id in ul or m.from_user.id in sudo_level or m.from_user.id in admins_group or m.from_user.id == Config.BOT_ID:
            return True
        return False

@Gojo.on_message(filters.all & ~filters.me,18)
async def lock_del_mess(c:Gojo, m: Message):
    message_locks = MessageLocks().get(m.chat.id)
    granular_db = GranularLocks(m.chat.id)
    locked_types = set(granular_db.get_locked())
    has_granular = bool(locked_types)
    has_message_lock = any(message_locks.get(field) for field in FLAG_FIELDS)
    if not has_message_lock and not has_granular:
        return
    if m.sender_chat and not (m.forward_from_chat or m.forward_from):
        # Messages sent as a chat (anonymous admins posting as the group
        # itself, linked-channel posts, other channels) are only removed
        # when the anon_channel lock ("send as chat") is enabled for this
        # chat. Any other lock (photo, links, ...) must not delete them.
        if m.sender_chat.id == m.chat.id:
            return
        if message_locks["anon_channel"]:
            await delete_messages(c,m)
        return
    is_approved = await is_approved_user(c,m)
    if not is_approved:
        for message_type in GRANULAR_LOCK_TYPES:
            if is_granular_locked(message_type, locked_types) and getattr(m, message_type, None):
                await delete_messages(c, m)
                return

    if not is_approved and message_locks["links"] and message_contains_link(m):
        await delete_messages(c, m)
        return

    if m.forward_from or m.forward_from_chat:
        if not is_approved:
            if message_locks["forward_all"]:
                await delete_messages(c,m)
                return
            elif message_locks["forward_users"] and not m.forward_from_chat:
                await delete_messages(c,m)
                return
            elif message_locks["forward_channels"] and m.forward_from_chat:
                await delete_messages(c,m)
                return

async def prevent_approved(m: Message):
    approved_users = Approve(m.chat.id).list_approved()
    ul = [user[0] for user in approved_users]
    for i in ul:
        try:
            await m.chat.unban_member(user_id=i)
        except (ChatAdminRequired, ChatNotModified, RPCError):
            continue
        LOGGER.info(f"Approved {i} in {m.chat.id}")
        await sleep(0.1)
    return


__PLUGIN__ = "locks"

__alt_name__ = ["grouplock", "lock", "grouplocks"]

__HELP__ = """
**Locks**

Use this to lock group permissions.
Allows you to lock and unlock permission types in the chat.

**Usage:**
• /lock `<type>`: Lock Chat permission.
• /unlock `<type>`: Unlock Chat permission.
• /locks: View Chat permission.
• /locktypes: Check available lock types!

**Examples:**
`/lock media` — locks media messages.
`/lock url` — deletes URLs, Telegram/t.me links and text links.
`/unlock url` — allows links again."""
