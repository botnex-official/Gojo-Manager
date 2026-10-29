from traceback import format_exc

from pyrogram import filters
from pyrogram.enums import ChatMemberStatus as CMS
from pyrogram.enums import ChatMembersFilter as cmf
from pyrogram.enums import ChatType
from pyrogram.errors import RPCError, UserNotParticipant
from pyrogram.types import CallbackQuery, Message

from Powers import LOGGER, SUPPORT_STAFF
from Powers.bot_class import Gojo
from Powers.database.reporting_db import Reporting
from Powers.utils.custom_filters import admin_filter, command
from Powers.utils.kbhelpers import ikb
from Powers.utils.parser import mention_html
from Powers.utils.report_control import parse_report_callback


def _public_message_link(chat, message_id):
    if chat.username:
        return f"https://t.me/{chat.username}/{message_id}"
    chat_id = str(chat.id).replace("-100", "")
    return f"https://t.me/c/{chat_id}/{message_id}"


async def _callback_is_chat_admin(client, callback, chat_id):
    try:
        member = await client.get_chat_member(chat_id, callback.from_user.id)
    except (RPCError, UserNotParticipant):
        return False
    return member.status in {CMS.OWNER, CMS.ADMINISTRATOR}


@Gojo.on_message(
    command("reports") & (filters.private | admin_filter),
)
async def report_setting(_, m: Message):
    args = m.text.split()
    db = Reporting(m.chat.id)

    if m.chat.type == ChatType.PRIVATE:
        if len(args) >= 2:
            option = args[1].lower()
            if option in ("yes", "on", "true"):
                db.set_settings(True)
                LOGGER.info(f"{m.from_user.id} enabled reports for them")
                await m.reply_text(
                    "Turned on reporting! You'll be notified whenever anyone reports something in groups you are admin.",
                )
            elif option in ("no", "off", "false"):
                db.set_settings(False)
                LOGGER.info(f"{m.from_user.id} disabled reports for them")
                await m.reply_text("Turned off reporting! You wont get any reports.")
        else:
            await m.reply_text(
                f"Your current report preference is: `{db.get_settings()}`",
            )
    elif len(args) >= 2:
        option = args[1].lower()
        if option in ("yes", "on", "true"):
            db.set_settings(True)
            LOGGER.info(f"{m.from_user.id} enabled reports in {m.chat.id}")
            await m.reply_text(
                "Turned on reporting! Admins who have turned on reports will be notified when /report "
                "or @admin is called.",
                quote=True,
            )
        elif option in ("no", "off", "false"):
            db.set_settings(False)
            LOGGER.info(f"{m.from_user.id} disabled reports in {m.chat.id}")
            await m.reply_text(
                "Turned off reporting! No admins will be notified on /report or @admin.",
                quote=True,
            )
    else:
        await m.reply_text(
            f"This group's current setting is: `{db.get_settings()}`",
        )


@Gojo.on_message(
    filters.group
    & filters.regex(r"(?i)^@admins?(?:\s+.*)?$")
)
async def admin_report_watcher(c: Gojo, m: Message):
    await report_watcher(c, m)


@Gojo.on_message(command("report") & filters.group)
async def report_watcher(c: Gojo, m: Message):
    if m.chat.type not in [ChatType.SUPERGROUP, ChatType.GROUP]:
        return
    if not m.from_user or not m.reply_to_message:
        return
    if await _message_sender_is_admin(m):
        return
    if not Reporting(m.chat.id).get_settings():
        return

    reported_user = m.reply_to_message.from_user
    if not reported_user:
        return

    me = await c.get_me()
    if reported_user.id == me.id:
        await m.reply_text("Nice try.")
        return
    if reported_user.id in SUPPORT_STAFF:
        await m.reply_text("Uh? You reporting my support team?")
        return

    chat_name = m.chat.title or m.chat.username or str(m.chat.id)
    if m.chat.username:
        msg = (
            f"<b>⚠️ Report: </b>{m.chat.title}\n"
            f"<b> • Report by:</b> {await mention_html(m.from_user.first_name, m.from_user.id)} "
            f"(<code>{m.from_user.id}</code>)\n"
            f"<b> • Reported user:</b> {await mention_html(reported_user.first_name, reported_user.id)} "
            f"(<code>{reported_user.id}</code>)"
        )
    else:
        msg = (
            f"{await mention_html(m.from_user.first_name, m.from_user.id)} "
            f"is calling for admins in '{chat_name}'!\n"
        )

    reported_msg_id = m.reply_to_message.id
    link = _public_message_link(m.chat, reported_msg_id)
    reply_markup = ikb(
        [
            [("➡ Message", link, "url")],
            [
                ("⚠ Kick", f"report_{m.chat.id}=kick={reported_user.id}={reported_msg_id}"),
                ("⛔️ Ban", f"report_{m.chat.id}=ban={reported_user.id}={reported_msg_id}"),
            ],
            [("❎ Delete Message", f"report_{m.chat.id}=del={reported_user.id}={reported_msg_id}")],
        ],
    )

    LOGGER.info(
        f"{m.from_user.id} reported msgid-{reported_msg_id} to admins in {m.chat.id}",
    )
    await m.reply_text(
        f"{await mention_html(m.from_user.first_name, m.from_user.id)} reported the message to the admins.",
        quote=True,
    )

    async for admin in c.get_chat_members(m.chat.id, filter=cmf.ADMINISTRATORS):
        if admin.user.is_bot or admin.user.is_deleted:
            continue
        if not Reporting(admin.user.id).get_settings():
            continue
        try:
            await c.send_message(
                admin.user.id,
                msg,
                reply_markup=reply_markup,
                disable_web_page_preview=True,
            )
            try:
                await m.reply_to_message.forward(admin.user.id)
                if len(m.text.split()) > 1:
                    await m.forward(admin.user.id)
            except RPCError:
                LOGGER.warning(
                    f"Could not forward report context to admin {admin.user.id} for chat {m.chat.id}",
                )
        except RPCError as exc:
            LOGGER.error(exc)
            LOGGER.error(format_exc())


async def _message_sender_is_admin(m):
    try:
        member = await m.chat.get_member(m.from_user.id)
    except (RPCError, UserNotParticipant):
        return False
    return member.status in {CMS.OWNER, CMS.ADMINISTRATOR}


@Gojo.on_callback_query(filters.regex(r"^report_"))
async def report_buttons(c: Gojo, q: CallbackQuery):
    parsed = parse_report_callback(q.data)
    if parsed is None:
        await q.answer("Invalid or expired report action.", show_alert=True)
        return

    chat_id, action, user_id, message_id = parsed
    if not await _callback_is_chat_admin(c, q, chat_id):
        await q.answer("Only a group admin can use report actions.", show_alert=True)
        return

    try:
        if action == "kick":
            await c.ban_chat_member(chat_id, user_id)
            await c.unban_chat_member(chat_id, user_id)
            await q.answer("✅ Successfully kicked")
        elif action == "ban":
            await c.ban_chat_member(chat_id, user_id)
            await q.answer("✅ Successfully banned")
        elif action == "del":
            await c.delete_messages(chat_id, message_id)
            await q.answer("✅ Message deleted")
    except RPCError as err:
        await q.answer(
            f"🛑 Action failed\n<b>Error:</b>\n<code>{err}</code>",
            show_alert=True,
        )


__PLUGIN__ = "reporting"

__alt_name__ = ["reports", "report"]

__HELP__ = """
**Report**

• /report <reason>: reply to a message to report it to admins.
• @admin <reason>: reply to a message to report it to admins.

**NOTE:** Reports from group admins are ignored.

**Admins Only:**
• /reports <on/off/yes/no>: change report setting, or view current status.
    ‣ If done in PM, toggles your status.
    ‣ If in group, toggles that group's status.
"""
