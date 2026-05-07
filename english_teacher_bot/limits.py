"""Simple in-memory rate limiting and daily caps to protect against runaway costs.

Swap for Redis later if you go multi-instance.
"""
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Optional

import config

_minute_window: Dict[str, Deque[float]] = defaultdict(deque)
_daily_count: Dict[str, list] = defaultdict(lambda: [0, 0.0])  # [count, window_start_ts]


def check(user_id: str) -> Optional[str]:
    """Returns None if allowed, otherwise a user-facing error message."""
    # Allowlist
    if config.ALLOWED_NUMBERS and user_id not in config.ALLOWED_NUMBERS:
        return "Sorry, this bot is private."

    now = time.time()

    # Per-minute limit
    window = _minute_window[user_id]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= config.MAX_MSGS_PER_MINUTE:
        return "You're sending messages too fast. Please wait a moment."
    window.append(now)

    # Per-day limit
    count, day_start = _daily_count[user_id]
    if now - day_start > 86400:
        _daily_count[user_id] = [0, now]
        count = 0
    if count >= config.MAX_MSGS_PER_DAY:
        return "You've reached today's message limit. See you tomorrow!"
    _daily_count[user_id][0] = count + 1

    return None
