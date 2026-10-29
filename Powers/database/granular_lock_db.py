from threading import RLock

from Powers.database import MongoDB

LOCK = RLock()


class GranularLocks(MongoDB):
    """Persistent per-chat message-type locks."""

    db_name = "granular_locks"

    def __init__(self, chat_id: int) -> None:
        super().__init__(self.db_name)
        self.chat_id = int(chat_id)
        self.chat_info = self._ensure()

    def _ensure(self):
        data = self.find_one({"_id": self.chat_id})
        if not data:
            return {"_id": self.chat_id, "locks": []}
        data.setdefault("locks", [])
        return data

    def get_locked(self):
        with LOCK:
            return list(self.chat_info.get("locks") or [])

    def is_locked(self, lock_type: str):
        return lock_type in self.get_locked()

    def add(self, lock_type: str):
        with LOCK:
            locks = self.get_locked()
            if lock_type in locks:
                return False
            locks.append(lock_type)
            self.collection.update_one(
                {"_id": self.chat_id},
                {"$set": {"locks": locks}},
                upsert=True,
            )
            self.chat_info["locks"] = locks
            return True

    def remove(self, lock_type: str):
        with LOCK:
            locks = self.get_locked()
            if lock_type not in locks:
                return False
            locks.remove(lock_type)
            self.collection.update_one(
                {"_id": self.chat_id},
                {"$set": {"locks": locks}},
                upsert=True,
            )
            self.chat_info["locks"] = locks
            return True

    def clear(self):
        with LOCK:
            self.chat_info["locks"] = []
            self.collection.update_one(
                {"_id": self.chat_id},
                {"$set": {"locks": []}},
                upsert=True,
            )
            return True
