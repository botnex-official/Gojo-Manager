from threading import RLock

from Powers import LOGGER
from Powers.database import MongoDB

INSERTION_LOCK = RLock()


class Captcha(MongoDB):
    db_name = "captcha_chats"

    def __init__(self, chat_id: int) -> None:
        super().__init__(self.db_name)
        self.chat_id = chat_id
        self.chat_info = self.__ensure_in_db()

    def get_settings(self):
        with INSERTION_LOCK:
            return dict(self.chat_info)

    def set_enabled(self, status: bool):
        with INSERTION_LOCK:
            self.chat_info["enabled"] = status
            return self.update({"_id": self.chat_id}, {"enabled": status})

    def set_timeout(self, seconds: int):
        with INSERTION_LOCK:
            self.chat_info["timeout"] = seconds
            return self.update({"_id": self.chat_id}, {"timeout": seconds})

    def set_max_attempts(self, attempts: int):
        with INSERTION_LOCK:
            self.chat_info["max_attempts"] = attempts
            return self.update({"_id": self.chat_id}, {"max_attempts": attempts})

    def set_action(self, action: str):
        with INSERTION_LOCK:
            self.chat_info["action"] = action
            return self.update({"_id": self.chat_id}, {"action": action})

    def __ensure_in_db(self):
        data = self.find_one({"_id": self.chat_id})
        if data:
            data.setdefault("enabled", False)
            data.setdefault("timeout", 120)
            data.setdefault("max_attempts", 3)
            data.setdefault("action", "kick")
            return data
        data = {
            "_id": self.chat_id,
            "enabled": False,
            "timeout": 120,
            "max_attempts": 3,
            "action": "kick",
        }
        self.insert_one(data)
        LOGGER.info(f"Initialized Captcha Document for chat {self.chat_id}")
        return data
