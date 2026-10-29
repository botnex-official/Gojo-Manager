from pyrogram import filters
from pyrogram.types import Message

from Powers import LOGGER
from Powers.bot_class import Gojo
from Powers.database.audit_db import AuditLogs
from Powers.utils.audit_logging import format_audit_event, normalize_log_chat
from Powers.utils.caching import ADMIN_CACHE, admin_cache_reload
from Powers.utils.custom_filters import admin_filter, command


async def write_audit(c, chat_id, user, action, details=""):
    settings = AuditLogs(chat_id).get_settings()
    if not settings.get("enabled") or not settings.get("log_chat_id"):
        return False
    event = {
        "action": action,
        "user_id": user.id if user else 0,
        "user_name": user.first_name if user else "Unknown",
        "details": details,
    }
    AuditLogs(chat_id).add_event(event)
    try:
        chat = await c.get_chat(chat_id)
        text = format_audit_event(action, event["user_id"], event["user_name"], chat_id, chat.title, details)
        await c.send_message(settings["log_chat_id"], text)
    except Exception as exc:
        LOGGER.warning(f"Audit log delivery failed for {chat_id}: {exc}")
    return True


@Gojo.on_message(command("setlog") & admin_filter)
async def set_log(c, m: Message):
    if len(m.command) < 2:
        await m.reply_text("Usage: /setlog <channel_or_chat_id>\nExample: /setlog -1001234567890")
        return
    log_chat_id = normalize_log_chat(m.command[1])
    if log_chat_id is None:
        try:
            log_chat = await c.get_chat(m.command[1])
            log_chat_id = log_chat.id
        except Exception:
            await m.reply_text("❌ Invalid log chat. Use a channel/group ID or @username.")
            return
    try:
        await c.get_chat(log_chat_id)
    except Exception as exc:
        await m.reply_text(f"❌ I cannot access that log chat. Add me there first.\n<code>{exc}</code>")
        return
    AuditLogs(m.chat.id).set_log_chat(log_chat_id)
    await m.reply_text(f"✅ Detailed logging enabled.\nLog chat: <code>{log_chat_id}</code>")


@Gojo.on_message(command("unsetlog") & admin_filter)
async def unset_log(_, m: Message):
    AuditLogs(m.chat.id).disable()
    await m.reply_text("✅ Detailed logging disabled for this group.")


@Gojo.on_message(command("logstatus") & admin_filter)
async def log_status(_, m: Message):
    settings = AuditLogs(m.chat.id).get_settings()
    status = "ON" if settings.get("enabled") else "OFF"
    await m.reply_text(f"<b>Audit Logging:</b> <code>{status}</code>\n<b>Log Chat:</b> <code>{settings.get('log_chat_id')}</code>")


@Gojo.on_message(
    filters.group
    & filters.command(
        ["warn", "swarn", "dwarn", "ban", "unban", "mute", "unmute", "kick", "lock", "unlock", "antiraid", "raidmode", "autoantiraid", "captcha", "antispam", "spamaction", "newfed", "joinfed", "leavefed", "fedban", "unfedban", "warnmode", "warnlimit", "resetwarns", "rmwarn"],
        prefixes=["/"],
    ),
    group=1,
)
async def audit_admin_command(c, m: Message):
    if not m.from_user:
        return
    try:
        admins = ADMIN_CACHE.get(m.chat.id)
        if admins is None:
            admins = await admin_cache_reload(m, "audit_logging")
        admin_ids = {item[0] for item in admins}
        if m.from_user.id not in admin_ids:
            return
        command_name = m.command[0] if m.command else "unknown"
        details = " ".join(m.command[1:])[:200] if len(m.command) > 1 else ""
        await write_audit(c, m.chat.id, m.from_user, command_name, details)
    except Exception as exc:
        LOGGER.warning(f"Audit command capture failed: {exc}")


__PLUGIN__ = "audit_logging"
__alt_name__ = ["setlog", "unsetlog", "logstatus"]

__HELP__ = """
**Detailed Logging**

**Admin commands:**
• /setlog <channel_or_chat_id> — Enable audit logging.
• /unsetlog — Disable audit logging.
• /logstatus — Show logging status.

The bot records configured admin actions per group and sends audit entries to the configured log chat.
"""
