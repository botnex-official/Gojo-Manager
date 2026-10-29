from asyncio import Lock
from html import escape

from pyrogram import enums
from pyrogram.enums import ChatType
from pyrogram.filters import regex
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from Powers.bot_class import Gojo
from Powers.utils.custom_filters import command
from Powers.utils.tictactoe import new_board, place, winner

# One game per chat. Never share a board across chat ids.
GAMES = {}
LOCKS = {}

_NOT_FOR_YOU = "This challenge is not for you."
_NOT_YOUR_TURN = "Not your turn."
_TAKEN = "That square is taken."
_OVER = "This game is already over."


def _html_name(user) -> str:
    """HTML mention when Pyrogram provides one, otherwise escaped first name."""
    if user is None:
        return "Unknown"
    mention = None
    try:
        mention = getattr(user, "mention", None)
    except Exception:
        mention = None
    if isinstance(mention, str) and mention:
        return mention
    first_name = getattr(user, "first_name", None) or "Unknown"
    return escape(str(first_name))


def _room(message) -> str:
    chat = getattr(message, "chat", None)
    if chat is None:
        return "other"
    chat_type = getattr(chat, "type", None)
    if chat_type == ChatType.PRIVATE:
        return "private"
    if chat_type in {ChatType.GROUP, ChatType.SUPERGROUP}:
        return "group"
    return "other"


def _human_opponent(message):
    """The replied-to human, or None if the reply cannot be challenged."""
    reply = getattr(message, "reply_to_message", None)
    user = getattr(reply, "from_user", None) if reply is not None else None
    if user is None or getattr(user, "is_bot", False):
        return None
    actor = getattr(message, "from_user", None)
    if actor is None or getattr(user, "id", None) == getattr(actor, "id", None):
        return None
    if getattr(user, "id", None) is None:
        return None
    return user


def _challenge_markup():
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("Accept", callback_data="ttt:a"),
            InlineKeyboardButton("Decline", callback_data="ttt:d"),
        ]],
    )


def _board_markup(board):
    rows = []
    for row in range(3):
        buttons = []
        for col in range(3):
            index = row * 3 + col
            mark = board[index]
            label = mark if mark in {"X", "O"} else str(index + 1)
            buttons.append(
                InlineKeyboardButton(label, callback_data=f"ttt:{index}"),
            )
        rows.append(buttons)
    return InlineKeyboardMarkup(rows)


def _header(game) -> str:
    return (
        f"{game['challenger_mention']} (X) vs "
        f"{game['opponent_mention']} (O)"
    )


def _turn_line(game) -> str:
    if game["turn"] == "X":
        who = game["challenger_mention"]
    else:
        who = game["opponent_mention"]
    return f"Turn: {who} ({game['turn']})"


async def _safe_answer(query, text=None, alert=False):
    try:
        if text:
            await query.answer(text, show_alert=alert)
        else:
            await query.answer()
    except Exception:
        return


async def _edit(message, text, markup="keep"):
    kwargs = {"parse_mode": enums.ParseMode.HTML}
    if markup != "keep":
        kwargs["reply_markup"] = markup
    try:
        await message.edit_text(text, **kwargs)
    except Exception:
        return


def _lock(chat_id):
    lock = LOCKS.get(chat_id)
    if lock is None:
        lock = Lock()
        LOCKS[chat_id] = lock
    return lock


def _pop_game(chat_id, game):
    if GAMES.get(chat_id) is game:
        GAMES.pop(chat_id, None)
        LOCKS.pop(chat_id, None)


@Gojo.on_message(command(["tictactoe", "ttt"]))
async def tictactoe_command(_, m: Message):
    if getattr(m, "from_user", None) is None:
        return
    room = _room(m)
    if room == "private":
        await m.reply_text("Use this command in a group.")
        return
    if room != "group":
        return
    opponent = _human_opponent(m)
    if opponent is None:
        await m.reply_text("Reply to the opponent.")
        return
    chat_id = m.chat.id
    async with _lock(chat_id):
        if chat_id in GAMES:
            await m.reply_text(
                "A tic-tac-toe game or challenge is already going in this chat.",
            )
            return
        game = {
            "challenger_id": m.from_user.id,
            "opponent_id": opponent.id,
            "board": new_board(),
            "turn": "X",
            "message_id": None,
            "accepted": False,
            "challenger_mention": _html_name(m.from_user),
            "opponent_mention": _html_name(opponent),
        }
        GAMES[chat_id] = game
        try:
            sent = await m.reply_text(
                (
                    f"{game['challenger_mention']} challenged "
                    f"{game['opponent_mention']} to tic-tac-toe.\n"
                    f"{game['opponent_mention']}, accept or decline?"
                ),
                reply_markup=_challenge_markup(),
                parse_mode=enums.ParseMode.HTML,
            )
        except Exception:
            _pop_game(chat_id, game)
            return
        if GAMES.get(chat_id) is not game:
            return
        game["message_id"] = sent.id


@Gojo.on_message(command("tttstop"))
async def tttstop_command(c: Gojo, m: Message):
    if getattr(m, "from_user", None) is None:
        return
    room = _room(m)
    if room == "private":
        await m.reply_text("Use this command in a group.")
        return
    if room != "group":
        return
    chat_id = m.chat.id
    async with _lock(chat_id):
        game = GAMES.get(chat_id)
        if game is None:
            await m.reply_text("There is no tic-tac-toe game in this chat.")
            return
        player_ids = {game["challenger_id"], game["opponent_id"]}
        if m.from_user.id not in player_ids:
            await m.reply_text("Only the two players can cancel this game.")
            return
        message_id = game.get("message_id")
        _pop_game(chat_id, game)
        await m.reply_text("Tic-tac-toe cancelled.")
        if not message_id:
            return
        try:
            await c.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="Tic-tac-toe was cancelled.",
                reply_markup=InlineKeyboardMarkup([]),
            )
        except Exception:
            return


@Gojo.on_callback_query(regex(r"^ttt:([ad]|[0-8])$"))
async def ttt_callback(_, q: CallbackQuery):
    user = getattr(q, "from_user", None)
    if user is None:
        return
    message = getattr(q, "message", None)
    chat = getattr(message, "chat", None) if message is not None else None
    data = getattr(q, "data", None)
    if chat is None or not data:
        return
    chat_id = chat.id
    async with _lock(chat_id):
        game = GAMES.get(chat_id)
        if game is None or message.id != game.get("message_id"):
            await _safe_answer(q)
            return
        action = data.split(":", 1)[1]
        if action in {"a", "d"}:
            await _challenge_action(q, chat_id, game, user, action)
            return
        await _move(q, chat_id, game, user, int(action))


async def _challenge_action(q, chat_id, game, user, action):
    if user.id != game["opponent_id"]:
        await _safe_answer(q, _NOT_FOR_YOU, alert=True)
        return
    if GAMES.get(chat_id) is not game:
        await _safe_answer(q)
        return
    if action == "d":
        if game["accepted"]:
            await _safe_answer(q)
            return
        _pop_game(chat_id, game)
        await _edit(
            q.message,
            f"{_html_name(user)} declined the tic-tac-toe challenge.",
            markup=InlineKeyboardMarkup([]),
        )
        await _safe_answer(q)
        return
    if game["accepted"]:
        await _safe_answer(q)
        return
    game["accepted"] = True
    game["board"] = new_board()
    game["turn"] = "X"
    await _edit(
        q.message,
        f"{_header(game)}\n{_turn_line(game)}",
        markup=_board_markup(game["board"]),
    )
    await _safe_answer(q)


async def _move(q, chat_id, game, user, index):
    if GAMES.get(chat_id) is not game or not game["accepted"]:
        await _safe_answer(q)
        return
    if winner(game["board"]) is not None:
        _pop_game(chat_id, game)
        await _safe_answer(q, _OVER, alert=True)
        return
    symbol = game["turn"]
    expected = game["challenger_id"] if symbol == "X" else game["opponent_id"]
    if user.id != expected:
        await _safe_answer(q, _NOT_YOUR_TURN, alert=True)
        return
    if GAMES.get(chat_id) is not game:
        await _safe_answer(q)
        return
    updated = place(game["board"], index, symbol)
    if updated is None:
        await _safe_answer(q, _TAKEN, alert=True)
        return
    if GAMES.get(chat_id) is not game:
        await _safe_answer(q)
        return
    game["board"] = updated
    result = winner(updated)
    if result in {"X", "O"}:
        _pop_game(chat_id, game)
        await _edit(
            q.message,
            f"{_header(game)}\n{_html_name(user)} ({symbol}) wins!",
            markup=_board_markup(updated),
        )
        await _safe_answer(q)
        return
    if result == "draw":
        _pop_game(chat_id, game)
        await _edit(
            q.message,
            f"{_header(game)}\nIt's a draw.",
            markup=_board_markup(updated),
        )
        await _safe_answer(q)
        return
    game["turn"] = "O" if symbol == "X" else "X"
    await _edit(
        q.message,
        f"{_header(game)}\n{_turn_line(game)}",
        markup=_board_markup(game["board"]),
    )
    await _safe_answer(q)


async def _roll_die(m: Message) -> int:
    reply_dice = getattr(m, "reply_dice", None)
    if reply_dice is None:
        raise RuntimeError("reply_dice is unavailable")
    sent = await reply_dice()
    dice = getattr(sent, "dice", None)
    value = getattr(dice, "value", None)
    if not isinstance(value, int):
        raise RuntimeError("dice value missing")
    return value


def _duel_outcome(name_a, score_a, name_b, score_b) -> str:
    if score_a > score_b:
        return f"{name_a} wins!"
    if score_b > score_a:
        return f"{name_b} wins!"
    return "It's a draw."


@Gojo.on_message(command(["duel", "diceduel"]))
async def dice_duel(_, m: Message):
    if getattr(m, "from_user", None) is None:
        return
    room = _room(m)
    if room == "private":
        await m.reply_text("Use this command in a group.")
        return
    if room != "group":
        return
    opponent = _human_opponent(m)
    if opponent is None:
        await m.reply_text("Reply to the opponent.")
        return
    name_a = _html_name(m.from_user)
    name_b = _html_name(opponent)
    try:
        score_a = await _roll_die(m)
        score_b = await _roll_die(m)
        lines = [
            "Dice duel",
            f"{name_a}: {score_a}",
            f"{name_b}: {score_b}",
        ]
        if score_a == score_b:
            lines.append("Tie. One reroll each.")
            score_a = await _roll_die(m)
            score_b = await _roll_die(m)
            lines.append(f"{name_a}: {score_a}")
            lines.append(f"{name_b}: {score_b}")
        lines.append(_duel_outcome(name_a, score_a, name_b, score_b))
    except Exception:
        await m.reply_text("Couldn't roll the dice. Try again.")
        return
    await m.reply_text(
        "\n".join(lines),
        parse_mode=enums.ParseMode.HTML,
    )


__PLUGIN__ = "games"
__alt_name__ = ["tictactoe", "ttt", "duel"]

__HELP__ = """
**Games**

• /tictactoe or /ttt: Reply to someone in a group to challenge them. Only the opponent can accept or decline. X starts. Only the player whose turn it is can move.
• /tttstop: Cancel this chat's tic-tac-toe game. Only the two players can use it.
• /duel or /diceduel: Reply to someone in a group to roll dice. Higher roll wins. A tie gets one reroll each, then a draw. No bets.
"""
