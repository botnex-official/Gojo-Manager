from datetime import datetime
from importlib import import_module as imp_mod
from logging import (INFO, WARNING, FileHandler, StreamHandler, basicConfig,
                     getLogger)
from os import environ, listdir, mkdir, path
from platform import python_version
from random import choice
from sys import exit as sysexit
from sys import stdout, version_info
from time import time
from traceback import format_exc

import lyricsgenius
import pyrogram
import pytz

LOG_DATETIME = datetime.now().strftime("%d_%m_%Y-%H_%M_%S")
LOGDIR = f"{__name__}/logs"

# Make Logs directory if it does not exixts
if not path.isdir(LOGDIR):
    mkdir(LOGDIR)

LOGFILE = f"{LOGDIR}/{__name__}_{LOG_DATETIME}_log.txt"

file_handler = FileHandler(filename=LOGFILE)
stdout_handler = StreamHandler(stdout)

basicConfig(
    format="%(asctime)s - [Gojo_Manager] - %(levelname)s - %(message)s",
    level=INFO,
    handlers=[file_handler, stdout_handler],
)

getLogger("pyrogram").setLevel(WARNING)
LOGGER = getLogger(__name__)

# if version < 3.9, stop bot.
if version_info[0] < 3 or version_info[1] < 7:
    LOGGER.error(
        (
            "You MUST have a Python Version of at least 3.7!\n"
            "Multiple features depend on this. Bot quitting."
        ),
    )
    sysexit(1)  # Quit the Script

# the secret configuration specific things
try:
    if environ.get("ENV"):
        from Powers.vars import Config
    else:
        from Powers.vars import Development as Config
except Exception as ef:
    LOGGER.error(ef)  # Print Error
    LOGGER.error(format_exc())
    sysexit(1)
#time zone
TIME_ZONE = pytz.timezone(Config.TIME_ZONE)

path = "./Version"
version = []
for i in listdir(path):
    if i.startswith("version") and i.endswith("md"):
        version.append(i)
    else:
        pass
VERSION = sorted(version)[-1][8:-3]
PYTHON_VERSION = python_version()
PYROGRAM_VERSION = pyrogram.__version__

LOGGER.info("------------------------")
LOGGER.info("|      Gojo_Manager      |")
LOGGER.info("------------------------")
LOGGER.info(f"Version: {VERSION}")
LOGGER.info(f"Owner: {str(Config.OWNER_ID)}")
LOGGER.info(f"Time zone set to {Config.TIME_ZONE}")
LOGGER.info("Source Code: https://github.com/botnex-official/Gojo-Manager\n")
LOGGER.info("Checking lyrics genius api...")
LOGGER.info("Initialising telegraph client")

# API based clients
if Config.GENIUS_API_TOKEN:
    LOGGER.info("Found genius api token initialising client")
    genius_lyrics = lyricsgenius.Genius(
        Config.GENIUS_API_TOKEN,
        skip_non_songs=True,
        excluded_terms=["(Remix)", "(Live)"],
        remove_section_headers=True,
    )
    is_genius_lyrics = True

    genius_lyrics.verbose = False
    LOGGER.info("Client setup complete")
elif not Config.GENIUS_API_TOKEN:
    LOGGER.error("Genius api not found lyrics command will not work")
    is_genius_lyrics = False
    genius_lyrics = False

is_audd = False
Audd = None
if Config.AuDD_API:
    is_audd = True
    Audd = Config.AuDD_API
    LOGGER.info("Found Audd api")

is_rmbg = False
RMBG = None
if Config.RMBG_API:
    is_rmbg = True
    RMBG = Config.RMBG_API
# Account Related
BOT_TOKEN = Config.BOT_TOKEN
API_ID = Config.API_ID
API_HASH = Config.API_HASH

# General Config
MESSAGE_DUMP = Config.MESSAGE_DUMP
SUPPORT_GROUP = Config.SUPPORT_GROUP
SUPPORT_CHANNEL = Config.SUPPORT_CHANNEL

# Users Config
def _int_ids(values):
    parsed = []
    for item in values or []:
        try:
            if item is None or str(item).strip() == "":
                continue
            parsed.append(int(item))
        except (TypeError, ValueError):
            continue
    return parsed


OWNER_ID = int(Config.OWNER_ID or 0)
DEV_USERS = _int_ids(getattr(Config, "DEV_USERS", []))
SUDO_USERS = _int_ids(getattr(Config, "SUDO_USERS", []))
WHITELIST_USERS = _int_ids(getattr(Config, "WHITELIST_USERS", []))
DEV = DEV_USERS

_STAFF_DB_LOADED = False


class _StaffView:
    """__contains__(user_id) -> bool. mode 'dev' includes DEV_USERS+OWNER. mode 'sudo' includes SUDO_USERS+DEV_USERS+OWNER."""

    def __init__(self, mode: str) -> None:
        self.mode = mode

    def __contains__(self, user_id) -> bool:
        self._load_extra_devs()
        try:
            uid = int(user_id)
        except (TypeError, ValueError):
            return False
        found = set()
        for entry in self._pool():
            try:
                found.add(int(entry))
            except (TypeError, ValueError):
                continue
        return uid in found

    def _pool(self):
        if self.mode == "dev":
            return list(DEV_USERS) + [OWNER_ID]
        if self.mode == "sudo":
            return list(SUDO_USERS) + list(DEV_USERS) + [OWNER_ID]
        return list(SUDO_USERS) + list(DEV_USERS) + list(WHITELIST_USERS) + [OWNER_ID]

    def _load_extra_devs(self) -> None:
        global _STAFF_DB_LOADED
        if _STAFF_DB_LOADED:
            return
        _STAFF_DB_LOADED = True
        try:
            from Powers.database.staff_db import list_dev_ids

            existing = set()
            for entry in DEV_USERS:
                try:
                    existing.add(int(entry))
                except (TypeError, ValueError):
                    continue
            for dev_id in list_dev_ids():
                try:
                    parsed = int(dev_id)
                except (TypeError, ValueError):
                    continue
                if parsed not in existing:
                    DEV_USERS.append(parsed)
                    existing.add(parsed)
        except (Exception, SystemExit):
            LOGGER.error("Failed to load persisted developers; using the env list")


DEV_LEVEL = _StaffView("dev")
SUDO_LEVEL = _StaffView("sudo")
# Live view so /adddev is honored by ban, mute, flood, and warn checks.
SUPPORT_STAFF = _StaffView("staff")

# Plugins, DB and Workers
DB_URI = Config.DB_URI
DB_NAME = Config.DB_NAME
NO_LOAD = Config.NO_LOAD
WORKERS = Config.WORKERS
BDB_URI = Config.BDB_URI

# Prefixes

HELP_COMMANDS = {}  # For help menu
UPTIME = time()  # Check bot uptime


async def load_cmds(all_plugins):
    """Loads all the plugins in bot."""
    for single in all_plugins:
        # If plugin in NO_LOAD, skip the plugin
        if single.lower() in [i.lower() for i in Config.NO_LOAD]:
            LOGGER.warning(f"Not loading '{single}' s it's added in NO_LOAD list")
            continue

        imported_module = imp_mod(f"Powers.plugins.{single}")
        if not hasattr(imported_module, "__PLUGIN__"):
            continue

        plugin_name = imported_module.__PLUGIN__.lower()
        plugin_dict_name = f"plugins.{plugin_name}"
        plugin_help = imported_module.__HELP__

        if plugin_dict_name in HELP_COMMANDS:
            raise Exception(
                (
                    "Can't have two plugins with the same name! Please change one\n"
                    f"Error while importing '{imported_module.__name__}'"
                ),
            )

        HELP_COMMANDS[plugin_dict_name] = {
            "buttons": [],
            "disablable": [],
            "alt_cmds": [],
            "help_msg": plugin_help,
        }

        if hasattr(imported_module, "__buttons__"):
            HELP_COMMANDS[plugin_dict_name]["buttons"] = imported_module.__buttons__
        if hasattr(imported_module, "_DISABLE_CMDS_"):
            HELP_COMMANDS[plugin_dict_name][
                "disablable"
            ] = imported_module._DISABLE_CMDS_
        if hasattr(imported_module, "__alt_name__"):
            HELP_COMMANDS[plugin_dict_name]["alt_cmds"] = imported_module.__alt_name__

        # Add the plugin name to cmd list
        (HELP_COMMANDS[plugin_dict_name]["alt_cmds"]).append(plugin_name)
    if NO_LOAD:
        LOGGER.warning(f"Not loading Plugins - {NO_LOAD}")

    return (
        ", ".join((i.split(".")[1]).capitalize() for i in list(HELP_COMMANDS.keys()))
        + "\n"
    )
