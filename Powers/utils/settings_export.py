from datetime import datetime, timezone

EXPORT_VERSION = 1

def build_export(chat_id, settings):
    clean = {k:v for k,v in settings.items() if k != "_id"}
    return {"version": EXPORT_VERSION, "chat_id": int(chat_id), "exported_at": datetime.now(timezone.utc).isoformat(), "settings": clean}

def sanitize_import(data):
    if not isinstance(data, dict) or data.get("version") != EXPORT_VERSION:
        raise ValueError("Unsupported settings backup version")
    settings = data.get("settings")
    if not isinstance(settings, dict):
        raise ValueError("Invalid settings payload")
    settings = {k:v for k,v in settings.items() if k not in {"_id", "chat_id", "owner", "admins"}}
    return {"version": EXPORT_VERSION, "chat_id": int(data.get("chat_id")), "settings": settings}
