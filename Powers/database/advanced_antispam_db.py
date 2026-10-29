from threading import RLock

from Powers import LOGGER
from Powers.database import MongoDB

INSERTION_LOCK = RLock()


class AdvancedAntiSpam(MongoDB):
    db_name = "advanced_antispam"

    def __init__(self, chat_id):
        super().__init__(self.db_name)
        self.chat_id = chat_id
        self.chat_info = self.__ensure_in_db()

    def get_settings(self):
        with INSERTION_LOCK:
            return dict(self.chat_info)

    def set(self, key, value):
        with INSERTION_LOCK:
            self.chat_info[key] = value
            return self.update({"_id": self.chat_id}, {key: value})

    def __ensure_in_db(self):
        data = self.find_one({"_id": self.chat_id})
        defaults = {
            "enabled": False,
            "threshold": 6,
            "window": 8,
            "duplicates": 3,
            "action": "mute",
            "action_time": 60,
            "delete": True,
        }
        if data:
            for key, value in defaults.items():
                data.setdefault(key, value)
            return data
        data = {"_id": self.chat_id, **defaults}
        self.insert_one(data)
        LOGGER.info(f"Initialized AdvancedAntiSpam Document for chat {self.chat_id}")
        return data
