from pyrogram import filters
from pyrogram.errors import ChatAdminRequired, RPCError
from pyrogram.types import Message

from Powers import LOGGER
from Powers.bot_class import Gojo
from Powers.database.federation_db import FederationDB
from Powers.utils.custom_filters import command, restrict_filter
from Powers.utils.extract_user import extract_user
from Powers.utils.federation import can_manage_fed, normalize_fed_name, valid_fed_name


db = FederationDB()


def _fed_arg(parts):
    return parts[1].strip() if len(parts) > 1 else ""


async def _get_fed(identifier):
    if not identifier:
        return None
    fed = db.get(identifier)
    if fed:
        return fed
    return db.get_by_name(normalize_fed_name(identifier))


async def _fed_admin(fed, user_id):
    return can_manage_fed(user_id, fed["owner"], set(fed.get("admins", [])))


@Gojo.on_message(command("newfed") & restrict_filter)
async def new_fed(_, m: Message):
    name = m.text.split(None, 1)[1].strip() if len(m.text.split(None, 1)) > 1 else ""
    name = normalize_fed_name(name)
    if not valid_fed_name(name):
        await m.reply_text("Usage: <code>/newfed my federation</code>\nName: 2-64 chars, letters/numbers/spaces/-/_ only.")
        return
    if db.get_by_name(name):
        await m.reply_text("A federation with this name already exists.")
        return
    fed_id = db.create(name, m.from_user.id)
    db.add_chat(fed_id, m.chat.id)
    await m.reply_text(f"✅ Federation created.\n<b>ID:</b> <code>{fed_id}</code>\n<b>Name:</b> {name}\nThis chat has been joined automatically.")


@Gojo.on_message(command("joinfed") & restrict_filter)
async def join_fed(_, m: Message):
    fed = await _get_fed(_fed_arg(m.text.split()))
    if not fed:
        await m.reply_text("Federation not found.")
        return
    if m.chat.id in fed.get("chats", []):
        await m.reply_text("This chat is already in that federation.")
        return
    db.add_chat(fed["_id"], m.chat.id)
    await m.reply_text(f"✅ Joined federation <b>{fed['name']}</b>.\nID: <code>{fed['_id']}</code>")


@Gojo.on_message(command("leavefed") & restrict_filter)
async def leave_fed(_, m: Message):
    fed = await _get_fed(_fed_arg(m.text.split()))
    if not fed:
        await m.reply_text("Federation not found.")
        return
    db.remove_chat(fed["_id"], m.chat.id)
    await m.reply_text(f"✅ This chat left federation <b>{fed['name']}</b>.")


@Gojo.on_message(command("chatfed") & restrict_filter)
async def chat_fed(_, m: Message):
    feds = list(db.collection.find({"chats": m.chat.id}))
    if not feds:
        await m.reply_text("This chat is not part of any federation.")
        return
    lines = ["<b>Federations for this chat:</b>"]
    for fed in feds:
        lines.append(f"• {fed['name']} — <code>{fed['_id']}</code>")
    await m.reply_text("\n".join(lines))


@Gojo.on_message(command("fedinfo") & restrict_filter)
async def fed_info(_, m: Message):
    fed = await _get_fed(_fed_arg(m.text.split()))
    if not fed:
        await m.reply_text("Federation not found.")
        return
    await m.reply_text(
        f"<b>Federation:</b> {fed['name']}\n"
        f"<b>ID:</b> <code>{fed['_id']}</code>\n"
        f"<b>Owner:</b> <code>{fed['owner']}</code>\n"
        f"<b>Admins:</b> {len(fed.get('admins', []))}\n"
        f"<b>Chats:</b> {len(fed.get('chats', []))}\n"
        f"<b>Banned users:</b> {len(fed.get('bans', {}))}"
    )


@Gojo.on_message(command("delfed") & restrict_filter)
async def delete_fed(_, m: Message):
    fed = await _get_fed(_fed_arg(m.text.split()))
    if not fed:
        await m.reply_text("Federation not found.")
        return
    if m.from_user.id != fed["owner"]:
        await m.reply_text("Only the federation owner can delete it.")
        return
    db.delete(fed["_id"])
    await m.reply_text(f"🗑 Federation <b>{fed['name']}</b> deleted.")


@Gojo.on_message(command("fedadmin") & restrict_filter)
async def fed_admin(_, m: Message):
    parts = m.text.split(None, 3)
    if len(parts) < 4 or parts[1].lower() not in ("add", "remove"):
        await m.reply_text("Usage: <code>/fedadmin add &lt;fed_id&gt; &lt;user_id&gt;</code>")
        return
    action, fed_id, user_raw = parts[1].lower(), parts[2], parts[3]
    fed = await _get_fed(fed_id)
    if not fed:
        await m.reply_text("Federation not found.")
        return
    if m.from_user.id != fed["owner"]:
        await m.reply_text("Only the federation owner can manage federation admins.")
        return
    try:
        user_id = int(user_raw.lstrip("@"))
    except ValueError:
        await m.reply_text("Use a numeric user ID for federation admin management.")
        return
    if action == "add":
        db.add_admin(fed["_id"], user_id)
        await m.reply_text(f"✅ <code>{user_id}</code> added as federation admin.")
    else:
        db.remove_admin(fed["_id"], user_id)
        await m.reply_text(f"✅ <code>{user_id}</code> removed from federation admins.")


@Gojo.on_message(command("fedban") & restrict_filter)
async def fed_ban(c: Gojo, m: Message):
    parts = m.text.split(None, 3)
    if len(parts) < 3:
        await m.reply_text("Usage: <code>/fedban &lt;fed_id&gt; &lt;user_id/reply&gt; &lt;reason&gt;</code>")
        return
    fed = await _get_fed(parts[1])
    if not fed:
        await m.reply_text("Federation not found.")
        return
    if not await _fed_admin(fed, m.from_user.id):
        await m.reply_text("You are not a federation admin.")
        return
    try:
        if m.reply_to_message:
            user_id, first_name, _ = await extract_user(c, m.reply_to_message)
            reason = m.text.split(None, 2)[2].strip() if len(parts) >= 3 else "No reason provided"
        else:
            if len(parts) < 4 or not parts[3].strip():
                await m.reply_text("Please provide a ban reason.")
                return
            user_id = int(parts[2].lstrip("@"))
            first_name = str(user_id)
            reason = parts[3].strip()
    except Exception:
        await m.reply_text("Could not resolve the target user.")
        return
    if user_id == m.from_user.id:
        await m.reply_text("You cannot federation-ban yourself.")
        return
    db.ban(fed["_id"], user_id, reason, m.from_user.id)
    banned = 0
    for chat_id in fed.get("chats", []):
        try:
            await c.ban_chat_member(chat_id, user_id)
            banned += 1
        except (ChatAdminRequired, RPCError):
            continue
    LOGGER.info(f"{m.from_user.id} fedbanned {user_id} in {fed['_id']}")
    await m.reply_text(f"🚫 <b>{first_name}</b> federation-banned.\nReason: <code>{reason}</code>\nApplied in {banned}/{len(fed.get('chats', []))} chats.")


@Gojo.on_message(command("unfedban") & restrict_filter)
async def fed_unban(_, m: Message):
    parts = m.text.split()
    if len(parts) < 3:
        await m.reply_text("Usage: <code>/unfedban &lt;fed_id&gt; &lt;user_id&gt;</code>")
        return
    fed = await _get_fed(parts[1])
    if not fed:
        await m.reply_text("Federation not found.")
        return
    if not await _fed_admin(fed, m.from_user.id):
        await m.reply_text("You are not a federation admin.")
        return
    try: user_id = int(parts[2].lstrip("@"))
    except ValueError:
        await m.reply_text("Use a numeric user ID.")
        return
    db.unban(fed["_id"], user_id)
    unbanned = 0
    for chat_id in fed.get("chats", []):
        try:
            await _.unban_chat_member(chat_id, user_id)
            unbanned += 1
        except (ChatAdminRequired, RPCError):
            continue
    await m.reply_text(
        f"✅ <code>{user_id}</code> removed from federation ban list.\n"
        f"Unbanned in {unbanned}/{len(fed.get('chats', []))} chats."
    )


@Gojo.on_message(command("fedbanlist") & restrict_filter)
async def fed_ban_list(_, m: Message):
    fed = await _get_fed(_fed_arg(m.text.split()))
    if not fed:
        await m.reply_text("Federation not found.")
        return
    if not await _fed_admin(fed, m.from_user.id):
        await m.reply_text("You are not a federation admin.")
        return
    bans = fed.get("bans", {})
    if not bans:
        await m.reply_text("Federation ban list is empty.")
        return
    lines = [f"<b>Fed ban list — {fed['name']}</b>"]
    for user_id, data in bans.items():
        lines.append(f"• <code>{user_id}</code> — {data.get('reason', 'No reason')}")
    await m.reply_text("\n".join(lines))


@Gojo.on_message(filters.new_chat_members & filters.group, 17)
async def enforce_fed_bans(c: Gojo, m: Message):
    feds = [f for f in db.find_all() if m.chat.id in f.get("chats", [])]
    if not feds:
        return
    for member in m.new_chat_members:
        for fed in feds:
            if str(member.id) not in fed.get("bans", {}) and member.id not in fed.get("bans", {}):
                continue
            try:
                await c.ban_chat_member(m.chat.id, member.id)
                LOGGER.info(f"Federation {fed['_id']} blocked {member.id} in {m.chat.id}")
            except (ChatAdminRequired, RPCError):
                pass


__PLUGIN__ = "federation"
__alt_name__ = ["newfed", "delfed", "joinfed", "leavefed", "chatfed", "fedinfo", "fedadmin", "fedban", "unfedban", "fedbanlist"]
__HELP__ = """
**Federation**

Create a network of groups sharing one federation ban list.

• /newfed <name>
• /joinfed <fed_id>
• /leavefed <fed_id>
• /chatfed
• /fedinfo <fed_id>
• /delfed <fed_id>
• /fedadmin add <fed_id> <user_id>
• /fedadmin remove <fed_id> <user_id>
• /fedban <fed_id> <user_id> <reason>
• /unfedban <fed_id> <user_id>
• /fedbanlist <fed_id>
"""
