from pyrogram import enums
from pyrogram.errors import ChatAdminRequired, RPCError, UserAdminInvalid
from pyrogram.types import ChatPermissions, Message

from Powers import DEV_LEVEL, LOGGER
from Powers.bot_class import Gojo
from Powers.utils.custom_filters import command


def _remote_target(m: Message):
    parts = m.text.split()
    if len(parts) < 3:
        return None, None
    return parts[1], parts[2]


async def _authorized(m: Message):
    if not m.from_user or m.from_user.id not in DEV_LEVEL:
        await m.reply_text("You don't have permission to use remote moderation.")
        return False
    return True


async def _resolve(c: Gojo, user_ref, chat_ref):
    user = await c.get_users(user_ref)
    chat = await c.get_chat(chat_ref)
    return user, chat


@Gojo.on_message(command("rban"))
async def remote_ban(c: Gojo, m: Message):
    if not await _authorized(m):
        return
    user_ref, chat_ref = _remote_target(m)
    if not user_ref or not chat_ref:
        return await m.reply_text("Usage: /rban <user_id|username> <chat_id|username>")
    try:
        user, chat = await _resolve(c, user_ref, chat_ref)
        member = await c.get_chat_member(chat.id, user.id)
        if member.status in {enums.ChatMemberStatus.OWNER, enums.ChatMemberStatus.ADMINISTRATOR}:
            return await m.reply_text("I can't ban an administrator or owner.")
        await c.ban_chat_member(chat.id, user.id)
        await m.reply_text(f"Banned {user.id} from {chat.id}.")
    except UserAdminInvalid:
        await m.reply_text("I can't act on that user.")
    except (ChatAdminRequired, RPCError) as e:
        LOGGER.error(e)
        await m.reply_text(f"Remote ban failed: {e}")


@Gojo.on_message(command("runban"))
async def remote_unban(c: Gojo, m: Message):
    if not await _authorized(m):
        return
    user_ref, chat_ref = _remote_target(m)
    if not user_ref or not chat_ref:
        return await m.reply_text("Usage: /runban <user_id|username> <chat_id|username>")
    try:
        user, chat = await _resolve(c, user_ref, chat_ref)
        await c.unban_chat_member(chat.id, user.id)
        await m.reply_text(f"Unbanned {user.id} from {chat.id}.")
    except (ChatAdminRequired, RPCError) as e:
        LOGGER.error(e)
        await m.reply_text(f"Remote unban failed: {e}")


@Gojo.on_message(command("rkick"))
async def remote_kick(c: Gojo, m: Message):
    if not await _authorized(m):
        return
    user_ref, chat_ref = _remote_target(m)
    if not user_ref or not chat_ref:
        return await m.reply_text("Usage: /rkick <user_id|username> <chat_id|username>")
    try:
        user, chat = await _resolve(c, user_ref, chat_ref)
        member = await c.get_chat_member(chat.id, user.id)
        if member.status in {enums.ChatMemberStatus.OWNER, enums.ChatMemberStatus.ADMINISTRATOR}:
            return await m.reply_text("I can't kick an administrator or owner.")
        await c.ban_chat_member(chat.id, user.id)
        await c.unban_chat_member(chat.id, user.id)
        await m.reply_text(f"Kicked {user.id} from {chat.id}.")
    except UserAdminInvalid:
        await m.reply_text("I can't act on that user.")
    except (ChatAdminRequired, RPCError) as e:
        LOGGER.error(e)
        await m.reply_text(f"Remote kick failed: {e}")


@Gojo.on_message(command("rmute"))
async def remote_mute(c: Gojo, m: Message):
    if not await _authorized(m):
        return
    user_ref, chat_ref = _remote_target(m)
    if not user_ref or not chat_ref:
        return await m.reply_text("Usage: /rmute <user_id|username> <chat_id|username>")
    try:
        user, chat = await _resolve(c, user_ref, chat_ref)
        member = await c.get_chat_member(chat.id, user.id)
        if member.status in {enums.ChatMemberStatus.OWNER, enums.ChatMemberStatus.ADMINISTRATOR}:
            return await m.reply_text("I can't mute an administrator or owner.")
        await c.restrict_chat_member(
            chat.id,
            user.id,
            permissions=ChatPermissions(can_send_messages=False),
        )
        await m.reply_text(f"Muted {user.id} in {chat.id}.")
    except UserAdminInvalid:
        await m.reply_text("I can't act on that user.")
    except (ChatAdminRequired, RPCError) as e:
        LOGGER.error(e)
        await m.reply_text(f"Remote mute failed: {e}")


@Gojo.on_message(command("runmute"))
async def remote_unmute(c: Gojo, m: Message):
    if not await _authorized(m):
        return
    user_ref, chat_ref = _remote_target(m)
    if not user_ref or not chat_ref:
        return await m.reply_text("Usage: /runmute <user_id|username> <chat_id|username>")
    try:
        user, chat = await _resolve(c, user_ref, chat_ref)
        await c.restrict_chat_member(
            chat.id,
            user.id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_audios=True,
                can_send_documents=True,
                can_send_photos=True,
                can_send_videos=True,
                can_send_video_notes=True,
                can_send_voice_notes=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
            ),
        )
        await m.reply_text(f"Unmuted {user.id} in {chat.id}.")
    except (ChatAdminRequired, RPCError) as e:
        LOGGER.error(e)
        await m.reply_text(f"Remote unmute failed: {e}")


__PLUGIN__ = "remote"

__HELP__ = """
**Remote Moderation**

• /rban <user_id|username> <chat_id|username>
• /runban <user_id|username> <chat_id|username>
• /rkick <user_id|username> <chat_id|username>
• /rmute <user_id|username> <chat_id|username>
• /runmute <user_id|username> <chat_id|username>
"""
