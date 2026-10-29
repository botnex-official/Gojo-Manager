from datetime import datetime
from uuid import uuid4

from Powers import TIME_ZONE as TZ
from Powers.database import MongoDB

class FederationDB(MongoDB):
    db_name = "federations"
    def __init__(self): super().__init__(self.db_name)
    def create(self, name, owner_id):
        fed_id = uuid4().hex[:12]
        self.insert_one({"_id": fed_id, "name": name, "owner": owner_id, "admins": [], "chats": [], "bans": {}, "created_at": datetime.now(TZ)})
        return fed_id
    def get(self, fed_id): return self.find_one({"_id": fed_id})
    def get_by_name(self, name): return self.find_one({"name": name})
    def add_chat(self, fed_id, chat_id): return self.collection.update_one({"_id": fed_id}, {"$addToSet": {"chats": chat_id}})
    def remove_chat(self, fed_id, chat_id): return self.collection.update_one({"_id": fed_id}, {"$pull": {"chats": chat_id}})
    def add_admin(self, fed_id, user_id): return self.collection.update_one({"_id": fed_id}, {"$addToSet": {"admins": user_id}})
    def remove_admin(self, fed_id, user_id): return self.collection.update_one({"_id": fed_id}, {"$pull": {"admins": user_id}})
    def ban(self, fed_id, user_id, reason, by): return self.collection.update_one({"_id": fed_id}, {"$set": {f"bans.{user_id}": {"reason": reason, "by": by, "time": datetime.now(TZ)}}})
    def unban(self, fed_id, user_id): return self.collection.update_one({"_id": fed_id}, {"$unset": {f"bans.{user_id}": ""}})
    def delete(self, fed_id): return self.delete_one({"_id": fed_id})
