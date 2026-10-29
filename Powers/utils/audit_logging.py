from datetime import datetime
from html import escape
from Powers import TIME_ZONE

def normalize_log_chat(value):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    return value if value < 0 else None

def format_audit_event(action, user_id, user_name, chat_id, chat_title, details=""):
    when = datetime.now(TIME_ZONE).strftime("%Y-%m-%d %H:%M:%S %Z")
    text = (
        f"<b>📝 {escape(str(action))}</b>\n"
        f"<b>Group:</b> {escape(str(chat_title))} (<code>{chat_id}</code>)\n"
        f"<b>Admin:</b> {escape(str(user_name))} (<code>{user_id}</code>)\n"
        f"<b>Time:</b> <code>{when}</code>"
    )
    if details:
        text += f"\n<b>Details:</b> {escape(str(details))}"
    return text
