from random import choice
from time import gmtime, strftime, time

from pyrogram import enums, filters
from pyrogram.enums import ChatMemberStatus as CMS
from pyrogram.enums import ChatType
from pyrogram.errors import (MediaCaptionTooLong, MessageNotModified,
                             QueryIdInvalid, UserIsBlocked)
from pyrogram.types import (CallbackQuery, InlineKeyboardButton,
                            InlineKeyboardMarkup, Message)

from Powers import (HELP_COMMANDS, LOGGER, PYROGRAM_VERSION, PYTHON_VERSION,
                    UPTIME, VERSION)
from Powers.bot_class import Gojo
from Powers.utils.custom_filters import command
from Powers.utils.extras import StartPic
from Powers.utils.pm_manager import resolve_confirm_chat
from Powers.utils.kbhelpers import ikb
from Powers.utils.start_utils import (gen_cmds_kb, gen_start_kb, get_help_msg,
                                      get_private_note, get_private_rules)
from Powers.vars import Config
from Powers.database.pm_connection_db import PMConnectionDB
from Powers.utils.pm_connection import make_connect_payload, parse_connect_payload

pm_connections = PMConnectionDB()


@Gojo.on_message(
    command("donate") & (filters.group | filters.private),
)
async def donate(_, m: Message):
    cpt = """
Hey There! Thanks for your thought of donating me!
You can donate by contacting my owner: [Sohan Rajpurohit](http://t.me/Sohan_Rajpurohit_1)
     """

    LOGGER.info(f"{m.from_user.id} fetched donation text in {m.chat.id}")
    await m.reply_photo(photo=str(choice(StartPic)), caption=cpt)
    return


@Gojo.on_callback_query(filters.regex("^close_admin$"))
async def close_admin_callback(c: Gojo, q: CallbackQuery):
    user_id = q.from_user.id
    # In a group this resolves to the message's own chat; in PM it
    # resolves to the clicker's connected group (resolve_confirm_chat),
    # so Cancel also works on prompts delivered through the PM bridge.
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
    await q.message.edit_text("Closed!")
    await q.answer("Closed menu!", show_alert=True)
    return



@Gojo.on_message(command("connect") & filters.group)
async def connect_pm(_, m: Message):
    """Generate the PM connection link for the current group.

    /start remains the normal bot start command. Group-to-PM linking is
    explicitly handled by /connect instead.
    """
    kb = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton(
                "🔗 Connect me to PM",
                url=f"https://t.me/{Config.BOT_USERNAME.lstrip('@')}?start={make_connect_payload(m.chat.id)}",
            )
        ]]
    )
    await m.reply_text(
        "🔗 <b>Connect this group to PM</b>\n\n"
        "Tap the button below and press <b>Start</b> in my PM.\n"
        "Only a group owner/admin can complete the connection.",
        reply_markup=kb,
    )
    return

@Gojo.on_message(
    command("start") & (filters.group | filters.private),
)
async def start(c: Gojo, m: Message):

    if m.chat.type == ChatType.PRIVATE:
        if len(m.text.strip().split()) > 1:
            help_option = (m.text.split(None, 1)[1]).lower()
            connect_chat_id = parse_connect_payload(help_option)
            if connect_chat_id is not None:
                try:
                    member = await c.get_chat_member(connect_chat_id, m.from_user.id)
                except Exception:
                    await m.reply_text("❌ I could not access that group. Make sure I am still in the group and try again.")
                    return
                if member.status not in {CMS.OWNER, CMS.ADMINISTRATOR}:
                    await m.reply_text("❌ Only a group owner/admin can connect this group to PM.")
                    return
                try:
                    chat = await c.get_chat(connect_chat_id)
                    pm_connections.connect(m.from_user.id, connect_chat_id)
                    await m.reply_text(f"✅ <b>Connected!</b>\n\nGroup: <b>{chat.title}</b>\nGroup ID: <code>{connect_chat_id}</code>\n\nYou can now use PM-based group management for this group.")
                except Exception as exc:
                    LOGGER.exception(exc)
                    await m.reply_text("❌ Connection failed. Please try again.")
                return

            if help_option.startswith("note") and (
                help_option not in ("note", "notes")
            ):
                await get_private_note(c, m, help_option)
                return
    
            if help_option.startswith("rules"):
                LOGGER.info(f"{m.from_user.id} fetched privaterules in {m.chat.id}")
                await get_private_rules(c, m, help_option)
                return

            help_msg, help_kb = await get_help_msg(m, help_option)

            if not help_msg:
                return
            elif help_msg:
                await m.reply_photo(
                    photo=str(choice(StartPic)),
                    caption=help_msg,
                    parse_mode=enums.ParseMode.MARKDOWN,
                    reply_markup=help_kb,
                    quote=True,
                )
                return
            if len(help_option.split("_",1)) == 2:
                if help_option.split("_")[1] == "help":
                    await m.reply_photo(
                        photo=str(choice(StartPic)),
                        caption=help_msg,
                        parse_mode=enums.ParseMode.MARKDOWN,
                        reply_markup=help_kb,
                        quote=True,
                    )
                    return
        try:
            cpt = f"""
Hey [{m.from_user.first_name}](http://t.me/{m.from_user.username})! I am Gojo Saturo Manager✨.
I'm here to help you manage your groups!
Hit /help to find out more about how to use me in my full potential!
"""

            await m.reply_photo(
                photo=str(choice(StartPic)),
                caption=cpt,
                reply_markup=(await gen_start_kb(m)),
                quote=True,
            )
        except UserIsBlocked:
            LOGGER.warning(f"Bot blocked by {m.from_user.id}")
    else:
      kb = InlineKeyboardMarkup(
        [
          [
            InlineKeyboardButton(
              "Connect me to pm", 
              url=f"https://t.me/{Config.BOT_USERNAME.lstrip('@')}?start={make_connect_payload(m.chat.id)}",
            ),
          ],
        ],
      )
        
      await m.reply_photo(
        photo=str(choice(StartPic)),
        caption="I'm alive :3",
        reply_markup=kb,
        quote=True,
      )
    return


@Gojo.on_callback_query(filters.regex("^start_back$"))
async def start_back(_, q: CallbackQuery):
    try:
        cpt = f"""
Hey [{q.from_user.first_name}](http://t.me/{q.from_user.username})! I am  Gojo Saturo Manager✨.
I'm here to help you manage your groups!
Hit /help to find out more about how to use me in my full potential!
"""

        await q.edit_message_caption(
            caption=cpt,
            reply_markup=(await gen_start_kb(q.message)),
        )
    except MessageNotModified:
        pass
    await q.answer()
    return


@Gojo.on_callback_query(filters.regex("^commands$"))
async def commands_menu(_, q: CallbackQuery):
    ou = await gen_cmds_kb(q.message)
    keyboard = ikb(ou, True)
    try:
        cpt = f"""
Hey **[{q.from_user.first_name}](http://t.me/{q.from_user.username})**! I am  Gojo Saturo Manager✨.
I'm here to help you manage your groups!
Commands available:
× /start: Start the bot
× /help: Give's you this message.

You can use `$` and `!` in placec of `/` as your prefix handler
"""

        await q.edit_message_caption(
            caption=cpt,
            reply_markup=keyboard,
        )
    except MessageNotModified:
        pass
    except QueryIdInvalid:
        await q.message.reply_photo(
            photo=str(choice(StartPic)), caption=cpt, reply_markup=keyboard
        )
    except Exception:
        # The message being edited may be a plain text message (sent by
        # the MediaCaptionTooLong fallback in get_module_info); those
        # cannot be caption-edited, so edit their text instead.
        try:
            await q.edit_message_text(cpt, reply_markup=keyboard)
        except Exception:
            pass

    await q.answer()
    return


@Gojo.on_message(command("help"))
async def help_menu(_, m: Message):
    if len(m.text.split()) >= 2:
        textt = m.text.replace(" ","_",).replace("_"," ",1)
        help_option = (textt.split(None)[1]).lower()
        help_msg, help_kb = await get_help_msg(m, help_option)

        if not help_msg:
            LOGGER.error(f"No help_msg found for help_option - {help_option}!!")
            return

        LOGGER.info(
            f"{m.from_user.id} fetched help for '{help_option}' text in {m.chat.id}",
        )

        if m.chat.type == ChatType.PRIVATE:
            if len(help_msg) >= 1026:
                await m.reply_text(
                    help_msg, parse_mode=enums.ParseMode.MARKDOWN, quote=True
                )
            else:
                await m.reply_photo(
                    photo=str(choice(StartPic)),
                    caption=help_msg,
                    parse_mode=enums.ParseMode.MARKDOWN,
                    reply_markup=help_kb,
                    quote=True,
                )
        else:

            await m.reply_photo(
                photo=str(choice(StartPic)),
                caption=f"Press the button below to get help for <i>{help_option}</i>",
                reply_markup=InlineKeyboardMarkup(
                  [
                    [
                      InlineKeyboardButton(
                        "Help",
                        url=f"t.me/{Config.BOT_USERNAME}?start={help_option}",
                        ),
                    ],
                  ],
                ),
            )
    else:

        if m.chat.type == ChatType.PRIVATE:
            ou = await gen_cmds_kb(m)
            keyboard = ikb(ou, True)
            msg = f"""
Hey **[{m.from_user.first_name}](http://t.me/{m.from_user.username})**!I am  Gojo Saturo Manager✨.
I'm here to help you manage your groups!
Commands available:
× /start: Start the bot
× /help: Give's you this message."""
        else:
            keyboard = InlineKeyboardMarkup(
              [
                [
                  InlineKeyboardButton(
                    "Help", 
                    url=f"t.me/{Config.BOT_USERNAME}?start=start_help",
                  ),
                ],
              ],
            )
            msg = "Contact me in PM to get the list of possible commands."

        await m.reply_photo(
            photo=str(choice(StartPic)),
            caption=msg,
            reply_markup=keyboard,
        )

    return

@Gojo.on_callback_query(filters.regex("^bot_curr_info$"))
async def give_curr_info(c: Gojo, q: CallbackQuery):
    start = time()
    up = strftime("%Hh %Mm %Ss", gmtime(time() - UPTIME))
    x = await c.send_message(q.message.chat.id, "Pinging..")
    delta_ping = time() - start
    await x.delete()
    txt = f"""
**{Config.BOT_NAME}** (@{Config.BOT_USERNAME})
🆔 Bot ID: `{Config.BOT_ID}`
🏓 Ping: {delta_ping * 1000:.3f} ms
📈 Uptime: {up}
🤖 Bot version: {VERSION}
🐍 Python version: {PYTHON_VERSION}
🔥 Pyrogram version: {PYROGRAM_VERSION}
    """
    try:
        await q.edit_message_caption(
            caption=txt,
            parse_mode=enums.ParseMode.MARKDOWN,
            reply_markup=ikb([[("« Back", "start_back")]]),
        )
    except MessageNotModified:
        pass
    except Exception:
        await q.answer(txt, show_alert=True)
        return
    await q.answer()
    return

@Gojo.on_callback_query(filters.regex("^plugins."))
async def get_module_info(c: Gojo, q: CallbackQuery):
    module = q.data.split(".", 1)[1]

    help_msg = HELP_COMMANDS[f"plugins.{module}"]["help_msg"]

    help_kb = HELP_COMMANDS[f"plugins.{module}"]["buttons"]
    await q.answer()
    try:
      await q.edit_message_caption(
          caption=help_msg,
          parse_mode=enums.ParseMode.MARKDOWN,
          reply_markup=ikb(help_kb, True, todo="commands"),
      )
    except MediaCaptionTooLong:
      await c.send_message(
          chat_id=q.message.chat.id,
          text=help_msg,
          parse_mode=enums.ParseMode.MARKDOWN,
          reply_markup=ikb(help_kb, True, todo="commands"),
      )
    except MessageNotModified:
      pass
    return
