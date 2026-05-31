"""Retry decorator with exponential backoff."""

import functools
import time

from loguru import logger

from common.exceptions import CrawlerError


def retry(max_attempts: int = 3, base_delay: float = 1.0, backoff_factor: float = 2.0):
    """Decorator: retry on CrawlerError with exponential backoff.

    Delays: base_delay, base_delay * backoff, base_delay * backoff^2, ...
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except CrawlerError as e:
                    last_exc = e
                    if attempt == max_attempts:
                        logger.error(
                            "{} failed after {} attempts: {}",
                            func.__name__, max_attempts, e,
                        )
                        raise
                    delay = base_delay * (backoff_factor ** (attempt - 1))
                    logger.warning(
                        "{} attempt {}/{} failed: {}. Retrying in {:.1f}s...",
                        func.__name__, attempt, max_attempts, e, delay,
                    )
                    time.sleep(delay)
            raise last_exc  # type: ignore[misc]
        return wrapper
    return decorator
