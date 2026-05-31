"""Command-line entry point for the Douyin scraper.

Usage:
    # Feed mode: scrape recommended videos from main page (no keyword)
    python scripts/run_scraper.py --mode feed --max-videos 20

    # Search mode: search keywords and scrape results
    python scripts/run_scraper.py --keywords "AI,科技" --max-videos 20 --no-comments
"""

import argparse
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.config import load_config
from common.logging_config import setup_logging
from crawler.platform import DouyinScraper
from storage.mongo_client import create_indexes, close_connection


def load_keywords(path: str | None = None) -> dict:
    if path is None:
        path = Path(__file__).resolve().parent.parent / "config" / "keywords.yaml"
    if not Path(path).exists():
        return {"keywords": ["人工智能"], "max_videos_per_keyword": 10, "max_comments_per_video": 50, "include_comments": True}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def main():
    parser = argparse.ArgumentParser(description="Douyin video scraper")
    parser.add_argument(
        "--mode", type=str, choices=["search", "feed"], default="search",
        help="Scraping mode: search (keywords) or feed (recommendations)",
    )
    parser.add_argument(
        "--keywords", type=str, default=None,
        help="Comma-separated search keywords (search mode only)",
    )
    parser.add_argument(
        "--max-videos", type=int, default=None,
        help="Max videos to scrape",
    )
    parser.add_argument(
        "--max-comments", type=int, default=None,
        help="Max comments per video",
    )
    parser.add_argument(
        "--no-comments", action="store_true",
        help="Skip comment scraping",
    )
    parser.add_argument(
        "--headful", action="store_true",
        help="Show browser window (disable headless mode)",
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    setup_logging(level="DEBUG" if args.debug else "INFO")
    load_config()

    kw_cfg = load_keywords()
    max_videos = args.max_videos or kw_cfg.get("max_videos_per_keyword", 10)
    max_comments = args.max_comments or kw_cfg.get("max_comments_per_video", 50)
    include_comments = not args.no_comments

    if args.headful:
        import common.config
        cfg = common.config.get_config()
        cfg["crawler"]["headless"] = False

    create_indexes()

    scraper = DouyinScraper()
    try:
        if args.mode == "feed":
            scraper.run_feed(
                max_videos=max_videos,
                include_comments=include_comments,
                max_comments_per_video=max_comments,
            )
        else:
            keywords = args.keywords.split(",") if args.keywords else kw_cfg.get("keywords", [])
            scraper.run(
                keywords=keywords,
                max_videos_per_keyword=max_videos,
                include_comments=include_comments,
                max_comments_per_video=max_comments,
            )
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    finally:
        close_connection()
        from crawler.browser import close_browser
        close_browser()


if __name__ == "__main__":
    main()
