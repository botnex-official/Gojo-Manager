from collections import deque


def is_flood(timestamps, threshold, window, now):
    if len(timestamps) < threshold:
        return False
    return now - timestamps[-threshold] <= window


def is_duplicate(messages, limit):
    if len(messages) < limit:
        return False
    return len(set(messages[-limit:])) == 1
