from os import getcwd

from prettyconf import Configuration
from prettyconf.loaders import EnvFile, Environment

env_file = f"{getcwd()}/.env"
config = Configuration(loaders=[Environment(), EnvFile(filename=env_file)])


class Config:
    """Config class for variables."""

    LOGGER = True
    BOT_TOKEN = config("BOT_TOKEN", default=None)
    API_ID = int(config("API_ID", default="0"))
    API_HASH = config("API_HASH", default="")
    OWNER_ID = int(config("OWNER_ID", default="0"))
    MESSAGE_DUMP = int(config("MESSAGE_DUMP", default=-100))
    DEV_USERS = [
        int(i)
        for i in config(
            "DEV_USERS",
            default="0",
        ).split(" ")
    ]
    SUDO_USERS = [
        int(i)
        for i in config(
            "SUDO_USERS",
            default="0",
        ).split(" ")
    ]
    WHITELIST_USERS = [
        int(i)
        for i in config(
            "WHITELIST_USERS",
            default="0",
        ).split(" ")
    ]
    GENIUS_API_TOKEN = config("GENIUS_API_TOKEN", default=None)
    AuDD_API = config("AuDD_API", default=None)
    RMBG_API = config("RMBG_API", default=None)
    DB_URI = config("DB_URI", default="")
    DB_NAME = config("DB_NAME", default="gojo_manager")
    BDB_URI = config("BDB_URI", default=None)
    NO_LOAD = config("NO_LOAD", default="").split()
    PREFIX_HANDLER = config("PREFIX_HANDLER", default="/").split()
    SUPPORT_GROUP = config("SUPPORT_GROUP", default="Purohit_bots_support")
    SUPPORT_CHANNEL = config("SUPPORT_CHANNEL", default="purohit_bots")
    WORKERS = int(config("WORKERS", default=16))
    TIME_ZONE = config("TIME_ZONE", default="Asia/Kolkata")
    BOT_USERNAME = config("BOT_USERNAME", default="")
    BOT_ID = config("BOT_ID", default="")
    BOT_NAME = config("BOT_NAME", default="Gojo Manager Bot")
    owner_username = config("OWNER_USERNAME", default="Sohan_rajpurohit_1")


class Development:
    """Development class for variables."""

    # Fill in these vars if you want to use Traditional method of deploying
    LOGGER = True
    AuDD_API = ""
    BOT_TOKEN = "YOUR_BOT_TOKEN"
    API_ID = "YOUR_API_ID"  # Your APP_ID from Telegram
    API_HASH = "YOUR_API_HASH"  # Your APP_HASH from Telegram
    OWNER_ID = "YOUR_TELEGRAM_ID"  # Your telegram user id
    MESSAGE_DUMP = "-100"  # Your Private Group ID for logs
    DEV_USERS = ["YOUR_TELEGRAM_ID"]
    SUDO_USERS = ["YOUR_TELEGRAM_ID"]
    WHITELIST_USERS = ["YOUR_TELEGRAM_ID"]
    DB_URI = "mongodb+srv://<username>:<password>@<cluster>.mongodb.net/?retryWrites=true&w=majority"  # Your mongo DB URI
    DB_NAME = "gojo_manager"  # Your DB name
    NO_LOAD = []
    GENIUS_API_TOKEN = ""
    RMBG_API = ""
    PREFIX_HANDLER = ["!", "/", "$"]
    SUPPORT_GROUP = "Purohit_bots_support"
    SUPPORT_CHANNEL = "purohit_bots"
    VERSION = "1.0"
    TIME_ZONE = "Asia/Kolkata"
    BDB_URI = ""
    WORKERS = 8
