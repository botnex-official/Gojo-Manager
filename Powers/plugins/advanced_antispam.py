import asyncio
import time
from collections import defaultdict, deque
from hashlib import sha256

from pyrogram import filters
from pyrogram.enums import ChatMemberStatus as CMS
from pyrogram.errors import RPCError
from pyrogram.types import ChatPermissions, Message

from Powers import DEV_USERS, SUPPORT_STAFF
from Powers.bot_class import Gojo
from Powers.database.advanced_antispam_db import AdvancedAntiSpam
from Powers.database.approve_db import Approve
from Powers.utils.antispam import is_duplicate, is_flood
from Powers.utils.custom_filters import admin_filter, bot_admin_filter, command

WINDOWS = defaultdict(lambda: defaultdict(lambda: deque(maxlen=50)))
CONTENT = defaultdict(lambda: defaultdict(lambda: deque(maxlen=10)))
MUTE_TASKS = {}
MUTE_PERMISSIONS = {}


def _fingerprint(message):
    text = (message.text or message.caption or "").strip().lower()
    return sha256(text.encode("utf-8")).hexdigest() if text else ""


async def _mute_for(c, chat_id, user_id, seconds):
    key = (chat_id, user_id)
    try:
        await c.restrict_chat_member(chat_id, user_id, ChatPermissions(can_send_messages=False))
        await asyncio.sleep(seconds)
        original = MUTE_PERMISSIONS.pop(key, None)
        if original is not None:
            await c.restrict_chat_member(chat_id, user_id, original)
    except (RPCError, asyncio.CancelledError):
        MUTE_PERMISSIONS.pop(key, None)


async def _take_action(c, m, settings, reason, member=None):
    action = settings["action"]
    if settings["delete"]:
        try:
            await m.delete()
        except RPCError:
            pass
    if action == "delete":
        return
    if action == "mute":
        key = (m.chat.id, m.from_user.id)
        old = MUTE_TASKS.pop(key, None)
        if old:
            old.cancel()
        # Preserve the member's existing permissions so an anti-spam mute does
        # not accidentally remove unrelated group restrictions when it expires.
        MUTE_PERMISSIONS[key] = getattr(member, "permissions", None) or m.chat.permissions
        MUTE_TASKS[key] = asyncio.create_task(
            _mute_for(c, m.chat.id, m.from_user.id, settings["action_time"])
        )
    elif action == "kick":
        try:
            await c.ban_chat_member(m.chat.id, m.from_user.id)
            await c.unban_chat_member(m.chat.id, m.from_user.id)
        except RPCError:
            pass
    elif action == "ban":
        try:
            await c.ban_chat_member(m.chat.id, m.from_user.id)
        except RPCError:
            pass
    try:
        await c.send_message(
            m.chat.id,
            f"🛡️ {m.from_user.mention} anti-spam action: {action} ({reason}).",
        )
    except RPCError:
        pass


@Gojo.on_message(command("antispam") & admin_filter & bot_admin_filter)
async def antispam_settings(_, m: Message):
    db = AdvancedAntiSpam(m.chat.id)
    args = m.command[1:]
    if not args:
        s = db.get_settings()
        await m.reply_text(
            f"Advanced Anti-Spam:\n• Enabled: {s['enabled']}\n"
            f"• Flood: {s['threshold']} msgs/{s['window']}s\n"
            f"• Duplicates: {s['duplicates']}\n• Action: {s['action']}\n"
            f"• Action time: {s['action_time']}s\n• Delete: {s['delete']}"
        )
        return
    value = args[0].lower()
    if value in {"on", "off"}:
        db.set("enabled", value == "on")
        await m.reply_text(f"Advanced Anti-Spam {'enabled' if value == 'on' else 'disabled'}.")
    elif value == "status":
        s = db.get_settings()
        await m.reply_text(
            f"Anti-Spam: {'ON' if s['enabled'] else 'OFF'} | flood={s['threshold']}/{s['window']}s | "
            f"duplicates={s['duplicates']} | action={s['action']} | mute={s['action_time']}s | delete={s['delete']}"
        )
    else:
        await m.reply_text("Usage: /antispam on|off|status")


@Gojo.on_message(command("spamlimit") & admin_filter & bot_admin_filter)
async def spam_limit(_, m: Message):
    db = AdvancedAntiSpam(m.chat.id)
    if len(m.command) < 2:
        s = db.get_settings()
        await m.reply_text(f"Current flood limit: {s['threshold']} messages in {s['window']}s")
        return
    try:
        threshold = int(m.command[1])
        window = int(m.command[2]) if len(m.command) > 2 else db.get_settings()["window"]
    except ValueError:
        await m.reply_text("Usage: /spamlimit <messages> [seconds]")
        return
    if not 3 <= threshold <= 50 or not 2 <= window <= 120:
        await m.reply_text("Messages: 3-50 | Window: 2-120 seconds.")
        return
    db.set("threshold", threshold)
    db.set("window", window)
    await m.reply_text(f"Flood limit set to {threshold} messages/{window}s.")


@Gojo.on_message(command("spamduplicates") & admin_filter & bot_admin_filter)
async def spam_duplicates(_, m: Message):
    db = AdvancedAntiSpam(m.chat.id)
    if len(m.command) < 2:
        await m.reply_text(f"Current duplicate limit: {db.get_settings()['duplicates']}")
        return
    try:
        value = int(m.command[1])
    except ValueError:
        await m.reply_text("Usage: /spamduplicates <number>")
        return
    if not 2 <= value <= 10:
        await m.reply_text("Duplicate limit must be between 2 and 10.")
        return
    db.set("duplicates", value)
    await m.reply_text(f"Duplicate-message limit set to {value}.")


@Gojo.on_message(command("spamaction") & admin_filter & bot_admin_filter)
async def spam_action(_, m: Message):
    db = AdvancedAntiSpam(m.chat.id)
    if len(m.command) < 2:
        await m.reply_text(f"Current action: {db.get_settings()['action']} (delete|mute|kick|ban)")
        return
    action = m.command[1].lower()
    if action not in {"delete", "mute", "kick", "ban"}:
        await m.reply_text("Action must be delete, mute, kick or ban.")
        return
    db.set("action", action)
    await m.reply_text(f"Anti-spam action set to {action}.")


@Gojo.on_message(command("spammactiontime") & admin_filter & bot_admin_filter)
async def spam_action_time(_, m: Message):
    db = AdvancedAntiSpam(m.chat.id)
    if len(m.command) < 2:
        await m.reply_text(f"Current action time: {db.get_settings()['action_time']}s")
        return
    try:
        value = int(m.command[1])
    except ValueError:
        await m.reply_text("Usage: /spammactiontime <seconds>")
        return
    if not 10 <= value <= 3600:
        await m.reply_text("Action time must be between 10 and 3600 seconds.")
        return
    db.set("action_time", value)
    await m.reply_text(f"Anti-spam action time set to {value}s.")


@Gojo.on_message(command("spamdelete") & admin_filter & bot_admin_filter)
async def spam_delete(_, m: Message):
    db = AdvancedAntiSpam(m.chat.id)
    if len(m.command) < 2:
        await m.reply_text(f"Delete detected messages: {db.get_settings()['delete']}")
        return
    value = m.command[1].lower()
    if value not in {"on", "off"}:
        await m.reply_text("Usage: /spamdelete on|off")
        return
    db.set("delete", value == "on")
    await m.reply_text(f"Anti-spam deletion {'enabled' if value == 'on' else 'disabled'}.")


@Gojo.on_message(filters.all & ~filters.bot, group=11)
async def antispam_watcher(c: Gojo, m: Message):
    if not m.chat or not m.from_user or m.from_user.is_bot:
        return
    if m.chat.type.value not in {"group", "supergroup"}:
        return
    settings = AdvancedAntiSpam(m.chat.id).get_settings()
    if not settings["enabled"] or m.from_user.id in DEV_USERS or m.from_user.id in SUPPORT_STAFF:
        return
    try:
        member = await m.chat.get_member(m.from_user.id)
        if member.status in {CMS.OWNER, CMS.ADMINISTRATOR}:
            return
        if m.from_user.id in {x[0] for x in Approve(m.chat.id).list_approved()}:
            return
    except RPCError:
        return

    now = time.time()
    times = WINDOWS[m.chat.id][m.from_user.id]
    while times and now - times[0] > settings["window"]:
        times.popleft()
    times.append(now)

    fp = _fingerprint(m)
    contents = CONTENT[m.chat.id][m.from_user.id]
    if fp:
        contents.append(fp)

    reason = None
    if is_flood(list(times), settings["threshold"], settings["window"], now):
        reason = "message flood"
    elif fp and is_duplicate(list(contents), settings["duplicates"]):
        reason = "repeated messages"

    if reason:
        await _take_action(c, m, settings, reason, member=member)
        times.clear()
        contents.clear()


__PLUGIN__ = "advanced_antispam"
__alt_name__ = [
    "antispam", "spamlimit", "spamduplicates", "spamaction",
    "spammactiontime", "spamdelete",
]
__HELP__ = """
**Advanced Anti-Spam**

Detects rapid message bursts and repeated messages per user.

**Admin Commands:**
• /antispam on|off|status
• /spamlimit <messages> [seconds]
• /spamduplicates <number>
• /spamaction delete|mute|kick|ban
• /spammactiontime <seconds>
• /spamdelete on|off

**Default:** disabled, 6 messages/8 seconds, 3 duplicates, mute for 60 seconds.
"""
