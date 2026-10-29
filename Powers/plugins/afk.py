from html import escape
from traceback import format_exc

from pyrogram import filters
from pyrogram.enums import MessageEntityType as MET
from pyrogram.errors import RPCError
from pyrogram.types import Message

from Powers import LOGGER
from Powers.bot_class import Gojo
from Powers.database.afk_db import AFK
from Powers.utils.custom_filters import command


def _message_text(message: Message) -> str:
    return message.text or message.caption or ""


async def _mentioned_users(c: Gojo, m: Message):
    text = _message_text(m)
    entities = m.entities if m.text else m.caption_entities
    if not text or not entities:
        return []

    users = []
    seen = set()
    for entity in entities:
        if entity.type == MET.TEXT_MENTION and entity.user:
            user = entity.user
        elif entity.type == MET.MENTION:
            username = text[entity.offset : entity.offset + entity.length]
            try:
                user = await c.get_users(username)
            except RPCError:
                continue
        else:
            continue
        if user and user.id not in seen:
            seen.add(user.id)
            users.append(user)
    return users


def _is_afk_command(message: Message) -> bool:
    text = _message_text(message).lstrip()
    if not text or text[0] not in "/!$":
        return False
    head = text[1:].split(None, 1)[0].split("@")[0].lower()
    return head in ("afk", "brb")


@Gojo.on_message(command(["afk", "brb"]))
async def set_afk(_, m: Message):
    if not m.from_user:
        return
    parts = m.text.split(None, 1) if m.text else []
    reason = parts[1].strip() if len(parts) == 2 else ""
    AFK().set(m.from_user.id, reason)
    suffix = f"\n<b>Reason:</b> {escape(reason)}" if reason else ""
    await m.reply_text(
        f"<b>{escape(m.from_user.first_name)}</b> is now AFK.{suffix}",
        quote=True,
    )


@Gojo.on_message(filters.group, group=1)
async def clear_afk(c: Gojo, m: Message):
    if not m.from_user or m.from_user.is_bot:
        return
    # Never treat the /afk (/brb) command message itself as "user is back":
    # Pyrogram dispatches group 1 for the same update right after group 0
    # (set_afk) stored the status, so without this guard the status just
    # set is removed again instantly and AFK can never persist.
    if _is_afk_command(m):
        return
    db = AFK()
    if not db.is_afk(m.from_user.id):
        return
    db.remove(m.from_user.id)
    try:
        await m.reply_text(
            f"Welcome back, <b>{escape(m.from_user.first_name)}</b>! Your AFK status has been removed.",
            quote=True,
        )
    except RPCError:
        LOGGER.warning("Could not send AFK return message in %s", m.chat.id)


@Gojo.on_message(filters.group & (filters.text | filters.caption), group=2)
async def reply_to_afk(c: Gojo, m: Message):
    if not m.from_user or m.from_user.is_bot:
        return
    if _is_afk_command(m):
        return
    try:
        for user in await _mentioned_users(c, m):
            data = AFK().get(user.id)
            # AFK.get() -> MongoDB.find_one() returns the sentinel False
            # (not None) when the user has no AFK row.
            if not data:
                continue
            reason = data.get("reason") or ""
            text = (
                f"<b>{escape(user.first_name)}</b> is currently AFK."
                f"\n<b>Reason:</b> {escape(reason)}" if reason
                else f"<b>{escape(user.first_name)}</b> is currently AFK."
            )
            await m.reply_text(text, quote=True)
    except Exception as exc:
        LOGGER.warning("AFK mention lookup failed: %s", exc)
        LOGGER.debug(format_exc())


__PLUGIN__ = "afk"
__alt_name__ = ["afk", "brb"]
__HELP__ = """
**AFK**

• /afk <reason>: mark yourself as AFK.
• Mention an AFK user to see their AFK status and reason.
• Sending a group message removes your own AFK status.

AFK state is persistent across bot restarts.
"""
