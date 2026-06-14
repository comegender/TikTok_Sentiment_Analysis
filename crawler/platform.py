"""Main crawler orchestration — search, scrape videos, collect comments.

Flow:
  1. Visit douyin.com to warm up cookies / fingerprint
  2. Search for keywords (intercepting search API responses)
  3. For each video: open page, intercept detail API response, optionally scrape comments
  4. Upsert everything into MongoDB

Key design: all API interception is done by setting up response listeners
BEFORE the browser navigates, so nothing is missed.
"""

from urllib.parse import quote

from loguru import logger
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from common.exceptions import CrawlerError
from crawler.browser import new_context
from crawler.middlewares.rate_limiter import RateLimiter
from crawler.middlewares.retry_handler import retry
from crawler.parsers.comment_parser import parse_comments_from_api
from crawler.parsers.video_parser import parse_video_from_api, parse_video_from_page
from crawler.stealth import apply_stealth
from storage.repository import count_comments, count_videos, insert_comments, upsert_video

DOUYIN_URL = "https://www.douyin.com"
SEARCH_URL = f"{DOUYIN_URL}/search/{{}}?type=general"
VIDEO_URL = f"{DOUYIN_URL}/video/{{}}"


def _extract_aweme_ids(obj, max_depth=5):
    """Recursively find all aweme_id strings in a nested dict/list."""
    if max_depth <= 0:
        return
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "aweme_id" and isinstance(value, (str, int)):
                yield str(value)
            elif isinstance(value, (dict, list)):
                yield from _extract_aweme_ids(value, max_depth - 1)
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, (dict, list)):
                yield from _extract_aweme_ids(item, max_depth - 1)


class DouyinScraper:
    """Orchestrates the full scrape workflow."""

    def __init__(self):
        self.limiter = RateLimiter()

    def run(
        self,
        keywords: list[str],
        max_videos_per_keyword: int = 20,
        include_comments: bool = True,
        max_comments_per_video: int = 100,
        max_replies_per_video: int = 20,
        manual_mode: bool = False,
    ):
        logger.info(
            "Starting keyword search scraper: keywords={}, max_videos={}, comments={}",
            keywords, max_videos_per_keyword, include_comments,
        )

        for keyword in keywords:
            try:
                aweme_ids = self._search(keyword, max_videos_per_keyword, manual_mode)
                logger.info("Keyword '{}': found {} videos", keyword, len(aweme_ids))
                for aweme_id in aweme_ids:
                    try:
                        self.limiter.wait()
                        self._scrape_video(aweme_id, include_comments, max_comments_per_video, max_replies_per_video)
                    except CrawlerError as e:
                        logger.error("Failed to scrape video {}: {}", aweme_id, e)
                        continue
            except CrawlerError as e:
                logger.error("Search failed for '{}': {}", keyword, e)
                continue

        logger.info(
            "Scraping done. videos={}, comments={}",
            count_videos(), count_comments(),
        )

    def run_feed(
        self,
        max_videos: int = 20,
        include_comments: bool = True,
        max_comments_per_video: int = 100,
        max_replies_per_video: int = 20,
        manual_mode: bool = False,
    ):
        """Scrape videos from the main page recommendation feed (no keyword search)."""
        logger.info(
            "Starting feed scraper: max_videos={}, comments={}",
            max_videos, include_comments,
        )

        aweme_ids = self._scrape_feed(max_videos)
        logger.info("Feed: found {} videos", len(aweme_ids))

        for aweme_id in aweme_ids:
            try:
                self.limiter.wait()
                self._scrape_video(aweme_id, include_comments, max_comments_per_video, max_replies_per_video)
            except CrawlerError as e:
                logger.error("Failed to scrape video {}: {}", aweme_id, e)
                continue

        logger.info(
            "Scraping done. videos={}, comments={}",
            count_videos(), count_comments(),
        )

    # ── search ──────────────────────────────────────────────────────────

    def _search(self, keyword: str, max_videos: int, manual_mode: bool = False) -> list[str]:
        """Search for a keyword. First warms up with main page, then intercepts
        search API responses for video IDs."""
        context = new_context()
        page = context.new_page()
        apply_stealth(page)

        captured_ids: list[str] = []

        def on_response(response):
            url = response.url
            path = url.split("douyin.com")[1].split("?")[0] if "douyin.com" in url else ""
            # 只从搜索接口提取视频 ID
            if "/aweme/v1/web/general/search/single/" in url and response.status == 200:
                try:
                    body = response.json()
                    for aid in _extract_aweme_ids(body):
                        if aid not in captured_ids:
                            captured_ids.append(aid)
                except Exception:
                    pass

        page.on("response", on_response)

        try:
            # Step 1: warm up — visit main page first to establish cookies
            page.goto(DOUYIN_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)

            # Step 2: simulate human search — type into search box on main page
            logger.debug("Simulating search for: {}", keyword)
            try:
                # Wait for search box to appear
                page.wait_for_selector('input[type="text"], input[placeholder*="搜索"], [class*="search"] input', timeout=5000)
                # Click the search box
                page.click('input[type="text"], input[placeholder*="搜索"], [class*="search"] input')
                page.wait_for_timeout(500)
                # Clear and type keyword character by character (human-like)
                page.keyboard.type(keyword, delay=100)
                page.wait_for_timeout(500)
                page.keyboard.press("Enter")
                logger.debug("Search submitted, waiting for results...")
            except Exception:
                # Fallback: direct URL navigation
                logger.debug("Fallback to direct URL search")
                search_url = SEARCH_URL.format(quote(keyword))
                page.goto(search_url, wait_until="domcontentloaded", timeout=30000)

            if manual_mode:
                input(
                    f"\n[MANUAL] 搜索 '{keyword}' 已提交。\n"
                    f"请在浏览器中完成验证码/短信验证，确认搜索结果已加载后，按 Enter 继续..."
                )

            page.wait_for_timeout(5000)

            # 从 DOM 提取视频链接（搜索结果的卡片）
            dom_ids = page.evaluate("""
            () => {
                const ids = [];
                document.querySelectorAll('a[href*="/video/"]').forEach(function(a) {
                    var m = a.href.match(/video\\/(\\d+)/);
                    if (m) ids.push(m[1]);
                });
                return ids;
            }
            """)
            logger.debug("DOM video IDs: {}", dom_ids)
            for aid in dom_ids:
                if aid not in captured_ids:
                    captured_ids.append(aid)

            # Step 3: scroll to load more results
            for _ in range(3):
                page.evaluate("window.scrollBy(0, 2000)")
                page.wait_for_timeout(2000)

        except PlaywrightTimeout:
            logger.warning("Search page load timed out for '{}'", keyword)
        except Exception as e:
            raise CrawlerError(f"Search failed for '{keyword}': {e}") from e
        finally:
            page.remove_listener("response", on_response)
            context.close()

        return list(dict.fromkeys(captured_ids))[:max_videos]

    # ── feed ────────────────────────────────────────────────────────────

    def _scrape_feed(self, max_videos: int) -> list[str]:
        """Collect video IDs from the main page recommendation feed API."""
        context = new_context()
        page = context.new_page()
        apply_stealth(page)

        captured_ids: list[str] = []

        def on_response(response):
            url = response.url
            if "/aweme/v2/web/module/feed/" in url and response.status == 200:
                try:
                    body = response.json()
                    for aid in _extract_aweme_ids(body):
                        if aid not in captured_ids:
                            captured_ids.append(aid)
                except Exception:
                    pass

        page.on("response", on_response)

        try:
            page.goto(DOUYIN_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)

            # Scroll to load more feed items (catch nav errors gracefully)
            for _ in range(max(max_videos // 10, 3)):
                if len(captured_ids) >= max_videos:
                    break
                try:
                    page.evaluate("window.scrollBy(0, 3000)")
                    page.wait_for_timeout(2000)
                except Exception:
                    break

        except PlaywrightTimeout:
            logger.warning("Feed page load timed out")
        except Exception as e:
            raise CrawlerError(f"Feed scraping failed: {e}") from e
        finally:
            page.remove_listener("response", on_response)
            context.close()

        logger.debug("Feed captured IDs: {}", captured_ids)
        return list(dict.fromkeys(captured_ids))[:max_videos]

    # ── video detail ────────────────────────────────────────────────────

    def _scrape_video(self, aweme_id: str, include_comments: bool, max_comments: int,
                       max_replies: int = 20):
        """Scrape a single video + optionally its comments.

        Sets up response listeners BEFORE navigation so the video detail
        API call triggered by page load is always captured.
        """
        context = new_context()
        page = context.new_page()
        apply_stealth(page)

        video_data: list[dict] = []
        comments_data: list[dict] = []

        def on_video_response(response):
            if "/aweme/v1/web/aweme/detail/" in response.url and response.status == 200:
                try:
                    video_data.append(response.json())
                except Exception:
                    pass

        def on_comment_response(response):
            if "/aweme/v1/web/comment/list/" in response.url and response.status == 200:
                try:
                    comments_data.append(response.json())
                except Exception:
                    pass

        def on_reply_response(response):
            if "/aweme/v1/web/comment/list/reply/" in response.url and response.status == 200:
                try:
                    body = response.json()
                    comments = parse_comments_from_api(body, aweme_id)
                    if comments:
                        insert_comments(comments)
                except Exception:
                    pass

        page.on("response", on_video_response)
        page.on("response", on_comment_response)
        page.on("response", on_reply_response)

        try:
            page.goto(VIDEO_URL.format(aweme_id), wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)  # wait for API responses to arrive

            video = None
            if video_data:
                video = parse_video_from_api(video_data[0])
            if video is None:
                video = parse_video_from_page(page)
            if video is None:
                logger.warning("No video data for {}", aweme_id)
                return

            upsert_video(video)

            # Parse initial comments and extract cursor for pagination
            start_cursor = 0
            for data in comments_data:
                for c in parse_comments_from_api(data, aweme_id):
                    insert_comments([c])
                # Use cursor from the last response as pagination start
                if data.get("cursor"):
                    start_cursor = data["cursor"]

            if include_comments:
                self._scroll_for_comments(page, aweme_id, max_comments, start_cursor)
                self._load_comment_replies(page, aweme_id, max_replies)

            logger.info(
                "Video {}: '{}' — done",
                aweme_id, video.desc[:30] if video.desc else "(no desc)",
            )

        except PlaywrightTimeout:
            logger.warning("Video page load timed out: {}", aweme_id)
        except Exception as e:
            raise CrawlerError(f"Scrape failed for video {aweme_id}: {e}") from e
        finally:
            page.remove_listener("response", on_video_response)
            page.remove_listener("response", on_comment_response)
            page.remove_listener("response", on_reply_response)
            context.close()

    def _load_comment_replies(self, page, aweme_id: str, max_replies: int):
        """Fetch and parse comment replies, stopping when max_replies is reached."""
        if max_replies <= 0:
            return
        from storage.repository import _db

        parent_comments = list(
            _db().comments.find(
                {"aweme_id": aweme_id, "reply_to_cid": None, "reply_count": {"$gt": 0}}
            )
        )
        if not parent_comments:
            logger.debug("No comments with replies to load for {}", aweme_id)
            return

        logger.info(
            "Loading replies for {} comments (max {})",
            len(parent_comments), max_replies,
        )

        inserted = 0
        for cid in [c["cid"] for c in parent_comments]:
            if inserted >= max_replies:
                break
            try:
                self.limiter.wait()
                result = page.evaluate(
                    """
                    async (params) => {
                        const url = '/aweme/v1/web/comment/list/reply/'
                            + '?comment_id=' + params.cid
                            + '&item_id=' + params.item_id
                            + '&cursor=0&count=20';
                        const r = await fetch(url, {
                            credentials: 'include',
                            headers: {
                                'Referer': 'https://www.douyin.com/video/'
                                    + params.item_id,
                            }
                        });
                        if (!r.ok) return null;
                        return r.json();
                    }
                    """,
                    {"cid": cid, "item_id": aweme_id},
                )
                if result:
                    replies = parse_comments_from_api(result, aweme_id)
                    if replies:
                        inserted += insert_comments(replies)
            except Exception as e:
                logger.warning("Failed to load replies for {}: {}", cid[:12], e)
                continue

        if inserted > 0:
            logger.info("Inserted {} reply comments for {}", inserted, aweme_id)

    def _scroll_for_comments(self, page, aweme_id: str, max_comments: int,
                             start_cursor: int = 0):
        """Load comments via direct API pagination, starting from start_cursor."""
        from storage.repository import _db

        def _current_count() -> int:
            return _db().comments.count_documents({"aweme_id": aweme_id})

        target = max_comments
        initial_count = _current_count()
        cursor = start_cursor
        has_more = cursor > 0  # only true if initial response gave us a cursor
        max_rounds = 30

        for _ in range(max_rounds):
            if not has_more:
                break
            if _current_count() - initial_count >= target:
                break

            self.limiter.wait()
            try:
                result = page.evaluate(
                    """
                    (params) => {
                        const url = '/aweme/v1/web/comment/list/'
                            + '?aweme_id=' + params.aweme_id
                            + '&cursor=' + params.cursor
                            + '&count=20';
                        return fetch(url, {
                            credentials: 'include',
                            headers: {
                                'Referer': 'https://www.douyin.com/video/'
                                    + params.aweme_id,
                            }
                        }).then(r => {
                            if (!r.ok) throw new Error('HTTP ' + r.status);
                            return r.json();
                        });
                    }
                    """,
                    {"aweme_id": aweme_id, "cursor": cursor},
                )
                comments = parse_comments_from_api(result, aweme_id)
                if comments:
                    insert_comments(comments)
                cursor = result.get("cursor", 0)
                has_more = bool(result.get("has_more", False) and cursor)
            except Exception as e:
                logger.warning("Comment pagination failed: {}", e)
                break

        collected = _current_count() - initial_count
        logger.info(
            "Comment pagination for {}: collected {} (target {})",
            aweme_id, collected, target,
        )
