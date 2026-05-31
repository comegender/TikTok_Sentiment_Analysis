"""CRUD operations for scraped data."""

from loguru import logger
from pymongo.database import Database
from pymongo.results import InsertOneResult

from storage.models import Comment, SentimentResult, Video


def _db() -> Database:
    from storage.mongo_client import get_database
    return get_database()


# ---- videos ----

def upsert_video(video: Video) -> bool:
    doc = video.model_dump()
    result = _db().videos.update_one(
        {"aweme_id": video.aweme_id},
        {"$set": doc},
        upsert=True,
    )
    return result.upserted_id is not None or result.modified_count > 0


def find_video(aweme_id: str) -> dict | None:
    return _db().videos.find_one({"aweme_id": aweme_id})


def count_videos() -> int:
    return _db().videos.count_documents({})


# ---- comments ----

def insert_comments(comments: list[Comment]) -> int:
    if not comments:
        return 0
    inserted = 0
    for c in comments:
        doc = c.model_dump()
        try:
            _db().comments.update_one(
                {"cid": c.cid},
                {"$set": doc},
                upsert=True,
            )
            inserted += 1
        except Exception as e:
            logger.warning("Failed to upsert comment {}: {}", c.cid, e)
    return inserted


def count_comments() -> int:
    return _db().comments.count_documents({})


# ---- sentiment_results ----

def upsert_sentiment_result(result: SentimentResult) -> bool:
    doc = result.model_dump()
    r = _db().sentiment_results.update_one(
        {"source_id": result.source_id, "source_type": result.source_type},
        {"$set": doc},
        upsert=True,
    )
    return r.upserted_id is not None or r.modified_count > 0


def find_unanalyzed_comments(limit: int = 500) -> list[dict]:
    """Find comments that haven't been analyzed yet."""
    analyzed_ids = {
        r["source_id"]
        for r in _db().sentiment_results.find(
            {"source_type": "comment"},
            {"source_id": 1},
        )
    }
    return list(
        _db().comments.find(
            {"cid": {"$nin": list(analyzed_ids)}},
            limit=limit,
        )
    )
