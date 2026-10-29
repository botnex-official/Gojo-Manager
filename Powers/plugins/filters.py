from re import escape as re_escape
from secrets import choice
from traceback import format_exc

from pyrogram import filters
from pyrogram.enums import ChatMemberStatus as CMS
from pyrogram.enums import ParseMode as PM
from pyrogram.errors import RPCError
from pyrogram.types import CallbackQuery, Message

from Powers.bot_class import LOGGER, Gojo
from Powers.database.filters_db import Filters
from Powers.utils.cmd_senders import send_cmd
from Powers.utils.custom_filters import admin_filter, command, owner_filter
from Powers.utils.kbhelpers import ikb
from Powers.utils.pm_manager import resolve_confirm_chat
from Powers.utils.msg_types import Types, get_filter_type
from Powers.utils.regex_utils import regex_searcher
from Powers.utils.string import (build_keyboard,
                                 escape_mentions_using_curly_brackets,
                                 parse_button, split_quotes)

# Initialise
db = Filters()


@Gojo.on_message(command("filters") & filters.group & ~filters.bot)
async def view_filters(_, m: Message):
    LOGGER.info(f"{m.from_user.id} checking filters in {m.chat.id}")

    filters_chat = f"Filters in <b>{m.chat.title}</b>:\n"
    all_filters = db.get_all_filters(m.chat.id)
    actual_filters = [j for i in all_filters for j in i.split("|")]

    if not actual_filters:
        await m.reply_text(f"There are no filters in {m.chat.title}")
        return

    filters_chat += "\n".join(
        [
            f" • {' | '.join([f'<code>{i}</code>' for i in i.split('|')])}"
            for i in all_filters
        ],
    )
    return await m.reply_text(filters_chat, disable_web_page_preview=True)


@Gojo.on_message(command(["filter", "addfilter"]) & admin_filter & ~filters.bot)
async def add_filter(_, m: Message):

    args = m.text.split(" ", 1)
    all_filters = db.get_all_filters(m.chat.id)
    actual_filters = {j for i in all_filters for j in i.split("|")}

    if not m.reply_to_message and len(m.text.split()) < 3:
        return await m.reply_text("Please read help section for how to save a filter!")

    if m.reply_to_message and len(args) < 2:
        return await m.reply_text("Please read help section for how to save a filter!")

    extracted = await split_quotes(args[1])
    keyword = extracted[0].lower()

    for k in keyword.split("|"):
        if k in actual_filters:
            return await m.reply_text(f"Filter <code>{k}</code> already exists!")

    if not keyword:
        return await m.reply_text(
            f"<code>{m.text}</code>\n\nError: You must give a name for this Filter!",
        )

    if keyword.startswith("<") or keyword.startswith(">"):
        return await m.reply_text("Cannot save a filter which starts with '<' or '>'")

    eee, msgtype, file_id = await get_filter_type(m)
    lol = eee if m.reply_to_message else extracted[1]
    teks = lol if msgtype == Types.TEXT else eee

    # On a media reply-save, text typed after the keyword in the /filter
    # command becomes the filter's caption (buttons included); with no
    # typed text the source message's caption is kept, as before.
    if m.reply_to_message and msgtype and msgtype != Types.TEXT:
        typed = extracted[1] if len(extracted) > 1 else None
        if typed:
            teks = typed

    if not m.reply_to_message and msgtype == Types.TEXT and len(m.text.split()) < 3:
        return await m.reply_text(
            f"<code>{m.text}</code>\n\nError: There is no text in here!",
        )

    if not teks and not msgtype:
        return await m.reply_text(
            'Please provide keyword for this filter reply with!\nEnclose filter in <code>"double quotes"</code>',
        )

    if not msgtype:
        return await m.reply_text(
            "Please provide data for this filter reply with!",
        )

    add = db.save_filter(m.chat.id, keyword, teks, msgtype, file_id)
    LOGGER.info(f"{m.from_user.id} added new filter ({keyword}) in {m.chat.id}")
    if add:
        await m.reply_text(
            f"Saved filter for '<code>{', '.join(keyword.split('|'))}</code>' in <b>{m.chat.title}</b>!",
        )
    await m.stop_propagation()


@Gojo.on_message(command(["stop", "unfilter"]) & admin_filter & ~filters.bot)
async def stop_filter(_, m: Message):
    args = m.command

    if len(args) < 1:
        return await m.reply_text("What should I stop replying to?")

    chat_filters = db.get_all_filters(m.chat.id)
    act_filters = {j for i in chat_filters for j in i.split("|")}

    if not chat_filters:
        return await m.reply_text("No filters active here!")

    for keyword in act_filters:
        if keyword == m.text.split(None, 1)[1].lower():
            db.rm_filter(m.chat.id, m.text.split(None, 1)[1].lower())
            LOGGER.info(f"{m.from_user.id} removed filter ({keyword}) in {m.chat.id}")
            await m.reply_text(
                f"Okay, I'll stop replying to that filter and it's aliases in <b>{m.chat.title}</b>.",
            )
            await m.stop_propagation()

    await m.reply_text(
        "That's not a filter - Click: /filters to get currently active filters.",
    )
    await m.stop_propagation()


@Gojo.on_message(
    command(
        ["rmallfilters", "removeallfilters", "stopall", "stopallfilters"],
    )
    & owner_filter,
)
async def rm_allfilters(_, m: Message):
    all_bls = db.get_all_filters(m.chat.id)
    if not all_bls:
        return await m.reply_text("No filters to stop in this chat.")

    return await m.reply_text(
        "Are you sure you want to clear all filters?",
        reply_markup=ikb(
            [[("⚠️ Confirm", "rm_allfilters"), ("❌ Cancel", "close_admin")]],
        ),
    )


@Gojo.on_callback_query(filters.regex("^rm_allfilters$"))
async def rm_allfilters_callback(c: Gojo, q: CallbackQuery):
    user_id = q.from_user.id
    # In a group this resolves to the message's own chat; in PM it
    # resolves to the clicker's connected group (resolve_confirm_chat).
    chat_id, user_status = await resolve_confirm_chat(c, q)
    if chat_id is None:
        await q.answer(
            "I could not find the group this belongs to. Please reconnect it in PM.",
            show_alert=True,
        )
        return
    if user_status not in {CMS.OWNER, CMS.ADMINISTRATOR}:
        await q.answer(
            "You're not even an admin, don't try this explosive shit!",
            show_alert=True,
        )
        return
    if user_status != CMS.OWNER:
        await q.answer(
            "You're just an admin, not owner\nStay in your limits!",
            show_alert=True,
        )
        return
    db.rm_all_filters(chat_id)
    if chat_id == q.message.chat.id:
        chat_title = q.message.chat.title
    else:
        chat_title = (await c.get_chat(chat_id)).title
    await q.message.edit_text(f"Cleared all filters for {chat_title}")
    LOGGER.info(f"{user_id} removed all filter from {chat_id}")
    await q.answer("Cleared all Filters!", show_alert=True)
    return


async def send_filter_reply(c: Gojo, m: Message, trigger: str):
    """Reply with assigned filter for the trigger"""
    getfilter = db.get_filter(m.chat.id, trigger)
    if m and not m.from_user:
        return

    if not getfilter:
        # The doc vanished between the watcher's scan and this lookup
        # (stopped/edited in between) — a raced filter is a silent no-op,
        # never an error message in the chat.
        return

    msgtype = getfilter["msgtype"]
    if not msgtype:
        return await m.reply_text("<b>Error:</b> Cannot find a type for this filter!!")

    try:
        # support for random filter texts
        splitter = "%%%"
        filter_reply = getfilter["filter_reply"].split(splitter)
        filter_reply = choice(filter_reply)
    except KeyError:
        filter_reply = ""

    parse_words = [
        "first",
        "last",
        "fullname",
        "id",
        "mention",
        "username",
        "chatname",
    ]
    text = await escape_mentions_using_curly_brackets(m, filter_reply, parse_words)
    teks, button = await parse_button(text)
    button = await build_keyboard(button)
    # build_keyboard returns raw (text, url, "url") tuples; ikb converts
    # them into real InlineKeyboardButtons (same as notes do). Wrapping
    # the tuples in InlineKeyboardMarkup directly made Pyrogram call
    # .write() on a tuple when serialising the markup.
    button = ikb(button) if button else None
    textt = teks
    try:
        if msgtype == Types.TEXT:
            if button:
                try:
                    await m.reply_text(
                        textt,
                        parse_mode=PM.MARKDOWN,
                        reply_markup=button,
                        disable_web_page_preview=True,
                        quote=True,
                    )
                    return
                except RPCError as ef:
                    await m.reply_text(
                        "An error has occured! Cannot parse note.",
                        quote=True,
                    )
                    LOGGER.error(ef)
                    LOGGER.error(format_exc())
                    return
            else:
                await m.reply_text(
                    textt,
                    parse_mode=PM.MARKDOWN,
                    quote=True,
                    disable_web_page_preview=True,
                )
                return

        elif msgtype in (
            Types.STICKER,
            Types.VIDEO_NOTE,
            Types.CONTACT,
            Types.ANIMATED_STICKER,
        ):
            await (await send_cmd(c, msgtype))(
                m.chat.id,
                getfilter["fileid"],
                reply_markup=button,
                reply_to_message_id=m.id,
            )
        else:
            await (await send_cmd(c, msgtype))(
                m.chat.id,
                getfilter["fileid"],
                caption=textt,
                parse_mode=PM.MARKDOWN,
                reply_markup=button,
                reply_to_message_id=m.id,
            )
    except Exception as ef:
        # Never post raw exception text into the chat; log it instead.
        LOGGER.error(ef)
        LOGGER.error(format_exc())
        return msgtype

    return msgtype


@Gojo.on_message(filters.text & filters.group & ~filters.bot, group=69)
async def filters_watcher(c: Gojo, m: Message):

    chat_filters = db.get_all_filters(m.chat.id)
    actual_filters = {j for i in chat_filters for j in i.split("|")}

    for trigger in actual_filters:
        pattern = r"( |^|[^\w])" + re_escape(trigger) + r"( |$|[^\w])"
        match = await regex_searcher(pattern, m.text.lower())
        if match:
            try:
                msgtype = await send_filter_reply(c, m, trigger)
                LOGGER.info(f"Replied with {msgtype} to {trigger} in {m.chat.id}")
            except Exception as ef:
                # Silent in chat: a broken filter must not spam the
                # group with raw exception text on every matching message.
                LOGGER.error(ef)
                LOGGER.error(format_exc())
            break
        continue
    return


__PLUGIN__ = "filters"

_DISABLE_CMDS_ = ["filters"]

__alt_name__ = ["filters", "autoreply"]

__HELP__ = """
**Filters**

• /filters: List all active filters saved in the chat.

**Admin only:**
• /filter "`<keyword>`" `<reply message>`: Add a filter to this chat. The bot will now reply that message whenever 'keyword'
is mentioned. If you reply to a sticker with a keyword, the bot will reply with that sticker.

If you want your keyword to be a sentence, use quotes. eg: /filter "hey there" How are you doin?
**Example:**
`/filter "filtername" Reply Text`

Aliases for filters can be too set, just put '|' between the filternames you want.
**Example:**
`/filter "filtername1|filtername2" Reply Text`
Using the you can make a single filter work on 2 filternames without manually adding another one.

• /stop `<filter keyword>`: Stop that filter.

**Note:**
For filters with aliases, if you stop one alias, the filter will stop working on other aliases too.

**For Example:**
If you stop the "filtername1" from above example, the bot will not respond to "filtername2".

**Chat creator only:**
• /removeallfilters: Remove all chat filters at once.

**Note:**
There is no limit on the number of filters you can add in a chat.
All filter keywords are in lowercase."""
