from pyrogram import enums, filters
from pyrogram.errors import PeerIdInvalid
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from Powers import *
from Powers.bot_class import Gojo
from Powers.utils.custom_filters import command
from Powers.utils.extract_user import extract_user
from Powers.utils.parser import mention_html


@Gojo.on_message(command("id") & (filters.group | filters.private))
async def id_info(c: Gojo, m: Message):

    ChatType = enums.ChatType
    user_id, _, _ = await extract_user(c, m)
    try:
        if user_id and len(m.text.split()) == 2:
            txt = f"Given user's id: <code>{user_id}</code>"
            await m.reply_text(txt, parse_mode=enums.ParseMode.HTML)
            return
        elif m.chat.type in [ChatType.SUPERGROUP, ChatType.GROUP] and not m.reply_to_message:
            await m.reply_text(text=f"This Group's ID is <code>{m.chat.id}</code>\nYour ID <code>{m.from_user.id}</code>")
            return

        elif m.chat.type == ChatType.PRIVATE and not m.reply_to_message:
            await m.reply_text(text=f"Your ID is <code>{m.chat.id}</code>.")
            return
    except Exception as e:
        await m.reply_text(e)
        return
    if user_id:
        if m.reply_to_message and m.reply_to_message.forward_from:
            user1 = m.reply_to_message.from_user
            user2 = m.reply_to_message.forward_from
            orig_sender = await mention_html(user2.first_name, user2.id)
            orig_id = f"<code>{user2.id}</code>"
            fwd_sender = await mention_html(user1.first_name, user1.id)
            fwd_id = f"<code>{user1.id}</code>"
            await m.reply_text(
                text=f"""Original Sender - {orig_sender} (<code>{orig_id}</code>)
Forwarder - {fwd_sender} (<code>{fwd_id}</code>)""",
                parse_mode=enums.ParseMode.HTML,
            )
        else:
            try:
                user = await c.get_users(user_id)
            except PeerIdInvalid:
                await m.reply_text(
                    text="""Failed to get user
      Peer ID invalid, I haven't seen this user anywhere earlier, maybe username would help to know them!"""
                )
                return

            await m.reply_text(
                f"{(await mention_html(user.first_name, user.id))}'s ID is <code>{user.id}</code>.",
                parse_mode=enums.ParseMode.HTML,
            )
    elif m.chat.type == ChatType.PRIVATE:
        text=f"Your ID is <code>{m.chat.id}</code>."
        if m.reply_to_message:
            if m.forward_from:
                text+=f"Forwarded from user ID <code>{m.forward_from.id}</code>."
            elif m.forward_from_chat:
                text+=f"Forwarded from user ID <code>{m.forward_from_chat.id}</code>."
        await m.reply_text(text)
    else:
        text=f"Chat ID <code>{m.chat.id}</code>\nYour ID <code>{m.from_user.id}</code>"
        await m.reply_text(text)
    return


@Gojo.on_message(command("bug"))
async def reporting_query(c: Gojo, m: Message):
    repl = m.reply_to_message
    if not repl:
        await m.reply_text("Please reply to a message to report it as bug")
        return
    if not repl.text:
        await m.reply_text("Please reply to a text message.")
        return
    txt = "#BUG\n"
    txt += repl.text.html
    txt += f"\nReported by: {m.from_user.id} ({m.from_user.mention})"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Update channel",url=f"https://t.me/{SUPPORT_GROUP}")]])
    try:
        z = await c.send_message(MESSAGE_DUMP,txt,parse_mode=enums.ParseMode.HTML)
    except Exception:
        txt = repl.text.html
        z = await c.send_message(MESSAGE_DUMP,txt,parse_mode=enums.ParseMode.HTML)
        await z.reply_text(f"#BUG\nReported by: {m.from_user.id} ({m.from_user.mention})")
    await repl.delete()
    await m.reply_photo(photo="./extras/Fire.jpg",caption="Successfully reported your bug",reply_markup=kb)
    ppost = z.link
    await c.send_message(OWNER_ID,f"New bug report\n{ppost}",disable_web_page_preview=True)
    return


__PLUGIN__ = "utils"
__alt_name__ = ["util", "misc", "tools"]

__HELP__ = """
**Utils**

• /id: Get the current group ID. If used by replying to a message, get that user's ID.
• /bug <reply to text message>: Report a bug.

/info is handled by the Info plugin.
"""
