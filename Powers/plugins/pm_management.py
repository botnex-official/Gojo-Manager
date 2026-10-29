"""PM-based group management bridge.

Only this module registers the PM bridge handler. The implementation in
Powers.utils.pm_manager is deliberately a plain async function so it cannot
be registered a second time by importing the utility module.
"""

import re

from pyrogram import filters

from Powers.bot_class import Gojo
from Powers.utils.pm_manager import pm_management_router as _pm_management_router


PM_COMMAND_FILTER = filters.private & filters.text & filters.regex(
    re.compile(r"^[/!$][A-Za-z0-9_]+(?:@[A-Za-z0-9_]+)?(?:\s+.*)?$", re.S)
)


@Gojo.on_message(PM_COMMAND_FILTER, group=-1)
async def pm_management_router(client, message):
    await _pm_management_router(client, message)


__PLUGIN__ = "pm_management"
__HELP__ = """
**Pm Management**

Manage a group you admin directly from my PM, without sending commands in the group itself.
Only one group can be connected to your PM at a time.

• /connect
    Use this in a group where you are an owner/admin, then tap **Connect me to PM** and press Start in my PM to link that group.

• /pmstatus
    Show which group is currently connected to your PM and your role in it.

• /disconnect
    Remove the current PM connection.

• /connections
    List your current PM connection (the connected group and your role).

• Group commands in PM
    Send any supported group-admin command here — for example /settings, /notes or /rules — and it will be applied to the connected group. Bot-global and dev commands are not available through PM.
"""
