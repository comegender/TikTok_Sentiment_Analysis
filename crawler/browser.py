"""Playwright browser lifecycle management.

Launches Chromium with Chinese locale and randomized viewport.
Supports loading saved login state for authenticated scraping.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from loguru import logger
from playwright.sync_api import Browser, BrowserContext, sync_playwright

from common.config import get_config

_playwright = None
_browser: Browser | None = None

_STATE_FILE = Path(__file__).resolve().parent.parent / "config" / "browser_state.json"


def _random_viewport() -> tuple[int, int]:
    cfg = get_config()["crawler"]["browser"]
    w = random.randint(
        cfg.get("viewport_width", 1280), cfg.get("viewport_width", 1920)
    )
    h = random.randint(
        cfg.get("viewport_height", 720), cfg.get("viewport_height", 1080)
    )
    return w, h


def _load_state() -> dict | None:
    """Load saved browser storage state (cookies, etc.) if available."""
    if _STATE_FILE.exists():
        try:
            with open(_STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
            if state.get("cookies"):
                logger.info("Loaded saved login state ({} cookies)", len(state["cookies"]))
                return state
        except Exception:
            pass
    return None


def launch_browser() -> Browser:
    global _browser, _playwright
    if _browser is not None:
        return _browser

    cfg = get_config()["crawler"]
    _playwright = sync_playwright().start()
    _browser = _playwright.chromium.launch(
        headless=cfg.get("headless", True),
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ],
    )
    logger.info("Browser launched (headless={})", cfg.get("headless", True))
    return _browser


def new_context(**extra_kwargs) -> BrowserContext:
    """Create a new browser context, loading saved login state if available."""
    cfg = get_config()["crawler"]["browser"]
    w, h = _random_viewport()

    state = _load_state()
    if state:
        extra_kwargs["storage_state"] = state

    context = launch_browser().new_context(
        viewport={"width": w, "height": h},
        locale=cfg.get("locale", "zh-CN"),
        timezone_id=cfg.get("timezone_id", "Asia/Shanghai"),
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        **extra_kwargs,
    )
    logger.debug("New browser context: {}x{}", w, h)
    return context


def close_browser():
    global _browser, _playwright
    if _browser is not None:
        _browser.close()
        _browser = None
        logger.info("Browser closed")
    if _playwright is not None:
        _playwright.stop()
        _playwright = None
