import re

FED_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9 _-]{1,63}$")

def normalize_fed_name(name):
    return " ".join(name.strip().lower().split())

def valid_fed_name(name):
    return bool(FED_NAME_RE.fullmatch(normalize_fed_name(name)))

def can_manage_fed(user_id, owner_id, admins):
    return user_id == owner_id or user_id in admins
