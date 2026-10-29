from threading import RLock

from Powers.database import MongoDB

LOCK = RLock()

# Documented link/forward flags. anon_channel persists the old anti_c_send list
# and is omitted from insert defaults so a links-only write stays on this schema.
CORE_FIELDS = (
    "links",
    "forward_all",
    "forward_users",
    "forward_channels",
)
FLAG_FIELDS = CORE_FIELDS + ("anon_channel",)


class MessageLocks(MongoDB):
    """Persistent per-chat link, forward, and send-as-chat locks.

    Reads never insert a document. Writes upsert a single chat document.
    """

    db_name = "message_locks"

    def __init__(self) -> None:
        super().__init__(self.db_name)

    def get(self, chat_id) -> dict:
        """Return lock flags. Missing chats are all False and are not created."""
        chat_id = int(chat_id)
        with LOCK:
            data = self.find_one({"_id": chat_id}) or {}
            return {
                "_id": chat_id,
                "links": bool(data.get("links", False)),
                "forward_all": bool(data.get("forward_all", False)),
                "forward_users": bool(data.get("forward_users", False)),
                "forward_channels": bool(data.get("forward_channels", False)),
                "anon_channel": bool(data.get("anon_channel", False)),
            }

    def get_flag(self, chat_id, field) -> bool:
        if field not in FLAG_FIELDS:
            raise ValueError(f"Unknown message lock field: {field}")
        return self.get(chat_id)[field]

    def set_flag(self, chat_id, field, enabled) -> None:
        """Upsert one flag. Other flags default to False only on insert."""
        if field not in FLAG_FIELDS:
            raise ValueError(f"Unknown message lock field: {field}")
        chat_id = int(chat_id)
        enabled = bool(enabled)
        defaults = {name: False for name in CORE_FIELDS if name != field}
        with LOCK:
            self.collection.update_one(
                {"_id": chat_id},
                {"$set": {field: enabled}, "$setOnInsert": defaults},
                upsert=True,
            )

    def enabled_links(self, chat_id) -> bool:
        return self.get_flag(chat_id, "links")

    def set_links(self, chat_id, enabled: bool) -> None:
        self.set_flag(chat_id, "links", enabled)

    def forward_mode_flags(self, chat_id):
        data = self.get(chat_id)
        return (
            data["forward_all"],
            data["forward_users"],
            data["forward_channels"],
        )
