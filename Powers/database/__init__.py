from sys import exit as exiter

from pymongo import MongoClient
from pymongo.errors import PyMongoError

from Powers import DB_NAME, DB_URI, LOGGER

try:
    # Bound every Mongo operation: without timeouts pymongo waits up to
    # serverSelectionTimeoutMS (30s default) for a server, and because the
    # whole DB layer is synchronous that stall freezes the event loop and
    # every pending update with it (audit H1/H6).
    Powers_db_client = MongoClient(
        DB_URI,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        socketTimeoutMS=15000,
        maxPoolSize=50,
    )
except PyMongoError as f:
    LOGGER.error(f"Error in Mongodb: {f}")
    exiter(1)
Powers_main_db = Powers_db_client[DB_NAME]

# Hot-path indexes (audit H2), keyed by collection name and using the exact
# field names the DB modules query by. Collections whose documents are
# keyed by ``_id`` (chats, greetings/welcome_chats, disabled, granular
# locks, message locks, captcha, advanced-antispam, antiraid, warn
# settings, notes settings, pm-connections by user id, ...) need no entry
# here: MongoDB always maintains an index on ``_id``, which is what those
# lookups use. Only field-based lookups are listed.
HOT_INDEXES = {
    "users": ["username"],
    "chat_filters": [[("chat_id", 1), ("keyword", 1)]],
    "notes": [[("chat_id", 1), ("note_name", 1)], "hash"],
    "chat_warns": [[("chat_id", 1), ("user_id", 1)]],
    "flood": ["chat_id"],
}

_ENSURED_INDEXES = set()


def ensure_index(collection, keys):
    """Create the ``keys`` index on ``collection`` once per process.

    Never raises: an index is a performance optimisation and must not be
    able to break a handler. Attempts (successful or not) are remembered,
    so repeated calls are no-ops and a failure is not retried per message.
    """
    marker = (collection.full_name, repr(keys))
    if marker in _ENSURED_INDEXES:
        return
    _ENSURED_INDEXES.add(marker)
    try:
        collection.create_index(keys)
    except Exception as exc:
        LOGGER.warning(
            f"Could not create index {keys} on {collection.full_name}: {exc}",
        )


class MongoDB:
    """Class for interacting with Bot database."""

    def __init__(self, collection) -> None:
        self.collection = Powers_main_db[collection]
        for keys in HOT_INDEXES.get(collection, ()):
            ensure_index(self.collection, keys)

    # Insert one entry into collection
    def insert_one(self, document):
        result = self.collection.insert_one(document)
        return repr(result.inserted_id)

    # Find one entry from collection
    def find_one(self, query):
        result = self.collection.find_one(query)
        if result:
            return result
        return False

    # Find entries from collection
    def find_all(self, query=None):
        if query is None:
            query = {}
        return list(self.collection.find(query))

    # Count entries from collection
    def count(self, query=None):
        if query is None:
            query = {}
        return self.collection.count_documents(query)

    # Delete one entry from collection
    def delete_one(self, query):
        self.collection.delete_one(query)
        return self.collection.count_documents({})

    # Delete every entry matching query
    def delete_many(self, query):
        self.collection.delete_many(query)
        return self.collection.count_documents({})

    # Replace one entry in collection
    def replace(self, query, new_data):
        old = self.collection.find_one(query)
        _id = old["_id"]
        self.collection.replace_one({"_id": _id}, new_data)
        new = self.collection.find_one({"_id": _id})
        return old, new

    # Update one entry from collection
    def update(self, query, update):
        result = self.collection.update_one(query, {"$set": update})
        new_document = self.collection.find_one(query)
        return result.modified_count, new_document

    @staticmethod
    def close():
        return Powers_db_client.close()


def __connect_first():
    _ = MongoDB("test")
    LOGGER.info("Initialized Database!\n")


__connect_first()
