"""Pure tic-tac-toe rules. No Telegram or bot imports."""

EMPTY = ""

# Rows, columns, and both diagonals. Exactly the eight standard wins.
_LINES = (
    (0, 1, 2),
    (3, 4, 5),
    (6, 7, 8),
    (0, 3, 6),
    (1, 4, 7),
    (2, 5, 8),
    (0, 4, 8),
    (2, 4, 6),
)


def new_board():
    """Return a fresh board of nine empty cells."""
    return [EMPTY for _ in range(9)]


def place(board, index, symbol):
    """Return a new board with symbol at index, or None if the move is illegal.

    Does not mutate the input list. index must be 0..8, the cell must be
    empty, and symbol must be "X" or "O".
    """
    if isinstance(index, bool) or not isinstance(index, int):
        return None
    if index < 0 or index > 8:
        return None
    if symbol not in {"X", "O"}:
        return None
    try:
        if board[index] != EMPTY:
            return None
    except (IndexError, TypeError):
        return None
    updated = list(board)
    updated[index] = symbol
    return updated


def winner(board):
    """Return "X", "O", "draw", or None if the game is still going."""
    if board is None or len(board) < 9:
        return None
    for a, b, c in _LINES:
        mark = board[a]
        if mark in {"X", "O"} and mark == board[b] == board[c]:
            return mark
    if len(board) == 9 and all(cell != EMPTY for cell in board):
        return "draw"
    return None
