from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from pyrogram import filters
from pyrogram.types import Message

from Powers import LOGGER, TIME_ZONE
from Powers.bot_class import Gojo
from Powers.database.scheduled_messages_db import ScheduledMessages
from Powers.utils.custom_filters import admin_filter, command
from Powers.utils.scheduled_messages import new_schedule_id, parse_schedule_args

DB = ScheduledMessages()
SCHEDULER = AsyncIOScheduler(timezone=TIME_ZONE, job_defaults={"coalesce": True, "max_instances": 1})
SCHEDULER_STARTED = False


def _job_id(chat_id, schedule_id):
    return f"scheduled:{chat_id}:{schedule_id}"


async def _send_scheduled(client, doc):
    chat_id = doc["chat_id"]
    try:
        await client.send_message(chat_id, doc["text"])
        # A one-time schedule must not become active again after a restart.
        if doc.get("kind") == "once":
            DB.update(chat_id, doc["schedule_id"], {"enabled": False})
    except Exception as exc:
        LOGGER.warning(f"Scheduled message {chat_id}/{doc.get('schedule_id')} failed: {exc}")


def _trigger_for(doc):
    kind = doc["kind"]
    if kind == "once":
        dt = datetime.strptime(
            f"{doc['date']} {doc['time']}", "%Y-%m-%d %H:%M"
        ).replace(tzinfo=TIME_ZONE)
        return DateTrigger(run_date=dt, timezone=TIME_ZONE)
    hour, minute = map(int, doc["time"].split(":"))
    if kind == "weekly":
        return CronTrigger(
            day_of_week=doc["weekday"], hour=hour, minute=minute, timezone=TIME_ZONE
        )
    return CronTrigger(hour=hour, minute=minute, timezone=TIME_ZONE)


def _add_job(client, doc):
    if not doc.get("enabled", True):
        return
    SCHEDULER.add_job(
        _send_scheduled,
        trigger=_trigger_for(doc),
        args=[client, doc],
        id=_job_id(doc["chat_id"], doc["schedule_id"]),
        replace_existing=True,
        misfire_grace_time=300,
    )


async def start_scheduler(client):
    global SCHEDULER_STARTED
    if SCHEDULER_STARTED:
        return
    for doc in DB.collection.find({"enabled": True}):
        try:
            _add_job(client, doc)
        except Exception:
            LOGGER.exception(f"Could not restore scheduled message {doc.get('schedule_id')}")
    SCHEDULER.start()
    SCHEDULER_STARTED = True
    LOGGER.info("Scheduled messages scheduler started")


async def _ensure_scheduler(client):
    if not SCHEDULER_STARTED:
        await start_scheduler(client)


@Gojo.on_message(command("schedule") & admin_filter)
async def schedule_message(c: Gojo, m: Message):
    await _ensure_scheduler(c)
    try:
        kind, fields, text = parse_schedule_args(m.command[1:])
    except ValueError as exc:
        await m.reply_text(f"❌ {exc}")
        return

    schedule_id = new_schedule_id()
    doc = {
        "schedule_id": schedule_id,
        "chat_id": m.chat.id,
        "kind": kind,
        "text": text,
        "enabled": True,
        "created_by": m.from_user.id,
        "created_at": datetime.now(TIME_ZONE),
        **fields,
    }
    if kind == "once":
        # APScheduler will remove the job after execution; the DB record remains for history.
        pass
    DB.create(doc)
    _add_job(c, doc)
    await m.reply_text(
        f"✅ Scheduled <code>{schedule_id}</code>\n"
        f"Type: <b>{kind}</b>\n"
        f"Message: {text}"
    )


@Gojo.on_message(command("schedules") & admin_filter)
async def list_schedules(_, m: Message):
    rows = DB.list(m.chat.id)
    if not rows:
        await m.reply_text("📭 No scheduled messages in this group.")
        return
    lines = ["📅 <b>Scheduled messages</b>"]
    for row in rows:
        status = "ON" if row.get("enabled", True) else "OFF"
        target = (
            f"{row['date']} {row['time']}" if row["kind"] == "once"
            else f"{row.get('weekday', 'daily')} {row['time']}"
        )
        lines.append(f"<code>{row['schedule_id']}</code> • {status} • {row['kind']} • {target}\n{row['text']}")
    await m.reply_text("\n\n".join(lines))


@Gojo.on_message(command("delschedule") & admin_filter)
async def delete_schedule(_, m: Message):
    if len(m.command) < 2:
        await m.reply_text("Usage: /delschedule <id>")
        return
    schedule_id = m.command[1]
    row = DB.get(m.chat.id, schedule_id)
    if not row:
        await m.reply_text("❌ Schedule not found.")
        return
    try:
        SCHEDULER.remove_job(_job_id(m.chat.id, schedule_id))
    except Exception:
        pass
    DB.delete(m.chat.id, schedule_id)
    await m.reply_text(f"✅ Schedule <code>{schedule_id}</code> deleted.")


@Gojo.on_message(command("scheduleoff") & admin_filter)
async def disable_schedule(_, m: Message):
    if len(m.command) < 2:
        await m.reply_text("Usage: /scheduleoff <id>")
        return
    schedule_id = m.command[1]
    if not DB.get(m.chat.id, schedule_id):
        await m.reply_text("❌ Schedule not found.")
        return
    try:
        SCHEDULER.pause_job(_job_id(m.chat.id, schedule_id))
    except Exception:
        pass
    DB.update(m.chat.id, schedule_id, {"enabled": False})
    await m.reply_text(f"⏸️ Schedule <code>{schedule_id}</code> disabled.")


@Gojo.on_message(command("scheduleon") & admin_filter)
async def enable_schedule(c: Gojo, m: Message):
    if len(m.command) < 2:
        await m.reply_text("Usage: /scheduleon <id>")
        return
    schedule_id = m.command[1]
    row = DB.get(m.chat.id, schedule_id)
    if not row:
        await m.reply_text("❌ Schedule not found.")
        return
    DB.update(m.chat.id, schedule_id, {"enabled": True})
    row["enabled"] = True
    _add_job(c, row)
    await m.reply_text(f"▶️ Schedule <code>{schedule_id}</code> enabled.")


@Gojo.on_message(command("editschedule") & admin_filter)
async def edit_schedule(c: Gojo, m: Message):
    if len(m.command) < 3:
        await m.reply_text("Usage: /editschedule <id> <new time/date syntax> <message>")
        return
    schedule_id = m.command[1]
    row = DB.get(m.chat.id, schedule_id)
    if not row:
        await m.reply_text("❌ Schedule not found.")
        return
    try:
        kind, fields, text = parse_schedule_args(m.command[2:])
    except ValueError as exc:
        await m.reply_text(f"❌ {exc}")
        return
    try:
        SCHEDULER.remove_job(_job_id(m.chat.id, schedule_id))
    except Exception:
        pass
    DB.update(m.chat.id, schedule_id, {"kind": kind, "text": text, **fields, "enabled": True})
    row.update({"kind": kind, "text": text, **fields, "enabled": True})
    _add_job(c, row)
    await m.reply_text(f"✅ Schedule <code>{schedule_id}</code> updated.")


__PLUGIN__ = "scheduled_messages"
__alt_name__ = ["schedule", "schedules", "delschedule", "scheduleoff", "scheduleon", "editschedule"]
__HELP__ = """
**Scheduled Messages**

• /schedule HH:MM &lt;message&gt; — Daily
• /schedule YYYY-MM-DD HH:MM &lt;message&gt; — One time
• /schedule daily HH:MM &lt;message&gt; — Daily
• /schedule weekly MON HH:MM &lt;message&gt; — Weekly
• /schedules — List schedules
• /editschedule &lt;id&gt; ... — Edit
• /scheduleoff &lt;id&gt; — Disable
• /scheduleon &lt;id&gt; — Enable
• /delschedule &lt;id&gt; — Delete

Schedules are stored in MongoDB and restored automatically after restart.
"""
