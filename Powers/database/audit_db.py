from datetime import datetime
from Powers import TIME_ZONE
from Powers.database import MongoDB

class AuditLogs(MongoDB):
    # Keep raw audit events bounded while retaining the per-chat configuration
    # document. TTL only applies to documents that contain created_at.
    RETENTION_SECONDS = 90 * 24 * 60 * 60

    def __init__(self, chat_id):
        super().__init__("audit_logs")
        self.chat_id = chat_id
        self.collection.create_index(
            "created_at",
            expireAfterSeconds=self.RETENTION_SECONDS,
            name="audit_events_ttl_90d",
        )
    def get_settings(self):
        doc = self.collection.find_one({"_id": self.chat_id})
        return doc or {"_id": self.chat_id, "enabled": False, "log_chat_id": None}
    def set_log_chat(self, log_chat_id):
        self.collection.update_one({"_id": self.chat_id}, {"$set": {"enabled": True, "log_chat_id": log_chat_id}}, upsert=True)
    def disable(self):
        self.collection.update_one({"_id": self.chat_id}, {"$set": {"enabled": False}}, upsert=True)
    def add_event(self, event):
        self.collection.insert_one({"chat_id": self.chat_id, "created_at": datetime.now(TIME_ZONE), **event})
