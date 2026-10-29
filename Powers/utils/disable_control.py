"""Helpers for Gojo's per-chat command disabling policy."""


def should_block_command(command, disabled_commands, is_admin):
    """Return whether a command must be stopped before its plugin handler runs."""
    if is_admin:
        return False
    normalized = str(command).strip().lower()
    disabled = {str(item).strip().lower() for item in (disabled_commands or [])}
    return bool(normalized and normalized in disabled)
