def make_connect_payload(chat_id):
    return f"connect_{int(chat_id)}"

def parse_connect_payload(payload):
    if not isinstance(payload, str) or not payload.startswith("connect_"):
        return None
    try:
        chat_id = int(payload.split("_", 1)[1])
    except (TypeError, ValueError):
        return None
    if chat_id >= 0:
        return None
    return chat_id
