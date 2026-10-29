"""Convert Rose (@MissRose_bot) settings exports into Gojo operations.

This module is deliberately separate from ``Powers/utils/settings_export.py``:
Gojo's own ``/exportsettings`` + ``/importsettings`` format is untouched.
A Rose export is a foreign format — a JSON document shaped
``{"bot_id": ..., "version": 2, "data": {...}}`` — and this converter turns
each Rose module into an explicit list of ``(target, payload)`` operations
that ``Powers/plugins/rose_import.py`` applies through Gojo's real database
classes. Anything Rose has that Gojo does not is reported as *skipped* with
a reason instead of being silently dropped or guessed at.
"""

from Powers.utils.msg_types import Types

ROSE_EXPORT_VERSION = 2

MEDIA_FILE_ID_WARNING = (
    "Some entries are media that was saved in Rose. Telegram file IDs are "
    "bot-scoped, so file IDs that belonged to Rose may not send from Gojo."
)


class RoseImportError(ValueError):
    """Raised when a document is not a supported Rose settings export."""


def parse_rose_export(document):
    """Validate the Rose export envelope and return its ``data`` dict."""
    if not isinstance(document, dict):
        raise RoseImportError(
            "This is not a Rose settings export (expected a JSON object).",
        )
    version = document.get("version")
    if version != ROSE_EXPORT_VERSION:
        raise RoseImportError(
            f"Unsupported Rose export version: {version!r} "
            f"(expected {ROSE_EXPORT_VERSION}).",
        )
    data = document.get("data")
    if not isinstance(data, dict):
        raise RoseImportError(
            "This is not a Rose settings export (the 'data' section is missing).",
        )
    return data


# ---------------------------------------------------------------------------
# Rose content (filters / notes / welcome / goodbye) type codes.
#
# Rose stores saved content with a numeric type code. Code 0 is text —
# confirmed against a genuine Rose export, in which every text entry
# carries type 0 and an empty data_id. Codes 1 and 2 are verified
# against the real ALL MOVIES 3 Rose export (2026-10-24): all 6
# type-1 entries carry a CAACAg... data_id (Telegram's sticker file-id
# prefix) and all 5 type-2 entries carry an AgACAg... data_id
# (Telegram's photo file-id prefix), with no exceptions. Any other
# code is still NOT guessed here: a media entry whose code is missing
# from this table is reported as skipped. Add further codes only once
# they are verified against a real Rose export that contains media.
# ---------------------------------------------------------------------------
ROSE_CONTENT_TYPE_MAP = {
    0: Types.TEXT,
    1: Types.STICKER,
    2: Types.PHOTO,
}


class _Conversion:
    """Accumulates operations, skips and warnings while converting."""

    def __init__(self):
        self.operations = []
        self.skipped = []
        self.warnings = []
        self.media_seen = False

    def op(self, target, payload):
        self.operations.append((target, payload))

    def skip(self, item, reason):
        self.skipped.append((item, reason))

    def warn(self, message):
        if message not in self.warnings:
            self.warnings.append(message)

    def result(self):
        if self.media_seen:
            self.warn(MEDIA_FILE_ID_WARNING)
        return {
            "operations": self.operations,
            "skipped": self.skipped,
            "warnings": self.warnings,
        }


def _as_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _convert_content_entry(entry, kind, target, result, type_map):
    """Convert one Rose saved-content entry (filter / note / greeting).

    ``kind`` is the human label used in skip reasons; ``target`` is the
    operation target to emit. Returns True when an operation was emitted.
    """
    if not isinstance(entry, dict):
        result.skip(kind, "an entry was not readable and was not imported")
        return False
    name = str(entry.get("name") or "").strip().lower()
    text = entry.get("text") or ""
    data_id = entry.get("data_id") or ""
    rose_type = entry.get("type", 0)
    if not name and target in ("filter", "note"):
        result.skip(kind, "an entry had no name and was not imported")
        return False
    msgtype = type_map.get(rose_type) if isinstance(rose_type, int) else None
    if msgtype is None:
        result.media_seen = True
        label = f"'{name}'" if name else "a media entry"
        result.skip(
            kind,
            f"{label} uses Rose media type code {rose_type}, which has no "
            "verified Gojo equivalent — not imported",
        )
        return False
    if int(msgtype) == int(Types.TEXT):
        if target in ("welcome_text", "goodbye_text"):
            if not text:
                return False
            result.op(target, {"text": text, "msgtype": int(Types.TEXT), "media": None})
        else:
            result.op(
                target,
                {"name": name, "text": text, "msgtype": int(Types.TEXT), "fileid": ""},
            )
        return True
    # A verified media type: keep Rose's file id (bot-scoped — see warning).
    result.media_seen = True
    if target in ("welcome_text", "goodbye_text"):
        result.op(
            target,
            {"text": text, "msgtype": int(msgtype), "media": data_id or None},
        )
    else:
        result.op(
            target,
            {"name": name, "text": text, "msgtype": int(msgtype), "fileid": data_id},
        )
    return True


def _convert_filters(section, result, type_map):
    entries = (section or {}).get("filters")
    if isinstance(entries, list):
        for entry in entries:
            _convert_content_entry(entry, "filters", "filter", result, type_map)


def _convert_notes(section, result, type_map):
    entries = (section or {}).get("notes")
    if isinstance(entries, list):
        for entry in entries:
            _convert_content_entry(entry, "notes", "note", result, type_map)
    if isinstance(section, dict) and "private_notes" in section:
        result.op("private_notes", {"enabled": bool(section["private_notes"])})


def _convert_rules(section, result):
    content = (section or {}).get("content") or ""
    if content:
        result.op(
            "rules",
            {
                "content": content,
                # Gojo's privrules = "send the rules to the user's PM";
                # Rose's send_to_chat is the exact inverse.
                "private": not bool((section or {}).get("send_to_chat", False)),
            },
        )
    if (section or {}).get("button_name"):
        result.skip("rules", "Rose's custom rules button name has no Gojo equivalent")


def _convert_greetings(section, result, type_map):
    section = section or {}
    if "should_welcome" in section:
        result.op("welcome_status", {"enabled": bool(section["should_welcome"])})
    if "should_goodbye" in section:
        result.op("goodbye_status", {"enabled": bool(section["should_goodbye"])})
    _convert_content_entry(section.get("welcome") or {}, "greetings", "welcome_text", result, type_map)
    _convert_content_entry(section.get("goodbye") or {}, "greetings", "goodbye_text", result, type_map)
    if "should_clean" in section:
        # Rose's should_clean deletes the previous welcome message when a
        # new one is sent — exactly Gojo's "clean welcome" toggle.
        result.op("clean_welcome", {"enabled": bool(section["should_clean"])})
    rose_only = (
        ("captcha_rules", "greeting captcha rules"),
        ("should_mute", "muting new members until they pass a check"),
        ("mute_mode", "the new-member mute mode"),
        ("mute_for", "the new-member mute duration"),
        ("mute_text", "the new-member mute text"),
        ("should_kick", "kicking members who do not pass the check"),
        ("kick_after", "the new-member check timeout"),
    )
    for key, label in rose_only:
        if key in section:
            result.skip(
                "greetings",
                f"Rose's {label} has no equivalent in Gojo's greetings",
            )


def _convert_clean_service(section, result):
    service_types = (section or {}).get("service_types") or {}
    values = [
        bool(value.get("clean"))
        for value in service_types.values()
        if isinstance(value, dict)
    ]
    if not values:
        return
    if isinstance(service_types.get("all"), dict):
        enabled = bool(service_types["all"].get("clean"))
    else:
        enabled = any(values)
    result.op("clean_service", {"enabled": enabled})
    if len(set(values)) > 1:
        result.warn(
            "Rose cleans each service message type separately; Gojo has a "
            "single clean-service switch, so the per-type detail was collapsed.",
        )


# Rose lock name -> (operation target, value). Granular names are Gojo's
# own (Powers/utils/lock_control.py), message flags are MessageLocks
# fields, and "polls" is a Telegram chat permission like Gojo's /lock.
ROSE_LOCK_MAP = {
    "photo": ("lock_granular", "photo"),
    "video": ("lock_granular", "video"),
    "document": ("lock_granular", "document"),
    "audio": ("lock_granular", "audio"),
    "voice": ("lock_granular", "voice"),
    "videonote": ("lock_granular", "video_note"),
    "sticker": ("lock_granular", "sticker"),
    "gif": ("lock_granular", "animation"),
    "contact": ("lock_granular", "contact"),
    "location": ("lock_granular", "location"),
    "url": ("lock_message_flag", "links"),
    "forward": ("lock_message_flag", "forward_all"),
    "forwarduser": ("lock_message_flag", "forward_users"),
    "forwardchannel": ("lock_message_flag", "forward_channels"),
    "anonchannel": ("lock_message_flag", "anon_channel"),
    "poll": ("lock_permission", "polls"),
}

_SCRIPT_LOCKS = {"cashtag", "cjk", "cyrillic", "email", "phone", "rtl", "zalgo"}
_LOCK_SKIP_REASONS = {
    "text": "Gojo has no text-only lock (its message lock blocks every message type)",
    "inline": "Gojo's inline lock shares the 'other messages' chat permission "
    "with stickers and games, so it cannot be applied on its own",
    "game": "Gojo's games lock shares the 'other messages' chat permission "
    "with stickers and inline bots, so it cannot be applied on its own",
    "forwardbot": "Gojo cannot lock forwards from bots separately",
    "forwardstory": "Gojo has no story-forward lock",
    "stickeranimated": "Gojo has no separate animated-sticker lock "
    "(its sticker lock covers all stickers)",
    "stickerpremium": "Gojo has no separate premium-sticker lock "
    "(its sticker lock covers all stickers)",
    "album": "Gojo has no media-group (album) lock",
    "collage": "Gojo has no media-group (collage) lock",
    "slideshow": "Gojo has no media-group (slideshow) lock",
    "bot": "Gojo has no lock for bots being added to the chat",
}


def _convert_locks(section, result):
    section = section or {}
    locks = section.get("locks") or {}
    lock_all = False
    for name, state in locks.items():
        if not isinstance(state, dict) or not state.get("locked"):
            continue  # Importing only turns locks ON; unlocked stays untouched.
        if name == "all":
            lock_all = True
            continue
        mapped = ROSE_LOCK_MAP.get(name)
        if mapped:
            target, value = mapped
            if target == "lock_permission":
                result.op(target, {"lock_type": value})
            elif target == "lock_message_flag":
                result.op(target, {"field": value})
            else:
                result.op(target, {"lock_type": value})
            continue
        if name in _SCRIPT_LOCKS:
            reason = (
                "Rose script/content-pattern lock — Gojo's watcher has no "
                "text-pattern locks"
            )
        else:
            reason = _LOCK_SKIP_REASONS.get(name, f"Gojo has no '{name}' lock")
        result.skip("locks", f"'{name}': {reason}")
    if lock_all:
        # Applied last, mirroring Gojo's own /lock all: it covers every
        # message flag and permission at once.
        result.op("lock_all", {})
    if section.get("lock_warns"):
        result.skip(
            "locks",
            "Rose's lock warnings (warn users who post locked content) "
            "have no Gojo equivalent",
        )
    if section.get("allowlisted_url"):
        result.skip(
            "locks",
            "Rose's URL allowlist for the url lock has no Gojo equivalent",
        )


ROSE_FLOOD_ACTIONS = {"ban": "ban", "kick": "kick", "mute": "mute"}
# Gojo's own default flood window/action for a fresh setup (flood.py).
GOJO_FLOOD_DEFAULT_WITHIN = 5
GOJO_FLOOD_DEFAULT_ACTION = "mute"


def _convert_antiflood(section, result):
    section = section or {}
    limit = _as_int(section.get("flood_limit"))
    timer = _as_int(section.get("flood_timer"))
    timer_limit = _as_int(section.get("flood_timer_limit"))
    action_raw = str(section.get("action") or "").lower()
    action = ROSE_FLOOD_ACTIONS.get(action_raw)
    if action is None:
        action = GOJO_FLOOD_DEFAULT_ACTION
        if action_raw:
            result.warn(
                f"Rose's flood action '{action_raw}' has no Gojo equivalent; "
                "Gojo's default 'mute' was used.",
            )
    if timer > 0 and timer_limit > 0:
        # Rose's timed mode: N messages within M seconds — the same shape
        # as Gojo's (limit, within).
        result.op(
            "flood_set",
            {"limit": timer_limit, "within": timer, "action": action},
        )
    elif limit > 0:
        result.op(
            "flood_set",
            {
                "limit": limit,
                "within": GOJO_FLOOD_DEFAULT_WITHIN,
                "action": action,
            },
        )
    else:
        result.op("flood_off", {})
    if _as_int(section.get("action_duration")):
        result.skip(
            "antiflood",
            "Rose's flood action duration has no Gojo equivalent — "
            "Gojo's flood actions are not timed",
        )
    if section.get("flood_clear"):
        result.skip(
            "antiflood",
            "Rose's flood_clear flag has no Gojo equivalent",
        )


ROSE_WARN_ACTIONS = {
    "ban": "ban",
    "kick": "kick",
    "mute": "mute",
    "none": "none",
    "tban": "ban",
    "tmute": "mute",
}


def _convert_warns(section, result):
    section = section or {}
    action_raw = str(section.get("action") or "").lower()
    mode = ROSE_WARN_ACTIONS.get(action_raw)
    if mode is None:
        result.skip(
            "warns",
            f"Rose's warn action '{action_raw}' has no Gojo equivalent; "
            "warn settings were not imported",
        )
    else:
        if action_raw.startswith("t"):
            result.warn(
                f"Rose's warn action '{action_raw}' is timed; Gojo's warn "
                "actions are not timed, so the plain action was used and "
                "the duration dropped.",
            )
        result.op(
            "warn_settings",
            {"limit": _as_int(section.get("warn_limit"), 3), "mode": mode},
        )
    if _as_int(section.get("warn_for")):
        result.skip(
            "warns",
            "Rose's warn expiry (warn_for) has no Gojo equivalent — "
            "Gojo warns do not expire",
        )
    if _as_int(section.get("action_duration")):
        result.skip(
            "warns",
            "Rose's warn action duration has no Gojo equivalent",
        )


def _convert_reports(section, result):
    if isinstance(section, dict) and "disable_reports" in section:
        result.op("reports", {"enabled": not bool(section["disable_reports"])})


def _convert_raids(section, result):
    section = section or {}
    auto_limit = _as_int(section.get("raid_mode_auto_limit"))
    fields = {"auto_enabled": auto_limit > 0}
    if auto_limit > 0:
        fields["threshold"] = auto_limit
    duration = _as_int(section.get("raid_mode_duration"))
    if duration > 0:
        # Rose's raid duration is how long raid mode stays active; in
        # Gojo the matching field is how long the lockdown lasts.
        fields["action_time"] = duration
    result.op("antiraid", {"fields": fields})
    if _as_int(section.get("raid_mode_action_duration")):
        result.skip(
            "raids",
            "Rose's raid action duration has no Gojo equivalent — Gojo's "
            "antiraid locks the chat for its action time instead",
        )


def _convert_pins(section, result):
    section = section or {}
    antichannelpin = bool(section.get("antichannelpin"))
    cleanlinked = bool(section.get("cleanlinked"))
    result.op(
        "pins",
        {"antichannelpin": antichannelpin, "cleanlinked": cleanlinked},
    )
    if antichannelpin and cleanlinked:
        result.skip(
            "pins",
            "cleanlinked was not applied: Gojo's pins settings make "
            "antichannelpin and cleanlinked mutually exclusive, and "
            "antichannelpin was applied",
        )


ROSE_BLACKLIST_ACTIONS = {
    "ban": "ban",
    "kick": "kick",
    "mute": "mute",
    "warn": "warn",
    "nothing": "none",
    "none": "none",
    "delete": "none",
}
ROSE_BLACKLIST_TIMED = {"tban": "ban", "tmute": "mute"}


def _convert_blocklists(section, result):
    section = section or {}
    entries = section.get("filters")
    if not isinstance(entries, list) or not entries:
        return  # Settings for an empty blocklist carry nothing to import.
    for entry in entries:
        trigger = None
        if isinstance(entry, str):
            trigger = entry
        elif isinstance(entry, dict):
            trigger = (
                entry.get("trigger") or entry.get("word") or entry.get("name")
            )
        if trigger:
            result.op("blacklist_add", {"trigger": str(trigger)})
        else:
            result.skip(
                "blocklists",
                "a blocklist entry could not be read and was not imported",
            )
    action_raw = str(section.get("action") or "").lower()
    if action_raw in ROSE_BLACKLIST_ACTIONS:
        result.op(
            "blacklist_action",
            {"action": ROSE_BLACKLIST_ACTIONS[action_raw]},
        )
    elif action_raw in ROSE_BLACKLIST_TIMED:
        result.op(
            "blacklist_action",
            {"action": ROSE_BLACKLIST_TIMED[action_raw]},
        )
        result.warn(
            f"Rose's blacklist action '{action_raw}' is timed; Gojo's is "
            "not, so the plain action was used and the duration dropped.",
        )
    elif action_raw:
        result.skip(
            "blocklists",
            f"Rose's blacklist action '{action_raw}' has no Gojo "
            "equivalent; Gojo's current blacklist action was kept",
        )
    reason = section.get("default_reason") or ""
    if reason:
        result.op("blacklist_reason", {"reason": reason})
    if section.get("should_delete") is False:
        result.warn(
            "Rose was set to not delete blocklisted messages; Gojo always "
            "deletes them, so that preference cannot be carried over.",
        )
    if _as_int(section.get("action_duration")):
        result.skip(
            "blocklists",
            "Rose's blacklist action duration has no Gojo equivalent",
        )


def _convert_disabled(section, result):
    section = section or {}
    if "disable_admin" in section:
        result.skip(
            "disabled",
            "Rose's disable_admin flag (whether admins can use disabled "
            "commands) has no Gojo equivalent",
        )
    entries = section.get("disabled")
    if not isinstance(entries, list) or not entries:
        return
    for entry in entries:
        command_name = None
        if isinstance(entry, str):
            command_name = entry
        elif isinstance(entry, dict):
            command_name = entry.get("command") or entry.get("name")
        if command_name:
            result.op(
                "disable_add",
                {"command": str(command_name).lstrip("/").lower()},
            )
        else:
            result.skip(
                "disabled",
                "a disabled-command entry could not be read and was not imported",
            )
    result.op(
        "disable_action",
        {"action": "del" if section.get("should_delete") else "none"},
    )


_MODULE_CONVERTERS = {
    "filters": _convert_filters,
    "notes": _convert_notes,
    "rules": _convert_rules,
    "greetings": _convert_greetings,
    "clean_service": _convert_clean_service,
    "locks": _convert_locks,
    "antiflood": _convert_antiflood,
    "warns": _convert_warns,
    "reports": _convert_reports,
    "raids": _convert_raids,
    "pins": _convert_pins,
    "blocklists": _convert_blocklists,
    "disabled": _convert_disabled,
}

# Rose modules with no Gojo equivalent at all.
_MODULE_SKIPS = {
    "admin": "Rose's admin flags (anonymous admins, legacy admin, admin "
    "error reports) have no Gojo settings equivalent",
    "clean_command": "Gojo has no clean-commands feature (deleting "
    "command messages by category)",
    "translations": "Gojo has no per-chat language setting",
}


def convert_rose_settings(data, type_map=None):
    """Convert a validated Rose ``data`` dict into Gojo operations.

    Returns ``{"operations": [(target, payload), ...],
    "skipped": [(item, reason), ...], "warnings": [str, ...]}``.
    ``type_map`` maps Rose content type codes to Gojo ``Types`` values
    and exists so the mapping can be extended once more Rose codes are
    verified; production callers should leave it as the default.
    """
    if type_map is None:
        type_map = ROSE_CONTENT_TYPE_MAP
    result = _Conversion()
    for key, section in data.items():
        converter = _MODULE_CONVERTERS.get(key)
        if converter is not None:
            if key in ("filters", "notes", "greetings"):
                converter(section, result, type_map)
            else:
                converter(section, result)
        elif key == "translations":
            lang = (section or {}).get("lang") if isinstance(section, dict) else None
            reason = _MODULE_SKIPS[key]
            if lang:
                reason = f"Rose's per-chat language ('{lang}') has no Gojo equivalent"
            result.skip("translations", reason)
        elif key in _MODULE_SKIPS:
            result.skip(key, _MODULE_SKIPS[key])
        else:
            result.skip(key, f"unknown Rose module '{key}' was not imported")
    return result.result()
