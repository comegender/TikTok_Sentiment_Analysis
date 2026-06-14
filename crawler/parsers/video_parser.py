"""Parse Douyin video detail from API response JSON or page JS state."""

from datetime import datetime

from loguru import logger
from playwright.sync_api import Page

from common.exceptions import ParseError
from storage.models import Author, Statistics, Video


def parse_video_from_api(json_data: dict) -> Video | None:
    """Parse a Video from the video detail API response JSON."""
    try:
        aweme = json_data.get("aweme_detail") or json_data
        if not aweme or not aweme.get("aweme_id"):
            return None

        aweme_id = str(aweme["aweme_id"])

        author_raw = aweme.get("author", {})
        author = Author(
            uid=str(author_raw.get("uid", "")),
            nickname=author_raw.get("nickname", ""),
            signature=author_raw.get("signature", ""),
            avatar_url=(
                author_raw.get("avatar_thumb", {}).get("url_list", [""])[0]
                if isinstance(author_raw.get("avatar_thumb"), dict)
                else ""
            ),
            follower_count=author_raw.get("follower_count", 0),
            ip_location=author_raw.get("ip_location", "") or aweme.get("ip_label", ""),
        )

        stats_raw = aweme.get("statistics", {})
        statistics = Statistics(
            digg_count=stats_raw.get("digg_count", 0),
            comment_count=stats_raw.get("comment_count", 0),
            share_count=stats_raw.get("share_count", 0),
            play_count=stats_raw.get("play_count", 0),
        )

        create_time = None
        ts = aweme.get("create_time")
        if ts:
            create_time = datetime.fromtimestamp(ts)

        hashtags = [
            tag["hashtag_name"]
            for tag in (aweme.get("text_extra") or [])
            if tag.get("hashtag_name")
        ]

        video = Video(
            aweme_id=aweme_id,
            desc=aweme.get("desc", ""),
            create_time=create_time,
            author=author,
            statistics=statistics,
            hashtags=hashtags,
            video_url=f"https://www.douyin.com/video/{aweme_id}",
        )
        logger.debug("Parsed video: {} ({})", video.desc[:40], aweme_id)
        return video

    except Exception as e:
        raise ParseError(f"Failed to parse video API response: {e}") from e


def parse_video_from_page(page: Page) -> Video | None:
    """Fallback: extract video data from page JS state or embedded script tags."""
    try:
        data = page.evaluate("""
        () => {
            const ids = ['__UNIVERSAL_DATA__', 'RENDER_DATA'];
            for (const id of ids) {
                const el = document.getElementById(id);
                if (el && el.textContent) {
                    try { return JSON.parse(el.textContent); } catch(e) {}
                }
            }
            for (const key of ['__INITIAL_STATE__']) {
                if (window[key]) return window[key];
            }
            return null;
        }
        """)
        if data:
            # The data might be wrapped or direct
            if "aweme_detail" in data:
                return parse_video_from_api(data)
            # Some pages nest it differently, try a few common paths
            for path in ["videoInfo", "video", "aweme"]:
                inner = data
                for part in path.split("."):
                    inner = inner.get(part) if isinstance(inner, dict) else None
                if inner and isinstance(inner, dict) and "aweme_id" in str(inner):
                    return parse_video_from_api({"aweme_detail": inner})
    except Exception:
        pass
    return None
