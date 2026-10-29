import asyncio
import json

from pyrogram import filters
from pyrogram.enums import ChatMemberStatus as CMS
from pyrogram.errors import ChatAdminRequired, ChatNotModified, RPCError
from pyrogram.types import ChatPermissions, Message

from Powers import LOGGER
from Powers.bot_class import Gojo
from Powers.database import MongoDB
from Powers.database.blacklist_db import Blacklist
from Powers.database.disable_db import Disabling
from Powers.database.filters_db import Filters
from Powers.database.flood_db import Floods
from Powers.database.granular_lock_db import GranularLocks
from Powers.database.greetings_db import Greetings
from Powers.database.message_lock_db import FLAG_FIELDS, MessageLocks
from Powers.database.notes_db import Notes, NotesSettings
from Powers.database.pins_db import Pins
from Powers.database.pm_connection_db import PMConnectionDB
from Powers.database.reporting_db import Reporting
from Powers.database.rules_db import Rules
from Powers.database.warns_db import WarnSettings
from Powers.utils.custom_filters import admin_filter, command
from Powers.utils.rose_import import (
    RoseImportError,
    convert_rose_settings,
    parse_rose_export,
)

# Rose settings exports are small JSON documents; anything bigger is not one.
MAX_ROSE_EXPORT_SIZE = 1024 * 1024

pm_connections = PMConnectionDB()

# Mirrors the defaults in Powers/plugins/antiraid.py — antiraid settings
# live in a raw MongoDB collection keyed by chat id.
ANTIRAID_DEFAULTS = {
    "enabled": False,
    "auto_enabled": False,
    "threshold": 8,
    "window": 20,
    "action_time": 300,
    "mode": "lock",
}


async def _get_connected_chat(client, user_id):
    connection = pm_connections.get(user_id)
    if not connection:
        return None, "❌ No group is connected to your PM. Open the group's /start message and tap <b>Connect me to pm</b> first."

    chat_id = connection.get("chat_id")
    if not isinstance(chat_id, int) or chat_id >= 0:
        return None, "❌ The saved PM connection is invalid. Please reconnect the group."

    try:
        member = await client.get_chat_member(chat_id, user_id)
    except Exception:
        return None, "❌ I could not access the connected group. Make sure I am still in the group and try again."

    if member.status not in {CMS.OWNER, CMS.ADMINISTRATOR}:
        return None, "❌ You are no longer an admin of the connected group."

    try:
        chat = await client.get_chat(chat_id)
    except Exception:
        return None, "❌ I could not load the connected group."

    return chat, None


def _apply_db_operations(chat_id, operations):
    """Apply every operation that only needs the database layer.

    Returns (counts, existing, pending, errors): per-target applied
    counts, how many filters/notes already existed, the permission-lock
    operations the async caller must finish, and per-operation errors.
    """
    counts = {}
    existing = 0
    pending = []
    errors = []

    filters_db = Filters()
    notes_db = Notes()
    cache = {}

    def cached(key, factory):
        if key not in cache:
            cache[key] = factory()
        return cache[key]

    for target, payload in operations:
        try:
            if target == "filter":
                added = filters_db.save_filter(
                    chat_id,
                    payload["name"],
                    payload["text"],
                    payload["msgtype"],
                    payload["fileid"],
                )
                if added:
                    counts[target] = counts.get(target, 0) + 1
                else:
                    existing += 1
            elif target == "note":
                added = notes_db.save_note(
                    chat_id,
                    payload["name"],
                    payload["text"],
                    payload["msgtype"],
                    payload["fileid"],
                )
                if added:
                    counts[target] = counts.get(target, 0) + 1
                else:
                    existing += 1
            elif target == "private_notes":
                NotesSettings().set_privatenotes(chat_id, payload["enabled"])
                counts[target] = counts.get(target, 0) + 1
            elif target == "rules":
                rules = cached("rules", lambda: Rules(chat_id))
                rules.set_rules(payload["content"])
                rules.set_privrules(payload["private"])
                counts[target] = counts.get(target, 0) + 1
            elif target in (
                "welcome_status",
                "welcome_text",
                "goodbye_status",
                "goodbye_text",
                "clean_welcome",
                "clean_service",
            ):
                greetings = cached("greetings", lambda: Greetings(chat_id))
                if target == "welcome_status":
                    greetings.set_current_welcome_settings(payload["enabled"])
                elif target == "welcome_text":
                    greetings.set_welcome_text(
                        payload["text"], payload["msgtype"], payload["media"]
                    )
                elif target == "goodbye_status":
                    greetings.set_current_goodbye_settings(payload["enabled"])
                elif target == "goodbye_text":
                    greetings.set_goodbye_text(
                        payload["text"], payload["msgtype"], payload["media"]
                    )
                elif target == "clean_welcome":
                    greetings.set_current_cleanwelcome_settings(payload["enabled"])
                else:
                    greetings.set_current_cleanservice_settings(payload["enabled"])
                counts[target] = counts.get(target, 0) + 1
            elif target == "lock_granular":
                granular = cached("granular", lambda: GranularLocks(chat_id))
                granular.add(payload["lock_type"])
                counts[target] = counts.get(target, 0) + 1
            elif target == "lock_message_flag":
                MessageLocks().set_flag(chat_id, payload["field"], True)
                counts[target] = counts.get(target, 0) + 1
            elif target in ("lock_permission", "lock_all"):
                pending.append((target, payload))
            elif target == "flood_off":
                Floods().rm_flood(chat_id)
                counts[target] = counts.get(target, 0) + 1
            elif target == "flood_set":
                Floods().save_flood(
                    chat_id,
                    payload["limit"],
                    payload["within"],
                    payload["action"],
                )
                counts[target] = counts.get(target, 0) + 1
            elif target == "warn_settings":
                warn_settings = cached("warns", lambda: WarnSettings(chat_id))
                warn_settings.set_warnlimit(payload["limit"])
                warn_settings.set_warnmode(payload["mode"])
                counts[target] = counts.get(target, 0) + 1
            elif target == "reports":
                reporting = cached("reporting", lambda: Reporting(chat_id))
                reporting.set_settings(payload["enabled"])
                counts[target] = counts.get(target, 0) + 1
            elif target == "antiraid":
                collection = MongoDB("antiraid")
                fields = dict(payload["fields"])
                if collection.find_one({"_id": chat_id}):
                    collection.update({"_id": chat_id}, fields)
                else:
                    collection.insert_one(
                        {"_id": chat_id, **ANTIRAID_DEFAULTS, **fields}
                    )
                counts[target] = counts.get(target, 0) + 1
            elif target == "pins":
                pins = cached("pins", lambda: Pins(chat_id))
                if payload["antichannelpin"]:
                    pins.antichannelpin_on()
                elif payload["cleanlinked"]:
                    pins.cleanlinked_on()
                else:
                    pins.antichannelpin_off()
                counts[target] = counts.get(target, 0) + 1
            elif target == "blacklist_add":
                blacklist = cached("blacklist", lambda: Blacklist(chat_id))
                blacklist.add_blacklist(payload["trigger"])
                counts[target] = counts.get(target, 0) + 1
            elif target == "blacklist_action":
                blacklist = cached("blacklist", lambda: Blacklist(chat_id))
                blacklist.set_action(payload["action"])
                counts[target] = counts.get(target, 0) + 1
            elif target == "blacklist_reason":
                blacklist = cached("blacklist", lambda: Blacklist(chat_id))
                blacklist.set_reason(payload["reason"])
                counts[target] = counts.get(target, 0) + 1
            elif target == "disable_add":
                disabling = cached("disabling", lambda: Disabling(chat_id))
                disabling.add_disable(payload["command"])
                counts[target] = counts.get(target, 0) + 1
            elif target == "disable_action":
                disabling = cached("disabling", lambda: Disabling(chat_id))
                disabling.set_action(payload["action"])
                counts[target] = counts.get(target, 0) + 1
            else:
                errors.append(f"unknown operation '{target}' was not applied")
        except Exception as exc:
            LOGGER.exception(f"Rose import: applying {target} failed")
            errors.append(f"{target}: {exc}")
    return counts, existing, pending, errors


async def _apply_permission_locks(c, chat_id, pending):
    """Apply lock operations that are Telegram chat permissions."""
    errors = []
    counts = {}
    for target, payload in pending:
        try:
            if target == "lock_all":
                # Mirrors Gojo's own /lock all.
                locks = MessageLocks()
                for field in FLAG_FIELDS:
                    locks.set_flag(chat_id, field, True)
                GranularLocks(chat_id).clear()
                try:
                    await c.set_chat_permissions(chat_id, ChatPermissions())
                except (ChatNotModified, ChatAdminRequired, RPCError) as exc:
                    errors.append(f"lock all: {exc}")
                    continue
                counts[target] = counts.get(target, 0) + 1
            elif target == "lock_permission":
                chat = await c.get_chat(chat_id)
                perms = getattr(chat, "permissions", None)
                if perms is None:
                    errors.append(
                        f"lock {payload['lock_type']}: could not read the "
                        "chat's current permissions"
                    )
                    continue
                kwargs = {
                    "can_send_messages": perms.can_send_messages,
                    "can_send_media_messages": perms.can_send_media_messages,
                    "can_send_other_messages": perms.can_send_other_messages,
                    "can_add_web_page_previews": perms.can_add_web_page_previews,
                    "can_send_polls": perms.can_send_polls,
                    "can_change_info": perms.can_change_info,
                    "can_invite_users": perms.can_invite_users,
                    "can_pin_messages": perms.can_pin_messages,
                }
                if payload["lock_type"] == "polls":
                    kwargs["can_send_polls"] = False
                try:
                    await c.set_chat_permissions(
                        chat_id, ChatPermissions(**kwargs)
                    )
                except (ChatNotModified, ChatAdminRequired, RPCError) as exc:
                    errors.append(f"lock {payload['lock_type']}: {exc}")
                    continue
                counts[target] = counts.get(target, 0) + 1
        except Exception as exc:
            LOGGER.exception(f"Rose import: applying {target} failed")
            errors.append(f"{target}: {exc}")
    return counts, errors


_SUMMARY_LINES = (
    ("Filters imported", ("filter",)),
    ("Notes imported", ("note",)),
    ("Private-notes setting applied", ("private_notes",)),
    ("Rules applied", ("rules",)),
    (
        "Greetings settings applied",
        (
            "welcome_status",
            "welcome_text",
            "goodbye_status",
            "goodbye_text",
            "clean_welcome",
            "clean_service",
        ),
    ),
    (
        "Locks set",
        ("lock_granular", "lock_message_flag", "lock_permission", "lock_all"),
    ),
    ("Anti-flood updated", ("flood_set", "flood_off")),
    ("Warning settings applied", ("warn_settings",)),
    ("Reports setting applied", ("reports",)),
    ("Anti-raid settings applied", ("antiraid",)),
    ("Pins settings applied", ("pins",)),
    ("Blocklist entries imported", ("blacklist_add",)),
    ("Blocklist settings applied", ("blacklist_action", "blacklist_reason")),
    ("Disabled commands imported", ("disable_add",)),
    ("Disabled-command setting applied", ("disable_action",)),
)


def _build_summary(chat_title, counts, existing, skipped, warnings, errors):
    lines = [f"✅ <b>Rose settings imported into {chat_title}</b>", ""]
    for label, targets in _SUMMARY_LINES:
        total = sum(counts.get(target, 0) for target in targets)
        if total:
            lines.append(f"• {label}: <b>{total}</b>")
    if existing:
        lines.append(
            f"• Filters/notes that already existed in Gojo (kept as-is): <b>{existing}</b>"
        )
    if skipped:
        lines.append("")
        lines.append("⚠️ <b>Not imported:</b>")
        for item, reason in skipped:
            lines.append(f"• <b>{item}</b> — {reason}")
    if warnings:
        lines.append("")
        lines.append("ℹ️ <b>Notes:</b>")
        for warning in warnings:
            lines.append(f"• {warning}")
    if errors:
        lines.append("")
        lines.append("❌ <b>Failed to apply:</b>")
        for error in errors:
            lines.append(f"• {error}")
    return "\n".join(lines)


async def _import_rose_for_chat(c, m: Message, chat_id: int, chat_title=None):
    source = m if m.document else m.reply_to_message
    if not source or not source.document:
        await m.reply_text(
            "Reply to a Rose settings export file with /importrose, or send "
            "the export file with /importrose as its caption."
        )
        return

    document = source.document
    if document.file_size and document.file_size > MAX_ROSE_EXPORT_SIZE:
        await m.reply_text(
            "❌ That file is too large to be a settings export (1 MB max)."
        )
        return

    try:
        raw = await source.download(in_memory=True)
        if isinstance(raw, (bytes, bytearray)):
            text = bytes(raw).decode("utf-8")
        else:
            text = raw.getvalue().decode("utf-8")
        parsed = json.loads(text)
        rose_data = parse_rose_export(parsed)
        converted = convert_rose_settings(rose_data)
    except (RoseImportError, ValueError, UnicodeDecodeError) as exc:
        await m.reply_text(
            "❌ That doesn't look like a Rose settings export.\n"
            f"<code>{exc}</code>"
        )
        return

    try:
        counts, existing, pending, errors = await asyncio.to_thread(
            _apply_db_operations, chat_id, converted["operations"]
        )
        if pending:
            perm_counts, perm_errors = await _apply_permission_locks(
                c, chat_id, pending
            )
            for target, count in perm_counts.items():
                counts[target] = counts.get(target, 0) + count
            errors.extend(perm_errors)
    except Exception:
        LOGGER.exception("Rose settings import failed")
        await m.reply_text("❌ Something went wrong while importing. No summary could be built; check the bot logs.")
        return

    title = chat_title or getattr(m.chat, "title", None) or str(chat_id)
    await m.reply_text(
        _build_summary(
            title,
            counts,
            existing,
            converted["skipped"],
            converted["warnings"],
            errors,
        )
    )


@Gojo.on_message(command("importrose") & admin_filter)
async def import_rose(c: Gojo, m: Message):
    await _import_rose_for_chat(c, m, m.chat.id)


@Gojo.on_message(command("importrose") & filters.private)
async def import_rose_pm(c: Gojo, m: Message):
    chat, error = await _get_connected_chat(c, m.from_user.id)
    if error:
        await m.reply_text(error)
        return
    await _import_rose_for_chat(c, m, chat.id, chat.title)


__PLUGIN__ = "rose_import"

__alt_name__ = ["importrose"]

__HELP__ = """
**Rose Settings Import**

**Admin commands:**
• Reply to a Rose (@MissRose_bot) settings export file with /importrose — Import that group's Rose settings into Gojo.
• You can also send the export file with /importrose as its caption.
• In PM, connect a group first; the import then applies to the connected group.

This is separate from /importsettings: that command only restores Gojo's
own backups. /importrose reads Rose's export format and converts what
Gojo supports — filters, notes, rules, greetings, locks, anti-flood,
warnings, reports, anti-raid, pins, blocklist and disabled commands.
Anything Rose has that Gojo does not is listed as skipped in the reply,
never silently dropped. Media saved in Rose carries Rose's file IDs,
which may not send from Gojo.
"""
