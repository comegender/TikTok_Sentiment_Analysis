"""MongoDB connection management and index creation."""

from loguru import logger
from pymongo import ASCENDING, DESCENDING, IndexModel, MongoClient
from pymongo.database import Database

from common.config import get_config


_client: MongoClient | None = None
_db: Database | None = None


def get_client() -> MongoClient:
    global _client
    if _client is None:
        config = get_config()
        _client = MongoClient(config["mongodb"]["uri"])
        logger.info("MongoDB connected: {}", config["mongodb"]["uri"])
    return _client


def get_database() -> Database:
    global _db
    if _db is None:
        config = get_config()
        _db = get_client().get_database(config["mongodb"]["database"])
    return _db


def create_indexes():
    db = get_database()

    db.videos.create_indexes([
        IndexModel([("aweme_id", ASCENDING)], unique=True, name="idx_aweme_id"),
        IndexModel([("create_time", DESCENDING)], name="idx_video_create_time"),
        IndexModel([("hashtags", ASCENDING)], name="idx_hashtags"),
        IndexModel([("author.uid", ASCENDING)], name="idx_author_uid"),
    ])
    logger.info("videos indexes created")

    db.comments.create_indexes([
        IndexModel([("cid", ASCENDING)], unique=True, name="idx_cid"),
        IndexModel([("aweme_id", ASCENDING), ("create_time", DESCENDING)], name="idx_aweme_comment_time"),
    ])
    logger.info("comments indexes created")

    db.sentiment_results.create_indexes([
        IndexModel([("source_id", ASCENDING), ("source_type", ASCENDING)], unique=True, name="idx_source"),
        IndexModel([("sentiment.label", ASCENDING)], name="idx_sentiment_label"),
        IndexModel([("analyzed_at", DESCENDING)], name="idx_analyzed_at"),
    ])
    logger.info("sentiment_results indexes created")


def close_connection():
    global _client, _db
    if _client is not None:
        _client.close()
        _client = None
        _db = None
        logger.info("MongoDB connection closed")
