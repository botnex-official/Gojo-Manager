from datetime import datetime
from threading import RLock

from Powers import TIME_ZONE as TZ
from Powers.database import MongoDB

INSERTION_LOCK = RLock()


class AFK(MongoDB):
    db_name = "afk"

    def __init__(self):
        super().__init__(self.db_name)

    def set(self, user_id: int, reason: str = ""):
        with INSERTION_LOCK:
            data = {"_id": int(user_id), "reason": reason.strip(), "since": datetime.now(TZ)}
            if self.find_one({"_id": int(user_id)}):
                return self.update(
                    {"_id": int(user_id)},
                    {"reason": data["reason"], "since": data["since"]},
                )
            return self.insert_one(data)

    def get(self, user_id: int):
        with INSERTION_LOCK:
            return self.find_one({"_id": int(user_id)})

    def remove(self, user_id: int):
        with INSERTION_LOCK:
            return self.delete_one({"_id": int(user_id)})

    def is_afk(self, user_id: int) -> bool:
        # MongoDB.find_one returns the sentinel False (not None) when no
        # document exists, so a plain truthiness check is required here:
        # a missing row means the user is NOT AFK.
        return bool(self.get(user_id))

    def all(self):
        with INSERTION_LOCK:
            return self.find_all() or []
