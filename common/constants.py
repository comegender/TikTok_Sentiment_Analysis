"""Shared enums used across modules."""

from enum import Enum


class SentimentLabel(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class CommentType(str, Enum):
    COMMENT = "comment"
    DANMAKU = "danmaku"


class SourceType(str, Enum):
    VIDEO = "video"
    COMMENT = "comment"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
