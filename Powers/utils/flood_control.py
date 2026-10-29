def register_hit(stamps, now, limit, within):
    """stamps: list of unix times for this user. Mutate a copy or the list.
    Drop stamps older than `within` seconds. Append `now`.
    If the remaining count >= limit, clear the list and return True (punish).
    Otherwise keep the trimmed list and return False.
    limit/within are ints >= 1. now is a number.
    Return (tripped: bool, new_stamps: list).
    Do not punish when the window has expired; only a fresh burst trips it.
    """
    fresh = [stamp for stamp in stamps if now - stamp <= within]
    fresh.append(now)
    if len(fresh) >= limit:
        fresh.clear()
        return True, fresh
    return False, fresh
