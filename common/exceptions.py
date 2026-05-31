"""Custom exception hierarchy — enables precise error handling per layer."""


class DouyinResearchError(Exception):
    """Base exception for all project errors."""


class CrawlerError(DouyinResearchError):
    """Raised when scraping encounters an error."""


class RateLimitError(CrawlerError):
    """Raised when request rate exceeds configured limits."""


class ParseError(CrawlerError):
    """Raised when HTML/API response parsing fails."""


class ConfigError(DouyinResearchError):
    """Raised when configuration is missing or invalid."""
