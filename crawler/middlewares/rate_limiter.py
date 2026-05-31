"""Adaptive rate limiter with human-like delays.

Uses Gaussian-distributed waits between requests and enforces
per-session and daily request caps.
"""

import random
import time
from datetime import datetime

from loguru import logger

from common.config import get_config
from common.exceptions import RateLimitError


class RateLimiter:
    def __init__(self):
        cfg = get_config()["crawler"]["rate_limiting"]
        self.min_delay = cfg["min_delay_seconds"]
        self.max_delay = cfg["max_delay_seconds"]
        self.per_session = cfg["requests_per_session"]
        self.session_cooldown = cfg["session_cooldown_seconds"]
        self.daily_max = get_config()["ethical_limits"]["max_daily_requests"]

        self._session_count = 0
        self._today_count = 0
        self._today_date = datetime.now().date()

    def wait(self):
        self._reset_daily_counter()

        if self._today_count >= self.daily_max:
            raise RateLimitError(
                f"Daily request limit reached ({self.daily_max}). "
                f"Try again tomorrow."
            )

        if self._session_count >= self.per_session:
            logger.info("Session cooldown: {}s", self.session_cooldown)
            time.sleep(self.session_cooldown)
            self._session_count = 0

        delay = random.gauss(self.min_delay + 1.0, 0.8)
        delay = max(self.min_delay, min(self.max_delay, delay))
        logger.debug("Rate limit delay: {:.1f}s", delay)
        time.sleep(delay)

        self._session_count += 1
        self._today_count += 1

    def _reset_daily_counter(self):
        today = datetime.now().date()
        if today != self._today_date:
            self._today_count = 0
            self._today_date = today

    @property
    def today_count(self) -> int:
        self._reset_daily_counter()
        return self._today_count
