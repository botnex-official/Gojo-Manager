import asyncio
import io
import json
from datetime import datetime

from pyrogram import filters
from pyrogram.enums import ChatMemberStatus as CMS
from pyrogram.types import Message

from Powers import LOGGER
from Powers.bot_class import Gojo
from Powers.database import Powers_main_db
from Powers.database.pm_connection_db import PMConnectionDB
from Powers.utils.custom_filters import admin_filter, command
from Powers.utils.settings_export import build_export, sanitize_import

# Only group-scoped configuration collections are included. User/content/global data is excluded.
EXPORT_COLLECTIONS = (
    "antiraid", "captcha_chats", "advanced_antispam", "chat_warn_settings",
    "flood", "disabled", "reporting", "welcome_chats", "rules",
)

pm_connections = PMConnectionDB()


def _json_default(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _get_chat_document(collection, chat_id):
    return collection.find_one({"_id": chat_id}) or collection.find_one({"chat_id": chat_id})


def collect_settings(chat_id):
    settings = {}
    for name in EXPORT_COLLECTIONS:
        doc = _get_chat_document(Powers_main_db[name], chat_id)
        if doc:
            doc = dict(doc)
            doc.pop("_id", None)
            doc.pop("user_id", None)
            settings[name] = doc
    return settings


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


async def _export_for_chat(m, chat_id, chat_title=None):
    # collect_settings reads every export collection synchronously; keep
    # it off the event loop (audit H1).
    payload = build_export(chat_id, await asyncio.to_thread(collect_settings, chat_id))
    raw = json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default).encode()
    file = io.BytesIO(raw)
    file.name = f"gojo-settings-{chat_id}.json"
    title = chat_title or getattr(m.chat, "title", None) or str(chat_id)
    await m.reply_document(
        file,
        caption=(
            f"✅ <b>Group settings backup created.</b>\n"
            f"Group: <b>{title}</b>\n\n"
            "Only supported group-scoped configuration is included."
        ),
    )


@Gojo.on_message(command("exportsettings") & admin_filter)
async def export_settings(_, m: Message):
    await _export_for_chat(m, m.chat.id)


@Gojo.on_message(command("exportsettings") & filters.private)
async def export_settings_pm(c, m: Message):
    chat, error = await _get_connected_chat(c, m.from_user.id)
    if error:
        await m.reply_text(error)
        return
    await _export_for_chat(m, chat.id, chat.title)


@Gojo.on_message(command("importsettings") & admin_filter)
async def import_settings(_, m: Message):
    await _import_for_chat(m, m.chat.id)


@Gojo.on_message(command("importsettings") & filters.private)
async def import_settings_pm(c, m: Message):
    chat, error = await _get_connected_chat(c, m.from_user.id)
    if error:
        await m.reply_text(error)
        return
    await _import_for_chat(m, chat.id)


async def _import_for_chat(m, chat_id):
    if not m.reply_to_message or not m.reply_to_message.document:
        await m.reply_text("Reply to a JSON settings backup with /importsettings")
        return

    document = m.reply_to_message.document
    if document.file_size > 512 * 1024:
        await m.reply_text("❌ Backup is too large. Maximum supported size is 512 KB.")
        return

    try:
        data = await m.reply_to_message.download(in_memory=True)
        parsed = json.loads(data.getvalue().decode("utf-8"))
        backup = sanitize_import(parsed)
        if backup["chat_id"] != chat_id:
            await m.reply_text(
                "❌ This backup belongs to a different group. "
                "Export a backup from the connected group first."
            )
            return

        imported = 0
        for name, doc in backup["settings"].items():
            if name not in EXPORT_COLLECTIONS or not isinstance(doc, dict):
                continue
            collection = Powers_main_db[name]
            existing = _get_chat_document(collection, chat_id)
            if existing:
                collection.update_one({"_id": existing["_id"]}, {"$set": doc})
            else:
                collection.insert_one({"_id": chat_id, "chat_id": chat_id, **doc})
            imported += 1

        await m.reply_text(
            f"✅ <b>Settings imported successfully.</b>\n"
            f"Collections restored: <b>{imported}</b>"
        )
    except Exception as exc:
        LOGGER.exception("Settings import failed")
        await m.reply_text(f"❌ Invalid or incompatible backup.\n<code>{exc}</code>")


__PLUGIN__ = "settings_export"
__alt_name__ = ["exportsettings", "importsettings"]

__HELP__ = """
**Settings Export / Import**

**Admin commands:**
• /exportsettings — Create a JSON backup of supported group configuration.
• Reply to a backup with /importsettings — Restore it to the same group.
• In PM, connect a group first; these commands then operate on the connected group.

Backups are versioned and limited to group-scoped configuration. User data, global bans, federation data and message/content databases are not exported.
"""
