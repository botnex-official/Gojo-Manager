from datetime import datetime

from Powers import TIME_ZONE as TZ
from Powers.database import MongoDB


class PMConnectionDB(MongoDB):
    """Persistent one-to-one mapping between a PM user and connected group."""

    db_name = "pm_connections"

    def __init__(self):
        super().__init__(self.db_name)

    def connect(self, user_id, chat_id):
        return self.collection.update_one(
            {"_id": int(user_id)},
            {
                "$set": {
                    "chat_id": int(chat_id),
                    "connected_at": datetime.now(TZ),
                }
            },
            upsert=True,
        )

    def get(self, user_id):
        return self.find_one({"_id": int(user_id)})

    def disconnect(self, user_id):
        return self.delete_one({"_id": int(user_id)})
