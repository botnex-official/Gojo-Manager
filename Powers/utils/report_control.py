"""Validation helpers for report callback actions."""


def parse_report_callback(data):
    """Parse a report action payload without trusting malformed input."""
    if not isinstance(data, str) or not data.startswith("report_"):
        return None
    parts = data[len("report_"):].split("=")
    if len(parts) != 4 or parts[1] not in {"kick", "ban", "del"}:
        return None
    try:
        chat_id = int(parts[0])
        user_id = int(parts[2])
        message_id = int(parts[3])
    except (TypeError, ValueError):
        return None
    if chat_id >= 0 or user_id <= 0 or message_id <= 0:
        return None
    return chat_id, parts[1], user_id, message_id
