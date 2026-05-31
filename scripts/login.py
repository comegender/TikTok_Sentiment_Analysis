"""Interactive login script — saves browser state (cookies) for reuse.

Usage:
    python scripts/login.py

This opens a browser window on douyin.com. You scan the QR code
or log in manually, then press Enter. The session is saved to
config/browser_state.json and will be reused by the scraper.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger

from common.config import load_config
from common.logging_config import setup_logging
from crawler.browser import launch_browser, close_browser

STATE_FILE = Path(__file__).resolve().parent.parent / "config" / "browser_state.json"


def main():
    setup_logging(level="INFO")
    cfg = load_config()
    cfg["crawler"]["headless"] = False  # force visible browser for login

    browser = launch_browser()
    context = browser.new_context(
        viewport={"width": 1280, "height": 900},
        locale="zh-CN",
        timezone_id="Asia/Shanghai",
    )
    page = context.new_page()

    # Apply stealth
    from crawler.stealth import apply_stealth
    apply_stealth(page)

    logger.info("Opening douyin.com — please log in (scan QR code)...")
    page.goto("https://www.douyin.com", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(2000)

    input("After logging in, press Enter here to save session...")

    # Save browser state
    state = context.storage_state()
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    logger.info("Session saved to {}", STATE_FILE)

    context.close()
    close_browser()
    logger.info("Done.")


if __name__ == "__main__":
    main()
