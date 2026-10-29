"""Persisted extra developers. Documents: {"_id": user_id, "role": "dev"}."""

from typing import List

from Powers.database import MongoDB

COLLECTION = "bot_staff"


def _db() -> MongoDB:
    return MongoDB(COLLECTION)


def list_dev_ids() -> List[int]:
    ids: List[int] = []
    for doc in _db().find_all({"role": "dev"}):
        try:
            ids.append(int(doc["_id"]))
        except (KeyError, TypeError, ValueError):
            continue
    return ids


def add_dev(user_id) -> None:
    uid = int(user_id)
    db = _db()
    current = db.find_one({"_id": uid})
    if current:
        if current.get("role") != "dev":
            db.update({"_id": uid}, {"role": "dev"})
        return
    db.insert_one({"_id": uid, "role": "dev"})


def remove_dev(user_id) -> None:
    _db().delete_one({"_id": int(user_id)})
