"""Run sentiment analysis on unanalyzed comments.

Usage:
    python analyzer/run_analysis.py                # 分析全部未分析评论
    python analyzer/run_analysis.py --task opinion  # 观点抽取
    python analyzer/run_analysis.py --limit 50     # 只分析 50 条
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger

from common.config import load_config
from common.logging_config import setup_logging
from storage.mongo_client import create_indexes, close_connection
from storage.repository import find_unanalyzed_comments, upsert_sentiment_result
from storage.models import SentimentResult
from analyzer.sentiment import SentimentAnalyzer


def main():
    parser = argparse.ArgumentParser(description="Sentiment analysis runner")
    parser.add_argument("--task", choices=["sentiment", "opinion"], default="sentiment")
    parser.add_argument("--limit", type=int, default=0,
                        help="Max comments to analyze (0 = all)")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    setup_logging(level="DEBUG" if args.debug else "INFO")
    load_config()
    create_indexes()

    analyzer = SentimentAnalyzer()  # auto-detect GPU/CPU

    while True:
        batch = find_unanalyzed_comments(limit=100)
        if not batch:
            logger.info("No unanalyzed comments remaining.")
            break

        if args.limit > 0:
            analyzed_so_far = 0  # approximate
            if analyzed_so_far + len(batch) > args.limit:
                batch = batch[:args.limit - analyzed_so_far]

        logger.info("Analyzing {} comments (task={}) ...", len(batch), args.task)

        if args.task == "sentiment":
            results = analyzer.batch_sentiment(batch)
        else:
            # opinion extraction — store as sentiment + aspects
            results = []
            for c in batch:
                text = c.get("text", "")
                opinions = analyzer.extract_opinions(text)
                results.append({
                    "source_type": "comment",
                    "source_id": c.get("cid", ""),
                    "original_text": text,
                    "sentiment_label": "",
                    "sentiment_score": 0.0,
                    "aspects": opinions,
                })

        for r in results:
            sr = SentimentResult(
                source_type=r["source_type"],
                source_id=r["source_id"],
                original_text=r["original_text"],
                sentiment_label=r["sentiment_label"],
                sentiment_score=r.get("sentiment_score", 0.0),
                aspects=r.get("aspects", []),
                model_name="Qwen2.5-1.5B-Instruct",
            )
            upsert_sentiment_result(sr)

        logger.info("Inserted {} results.", len(results))

    close_connection()
    logger.info("Analysis complete.")


if __name__ == "__main__":
    main()
