from pyrogram.enums import ChatMemberStatus as CMS, ChatType
from pyrogram.errors import UserNotParticipant

from Powers.utils.caching import ADMIN_CACHE, admin_cache_reload


PERMISSION_ATTRIBUTES = {
    "restrict": "can_restrict_members",
    "promote": "can_promote_members",
    "change_info": "can_change_info",
    "pin": "can_pin_messages",
}


async def get_member(message, user_id=None):
    """Return a chat member, handling PM and anonymous-admin edge cases."""
    chat = getattr(message, "chat", None)
    if chat is None:
        return None

    user_id = user_id or getattr(getattr(message, "from_user", None), "id", None)
    if user_id is None:
        return None

    try:
        return await chat.get_member(user_id)
    except (UserNotParticipant, ValueError):
        return None


async def is_admin(message):
    sender_chat = getattr(message, "sender_chat", None)
    chat = getattr(message, "chat", None)
    if (
        sender_chat is not None
        and chat is not None
        and sender_chat.id == chat.id
    ):
        return True

    member = await get_member(message)
    return bool(member and member.status in {CMS.OWNER, CMS.ADMINISTRATOR})


async def is_owner(message):
    member = await get_member(message)
    return bool(member and member.status == CMS.OWNER)


async def has_permission(message, permission, bot_id=None):
    """Central, reply-free permission check used by group and PM command layers."""
    if permission == "admin":
        return await is_admin(message)

    if permission == "owner":
        return await is_owner(message)

    if permission == "bot_admin":
        chat = getattr(message, "chat", None)
        if chat is None or chat.type not in {ChatType.SUPERGROUP, ChatType.GROUP}:
            return False
        if bot_id is None:
            return False
        member = await get_member(message, bot_id)
        return bool(member and member.status in {CMS.OWNER, CMS.ADMINISTRATOR})

    attribute = PERMISSION_ATTRIBUTES.get(permission)
    if attribute is None:
        return False

    member = await get_member(message)
    if not member or member.status not in {CMS.OWNER, CMS.ADMINISTRATOR}:
        return False

    return bool(getattr(member.privileges, attribute, False))
