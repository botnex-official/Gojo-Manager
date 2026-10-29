import asyncio
import secrets

from pyrogram import filters
from pyrogram.enums import ChatMemberStatus as CMS
from pyrogram.errors import RPCError
from pyrogram.types import CallbackQuery, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup, Message

from Powers import DEV_USERS
from Powers.bot_class import Gojo
from Powers.database.captcha_db import Captcha
from Powers.utils.custom_filters import admin_filter, bot_admin_filter, command

PENDING = {}
TIMEOUT_TASKS = {}


def _snapshot(permissions):
    if not permissions:
        return None
    fields = (
        "can_send_messages", "can_send_audios", "can_send_documents",
        "can_send_photos", "can_send_videos", "can_send_video_notes",
        "can_send_voice_notes", "can_send_polls", "can_add_web_page_previews",
        "can_change_info", "can_invite_users", "can_pin_messages", "can_manage_topics",
    )
    return {field: getattr(permissions, field, None) for field in fields}


def _permissions(snapshot):
    if not snapshot:
        return ChatPermissions(can_send_messages=True)
    return ChatPermissions(**{k: v for k, v in snapshot.items() if v is not None})


async def _finish(c, key, success, reason=""):
    data = PENDING.pop(key, None)
    task = TIMEOUT_TASKS.pop(key, None)
    if task and task is not asyncio.current_task():
        task.cancel()
    if not data:
        return
    try:
        if success:
            await c.restrict_chat_member(key[0], key[1], _permissions(data["permissions"]))
            await c.send_message(key[0], f"✅ {data['name']} verified. Welcome!")
        else:
            await c.ban_chat_member(key[0], key[1])
            if data["action"] == "kick":
                try:
                    await c.unban_chat_member(key[0], key[1])
                except RPCError:
                    pass
            await c.send_message(key[0], f"❌ {data['name']} failed CAPTCHA verification{reason}.")
        try:
            await c.delete_messages(key[0], data["message_id"])
        except RPCError:
            pass
    except RPCError:
        pass


async def _expire(c, key, seconds):
    try:
        await asyncio.sleep(seconds)
        if key in PENDING:
            await _finish(c, key, False, " (timeout)")
    except asyncio.CancelledError:
        pass


@Gojo.on_message(command("captcha") & admin_filter & bot_admin_filter)
async def captcha_settings(c: Gojo, m: Message):
    db = Captcha(m.chat.id)
    args = m.command[1:]
    if not args:
        s = db.get_settings()
        await m.reply_text(
            f"CAPTCHA settings:\n• Enabled: {s['enabled']}\n• Timeout: {s['timeout']}s\n"
            f"• Max attempts: {s['max_attempts']}\n• Failure action: {s['action']}"
        )
        return
    action = args[0].lower()
    if action in {"on", "off"}:
        db.set_enabled(action == "on")
        await m.reply_text(f"CAPTCHA {'enabled' if action == 'on' else 'disabled'}.")
    elif action == "status":
        s = db.get_settings()
        await m.reply_text(
            f"CAPTCHA: {'ON' if s['enabled'] else 'OFF'} | timeout={s['timeout']}s | "
            f"attempts={s['max_attempts']} | action={s['action']}"
        )
    else:
        await m.reply_text("Usage: /captcha on|off|status")


@Gojo.on_message(command("captchatime") & admin_filter & bot_admin_filter)
async def captcha_time(_, m: Message):
    db = Captcha(m.chat.id)
    if len(m.command) < 2:
        await m.reply_text(f"Current timeout: {db.get_settings()['timeout']}s")
        return
    try:
        value = int(m.command[1])
    except ValueError:
        await m.reply_text("Use seconds, e.g. /captchatime 120")
        return
    if not 30 <= value <= 900:
        await m.reply_text("Timeout must be between 30 and 900 seconds.")
        return
    db.set_timeout(value)
    await m.reply_text(f"CAPTCHA timeout set to {value}s.")


@Gojo.on_message(command("captchamaxattempts") & admin_filter & bot_admin_filter)
async def captcha_attempts(_, m: Message):
    db = Captcha(m.chat.id)
    if len(m.command) < 2:
        await m.reply_text(f"Current attempts: {db.get_settings()['max_attempts']}")
        return
    try:
        value = int(m.command[1])
    except ValueError:
        await m.reply_text("Use a number, e.g. /captchamaxattempts 3")
        return
    if not 1 <= value <= 10:
        await m.reply_text("Attempts must be between 1 and 10.")
        return
    db.set_max_attempts(value)
    await m.reply_text(f"Maximum CAPTCHA attempts set to {value}.")


@Gojo.on_message(command("captchaaction") & admin_filter & bot_admin_filter)
async def captcha_action(_, m: Message):
    db = Captcha(m.chat.id)
    if len(m.command) < 2:
        await m.reply_text(f"Current action: {db.get_settings()['action']} (kick|ban)")
        return
    action = m.command[1].lower()
    if action not in {"kick", "ban"}:
        await m.reply_text("Action must be kick or ban.")
        return
    db.set_action(action)
    await m.reply_text(f"CAPTCHA failure action set to {action}.")


@Gojo.on_chat_member_updated(filters.group, group=68)
async def captcha_join(c: Gojo, member):
    if not member.new_chat_member or member.old_chat_member:
        return
    user = member.new_chat_member.user
    if user.is_bot or user.id in DEV_USERS or user.id == c.me.id:
        return
    settings = Captcha(member.chat.id).get_settings()
    if not settings["enabled"]:
        return
    try:
        current = await member.chat.get_member(user.id)
        if current.status in {CMS.ADMINISTRATOR, CMS.OWNER}:
            return
        permissions = _snapshot(member.chat.permissions)
        await c.restrict_chat_member(
            member.chat.id, user.id, ChatPermissions(can_send_messages=False)
        )
    except RPCError:
        return

    numbers = [1, 2, 3, 4]
    correct = secrets.choice(numbers)
    token = secrets.token_hex(6)
    key = (member.chat.id, user.id)
    PENDING[key] = {
        "token": token, "correct": correct, "attempts": 0,
        "max_attempts": settings["max_attempts"], "permissions": permissions,
        "action": settings["action"], "name": user.first_name,
    }
    buttons = [[InlineKeyboardButton(
        str(n), callback_data=f"captcha:{member.chat.id}:{user.id}:{token}:{n}"
    ) for n in numbers]]
    try:
        msg = await c.send_message(
            member.chat.id,
            f"🛡️ {user.mention}, verify that you're human by pressing the correct button below.\n\n"
            f"You have {settings['timeout']} seconds.",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        PENDING[key]["message_id"] = msg.id
        TIMEOUT_TASKS[key] = asyncio.create_task(
            _expire(c, key, settings["timeout"])
        )
    except RPCError:
        PENDING.pop(key, None)


@Gojo.on_callback_query(filters.regex(r"^captcha:"))
async def captcha_callback(c: Gojo, q: CallbackQuery):
    try:
        _, chat_id, user_id, token, selected = q.data.split(":", 4)
        chat_id, user_id, selected = int(chat_id), int(user_id), int(selected)
    except (ValueError, AttributeError):
        await q.answer("Invalid CAPTCHA.", show_alert=True)
        return

    if q.from_user.id != user_id:
        await q.answer("This CAPTCHA is not for you.", show_alert=True)
        return

    key = (chat_id, user_id)
    data = PENDING.get(key)
    if not data or data.get("token") != token:
        await q.answer("This CAPTCHA has expired.", show_alert=True)
        return

    if selected == data["correct"]:
        await q.answer("Verified!")
        await _finish(c, key, True)
        return

    data["attempts"] += 1
    remaining = data["max_attempts"] - data["attempts"]
    if remaining <= 0:
        await q.answer("Maximum attempts reached.", show_alert=True)
        await _finish(c, key, False, " (too many wrong attempts)")
    else:
        await q.answer(f"Wrong button. {remaining} attempts left.", show_alert=True)


__PLUGIN__ = "captcha"
__alt_name__ = ["captcha", "captchatime", "captchamaxattempts", "captchaaction"]

__HELP__ = """
**CAPTCHA Verification**

Restricts new members until they pass a button CAPTCHA.

**Admin Commands:**
• /captcha on|off|status
• /captchatime <seconds>
• /captchamaxattempts <number>
• /captchaaction kick|ban

**Default:** disabled, 120s timeout, 3 attempts, kick on failure.
"""
