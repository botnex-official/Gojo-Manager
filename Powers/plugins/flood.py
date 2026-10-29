import asyncio
import time
from random import choice
from traceback import format_exc

from pyrogram import filters
from pyrogram.enums import ChatMemberStatus as CMS
from pyrogram.enums import ChatType as CT
from pyrogram.errors import RPCError, UserAdminInvalid
from pyrogram.types import (CallbackQuery, ChatPermissions,
                            InlineKeyboardButton, InlineKeyboardMarkup,
                            Message)

from Powers import LOGGER, SUPPORT_GROUP, SUPPORT_STAFF
from Powers.bot_class import Gojo
from Powers.database.approve_db import Approve
from Powers.database.flood_db import Floods
from Powers.utils.custom_filters import admin_filter, command
from Powers.utils.extras import BAN_GIFS, KICK_GIFS, MUTE_GIFS
from Powers.utils.flood_control import register_hit
from Powers.utils.kbhelpers import ikb
from Powers.vars import Config

on_key = ["on", "start", "enable"]
off_key = ["off", "stop", "disable", "end"]

close_kb =InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton(
                "Close ❌",
                callback_data="f_close"
            )
        ]
    ]
)

action_kb = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton(
                "Mute 🔇",
                callback_data="f_mute"
            ),
            InlineKeyboardButton(
                "Ban 🚷",
                callback_data="f_ban"
            ),
            InlineKeyboardButton(
                "Kick 🦿",
                callback_data="f_kick"
            )
        ],
        [
            InlineKeyboardButton(
                "➡️ Skip",
                callback_data="f_skip"
            )
        ]
    ]
)

within_kb = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton(
                "5",
                callback_data="f_f_5"
            ),
            InlineKeyboardButton(
                "10",
                callback_data="f_f_10"
            ),
            InlineKeyboardButton(
                "15",
                callback_data="f_f_15"
            )
        ],
        [
            InlineKeyboardButton(
                "➡️ Skip",
                callback_data="f_f_skip"
            )
        ]
    ]
)

limit_kb = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton("5", callback_data="f_5"),
            InlineKeyboardButton("10", callback_data="f_10"),
            InlineKeyboardButton("15", callback_data="f_15"),
        ],
        [InlineKeyboardButton("➡️ Skip", callback_data="f_f_f_skip")],
    ]
)


def _flood_status(is_flood):
    """Return persisted flood settings as limit, window, action."""
    return is_flood[0], is_flood[1], is_flood[2]


def _has_restrict_power(member) -> bool:
    """Chat owner, or an administrator whose privileges can restrict members."""
    status = member.status
    if status == CMS.OWNER:
        return True
    if status != CMS.ADMINISTRATOR:
        return False
    privileges = member.privileges
    return privileges is not None and bool(privileges.can_restrict_members)


async def _caller_may_reverse(q: CallbackQuery) -> bool:
    """Support staff, the chat owner, or an admin allowed to restrict."""
    if q.from_user.id in SUPPORT_STAFF:
        return True
    member = await q.message.chat.get_member(q.from_user.id)
    return _has_restrict_power(member)


_FLOOD_HITS = {}
_FLOOD_LOCK = asyncio.Lock()


@Gojo.on_message(command(['floodaction','actionflood']) & admin_filter)
async def flood_action(c: Gojo, m: Message):
    if m.chat.type == CT.PRIVATE:
        await m.reply_text("Use this command in group")
        return
    bot = await c.get_chat_member(m.chat.id, Config.BOT_ID)
    if not _has_restrict_power(bot):
        return await m.reply_text("Give me permission to restrict members first")
    Flood = Floods()
    c_id = m.chat.id
    is_flood = Flood.is_chat(c_id)
    if is_flood:
        saction = is_flood[2]
        await m.reply_text(
            f"Choose a action given bellow to do when flood happens.\n **CURRENT ACTION** is {saction}",
            reply_markup=action_kb
        )
        return
    await m.reply_text("Switch on the flood protection first.")
    return

@Gojo.on_message(command(['isflood', 'flood']) & ~filters.bot)
async def flood_on_off(c: Gojo, m: Message):
    if m.chat.type == CT.PRIVATE:   
      return await m.reply_text("This command is ment to be used in groups.")
    Flood = Floods()
    c_id = m.chat.id
    is_flood = Flood.is_chat(c_id)
    c_id = m.chat.id
    if is_flood:
      saction = is_flood[2]
      slimit = is_flood[0]
      swithin = is_flood[1]
      return await m.reply_text(f"Flood is on for this chat\n**Action**: {saction}\n**Messages**: {slimit} within {swithin} sec")
    return await m.reply_text("Flood protection is off for this chat.")

@Gojo.on_message(command(['setflood']) & ~filters.bot & admin_filter)
async def flood_set(c: Gojo, m: Message):
    if m.chat.type == CT.PRIVATE:
        return await m.reply_text("This command is ment to be used in groups.")
    bot = await c.get_chat_member(m.chat.id, Config.BOT_ID)
    if not _has_restrict_power(bot):
        return await m.reply_text("Give me permission to restrict members first")
    Flood = Floods()
    split = m.text.split(None, 1)
    c_id = m.chat.id
    is_flood = Flood.is_chat(c_id)

    if len(split) == 1:
        c_id = m.chat.id
        if is_flood: 
            saction = is_flood[2]
            slimit = is_flood[0]
            swithin = is_flood[1]   
            return await m.reply_text(f"Flood is on for this chat\n**Action**:{saction}\n**Messages**:{slimit} within {swithin} sec")
        return await m.reply_text("Flood protection is off of this chat.")
    
    if len(split) == 2:
        c_id = m.chat.id
        if split[1].lower() in on_key:
            if is_flood:
                slimit, swithin, saction = _flood_status(is_flood)
                return await m.reply_text(f"Flood is on for this chat\n**Action**:{saction}\n**Messages**:{slimit} within {swithin} sec")
            Flood.save_flood(m.chat.id, 5, 5, 'mute')
            await m.reply_text("Flood protection has been started for this group.")
            return
        if split[1].lower() in off_key:
            x = Flood.rm_flood(c_id)
            if x:
                await m.reply_text("Flood protection has been stopped for this chat")
                return
            await m.reply_text("Failed to stop flood protection")
            return
        if split[1].isdigit():
            limit = int(split[1])
            if not 3 <= limit <= 100:
                await m.reply_text(
                    "Flood limit must be a number between 3 and 100."
                )
                return
            if is_flood:
                _, swithin, saction = _flood_status(is_flood)
            else:
                swithin, saction = 5, "mute"
            Flood.save_flood(c_id, limit, swithin, saction)
            await m.reply_text(
                f"Flood protection is on for this chat\n**Action**:{saction}\n**Messages**:{limit} within {swithin} sec"
            )
            return
    await m.reply_text("**Usage:**\n `/setflood on/off/<limit>`")
    return

@Gojo.on_callback_query(filters.regex("^f_"))
async def callbacks(c: Gojo, q: CallbackQuery):
    data = q.data
    if data == "f_close":
        await q.answer("Closed")
        await q.message.delete()
        return
    c_id = q.message.chat.id
    Flood = Floods()
    is_flood = Flood.is_chat(c_id)
    if is_flood:
        saction = is_flood[2]
        slimit = is_flood[0]
        swithin = is_flood[1]
    user = q.from_user.id
    user_status = (await q.message.chat.get_member(q.from_user.id)).status
    if user in SUPPORT_STAFF or user_status in [CMS.OWNER, CMS.ADMINISTRATOR]:
        if data in ["f_mute", "f_ban", "f_kick", "f_skip"]:
            change = data.split("_")[1]
            if change == "skip":
                await q.answer("Skip", show_alert=True)
                await q.edit_message_text(
                    f"Set the limit of message after the flood protection will be activated\n **CURRENT LIMIT** {slimit} messages",
                    reply_markup=limit_kb
                )
                return
            if change != saction:
                Flood.save_flood(c_id, slimit, swithin, change)
            await q.answer("Updated action", show_alert=True)
            await q.edit_message_text(
                f"Set the limit of message after the flood protection will be activated\n **CURRENT LIMIT** {slimit} messages",
                reply_markup=limit_kb
            )
        elif data in ["f_5", "f_10", "f_15", "f_f_f_skip"]:
            try:
                change = int(data.split("_")[-1])
            except ValueError:
                await q.answer("skip")
                await q.edit_message_text(
                    f"Set the time with the number of message recived treated as flood\n **CUURENT TIME** {swithin}",
                    reply_markup=within_kb
                )
                return
            if not change == slimit:
                Flood.save_flood(c_id, change, swithin, saction)
                await q.answer("Updated limit", show_alert=True)
                await q.edit_message_text(
                    f"Set the time with the number of message recived treated as flood\n **CUURENT TIME** {swithin}",
                    reply_markup=within_kb
                )
                return
            else:
                await q.answer("Updated action", show_alert=True)
                await q.edit_message_text(
                    f"Set the time with the number of message recived treated as flood\n **CUURENT TIME** {swithin}",
                    reply_markup=within_kb
                )
                return
        elif data in ["f_f_5", "f_f_10", "f_f_15", "f_f_skip"]:
            data = data.split("_")[-1]
            try:
                change = int(data)
            except ValueError:
                await q.edit_message_text(
                    "Flood protection setting has been updated",
                    reply_markup=close_kb
                )
                return
            if not change == swithin:
                Flood.save_flood(c_id, slimit, change, saction)
                await q.answer("Updated", show_alert=True)
                await q.edit_message_text(
                    "Flood protection setting has been updated",
                    reply_markup=close_kb
                )
                return
            else:
                await q.answer("Updated action", show_alert=True)
                await q.edit_message_text(
                    f"Set the limit of message after the flood protection will be activated\n **CURRENT LIMIT** {slimit} messages",
                    reply_markup=limit_kb
                )
    else:
        await q.answer(
            "You don't have enough permission to do this!\nStay in your limits!",
            show_alert=True,
            )
        return

@Gojo.on_callback_query(filters.regex("^un_"))
async def reverse_callbacks(c: Gojo, q: CallbackQuery):
    data = q.data.split("_")
    action = data[1]
    user_id = int(q.data.split("=")[1])
    if not q.from_user:
        return q.answer("Looks like you are not an user 👀")
    if action == "ban":
        if not await _caller_may_reverse(q):
            await q.answer(
                "You don't have enough permission to do this!\nStay in your limits!",
                show_alert=True,
            )
            return
        whoo = await c.get_chat(user_id)
        doneto = whoo.first_name if whoo.first_name else whoo.title
        try:
            await q.message.chat.unban_member(user_id)
        except RPCError as e:
            await q.message.edit_text(f"Error: {e}")
            return
        await q.message.edit_text(f"{q.from_user.mention} unbanned {doneto}!")
        return

    if action == "mute":
        if not await _caller_may_reverse(q):
            await q.answer(
                "You don't have enough permission to do this!\nStay in your limits!",
                show_alert=True,
            )
            return
        whoo = await c.get_users(user_id)
        try:
            await q.message.chat.unban_member(user_id)
        except RPCError as e:
            await q.message.edit_text(f"Error: {e}")
            return
        await q.message.edit_text(f"{q.from_user.mention} unmuted {whoo.mention}!")
        return

async def _apply_flood_action(m: Message, action: str, u_id: int):
    """Ban, kick, or mute the flooding user. Stamps are already cleared."""
    if action == "ban":
        try:
            await m.chat.ban_member(u_id)
            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "Unban",
                            callback_data=f"un_ban_={u_id}",
                        ),
                    ],
                ],
            )
            txt = "Don't dare to spam here if I am around!"
            await m.reply_animation(
                animation=str(choice(BAN_GIFS)),
                caption=txt,
                reply_markup=keyboard,
            )
        except UserAdminInvalid:
            await m.reply_text(
                "I can't protect this chat from this user",
            )
        except RPCError as ef:
            await m.reply_text(
                text=f"""Some error occured, report it using `/bug`

                        <b>Error:</b> <code>{ef}</code>"""
            )
            LOGGER.error(ef)
            LOGGER.error(format_exc())
        return

    if action == "kick":
        try:
            await m.chat.ban_member(u_id)
            txt = "Don't dare to spam here if I am around!"
            await m.reply_animation(
                animation=str(choice(KICK_GIFS)),
                caption=txt,
            )
            await m.chat.unban_member(u_id)
        except UserAdminInvalid:
            await m.reply_text(
                "I can't protect this chat from this user",
            )
        except RPCError as ef:
            await m.reply_text(
                text=f"""Some error occured, report it using `/bug`

                        <b>Error:</b> <code>{ef}</code>"""
            )
            LOGGER.error(ef)
            LOGGER.error(format_exc())
        return

    if action == "mute":
        try:
            await m.chat.restrict_member(
                u_id,
                ChatPermissions(),
            )
            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "Unmute",
                            callback_data=f"un_mute_={u_id}",
                        ),
                    ],
                ],
            )
            txt = "Don't dare to spam here if I am around!"
            await m.reply_animation(
                animation=str(choice(MUTE_GIFS)),
                caption=txt,
                reply_markup=keyboard,
            )
        except UserAdminInvalid:
            await m.reply_text(
                "I can't protect this chat from this user",
            )
        except RPCError as ef:
            await m.reply_text(
                text=f"""Some error occured, report it using `/bug`

                        <b>Error:</b> <code>{ef}</code>"""
            )
            LOGGER.error(ef)
            LOGGER.error(format_exc())


@Gojo.on_message(filters.group & ~filters.bot & ~filters.service, group=10)
async def flood_watcher(c: Gojo, m: Message):
    if not m.chat or not m.from_user:
        return

    c_id = m.chat.id
    u_id = m.from_user.id
    is_flood = Floods().is_chat(c_id)
    if not is_flood:
        return

    app_users = Approve(m.chat.id).list_approved()
    if u_id in {i[0] for i in app_users}:
        return

    if u_id in SUPPORT_STAFF:
        return

    try:
        user_status = (await m.chat.get_member(u_id)).status
    except Exception:
        return

    if user_status in [CMS.OWNER, CMS.ADMINISTRATOR]:
        return

    action = is_flood[2]
    limit = int(is_flood[0])
    within = int(is_flood[1])
    key = (c_id, u_id)

    async with _FLOOD_LOCK:
        tripped, new_stamps = register_hit(
            _FLOOD_HITS.get(key, []),
            time.time(),
            limit,
            within,
        )
        if new_stamps:
            _FLOOD_HITS[key] = new_stamps
        else:
            _FLOOD_HITS.pop(key, None)

    if tripped:
        await _apply_flood_action(m, action, u_id)


__PLUGIN__ = "flood"
__alt_name__ = [
  "anit-flood",
  "flood",
  "spam",
  "anti-spam",
]
__HELP__ = """
**Anti Flood**
**User Commands:**
• /flood: to check weather the group is protected from spam or not.

**Admin only:**
• /setflood `on/off`: To activate or deactivate the flood protection
• /setflood `<number>`: Set the flood limit to that many messages (3-100) and switch flood protection on, keeping the current window/action.
• /floodaction: To customize the flood settings.

**Example:**
`/setflood on`
`/setflood 7`
"""

