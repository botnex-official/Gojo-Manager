import subprocess as subp
import sys
from asyncio import create_subprocess_shell, sleep, subprocess
from io import BytesIO, StringIO
import os
from os import execvp
from sys import executable
from time import gmtime, strftime, time
from traceback import format_exc
import traceback
import aiofiles
import datetime
from pyrogram.errors import (
    ChannelInvalid,
    ChannelPrivate,
    ChatAdminRequired,
    EntityBoundsInvalid,
    FloodWait,
    MessageTooLong,
    PeerIdInvalid,
    RPCError,
    InputUserDeactivated,
    UserIsBlocked
)

from pyrogram.types import Message

from Powers import (API_HASH, BDB_URI, BOT_TOKEN, DB_URI, DEV_LEVEL, DEV_USERS,
                    LOG_DATETIME, LOGFILE, LOGGER, MESSAGE_DUMP, OWNER_ID, UPTIME)
from Powers.bot_class import Gojo
from Powers.database import MongoDB
from Powers.database.chats_db import Chats
from Powers.database.staff_db import add_dev as persist_dev
from Powers.database.staff_db import remove_dev
from Powers.database.users_db import Users
from Powers.plugins.clean_db import clean_my_db
from Powers.utils.clean_file import remove_markdown_and_html
from Powers.utils.custom_filters import command
from Powers.utils.extract_user import extract_user
from Powers.utils.parser import mention_markdown
from Powers.vars import Config


@Gojo.on_message(command(["adddev", "rmdev"]))
async def add_dev(c: Gojo, m:Message):
    if int(m.from_user.id) != int(OWNER_ID):
        await m.reply_text("Only owner can do that")
        return
    split = m.text.split(None)
    reply_to = m.reply_to_message
    user = None
    if reply_to and getattr(reply_to, "from_user", None):
        user = reply_to.from_user.id
    elif len(split) == 2:
        try:
            extracted = await extract_user(c, m)
            if not isinstance(extracted, tuple):
                return
            user = extracted[0]
        except Exception as e:
            await m.reply_text(f"Give me id of the user {e}")
            return
    else:
        await m.reply_text("Reply to message to add the user in dev")
        return
    try:
        user = int(user)
    except (TypeError, ValueError, NameError):
        await m.reply_text("Give me id of the user")
        return
    if m.command[0] == "rmdev":
        if user == int(OWNER_ID):
            await m.reply_text("Cannot remove the owner")
            return
        # Pull persisted devs into DEV_USERS before the in-memory edit.
        _ = user in DEV_LEVEL
        removed = False
        for entry in list(DEV_USERS):
            try:
                if int(entry) == user:
                    DEV_USERS.remove(entry)
                    removed = True
            except (TypeError, ValueError):
                continue
        remove_dev(user)
        if removed:
            await m.reply_text(f"Removed {user} from dev")
        else:
            await m.reply_text("User is not a dev")
        return
    already = False
    for entry in DEV_USERS:
        try:
            if int(entry) == user:
                already = True
                break
        except (TypeError, ValueError):
            continue
    if not already:
        DEV_USERS.append(user)
    persist_dev(user)
    await m.reply_text(f"Added {user} to dev")
    return
      
@Gojo.on_message(command("ping", sudo_cmd=True))
async def ping(_, m: Message):
    LOGGER.info(f"{m.from_user.id} used ping cmd in {m.chat.id}")
    start = time()
    replymsg = await m.reply_text(text="Pinging...", quote=True)
    delta_ping = time() - start
    await replymsg.edit_text(f"<b>Pong!</b>\n{delta_ping * 1000:.3f} ms")
    return


@Gojo.on_message(command("logs", dev_cmd=True))
async def send_log(c: Gojo, m: Message):
    replymsg = await m.reply_text("Sending logs...!")
    await c.send_message(
        MESSAGE_DUMP,
        f"#LOGS\n\n**User:** {(await mention_markdown(m.from_user.first_name, m.from_user.id))}",
    )
    if os.path.isfile(LOGFILE):
        await m.reply_document(
            document=LOGFILE,
            quote=True,
        )
    else:
        await m.reply_text("The log is empty.")
    await replymsg.delete()
    return


@Gojo.on_message(command("neofetch", dev_cmd=True))
async def neofetch_stats(_, m: Message):
    cmd = "neofetch --stdout"

    process = await create_subprocess_shell(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    e = stderr.decode()
    if not e:
        e = "No Error"
    OUTPUT = stdout.decode()
    if not OUTPUT:
        OUTPUT = "No Output"

    try:
        await m.reply_text(OUTPUT, quote=True)
    except MessageTooLong:
        with BytesIO(str.encode(await remove_markdown_and_html(OUTPUT))) as f:
            f.name = "neofetch.txt"
            await m.reply_document(document=f, caption="neofetch result")
        await m.delete()
    return

HARMFUL = [
    "base64",
    "bash",
    "get_me()",
    "phone",
    "os.system",
    "sys.stdout",
    "sys.stderr",
    "subprocess",
    "DB_URI",
    "DB_URI",
    "BOT_TOKEN",
    "API_HASH",
    "APP_ID",
    "SSH_CLIENT",
    "SSH_CONNECTION",
    "SSH",
]


def _configured_secrets():
    """Live secret values from config, referenced programmatically.

    Used only to keep these values out of /eval and /exec output; the
    values themselves are never hard-coded here.
    """
    values = [BOT_TOKEN, API_HASH, DB_URI, BDB_URI]
    for attr in ("GENIUS_API_TOKEN", "RMBG_API", "AuDD_API"):
        values.append(getattr(Config, attr, None))
    secrets = []
    for value in values:
        if value:
            secrets.append(str(value))
            # Also catch the user:password part of credentialed URIs and
            # the token halves, which can show up on their own in output.
            secrets.extend(
                part for part in re_split_secrets(str(value)) if len(part) >= 6
            )
    return sorted(set(secrets), key=len, reverse=True)


def re_split_secrets(value):
    import re as _re

    return _re.split(r"[@:/]", value)


def _redact_secrets(text):
    """Replace any configured secret value in *text* with a placeholder."""
    if not text:
        return text
    redacted = str(text)
    for secret in _configured_secrets():
        redacted = redacted.replace(secret, "[REDACTED]")
    return redacted


def _contains_harmful(text):
    """Return the first HARMFUL pattern present in *text*, else None."""
    if not text:
        return None
    for pattern in HARMFUL:
        if pattern and pattern in text:
            return pattern
    # NAME=value style access to a harmful name (e.g. BOT_TOKEN=...)
    for word in str(text).replace("=", " ").split():
        if word in HARMFUL:
            return word
    return None


@Gojo.on_message(command(["eval", "py"], dev_cmd=True))
async def evaluate_code(c: Gojo, m: Message):
    if int(m.from_user.id) != int(OWNER_ID):
        await m.reply_text("Only the bot owner can use this.")
        return
    if len(m.text.split()) == 1:
        await m.reply_text(text="Please execute the code correctly!")
        return
    sm = await m.reply_text("`Processing...`")
    cmd = m.text.split(None, maxsplit=1)[1]
    if _contains_harmful(cmd):
        await sm.delete()
        await m.reply_text(
            "Refused: the command references a protected name/pattern."
        )
        await c.send_message(
            MESSAGE_DUMP,
            f"@{m.from_user.username} TRIED TO FETCH ENV OF BOT \n userid = {m.from_user.id}",
        )
        return
    if "while True:" in cmd:
        await sm.delete()
        await m.reply_text("BSDK SPAM NI")
        await c.send_message(
            MESSAGE_DUMP,
            f"@{m.from_user.username} TREID TO USE `while True` \n userid = {m.from_user.id}"
            )
        return
    if m.reply_to_message and m.reply_to_message.document:
        if m.reply_to_message.document.mime_type.split("/")[1] == "x-python" or m.reply_to_message.document.file_name.endswith("py"):
            await sm.delete()
            await m.reply_text("Loading external plugin is prohibited")
            return
    reply_to_id = m.id
    if m.reply_to_message:
        reply_to_id = m.reply_to_message.id

    old_stderr = sys.stderr
    old_stdout = sys.stdout
    redirected_output = sys.stdout = StringIO()
    redirected_error = sys.stderr = StringIO()
    stdout, stderr, exc = None, None, None

    try:
        await aexec(cmd, c, m)
    except Exception as ef:
        LOGGER.error(ef)
        exc = format_exc()

    stdout = redirected_output.getvalue()
    stderr = redirected_error.getvalue()
    sys.stdout = old_stdout
    sys.stderr = old_stderr

    evaluation = ""
    if exc:
        evaluation = exc
    elif stderr:
        evaluation = stderr
    elif stdout:
        evaluation = stdout
    else:
        evaluation = "Success"
    # The checks below protect the only user who can reach this code (the
    # owner, enforced above): redact configured secrets and harmful names
    # from whatever the evaluated code printed before it is sent anywhere.
    evaluation = _redact_secrets(evaluation)
    if _contains_harmful(evaluation):
        evaluation = "[REDACTED]"
        await c.send_message(
            MESSAGE_DUMP,
            f"@{m.from_user.username} EVAL OUTPUT WAS REDACTED (protected value) \n userid = {m.from_user.id}",
        )

    final_output = f"<b>EVAL</b>: <code>{_redact_secrets(cmd)}</code>\n\n<b>OUTPUT</b>:\n<code>{evaluation}</code> \n"

    try:
        await sm.edit(final_output)
    except MessageTooLong:
        with BytesIO(str.encode(await remove_markdown_and_html(final_output))) as f:
            f.name = "py.txt"
            await m.reply_document(
                document=f,
                caption=cmd,
                disable_notification=True,
                reply_to_message_id=reply_to_id,
            )
        await sm.delete()

    return


async def aexec(code, c, m):
    exec("async def __aexec(c, m): " + "".join(f"\n {l}" for l in code.split("\n")))
    return await locals()["__aexec"](c, m)




@Gojo.on_message(command(["exec", "sh"], dev_cmd=True))
async def execution(c: Gojo, m: Message):
    if int(m.from_user.id) != int(OWNER_ID):
        await m.reply_text("Only the bot owner can use this.")
        return
    if len(m.text.split()) == 1:
        await m.reply_text(text="Please execute the code correctly!")
        return
    sm = await m.reply_text("`Processing...`\n")
    cmd = m.text.split(maxsplit=1)[1]
    if _contains_harmful(cmd):
        await sm.delete()
        await m.reply_text(
            "Refused: the command references a protected name/pattern."
        )
        await c.send_message(
            MESSAGE_DUMP,
            f"@{m.from_user.username} TRIED TO FETCH ENV OF BOT \n userid = {m.from_user.id}",
        )
        return

    reply_to_id = m.id
    if m.reply_to_message:
        reply_to_id = m.reply_to_message.id

    process = await create_subprocess_shell(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    e = stderr.decode().strip()
    if not e:
        e = "No Error"
    o = stdout.decode().strip()
    if not o:
        o = "No Output"
    out = o
    # Redact configured secrets / harmful names from the command output
    # before sending it; this protects the owner, the only user who can
    # run /exec at all.
    out = _redact_secrets(out)
    e = _redact_secrets(e)
    if _contains_harmful(out) or _contains_harmful(e):
        out = "[REDACTED]"
        e = "[REDACTED]"
        await c.send_message(
            MESSAGE_DUMP,
            f"@{m.from_user.username} EXEC OUTPUT WAS REDACTED (protected value) \n userid = {m.from_user.id}",
        )

    OUTPUT = ""
    OUTPUT += f"<b>QUERY:</b>\n<u>Command:</u>\n<code>{_redact_secrets(cmd)}</code> \n"
    OUTPUT += f"<u>PID</u>: <code>{process.pid}</code>\n\n"
    OUTPUT += f"<b>stderr</b>: \n<code>{e}</code>\n\n"
    OUTPUT += f"<b>stdout</b>: \n<code>{out}</code>"

    try:
        await sm.edit_text(OUTPUT)
    except (MessageTooLong, EntityBoundsInvalid):
        with BytesIO(str.encode(await remove_markdown_and_html(OUTPUT))) as f:
            f.name = "sh.txt"
            await m.reply_document(
                document=f,
                caption=cmd,
                disable_notification=True,
                reply_to_message_id=reply_to_id,
            )
        await sm.delete()
    return

async def stop_and_send_logger(c:Gojo,is_update=False):
    runtime = strftime("%Hh %Mm %Ss", gmtime(time() - UPTIME))
    LOGGER.info("Uploading logs before stopping...!\n")
        # Send Logs to MESSAGE_DUMP and LOG_CHANNEL
    await c.send_document(
            MESSAGE_DUMP,
            document=LOGFILE,
            caption=(
                f"{'Updating and Restarting'if is_update else 'Restarting'} The Bot !\n\n" f"Uptime: {runtime}\n" f"<code>{LOG_DATETIME}</code>"
            ),
        )
    if MESSAGE_DUMP:
        # LOG_CHANNEL is not necessary
        await c.send_document(
                MESSAGE_DUMP,
                document=LOGFILE,
                caption=f"Uptime: {runtime}",
            )
    MongoDB.close()
    LOGGER.info(
            f"""Bot Stopped.
            Logs have been uploaded to the MESSAGE_DUMP Group!
            Runtime: {runtime}s\n
        """,
        )
    return

@Gojo.on_message(command(["restart", "update"], owner_cmd=True),group=-100)
async def restart_the_bot(c:Gojo,m:Message):
    try:
        cmds = m.command
        await m.reply_text(f"Restarting{' and updating ' if cmds[0] == 'update' else ' '}the bot...\nType `/ping` after few minutes")
        if cmds[0] == "update":
            try:
                out = subp.check_output(["git", "pull"]).decode("UTF-8")
                if "Already up to date." in str(out):
                    return await m.reply_text("Its already up-to date!")
                await m.reply_text(f"```{out}```")
            except Exception as e:
                return await m.reply_text(str(e))
            m = await m.reply_text("**Updated with main branch, restarting now.**")
            await stop_and_send_logger(c,True)
        if cmds[0] == "restart":
            await stop_and_send_logger(c)
        execvp(executable, [executable, "-m", "Powers"])
    except Exception as e:
        await m.reply_text(f"Failed to restart the bot due to\n{e}")
        LOGGER.error(e)
        LOGGER.error(format_exc())
        return

@Gojo.on_message(command("chatlist", dev_cmd=True))
async def chats(c: Gojo, m: Message):
    exmsg = await m.reply_text(text="Exporting Charlist...")
    await c.send_message(
        MESSAGE_DUMP,
        f"#CHATLIST\n\n**User:** {(await mention_markdown(m.from_user.first_name, m.from_user.id))}",
    )
    all_chats = (Chats.list_chats_full()) or {}
    chatfile = """List of chats in my database.

        <b>Chat name | Chat ID | Members count</b>"""
    P = 1
    for chat in all_chats:
        try:
            chat_info = await c.get_chat(chat["_id"])
            chat_members = chat_info.members_count
            try:
                invitelink = chat_info.invite_link
            except KeyError:
                invitelink = "No Link!"
            chatfile += f"{P}. {chat['chat_name']} | {chat['_id']} | {chat_members} | {invitelink}\n"
            P += 1
        except ChatAdminRequired:
            pass
        except (ChannelPrivate, ChannelInvalid):
            Chats.remove_chat(chat["_id"])
        except PeerIdInvalid:
            LOGGER.warning(f"Peer not found {chat['_id']}")
        except FloodWait as ef:
            LOGGER.error("FloodWait required, Sleeping for 60s")
            LOGGER.error(ef)
            sleep(60)
        except RPCError as ef:
            LOGGER.error(ef)
            await m.reply_text(f"**Error:**\n{ef}")

    with BytesIO(str.encode(await remove_markdown_and_html(chatfile))) as f:
        f.name = "chatlist.txt"
        await m.reply_document(
            document=f,
            caption="Here is the list of chats in my Database.",
        )
    await exmsg.delete()
    return


@Gojo.on_message(command("uptime", dev_cmd=True))
async def uptime(_, m: Message):
    up = strftime("%Hh %Mm %Ss", gmtime(time() - UPTIME))
    await m.reply_text(text=f"<b>Uptime:</b> <code>{up}</code>", quote=True)
    return


@Gojo.on_message(command("leavechat", dev_cmd=True))
async def leave_chat(c: Gojo, m: Message):
    if len(m.text.split()) != 2:
        await m.reply_text("Supply a chat id which I should leave!", quoet=True)
        return

    chat_id = m.text.split(None, 1)[1]

    replymsg = await m.reply_text(f"Trying to leave chat {chat_id}...", quote=True)
    try:
        await c.leave_chat(chat_id)
        await replymsg.edit_text(f"Left <code>{chat_id}</code>.")
    except PeerIdInvalid:
        await replymsg.edit_text("Haven't seen this group in this session!")
    except RPCError as ef:
        LOGGER.error(ef)
        await replymsg.edit_text(f"Failed to leave chat!\nError: <code>{ef}</code>.")
    return

async def send_msg(user_id, message):
    try:
        await message.copy(chat_id=user_id)
        return 200, None
    except FloodWait as e:
        await asyncio.sleep(e.x)
        return send_msg(user_id, message)
    except InputUserDeactivated:
        return 400, f"{user_id} : deactivated\n"
    except UserIsBlocked:
        return 400, f"{user_id} : blocked the bot\n"
    except PeerIdInvalid:
        return 400, f"{user_id} : user id invalid\n"
    except Exception:
        return 500, f"{user_id} : {traceback.format_exc()}\n"

@Gojo.on_message(command("broadcast", dev_cmd=True))
async def broadcast(c: Gojo, m: Message):
    if m.reply_to_message:
        broadcast_msg = m.reply_to_message
    else:
        await m.reply_text("Reply to a message to broadcast it")
        return

    exmsg = await m.reply_text("Started broadcasting!")
    user_start_time = time()

    total_users = Users.count_users()
    total_chats = Chats.count_chats()

    await exmsg.edit(f"Started broadcasting!\n\nFound total **{total_users} users**.")

    all_users = (Users.list_users()) or {}

    done_broadcast = 0
    success, failed = 0, 0

    async with aiofiles.open("users-broadcast.txt", "w") as broadcast_log_file:
        for user in all_users:
            sts, msg = await send_msg(user_id=int(user["_id"]), message=broadcast_msg)
            if msg is not None:
                await broadcast_log_file.write(msg)
            if sts == 200:
                success += 1
            else:
                failed += 1
            done_broadcast += 1

    completed_in = datetime.timedelta(seconds=int(time() - user_start_time))

    await exmsg.edit_text(
        f"Users broadcasting completed ✅\nSent message to {done_broadcast} users.",
    )

    if failed == 0:
        await m.reply_text(
            text=f"Users broadcast completed in `{completed_in}`\n\nTotal users {total_users}.\nTotal done {done_broadcast}, {success} success and {failed} failed.",
            quote=True,
        )
    else:
        await m.reply_document(
            document="users-broadcast.txt",
            caption=f"Users broadcast completed in `{completed_in}`\n\nTotal users {total_users}.\nTotal done {done_broadcast}, {success} success and {failed} failed.",
            quote=True,
        )
    
    os.remove("users-broadcast.txt")
    return
  
@Gojo.on_message(command("chatbroadcast", dev_cmd=True))
async def chat_broadcast(c: Gojo, m: Message):
    
    if m.reply_to_message:
        broadcast_msg = m.reply_to_message
    else:
        await m.reply_text("Reply to a message to broadcast it")
        return

    exmsg = await m.reply_text("Started broadcasting!")

    total_chats = Chats.count_chats()

    await exmsg.edit(f"Started broadcasting!\n\nFound total **{total_chats} chats**.")

    chats_start_time = time()
    all_chats = (Chats.list_chats_full()) or {}

    done_broadcast = 0
    success, failed = 0, 0

    async with aiofiles.open("chats-broadcast.txt", "w") as broadcast_log_file:
        for chat in all_chats:
            sts, msg = await send_msg(user_id=int(chat["_id"]), message=broadcast_msg)
            if msg is not None:
                await broadcast_log_file.write(msg)
            if sts == 200:
                success += 1
            else:
                failed += 1
            done_broadcast += 1

    completed_in = datetime.timedelta(seconds=int(time() - chats_start_time))

    await exmsg.edit_text(
        f"Chats broadcasting completed ✅\nSent message to {done_broadcast} chats.",
    )

    if failed == 0:
        await m.reply_text(
            text=f"Chats broadcast completed in `{completed_in}`\n\nTotal chats {total_chats}.\nTotal done {done_broadcast}, {success} success and {failed} failed.",
            quote=True,
        )
    else:
        await m.reply_document(
            document="chats-broadcast.txt",
            caption=f"Chats broadcast completed in `{completed_in}`\n\nTotal chats {total_chats}.\nTotal done {done_broadcast}, {success} success and {failed} failed.",
            quote=True,
        )
    
    os.remove("chats-broadcast.txt")
    return

@Gojo.on_message(command(["cleandb","cleandatabase"],sudo_cmd=True))
async def cleeeen(c:Gojo,m:Message):
    x = await m.reply_text("Cleaning the database...")
    try:
        z = await clean_my_db(c,True,m.from_user.id)
        try:
            await x.delete()
        except Exception:
            pass
        await m.reply_text(z)
        return
    except Exception as e:
        await m.reply_text(e)
        await x.delete()
        LOGGER.error(e)
        LOGGER.error(format_exc())
        return

__PLUGIN__ = "devs"


__HELP__ = """
**DEV and SUDOERS commands**

**Owner's commands:**
• /restart : Restart the bot
• /update : To update the bot with the main stream repo

**Dev's commands:**
• /adddev : Reply to message or give me user id or username
• /logs : Return the logs of bot.
• /neofetch : Fetch neo.
• /eval : Evaluate the given python code.
• /exec : Execute the given code.
• /chatlist : Return the list of chats present in database
• /uptime : Return the uptime of the bot.
• /leavechat : Bot will leave the provided chat.
• /chatbroadcast : Broadcast the messge to chats.

**Sudoer's command:**
• /ping : return the ping of the bot.
• /cleandb : Delete useless junks from database (Automatically start cleaning it at 3:00:00 AM)

**Example:**
/ping
"""
