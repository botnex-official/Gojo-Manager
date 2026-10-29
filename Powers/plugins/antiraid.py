
from asyncio import create_task, sleep
from collections import defaultdict, deque
from time import monotonic

from pyrogram import filters
from pyrogram.errors import ChatAdminRequired, ChatNotModified, RPCError
from pyrogram.types import ChatPermissions, Message

from Powers import LOGGER
from Powers.bot_class import Gojo
from Powers.database import MongoDB
from Powers.utils.custom_filters import command, restrict_filter

RAID_DB = MongoDB("antiraid")
JOIN_WINDOWS = defaultdict(deque)
RESTORE_TASKS = {}
ORIGINAL_PERMISSIONS = {}
DEFAULTS = {
    "enabled": False,
    "auto_enabled": False,
    "threshold": 8,
    "window": 20,
    "action_time": 300,
    "mode": "lock",
}


def _settings(chat_id):
    data = RAID_DB.find_one({"_id": chat_id})
    if not data:
        data = {"_id": chat_id, **DEFAULTS}
        RAID_DB.insert_one(data)
    else:
        missing = {k: v for k, v in DEFAULTS.items() if k not in data}
        if missing:
            RAID_DB.update({"_id": chat_id}, missing)
            data.update(missing)
    return data


def _update(chat_id, **values):
    return RAID_DB.update({"_id": chat_id}, values)[1]


async def _restore_permissions(client, chat_id, action_time):
    try:
        await sleep(max(1, int(action_time)))
        original = ORIGINAL_PERMISSIONS.pop(chat_id, None)
        if original is None:
            LOGGER.warning("No permission snapshot available for AntiRaid restore in %s", chat_id)
            return
        await client.set_chat_permissions(chat_id, original)
        LOGGER.info("AutoRaid lockdown expired in %s", chat_id)
    except (ChatNotModified, ChatAdminRequired, RPCError) as exc:
        LOGGER.warning("Could not restore AntiRaid permissions in %s: %s", chat_id, exc)
    finally:
        RESTORE_TASKS.pop(chat_id, None)


async def _trigger_raid(client, message, members):
    chat_id = message.chat.id
    settings = _settings(chat_id)
    mode = settings.get("mode", "lock")
    LOGGER.warning(
        "AutoRaid triggered in %s: %s joins in %ss; mode=%s",
        chat_id, len(members), settings.get("window"), mode,
    )

    if mode == "ban":
        for member in members:
            try:
                if member.is_bot:
                    continue
                await client.ban_chat_member(chat_id, member.id)
            except RPCError as exc:
                LOGGER.warning("AutoRaid could not ban %s in %s: %s", member.id, chat_id, exc)
        return

    try:
        # Snapshot the real permissions BEFORE applying the lockdown. Otherwise
        # the restore task would snapshot the already-locked state.
        if chat_id not in ORIGINAL_PERMISSIONS:
            ORIGINAL_PERMISSIONS[chat_id] = message.chat.permissions
        await client.set_chat_permissions(
            chat_id,
            ChatPermissions(
                can_send_messages=False,
                can_send_media_messages=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
                can_send_polls=False,
                can_change_info=False,
                can_invite_users=False,
                can_pin_messages=False,
            ),
        )
        old = RESTORE_TASKS.get(chat_id)
        if old:
            old.cancel()
        RESTORE_TASKS[chat_id] = create_task(
            _restore_permissions(client, chat_id, settings.get("action_time", 300))
        )
    except ChatNotModified:
        pass
    except ChatAdminRequired:
        LOGGER.warning("AutoRaid needs admin permission in %s", chat_id)
    except RPCError as exc:
        LOGGER.error("AutoRaid lockdown failed in %s: %s", chat_id, exc)


@Gojo.on_message(command("antiraid") & restrict_filter)
async def antiraid_cmd(_, m: Message):
    settings = _settings(m.chat.id)
    parts = m.text.split(None, 1)
    arg = parts[1].lower() if len(parts) > 1 else "status"
    if arg in ("on", "enable", "enabled"):
        _update(m.chat.id, enabled=True)
        await m.reply_text(
            f"Anti-Raid enabled. Threshold: {settings['threshold']} joins in {settings['window']}s."
        )
    elif arg in ("off", "disable", "disabled"):
        _update(m.chat.id, enabled=False)
        await m.reply_text("Anti-Raid disabled.")
    else:
        status = "ON" if settings.get("enabled") else "OFF"
        auto = "ON" if settings.get("auto_enabled") else "OFF"
        await m.reply_text(
            "<b>Anti-Raid Settings</b>\n\n"
            f"Status: <b>{status}</b>\n"
            f"AutoRaid: <b>{auto}</b>\n"
            f"Threshold: <b>{settings['threshold']}</b> joins\n"
            f"Detection window: <b>{settings['window']}s</b>\n"
            f"Action duration: <b>{settings['action_time']}s</b>\n"
            f"Mode: <b>{settings['mode']}</b>"
        )


@Gojo.on_message(command("raidmode") & restrict_filter)
async def raidmode_cmd(_, m: Message):
    parts = m.text.split(None, 1)
    if len(parts) < 2:
        await m.reply_text(
            f"Current AutoRaid mode: <b>{_settings(m.chat.id).get('mode', 'lock')}</b>\n"
            "Use: /raidmode lock or /raidmode ban"
        )
        return
    mode = parts[1].lower()
    if mode not in ("lock", "ban"):
        await m.reply_text("Use /raidmode lock or /raidmode ban.")
        return
    _update(m.chat.id, mode=mode)
    await m.reply_text(f"AutoRaid mode set to <b>{mode}</b>.")


@Gojo.on_message(command("raidtime") & restrict_filter)
async def raidtime_cmd(_, m: Message):
    parts = m.text.split()
    if len(parts) < 2:
        await m.reply_text(f"Current raid detection window: <b>{_settings(m.chat.id)['window']}s</b>\nUse: /raidtime 20")
        return
    try:
        value = max(5, min(300, int(parts[1])))
    except ValueError:
        await m.reply_text("Raid time must be between 5 and 300 seconds.")
        return
    _update(m.chat.id, window=value)
    await m.reply_text(f"Raid detection window set to <b>{value}s</b>.")


@Gojo.on_message(command("raidactiontime") & restrict_filter)
async def raidactiontime_cmd(_, m: Message):
    parts = m.text.split()
    if len(parts) < 2:
        await m.reply_text(f"Current raid action duration: <b>{_settings(m.chat.id)['action_time']}s</b>\nUse: /raidactiontime 300")
        return
    try:
        value = max(30, min(3600, int(parts[1])))
    except ValueError:
        await m.reply_text("Action time must be between 30 and 3600 seconds.")
        return
    _update(m.chat.id, action_time=value)
    await m.reply_text(f"Raid action duration set to <b>{value}s</b>.")


@Gojo.on_message(command("autoantiraid") & restrict_filter)
async def autoantiraid_cmd(_, m: Message):
    parts = m.text.split(None, 1)
    arg = parts[1].lower() if len(parts) > 1 else "status"
    if arg in ("on", "enable", "enabled"):
        _update(m.chat.id, auto_enabled=True)
        await m.reply_text("AutoRaid enabled.")
    elif arg in ("off", "disable", "disabled"):
        _update(m.chat.id, auto_enabled=False)
        await m.reply_text("AutoRaid disabled.")
    else:
        status = "ON" if _settings(m.chat.id).get("auto_enabled") else "OFF"
        await m.reply_text(f"AutoRaid: <b>{status}</b>")


@Gojo.on_message(command("setautoantiraid") & restrict_filter)
async def setautoantiraid_cmd(_, m: Message):
    parts = m.text.split()
    if len(parts) < 2:
        settings = _settings(m.chat.id)
        await m.reply_text(
            f"Current threshold: <b>{settings['threshold']}</b> joins / {settings['window']}s\n"
            "Use: /setautoantiraid 8"
        )
        return
    try:
        value = max(3, min(100, int(parts[1])))
    except ValueError:
        await m.reply_text("Threshold must be between 3 and 100.")
        return
    _update(m.chat.id, threshold=value, auto_enabled=True, enabled=True)
    await m.reply_text(f"AutoRaid threshold set to <b>{value}</b> joins. AutoRaid is ON.")


@Gojo.on_message(filters.new_chat_members & filters.group, group=5)
async def antiraid_new_members(client: Gojo, m: Message):
    settings = _settings(m.chat.id)
    if not (settings.get("enabled") or settings.get("auto_enabled")):
        return

    now = monotonic()
    window = max(5, int(settings.get("window", 20)))
    threshold = max(3, int(settings.get("threshold", 8)))
    joins = JOIN_WINDOWS[m.chat.id]

    for member in (m.new_chat_members or []):
        joins.append((now, member))

    cutoff = now - window
    while joins and joins[0][0] < cutoff:
        joins.popleft()

    if len(joins) < threshold:
        return

    members = [item[1] for item in joins]
    joins.clear()
    await _trigger_raid(client, m, members)


__PLUGIN__ = "antiraid"
__alt_name__ = [
    "antiraid", "raidmode", "raidtime", "raidactiontime",
    "autoantiraid", "setautoantiraid",
]
__HELP__ = """
**Anti-Raid + AutoRaid**

• /antiraid on|off - Enable or disable raid protection.
• /antiraid - Show current raid settings.
• /autoantiraid on|off - Enable automatic raid detection.
• /setautoantiraid <joins> - Set the join threshold and enable AutoRaid.
• /raidtime <seconds> - Set the detection window.
• /raidactiontime <seconds> - Set temporary lockdown duration.
• /raidmode lock|ban - Choose lockdown or ban action.
"""
