from datetime import datetime
from uuid import uuid4

from Powers import TIME_ZONE


def new_schedule_id():
    return uuid4().hex[:8]


def parse_schedule_args(args):
    """Return (kind, fields, text) for supported schedule syntax."""
    if not args:
        raise ValueError("Missing schedule time and message")

    if args[0].lower() == "daily":
        if len(args) < 3:
            raise ValueError("Usage: /schedule daily HH:MM <message>")
        time_text = args[1]
        text = " ".join(args[2:]).strip()
        _parse_time(time_text)
        if not text:
            raise ValueError("Message cannot be empty")
        return "daily", {"time": time_text}, text

    if args[0].lower() == "weekly":
        if len(args) < 4:
            raise ValueError("Usage: /schedule weekly MON HH:MM <message>")
        weekday = args[1].lower()[:3]
        if weekday not in {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}:
            raise ValueError("Invalid weekday")
        time_text = args[2]
        text = " ".join(args[3:]).strip()
        _parse_time(time_text)
        if not text:
            raise ValueError("Message cannot be empty")
        return "weekly", {"weekday": weekday, "time": time_text}, text

    if len(args) >= 3 and _looks_like_date(args[0]):
        date_text, time_text = args[0], args[1]
        _parse_datetime(date_text, time_text)
        text = " ".join(args[2:]).strip()
        if not text:
            raise ValueError("Message cannot be empty")
        return "once", {"date": date_text, "time": time_text}, text

    if len(args) >= 2:
        time_text = args[0]
        _parse_time(time_text)
        text = " ".join(args[1:]).strip()
        if not text:
            raise ValueError("Message cannot be empty")
        return "daily", {"time": time_text}, text

    raise ValueError("Usage: /schedule HH:MM <message>")


def _looks_like_date(value):
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _parse_time(value):
    try:
        datetime.strptime(value, "%H:%M")
    except ValueError as exc:
        raise ValueError("Time must be HH:MM (24-hour format)") from exc


def _parse_datetime(date_text, time_text):
    try:
        dt = datetime.strptime(f"{date_text} {time_text}", "%Y-%m-%d %H:%M")
    except ValueError as exc:
        raise ValueError("Date/time must be YYYY-MM-DD HH:MM") from exc
    if dt.replace(tzinfo=TIME_ZONE) <= datetime.now(TIME_ZONE):
        raise ValueError("One-time schedule must be in the future")
    return dt
