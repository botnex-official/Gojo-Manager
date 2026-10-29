"""Central lock policy helpers used by the Gojo lock plugin."""

GRANULAR_LOCK_TYPES = frozenset({
    "photo",
    "video",
    "document",
    "audio",
    "voice",
    "video_note",
    "sticker",
    "animation",
    "contact",
    "location",
})

GRANULAR_LOCK_ALIASES = {
    "gif": "animation",
    "gifs": "animation",
    "voice_note": "voice",
    "voicenote": "voice",
    "videonote": "video_note",
    "video-notes": "video_note",
}


def normalize_lock_type(lock_type):
    """Normalize a lock name and resolve supported aliases."""
    value = str(lock_type or "").strip().lower()
    return GRANULAR_LOCK_ALIASES.get(value, value)


def is_granular_lock(lock_type):
    """Return whether a lock name is a supported message-level lock."""
    return normalize_lock_type(lock_type) in GRANULAR_LOCK_TYPES


def is_locked(lock_type, locked_types):
    """Return whether a normalized/aliased lock is active."""
    return normalize_lock_type(lock_type) in {
        normalize_lock_type(item) for item in (locked_types or ())
    }


def add_lock(locked_types, lock_type):
    """Add a granular lock to a mutable set and report whether it was new."""
    normalized = normalize_lock_type(lock_type)
    if normalized not in GRANULAR_LOCK_TYPES:
        return False
    if normalized in locked_types:
        return False
    locked_types.add(normalized)
    return True


def remove_lock(locked_types, lock_type):
    """Remove a granular lock from a mutable set and report whether it existed."""
    normalized = normalize_lock_type(lock_type)
    if normalized not in locked_types:
        return False
    locked_types.remove(normalized)
    return True
