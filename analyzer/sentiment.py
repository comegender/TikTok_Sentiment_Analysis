"""Sentiment analysis using Qwen2.5-1.5B-Instruct via ModelScope.

Supports: sentiment classification, opinion extraction, user profiling.
"""

import re
from dataclasses import dataclass

from loguru import logger


@dataclass
class SentimentResult:
    label: str       # "positive" | "negative" | "neutral"
    score: float     # 0.0 ~ 1.0


# ── Prompt templates ──

SENTIMENT_PROMPT = """判断以下抖音评论的情感倾向。

规则：
- 仅回复一个词：positive（正面）、negative（负面）或 neutral（中性）
- 如果评论包含明显的正面情绪（喜欢、赞美、开心、认同），回复 positive
- 如果评论包含明显的负面情绪（厌恶、批评、愤怒、讽刺），回复 negative
- 如果评论是中性陈述、提问或无情感倾向，回复 neutral
- 不要输出任何解释或其他文字

评论：{text}
"""

OPINION_PROMPT = """从以下抖音评论中抽取评价对象和对应的情感态度。

以 JSON 数组格式输出，每个元素包含 "term"（评价对象）和 "sentiment"（positive/negative）。
如果评论没有明确评价对象，返回空数组 []。
只输出 JSON，不要输出其他文字。

评论：{text}
"""

USER_PROFILE_PROMPT = """根据以下来自同一用户的抖音评论记录，概括该用户的特征。
从兴趣领域、情感倾向、活跃程度三个维度描述。
用 2-3 句话中文回答。

评论记录：
{texts}
"""


class SentimentAnalyzer:
    """Unified analyzer using Qwen2.5-Instruct for multi-task inference."""

    def __init__(self, model_name: str = "Qwen/Qwen2.5-1.5B-Instruct",
                 device: str | None = None):
        self.model_name = model_name
        if device is None:
            import torch
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device
        self._model = None
        self._tokenizer = None

    def _ensure_loaded(self):
        if self._model is not None:
            return
        logger.info("Loading model {} from ModelScope ...", self.model_name)
        from modelscope import AutoModelForCausalLM, AutoTokenizer

        self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self._model = AutoModelForCausalLM.from_pretrained(
            self.model_name,
            device_map=self.device,
            torch_dtype="auto",
        )
        logger.info("Model loaded on {}", self.device)

    def _generate(self, prompt: str, max_tokens: int = 128) -> str:
        self._ensure_loaded()
        messages = [{"role": "user", "content": prompt}]
        text = self._tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True,
        )
        inputs = self._tokenizer(text, return_tensors="pt").to(self.device)
        outputs = self._model.generate(
            **inputs,
            max_new_tokens=max_tokens,
            temperature=0.1,
            do_sample=False,
            pad_token_id=self._tokenizer.pad_token_id,
        )
        response = self._tokenizer.decode(
            outputs[0][len(inputs.input_ids[0]):],
            skip_special_tokens=True,
        )
        return response.strip()

    # ── sentiment ──

    def analyze_sentiment(self, text: str) -> SentimentResult:
        prompt = SENTIMENT_PROMPT.format(text=text)
        raw = self._generate(prompt, max_tokens=16)

        label = "neutral"
        raw_lower = raw.lower().strip()
        if "positive" in raw_lower:
            label = "positive"
        elif "negative" in raw_lower:
            label = "negative"

        score = 1.0
        match = re.search(r"(\d+\.?\d*)", raw)
        if match:
            score = min(float(match.group(1)), 1.0)

        return SentimentResult(label=label, score=score)

    # ── opinion ──

    def extract_opinions(self, text: str) -> list[dict]:
        prompt = OPINION_PROMPT.format(text=text)
        raw = self._generate(prompt, max_tokens=256)

        try:
            json_match = re.search(r"\[.*\]", raw, re.DOTALL)
            if json_match:
                import json
                return json.loads(json_match.group(0))
        except Exception:
            pass
        return []

    # ── user profile ──

    def profile_user(self, texts: list[str]) -> str:
        combined = "\n".join(f"- {t}" for t in texts[:50])
        prompt = USER_PROFILE_PROMPT.format(texts=combined)
        return self._generate(prompt, max_tokens=256)

    # ── batch ──

    def batch_sentiment(self, comments: list[dict]) -> list[dict]:
        """Analyze a batch of comments, returning results with source info."""
        results = []
        for i, c in enumerate(comments):
            text = c.get("text", "")
            if not text.strip():
                result = {"label": "neutral", "score": 1.0}
            else:
                sr = self.analyze_sentiment(text)
                result = {"label": sr.label, "score": sr.score}
            results.append({
                "source_type": c.get("source_type", "comment"),
                "source_id": c.get("source_id", c.get("cid", "")),
                "original_text": text,
                "sentiment_label": result["label"],
                "sentiment_score": result["score"],
            })
            if (i + 1) % 10 == 0:
                logger.info("  progress: {}/{}", i + 1, len(comments))
        return results
