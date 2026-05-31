"""Pydantic models for data validation."""

from datetime import datetime

from pydantic import BaseModel, Field


class Author(BaseModel):
    uid: str
    nickname: str = ""
    signature: str = ""
    avatar_url: str = ""
    follower_count: int = 0
    ip_location: str = ""


class Statistics(BaseModel):
    digg_count: int = 0
    comment_count: int = 0
    share_count: int = 0
    play_count: int = 0


class Video(BaseModel):
    aweme_id: str
    desc: str = ""
    create_time: datetime | None = None
    author: Author = Field(default_factory=Author)
    statistics: Statistics = Field(default_factory=Statistics)
    hashtags: list[str] = Field(default_factory=list)
    video_url: str = ""
    scraped_at: datetime = Field(default_factory=datetime.utcnow)


class CommentUser(BaseModel):
    uid: str = ""
    nickname: str = ""
    ip_location: str = ""


class Comment(BaseModel):
    cid: str
    aweme_id: str
    text: str
    create_time: datetime | None = None
    user: CommentUser = Field(default_factory=CommentUser)
    digg_count: int = 0
    reply_count: int = 0
    reply_to_cid: str | None = None
    scraped_at: datetime = Field(default_factory=datetime.utcnow)


class SentimentResult(BaseModel):
    source_type: str  # "video" | "comment"
    source_id: str    # aweme_id | cid
    original_text: str = ""
    cleaned_text: str = ""
    tokens: list[str] = Field(default_factory=list)
    sentiment_label: str = ""  # positive | negative | neutral
    sentiment_score: float = 0.0
    sentiment_polarity: float = 0.0
    aspects: list[dict] = Field(default_factory=list)
    model_name: str = ""
    analyzed_at: datetime = Field(default_factory=datetime.utcnow)
