"""Parse Douyin comments from intercepted API responses.

Comments are loaded via paginated XHR calls when scrolling.
We intercept these responses to get clean JSON data.
"""

import json
import re
from datetime import datetime

from loguru import logger
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from common.exceptions import ParseError
from storage.models import Comment, CommentUser


def parse_comments_from_api(json_data: dict, aweme_id: str) -> list[Comment]:
    """Parse a list of Comments from the comment list API response JSON."""
    comments = []
    try:
        comment_list = json_data.get("comments") or []
        for item in comment_list:
            user_raw = item.get("user", {})
            user = CommentUser(
                uid=str(user_raw.get("uid", "")),
                nickname=user_raw.get("nickname", ""),
                ip_location=item.get("ip_label", "")
                or user_raw.get("ip_location", ""),
            )

            create_time = None
            ts = item.get("create_time")
            if ts:
                create_time = datetime.fromtimestamp(ts)

            reply_id = item.get("reply_comment_id")
            reply_to = str(reply_id) if reply_id else None

            comment = Comment(
                cid=str(item.get("cid", "")),
                aweme_id=aweme_id,
                text=item.get("text", ""),
                create_time=create_time,
                user=user,
                digg_count=item.get("digg_count", 0),
                reply_count=item.get("reply_comment_count", 0)
                or item.get("reply_count", 0),
                reply_to_cid=reply_to,
            )
            comments.append(comment)

    except Exception as e:
        raise ParseError(f"Failed to parse comment API response: {e}") from e

    return comments


def wait_for_comments_api(
    page: Page,
    aweme_id: str,
    max_comments: int = 100,
    timeout_ms: int = 10000,
) -> list[Comment]:
    """Scroll the comment area to trigger loading, intercept API responses.

    Returns all captured comments, deduplicated by cid.
    """
    all_comments: dict[str, Comment] = {}

    def on_response(response):
        url = response.url
        if "/aweme/v1/web/comment/list/" in url and response.status == 200:
            try:
                body = response.json()
                for c in parse_comments_from_api(body, aweme_id):
                    if c.cid not in all_comments:
                        all_comments[c.cid] = c
            except Exception:
                pass

    page.on("response", on_response)

    _scroll_comments(page, max_comments, timeout_ms)

    page.remove_listener("response", on_response)

    comments = list(all_comments.values())
    logger.info("Captured {} comments for video {}", len(comments), aweme_id)
    return comments


def _scroll_comments(page: Page, max_comments: int, timeout_ms: int):
    """Repeatedly scroll the comment area to trigger more API calls."""
    scroll_js = """
    () => {
        const selectors = [
            '.comment-mainContent',
            '[data-e2e="comment-list"]',
            '.comment-container',
            '[class*="comment"]',
        ];
        for (const sel of selectors) {
            const el = document.querySelector(sel);
            if (el) {
                el.scrollTop = el.scrollHeight;
                return true;
            }
        }
        window.scrollBy(0, 3000);
        return false;
    }
    """

    for i in range(max(max_comments // 20, 1)):
        try:
            page.evaluate(scroll_js)
            page.wait_for_timeout(1500)
        except Exception:
            break
