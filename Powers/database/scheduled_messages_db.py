from datetime import datetime

from Powers import TIME_ZONE as TZ
from Powers.database import MongoDB


class ScheduledMessages(MongoDB):
    def __init__(self):
        super().__init__("scheduled_messages")
        self.collection.create_index(
            [("chat_id", 1), ("schedule_id", 1)],
            unique=True,
            name="scheduled_chat_id_unique",
        )
        self.collection.create_index(
            [("chat_id", 1), ("enabled", 1)],
            name="scheduled_chat_enabled",
        )

    def create(self, document):
        return self.collection.insert_one(document).inserted_id

    def get(self, chat_id, schedule_id):
        return self.collection.find_one({"chat_id": chat_id, "schedule_id": schedule_id})

    def list(self, chat_id):
        return list(self.collection.find({"chat_id": chat_id}).sort("created_at", 1))

    def delete(self, chat_id, schedule_id):
        return self.collection.delete_one({"chat_id": chat_id, "schedule_id": schedule_id})

    def update(self, chat_id, schedule_id, updates):
        updates["updated_at"] = datetime.now(TZ)
        return self.collection.update_one(
            {"chat_id": chat_id, "schedule_id": schedule_id},
            {"$set": updates},
        )
