"""Interactive group-settings center for admins.

The panel reads live state and exposes safe one-tap controls backed by the
existing feature/database implementations.
"""

import asyncio
from html import escape

from pyrogram import filters
from pyrogram.enums import ChatMemberStatus as CMS, ChatType
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from Powers import LOGGER
from Powers.bot_class import Gojo
from Powers.database import MongoDB
from Powers.database.advanced_antispam_db import AdvancedAntiSpam
from Powers.database.blacklist_db import Blacklist
from Powers.database.captcha_db import Captcha
from Powers.database.greetings_db import Greetings
from Powers.database.flood_db import Floods
from Powers.database.granular_lock_db import GranularLocks
from Powers.database.notes_db import NotesSettings
from Powers.database.pm_connection_db import PMConnectionDB
from Powers.database.rules_db import Rules
from Powers.database.reporting_db import Reporting
from Powers.database.warns_db import WarnSettings
from Powers.plugins.antiraid import _settings as _raid_settings
from Powers.plugins.settings_export import collect_settings
from Powers.utils.custom_filters import command

pm_connections = PMConnectionDB()

CATEGORIES = {
    "moderation": (
        "🛡️ Moderation",
        "Configure warning behavior and member-safety policies.",
        [
            ("⚠️ Warnings", "Set the warning mode and warning limit used by the group.", "/warnings, /warnmode, /warnlimit"),
            ("🚫 Blacklist action", "Choose what happens when a blacklist trigger is detected.", "/blaction, /blacklistaction, /blacklistmode"),
            ("📢 Reports", "Enable or disable report notifications for this group.", "/reports on|off"),
        ],
    ),
    "locks": (
        "🔒 Locks",
        "Control which message types and group permissions are allowed.",
        [
            ("🔒 Permission locks", "Lock or unlock Telegram group permissions.", "/lock <type>, /unlock <type>, /locks"),
            ("🔗 Link lock", "Delete URLs, Telegram links and text links.", "/lock links, /unlock links"),
            ("📦 Media locks", "Lock individual media types such as photos, videos, documents and stickers.", "/lock <type>, /unlock <type>, /locktypes"),
            ("↪️ Forward locks", "Block forwarded messages from users or channels.", "/lock forwardall|forwardu|forwardc, /unlock <type>"),
        ],
    ),
    "protection": (
        "🛡️ Protection",
        "Automatic protection against floods, raids, spam and unwanted joins.",
        [
            ("🌊 Anti-Flood", "Configure flood detection and its response.", "/setflood, /flood, /floodaction"),
            ("🚨 Anti-Raid", "Configure raid detection, mode, timing and action.", "/antiraid, /raidmode, /raidtime, /raidactiontime"),
            ("🤖 Auto-Raid", "Configure automatic raid protection thresholds/actions.", "/autoantiraid, /setautoantiraid"),
            ("🧩 CAPTCHA", "Verify new members before allowing them to participate.", "/captcha, /captchatime, /captchamaxattempts, /captchaaction"),
            ("🛡️ Advanced Anti-Spam", "Configure burst/duplicate detection and its response.", "/antispam, /spamlimit, /spamduplicates, /spamaction, /spammactiontime, /spamdelete"),
        ],
    ),
    "content": (
        "📝 Content",
        "Configure automatic replies, blocked content and group information.",
        [
            ("🔎 Filters", "Create and remove automatic keyword responses.", "/filter, /stop, /filters, /rmallfilters"),
            ("🚫 Blacklist", "Manage blocked words and phrases.", "/addblacklist, /unblacklist, /blacklist, /rmallblacklist"),
            ("📌 Notes", "Store and manage reusable replies/media for the group.", "/save, /get, /notes, /clear, /clearall"),
            ("📜 Rules", "Set, view and clear the group's rules.", "/setrules, /rules, /clearrules, /privrules"),
            ("👋 Greetings", "Configure welcome/goodbye messages and service-message cleanup.", "/setwelcome, /setgoodbye, /resetwelcome, /resetgoodbye, /cleanwelcome, /cleangoodbye, /cleanservice"),
        ],
    ),
    "admin": (
        "👮 Admin",
        "Operational controls that affect how the bot behaves in this group.",
        [
            ("🔕 Disabled commands", "Disable or re-enable bot commands for this group.", "/disable, /enable, /disabled, /enableall, /disableable, /disabledel"),
            ("📝 Audit log", "Configure and inspect the group's audit log.", "/setlog, /unsetlog, /logstatus"),
            ("📌 Pin protection", "Control automatic handling of linked-channel pins.", "/antichannelpin on|off, /cleanlinked on|off"),
            ("📌 Pin utilities", "Manage pinned messages and permanent pins.", "/pin, /unpin, /unpinall, /permapin"),
            ("🔐 Federation", "Manage this group's federation membership/settings.", "/joinfed, /leavefed, /chatfed"),
        ],
    ),
    "automation": (
        "⚙️ Automation & Backup",
        "Scheduled group automation and supported configuration backup.",
        [
            ("📅 Scheduled messages", "Create, list, edit, enable, disable and delete schedules.", "/schedule, /schedules, /editschedule, /scheduleon, /scheduleoff, /delschedule"),
            ("🗃️ Settings backup", "Export or import supported group-scoped configuration.", "/exportsettings, /importsettings"),
        ],
    ),
}

_STATUS_LABELS = {
    "antiraid": "🚨 Anti-Raid",
    "captcha_chats": "🧩 CAPTCHA",
    "advanced_antispam": "🛡️ Advanced Anti-Spam",
    "chat_warn_settings": "⚠️ Warnings",
    "flood": "🌊 Anti-Flood",
    "disabled": "🔕 Disabled Commands",
    "reporting": "📢 Reports",
    "welcome_chats": "👋 Greetings",
    "rules": "📜 Rules",
}


def _main_keyboard():
    items = list(CATEGORIES.items())
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(items[i][1][0], callback_data=f"gsettings:cat:{items[i][0]}"),
            *([InlineKeyboardButton(items[i + 1][1][0], callback_data=f"gsettings:cat:{items[i + 1][0]}")]
              if i + 1 < len(items) else []),
        ]
        for i in range(0, len(items), 2)
    ])


def _category_keyboard(category):
    items = CATEGORIES[category][2]
    rows = [
        [InlineKeyboardButton(name, callback_data=f"gsettings:item:{category}:{index}")]
        for index, (name, _, _) in enumerate(items)
    ]
    rows.append([InlineKeyboardButton("« Back", callback_data="gsettings:home")])
    return InlineKeyboardMarkup(rows)


def _item_keyboard(category, index, controls=None):
    rows = list(controls or [])
    rows.append([InlineKeyboardButton("🔄 Refresh", callback_data=f"gsettings:refresh:{category}:{index}")])
    rows.append([InlineKeyboardButton("« Back", callback_data=f"gsettings:cat:{category}")])
    rows.append([InlineKeyboardButton("🏠 Main Settings", callback_data="gsettings:home")])
    return InlineKeyboardMarkup(rows)


def _on_off(value):
    return "ON" if value else "OFF"


def _current_summary(chat_id):
    settings = collect_settings(chat_id)
    lines = []

    raid = settings.get("antiraid")
    if raid:
        lines.append(
            f"{_STATUS_LABELS['antiraid']}: <code>{_on_off(raid.get('enabled'))}</code> · "
            f"auto <code>{_on_off(raid.get('auto_enabled'))}</code> · "
            f"{raid.get('threshold')} joins/{raid.get('window')}s · "
            f"{escape(str(raid.get('mode')))} · {raid.get('action_time')}s"
        )

    captcha = settings.get("captcha_chats")
    if captcha:
        lines.append(
            f"{_STATUS_LABELS['captcha_chats']}: <code>{_on_off(captcha.get('enabled'))}</code> · "
            f"timeout {captcha.get('timeout')}s · attempts {captcha.get('max_attempts')} · "
            f"{escape(str(captcha.get('action')))}"
        )

    spam = settings.get("advanced_antispam")
    if spam:
        lines.append(
            f"{_STATUS_LABELS['advanced_antispam']}: <code>{_on_off(spam.get('enabled'))}</code> · "
            f"{spam.get('threshold')}/{spam.get('window')}s · dup {spam.get('duplicates')} · "
            f"{escape(str(spam.get('action')))} {spam.get('action_time')}s · "
            f"delete <code>{_on_off(spam.get('delete'))}</code>"
        )

    warns = settings.get("chat_warn_settings")
    if warns:
        lines.append(
            f"{_STATUS_LABELS['chat_warn_settings']}: mode <code>{escape(str(warns.get('warn_mode')))}</code> · "
            f"limit <code>{warns.get('warn_limit')}</code>"
        )

    flood = settings.get("flood")
    if flood:
        lines.append(
            f"{_STATUS_LABELS['flood']}: <code>ON</code> · "
            f"{flood.get('limit')} msgs/{flood.get('within')}s · {escape(str(flood.get('action')))}"
        )

    disabled = settings.get("disabled")
    if disabled:
        commands = disabled.get("commands") or []
        lines.append(
            f"{_STATUS_LABELS['disabled']}: "
            f"<code>{len(commands)}</code> command(s) disabled"
            + (f" · {escape(', '.join(map(str, commands[:8])))}" if commands else "")
        )

    reports = settings.get("reporting")
    if reports:
        lines.append(f"{_STATUS_LABELS['reporting']}: <code>{_on_off(reports.get('status', reports.get('enabled', False)))}</code>")

    welcome = settings.get("welcome_chats")
    if welcome:
        lines.append(
            f"{_STATUS_LABELS['welcome_chats']}: welcome <code>{_on_off(welcome.get('welcome'))}</code> · "
            f"goodbye <code>{_on_off(welcome.get('goodbye'))}</code> · "
            f"clean welcome <code>{_on_off(welcome.get('cleanwelcome'))}</code> · "
            f"clean goodbye <code>{_on_off(welcome.get('cleangoodbye'))}</code> · "
            f"clean service <code>{_on_off(welcome.get('cleanservice'))}</code>"
        )

    rules = settings.get("rules")
    # The rules document exists as soon as ANY rules-related value is
    # stored (e.g. toggling private-rules creates it with no text).
    # SET must mean rules TEXT is present — the same test the Rules
    # item page uses — not merely that the document exists.
    if rules and rules.get("rules"):
        lines.append(f"{_STATUS_LABELS['rules']}: <code>SET</code>")

    if not lines:
        return "<i>No stored group configuration found yet.</i>"

    return "\n".join(lines)


async def _resolve_chat(client, user_id, chat_id=None):
    if chat_id is None:
        connection = pm_connections.get(user_id)
        if not connection:
            return None
        chat_id = connection["chat_id"]

    chat = await client.get_chat(chat_id)
    member = await client.get_chat_member(chat.id, user_id)
    return chat if member.status in {CMS.OWNER, CMS.ADMINISTRATOR} else None


async def _show_home(message, chat):
    # _current_summary gathers from many collections synchronously; run it
    # in a worker thread so rendering the panel never blocks the event
    # loop (audit H1).
    summary = await asyncio.to_thread(_current_summary, chat.id)
    await message.edit_text(
        "⚙️ <b>Group Settings</b>\n\n"
        f"<b>Group:</b> {escape(chat.title or str(chat.id))}\n"
        f"<b>ID:</b> <code>{chat.id}</code>\n\n"
        "<b>Current configuration</b>\n"
        f"{summary}\n\n"
        "Select a category for descriptions and existing commands.",
        reply_markup=_main_keyboard(),
    )


async def _show_category(message, chat, category):
    title, description, _ = CATEGORIES[category]
    await message.edit_text(
        f"{title}\n\n<b>{escape(chat.title or str(chat.id))}</b>\n\n"
        f"{description}\n\nSelect a setting:",
        reply_markup=_category_keyboard(category),
    )


def _item_status(client, chat, category, index):
    """Read the real current state without changing group configuration.

    Fully synchronous (Mongo reads only) — callers must run it via
    asyncio.to_thread so it never blocks the event loop (audit H1).
    """
    name = CATEGORIES[category][2][index][0]
    chat_id = chat.id

    if name == "⚠️ Warnings":
        doc = MongoDB("chat_warn_settings").find_one({"_id": chat_id})
        if not doc:
            return "No custom warning settings stored."
        return (
            f"Mode: <code>{escape(str(doc.get('warn_mode', 'none')))}</code> · "
            f"Limit: <code>{doc.get('warn_limit', 3)}</code>"
        )

    if name == "🚫 Blacklist action":
        doc = MongoDB("blacklists").find_one({"_id": chat_id})
        if not doc:
            return "No blacklist configuration stored."
        triggers = doc.get("triggers") or []
        return (
            f"Action: <code>{escape(str(doc.get('action', 'none')))}</code> · "
            f"Blocked words/phrases: <code>{len(triggers)}</code>"
        )

    if name == "📢 Reports":
        doc = MongoDB("reporting").find_one({"_id": chat_id})
        status = bool(doc.get("status")) if doc else False
        return f"Reports: <code>{_on_off(status)}</code>"

    if name == "🔒 Permission locks":
        permissions = chat.permissions
        if not permissions:
            return "Telegram permissions are unavailable."
        locked = []
        checks = (
            ("messages", permissions.can_send_messages),
            ("media", permissions.can_send_media_messages),
            ("other media", permissions.can_send_other_messages),
            ("web previews", permissions.can_add_web_page_previews),
            ("polls", permissions.can_send_polls),
            ("change info", permissions.can_change_info),
            ("invite users", permissions.can_invite_users),
            ("pin messages", permissions.can_pin_messages),
        )
        locked.extend(label for label, allowed in checks if allowed is False)
        return "Locked: " + (", ".join(locked) if locked else "None")

    if name in {"🔗 Link lock", "↪️ Forward locks"}:
        from Powers.plugins import locks as locks_plugin

        if name == "🔗 Link lock":
            enabled = chat_id in locks_plugin.anti_links
            return f"Links: <code>{_on_off(enabled)}</code>"
        states = (
            ("all", chat_id in locks_plugin.anti_forward),
            ("users", chat_id in locks_plugin.anti_forward_u),
            ("channels", chat_id in locks_plugin.anti_forward_c),
        )
        return "Forward locks: " + ", ".join(
            f"{label} <code>{_on_off(enabled)}</code>" for label, enabled in states
        )

    if name == "📦 Media locks":
        doc = MongoDB("granular_locks").find_one({"_id": chat_id}) or {}
        locked = doc.get("locks") or []
        return "Granular locks: " + (", ".join(map(str, sorted(locked))) if locked else "None")

    if name in {"🌊 Anti-Flood", "🚨 Anti-Raid", "🤖 Auto-Raid", "🧩 CAPTCHA", "🛡️ Advanced Anti-Spam"}:
        keys = {
            "🌊 Anti-Flood": "flood",
            "🚨 Anti-Raid": "antiraid",
            "🤖 Auto-Raid": "antiraid",
            "🧩 CAPTCHA": "captcha_chats",
            "🛡️ Advanced Anti-Spam": "advanced_antispam",
        }
        doc = collect_settings(chat_id).get(keys[name])
        if not doc:
            return "No stored configuration found."
        if name == "🌊 Anti-Flood":
            return (
                f"Limit: <code>{doc.get('limit')}</code> messages/{doc.get('within')}s · "
                f"Action: <code>{escape(str(doc.get('action')))}</code>"
            )
        if name == "🚨 Anti-Raid":
            return (
                f"Enabled: <code>{_on_off(doc.get('enabled'))}</code> · "
                f"Auto: <code>{_on_off(doc.get('auto_enabled'))}</code> · "
                f"Threshold: <code>{doc.get('threshold')}</code> joins/{doc.get('window')}s · "
                f"Mode: <code>{escape(str(doc.get('mode')))}</code> · "
                f"Action time: <code>{doc.get('action_time')}s</code>"
            )
        if name == "🤖 Auto-Raid":
            return (
                f"Enabled: <code>{_on_off(doc.get('auto_enabled'))}</code> · "
                f"Threshold: <code>{doc.get('threshold')}</code> joins/{doc.get('window')}s"
            )
        if name == "🧩 CAPTCHA":
            return (
                f"Enabled: <code>{_on_off(doc.get('enabled'))}</code> · "
                f"Timeout: <code>{doc.get('timeout')}s</code> · "
                f"Attempts: <code>{doc.get('max_attempts')}</code> · "
                f"Action: <code>{escape(str(doc.get('action')))}</code>"
            )
        return (
            f"Enabled: <code>{_on_off(doc.get('enabled'))}</code> · "
            f"Limit: <code>{doc.get('threshold')}</code>/{doc.get('window')}s · "
            f"Duplicates: <code>{doc.get('duplicates')}</code> · "
            f"Action: <code>{escape(str(doc.get('action')))}</code> {doc.get('action_time')}s · "
            f"Delete: <code>{_on_off(doc.get('delete'))}</code>"
        )

    if name == "🔎 Filters":
        count = MongoDB("chat_filters").count({"chat_id": chat_id})
        return f"Configured filters: <code>{count}</code>"

    if name == "🚫 Blacklist":
        doc = MongoDB("blacklists").find_one({"_id": chat_id})
        count = len((doc or {}).get("triggers") or [])
        action = (doc or {}).get("action", "none")
        return f"Blocked words/phrases: <code>{count}</code> · Action: <code>{escape(str(action))}</code>"

    if name == "📌 Notes":
        count = MongoDB("notes").count({"chat_id": chat_id})
        settings = MongoDB("notes_settings").find_one({"_id": chat_id}) or {}
        return (
            f"Notes: <code>{count}</code> · Private notes: "
            f"<code>{_on_off(settings.get('privatenotes', False))}</code>"
        )

    if name == "📜 Rules":
        doc = MongoDB("rules").find_one({"_id": chat_id})
        if not doc or not doc.get("rules"):
            return "Rules: <code>NOT SET</code>"
        return f"Rules: <code>SET</code> · Private rules: <code>{_on_off(doc.get('privrules'))}</code>"

    if name == "👋 Greetings":
        doc = MongoDB("welcome_chats").find_one({"_id": chat_id})
        if not doc:
            return "No stored greeting configuration found."
        return (
            f"Welcome <code>{_on_off(doc.get('welcome'))}</code> · "
            f"Goodbye <code>{_on_off(doc.get('goodbye'))}</code> · "
            f"Clean welcome <code>{_on_off(doc.get('cleanwelcome'))}</code> · "
            f"Clean goodbye <code>{_on_off(doc.get('cleangoodbye'))}</code> · "
            f"Clean service <code>{_on_off(doc.get('cleanservice'))}</code>"
        )

    if name == "🔕 Disabled commands":
        doc = MongoDB("disabled").find_one({"_id": chat_id}) or {}
        commands = doc.get("commands") or []
        return (
            f"Disabled: <code>{len(commands)}</code> command(s)"
            + (f" · {escape(', '.join(map(str, commands[:15])))}" if commands else "")
        )

    if name == "📝 Audit log":
        doc = MongoDB("audit_logs").find_one({"_id": chat_id}) or {}
        return (
            f"Enabled: <code>{_on_off(doc.get('enabled', False))}</code> · "
            f"Log chat: <code>{doc.get('log_chat_id') or 'not set'}</code>"
        )

    if name == "📌 Pin protection":
        doc = MongoDB("antichannelpin").find_one({"_id": chat_id}) or {}
        return (
            f"AntiChannelPin: <code>{_on_off(doc.get('antichannelpin', False))}</code> · "
            f"CleanLinked: <code>{_on_off(doc.get('cleanlinked', False))}</code>"
        )

    if name == "📌 Pin utilities":
        pinned = getattr(chat, "pinned_message", None)
        if not pinned:
            return "Current pinned message: <code>None</code>"
        return f"Current pinned message ID: <code>{pinned.id}</code> · /permapin creates a bot-pinned message."

    if name == "🔐 Federation":
        doc = MongoDB("federations").find_one({"chats": chat_id})
        if not doc:
            return "Federation: <code>NOT CONNECTED</code>"
        return (
            f"Federation: <code>{escape(str(doc.get('name', doc.get('_id'))))}</code> · "
            f"ID: <code>{escape(str(doc.get('_id')))}</code>"
        )

    if name == "📅 Scheduled messages":
        rows = MongoDB("scheduled_messages").find_all({"chat_id": chat_id})
        enabled = sum(1 for row in rows if row.get("enabled", True))
        return f"Schedules: <code>{len(rows)}</code> total · <code>{enabled}</code> enabled"

    if name == "🗃️ Settings backup":
        return (
            "Supported backup collections: <code>9</code> · "
            "Use /exportsettings to create a backup or /importsettings to restore one."
        )

    return "Current state is not available for this setting."



def _control_rows(chat_id, category, index, name):
    rows = []

    def toggle(label, key, current):
        rows.append([
            InlineKeyboardButton(
                f"{label} ON {'✓' if current else ''}".strip(),
                callback_data=f"gsettings:toggle:{category}:{index}:{key}:on",
            ),
            InlineKeyboardButton(
                f"{label} OFF {'✓' if not current else ''}".strip(),
                callback_data=f"gsettings:toggle:{category}:{index}:{key}:off",
            ),
        ])

    if name == "⚠️ Warnings":
        mode = WarnSettings(chat_id).get_warnmode()
        rows.append([
            InlineKeyboardButton(f"Kick {'✓' if mode == 'kick' else ''}", callback_data=f"gsettings:warnmode:{category}:{index}:kick"),
            InlineKeyboardButton(f"Ban {'✓' if mode == 'ban' else ''}", callback_data=f"gsettings:warnmode:{category}:{index}:ban"),
            InlineKeyboardButton(f"Mute {'✓' if mode == 'mute' else ''}", callback_data=f"gsettings:warnmode:{category}:{index}:mute"),
        ])
        # 'none' is the default mode (no punishment at the limit). Without
        # this button a chat whose mode was set to ban/kick/mute could
        # never return to 'none' from the panel — mirror the Blacklist
        # action control below, which has always offered None.
        rows.append([
            InlineKeyboardButton(f"None {'✓' if mode == 'none' else ''}", callback_data=f"gsettings:warnmode:{category}:{index}:none"),
        ])
    elif name == "🚫 Blacklist action":
        action = Blacklist(chat_id).get_action()
        rows.append([
            InlineKeyboardButton(f"Ban {'✓' if action == 'ban' else ''}", callback_data=f"gsettings:blaction:{category}:{index}:ban"),
            InlineKeyboardButton(f"Kick {'✓' if action == 'kick' else ''}", callback_data=f"gsettings:blaction:{category}:{index}:kick"),
            InlineKeyboardButton(f"Mute {'✓' if action == 'mute' else ''}", callback_data=f"gsettings:blaction:{category}:{index}:mute"),
        ])
        rows.append([
            InlineKeyboardButton(f"Warn {'✓' if action == 'warn' else ''}", callback_data=f"gsettings:blaction:{category}:{index}:warn"),
            InlineKeyboardButton(f"None {'✓' if action == 'none' else ''}", callback_data=f"gsettings:blaction:{category}:{index}:none"),
        ])
    elif name == "🌊 Anti-Flood":
        flood = Floods().is_chat(chat_id)
        enabled = bool(flood)
        rows.append([
            InlineKeyboardButton(f"ON {'✓' if enabled else ''}".strip(), callback_data=f"gsettings:flood:{category}:{index}:on"),
            InlineKeyboardButton(f"OFF {'✓' if not enabled else ''}".strip(), callback_data=f"gsettings:flood:{category}:{index}:off"),
        ])
        if flood:
            limit, within, flood_action = flood
            rows.append([
                InlineKeyboardButton(f"Limit 5 {'✓' if int(limit) == 5 else ''}".strip(), callback_data=f"gsettings:floodlimit:{category}:{index}:5"),
                InlineKeyboardButton(f"Limit 10 {'✓' if int(limit) == 10 else ''}".strip(), callback_data=f"gsettings:floodlimit:{category}:{index}:10"),
                InlineKeyboardButton(f"Limit 15 {'✓' if int(limit) == 15 else ''}".strip(), callback_data=f"gsettings:floodlimit:{category}:{index}:15"),
            ])
            rows.append([
                InlineKeyboardButton(f"Window 5s {'✓' if int(within) == 5 else ''}".strip(), callback_data=f"gsettings:floodwindow:{category}:{index}:5"),
                InlineKeyboardButton(f"Window 10s {'✓' if int(within) == 10 else ''}".strip(), callback_data=f"gsettings:floodwindow:{category}:{index}:10"),
                InlineKeyboardButton(f"Window 15s {'✓' if int(within) == 15 else ''}".strip(), callback_data=f"gsettings:floodwindow:{category}:{index}:15"),
            ])
            rows.append([
                InlineKeyboardButton(f"Mute {'✓' if flood_action == 'mute' else ''}".strip(), callback_data=f"gsettings:floodaction:{category}:{index}:mute"),
                InlineKeyboardButton(f"Kick {'✓' if flood_action == 'kick' else ''}".strip(), callback_data=f"gsettings:floodaction:{category}:{index}:kick"),
                InlineKeyboardButton(f"Ban {'✓' if flood_action == 'ban' else ''}".strip(), callback_data=f"gsettings:floodaction:{category}:{index}:ban"),
            ])
    elif name == "📢 Reports":
        toggle("Reports", "reports", bool((MongoDB("reporting").find_one({"_id": chat_id}) or {}).get("status", False)))
    elif name == "🚨 Anti-Raid":
        toggle("Anti-Raid", "antiraid", bool(_raid_settings(chat_id).get("enabled")))
    elif name == "🤖 Auto-Raid":
        toggle("Auto-Raid", "autorraid", bool(_raid_settings(chat_id).get("auto_enabled")))
    elif name == "🧩 CAPTCHA":
        toggle("CAPTCHA", "captcha", bool(Captcha(chat_id).get_settings().get("enabled")))
    elif name == "🛡️ Advanced Anti-Spam":
        settings = AdvancedAntiSpam(chat_id).get_settings()
        toggle("Anti-Spam", "antispam", bool(settings.get("enabled")))
        toggle("Delete", "spamdelete", bool(settings.get("delete")))
    elif name == "📦 Media locks":
        lockdb = GranularLocks(chat_id)
        locked = set(lockdb.get_locked())
        lock_types = ("photo", "video", "document", "audio", "voice", "video_note", "sticker", "animation", "contact", "location")
        for start in (0, 3, 6):
            rows.append([
                InlineKeyboardButton(
                    f"{lock_type.title()} {'✓' if lock_type in locked else ''}".strip(),
                    callback_data=f"gsettings:granular:{category}:{index}:{lock_type}:toggle",
                )
                for lock_type in lock_types[start:start + 3]
            ])
        rows.append([InlineKeyboardButton(
            f"Location {'✓' if 'location' in locked else ''}".strip(),
            callback_data=f"gsettings:granular:{category}:{index}:location:toggle",
        )])
    elif name == "📌 Notes":
        toggle("Private notes", "privatenotes", NotesSettings().get_privatenotes(chat_id))
    elif name == "📜 Rules":
        toggle("Private rules", "privrules", bool((MongoDB("rules").find_one({"_id": chat_id}) or {}).get("privrules", False)))
    elif name == "👋 Greetings":
        settings = MongoDB("welcome_chats").find_one({"_id": chat_id}) or {}
        for label, key in (
            ("Welcome", "welcome"),
            ("Goodbye", "goodbye"),
            ("Clean welcome", "cleanwelcome"),
            ("Clean goodbye", "cleangoodbye"),
            ("Clean service", "cleanservice"),
        ):
            toggle(label, f"greeting_{key}", bool(settings.get(key, False)))
    return rows


def _apply_control(chat_id, action, value):
    # Synchronous DB writes only — callers run this via asyncio.to_thread.
    if action == "warnmode":
        WarnSettings(chat_id).set_warnmode(value)
    elif action == "blaction":
        Blacklist(chat_id).set_action(value)
    elif action == "reports":
        Reporting(chat_id).set_settings(value)
    elif action == "antiraid":
        _raid_settings(chat_id)
        MongoDB("antiraid").update({"_id": chat_id}, {"enabled": value})
    elif action == "autorraid":
        _raid_settings(chat_id)
        MongoDB("antiraid").update({"_id": chat_id}, {"auto_enabled": value})
    elif action == "captcha":
        Captcha(chat_id).set_enabled(value)
    elif action == "antispam":
        AdvancedAntiSpam(chat_id).set("enabled", value)
    elif action == "spamdelete":
        AdvancedAntiSpam(chat_id).set("delete", value)
    elif action == "privatenotes":
        NotesSettings().set_privatenotes(chat_id, value)
    elif action == "privrules":
        Rules(chat_id).set_privrules(value)
    elif action.startswith("greeting_"):
        Greetings(chat_id).collection.update_one(
            {"_id": chat_id},
            {"$set": {action.removeprefix("greeting_"): value}},
            upsert=True,
        )
    else:
        raise ValueError("Unknown settings control")


async def _show_item(message, chat, category, index, client=None):
    name, description, commands = CATEGORIES[category][2][index]
    # Both gathers are synchronous Mongo work; keep them off the event
    # loop so one panel render cannot stall every other update (audit H1).
    if client:
        status = await asyncio.to_thread(_item_status, client, chat, category, index)
    else:
        status = "Current state unavailable."
    controls = await asyncio.to_thread(_control_rows, chat.id, category, index, name)
    await message.edit_text(
        f"{name}\n\n"
        f"<b>Group:</b> {escape(chat.title or str(chat.id))}\n"
        f"<b>Current state:</b>\n{status}\n\n"
        f"<b>What it does:</b> {description}\n\n"
        f"<b>Existing commands:</b> <code>{escape(commands)}</code>\n\n"
        "Use the controls below for supported one-tap changes. "
        "Other settings remain available through the existing commands.",
        reply_markup=_item_keyboard(category, index, controls),
    )


async def _open_from_message(client, message):
    if message.chat.type == ChatType.PRIVATE:
        chat = await _resolve_chat(client, message.from_user.id)
        if not chat:
            await message.reply_text("❌ No authorized connected group found. Use /connect in the group first.")
            return
    else:
        member = await client.get_chat_member(message.chat.id, message.from_user.id)
        if member.status not in {CMS.OWNER, CMS.ADMINISTRATOR}:
            await message.reply_text("❌ Only group admins can open Group Settings.")
            return
        chat = message.chat

    summary = await asyncio.to_thread(_current_summary, chat.id)
    await message.reply_text(
        "⚙️ <b>Group Settings</b>\n\n"
        f"<b>Group:</b> {escape(chat.title or str(chat.id))}\n"
        f"<b>ID:</b> <code>{chat.id}</code>\n\n"
        "<b>Current configuration</b>\n"
        f"{summary}\n\n"
        "Select a category:",
        reply_markup=_main_keyboard(),
    )


@Gojo.on_message(command("settings"))
async def group_settings_command(client: Gojo, message: Message):
    await _open_from_message(client, message)


@Gojo.on_callback_query(filters.regex(r"^gsettings:"))
async def group_settings_callback(client: Gojo, query: CallbackQuery):
    parts = query.data.split(":")
    if len(parts) < 2:
        await query.answer("Invalid settings action.", show_alert=True)
        return

    source_chat_id = query.message.chat.id if query.message.chat.type != ChatType.PRIVATE else None
    try:
        chat = await _resolve_chat(client, query.from_user.id, source_chat_id)
    except Exception:
        # Never let a resolution failure die silently in the dispatcher:
        # the user must get feedback instead of a spinner that never ends.
        LOGGER.exception(
            "Group settings callback could not resolve a chat for user %s (data=%s)",
            query.from_user.id,
            query.data,
        )
        await query.answer("Could not load that group. Please try again.", show_alert=True)
        return
    if not chat:
        await query.answer("You are no longer an admin of this group.", show_alert=True)
        return

    action = parts[1]
    if action == "flood" and len(parts) == 5:
        category = parts[2]
        try:
            index = int(parts[3])
        except ValueError:
            index = -1
        desired = parts[4]
        if category not in CATEGORIES or not 0 <= index < len(CATEGORIES[category][2]) or desired not in {"on", "off"}:
            await query.answer("Invalid flood control.", show_alert=True)
            return
        flood = Floods().is_chat(chat.id)
        if desired == "on" and not flood:
            Floods().save_flood(chat.id, 5, 5, "mute")
        elif desired == "off" and flood:
            Floods().rm_flood(chat.id)
        await _show_item(query.message, chat, category, index, client)
        await query.answer("Updated")
        return
    elif action in {"floodlimit", "floodwindow", "floodaction"} and len(parts) == 5:
        # The Anti-Flood value buttons emit exactly five segments
        # ("gsettings:floodlimit:<category>:<index>:<value>"). This branch
        # previously demanded six, so every value click fell through to
        # the "Unknown settings action." alert and nothing ever applied.
        category = parts[2]
        try:
            index = int(parts[3])
        except ValueError:
            index = -1
        value = parts[4]
        if category not in CATEGORIES or not 0 <= index < len(CATEGORIES[category][2]):
            await query.answer("Setting not found.", show_alert=True)
            return
        if action in {"floodlimit", "floodwindow"}:
            if value not in {"5", "10", "15"}:
                await query.answer("Invalid flood value.", show_alert=True)
                return
        elif value not in {"mute", "kick", "ban"}:
            await query.answer("Invalid flood action.", show_alert=True)
            return
        flood = Floods().is_chat(chat.id)
        if not flood:
            await query.answer("Enable Anti-Flood first.", show_alert=True)
            return
        limit, within, flood_action = flood
        if action == "floodlimit":
            limit = int(value)
        elif action == "floodwindow":
            within = int(value)
        else:
            flood_action = value
        Floods().save_flood(chat.id, limit, within, flood_action)
        await _show_item(query.message, chat, category, index, client)
        await query.answer("Updated")
        return
    elif action == "granular" and len(parts) == 6:
        category = parts[2]
        try:
            index = int(parts[3])
        except ValueError:
            index = -1
        lock_type = parts[4]
        if category not in CATEGORIES or not 0 <= index < len(CATEGORIES[category][2]):
            await query.answer("Setting not found.", show_alert=True)
            return
        db = GranularLocks(chat.id)
        if db.is_locked(lock_type):
            db.remove(lock_type)
        else:
            db.add(lock_type)
        await _show_item(query.message, chat, category, index, client)
        await query.answer("Updated")
        return
    if action == "toggle" and len(parts) == 6:
        category = parts[2]
        try:
            index = int(parts[3])
        except ValueError:
            index = -1
        key = parts[4]
        desired = parts[5]
        if category not in CATEGORIES or not 0 <= index < len(CATEGORIES[category][2]):
            await query.answer("Setting not found.", show_alert=True)
            return
        if desired not in {"on", "off"}:
            await query.answer("Invalid ON/OFF value.", show_alert=True)
            return
        allowed = {
            "reports", "antiraid", "autorraid", "captcha", "antispam",
            "spamdelete", "privatenotes", "privrules",
        }
        if key.startswith("greeting_"):
            allowed.add(key)
        if key not in allowed:
            await query.answer("Unknown control.", show_alert=True)
            return
        await asyncio.to_thread(_apply_control, chat.id, key, desired == "on")
        await _show_item(query.message, chat, category, index, client)
        await query.answer("Updated")
    elif action in {"warnmode", "blaction"} and len(parts) == 5:
        category = parts[2]
        try:
            index = int(parts[3])
        except ValueError:
            index = -1
        value = parts[4]
        valid = (
            value in {"kick", "ban", "mute", "none"}
            if action == "warnmode"
            else value in {"ban", "kick", "mute", "warn", "none"}
        )
        if category not in CATEGORIES or not 0 <= index < len(CATEGORIES[category][2]) or not valid:
            await query.answer("Invalid setting action.", show_alert=True)
            return
        await asyncio.to_thread(_apply_control, chat.id, action, value)
        await _show_item(query.message, chat, category, index, client)
        await query.answer("Updated")
    elif action == "refresh" and len(parts) == 4:
        category = parts[2]
        try:
            index = int(parts[3])
        except ValueError:
            index = -1
        if category not in CATEGORIES or not 0 <= index < len(CATEGORIES[category][2]):
            await query.answer("Setting not found.", show_alert=True)
            return
        await _show_item(query.message, chat, category, index, client)
    elif action == "home" and len(parts) == 2:
        await _show_home(query.message, chat)
    elif action == "cat" and len(parts) == 3 and parts[2] in CATEGORIES:
        await _show_category(query.message, chat, parts[2])
    elif action == "item" and len(parts) == 4:
        category = parts[2]
        try:
            index = int(parts[3])
        except ValueError:
            index = -1
        if category not in CATEGORIES or not 0 <= index < len(CATEGORIES[category][2]):
            await query.answer("Setting not found.", show_alert=True)
            return
        await _show_item(query.message, chat, category, index, client)
    else:
        await query.answer("Unknown settings action.", show_alert=True)
        return

    await query.answer()


__PLUGIN__ = "group_settings"
__alt_name__ = ["settings"]
__HELP__ = """
**Group Settings**

• /settings — Open the interactive Group Settings panel.
• Works in a group for admins/owners.
• In PM, connect a group with /connect first.
• The panel shows current stored group configuration and documents the real commands from existing feature plugins.
"""
