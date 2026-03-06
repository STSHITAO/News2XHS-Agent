from __future__ import annotations

import re
import unicodedata


_ALLOWED_TOKEN_RE = re.compile(r"[A-Za-z0-9\u4e00-\u9fff]+")


def sanitize_topic(value: str, *, fallback: str = "热点新闻", max_len: int = 24) -> str:
    text = unicodedata.normalize("NFKC", (value or "").strip())
    cleaned = "".join(_ALLOWED_TOKEN_RE.findall(text))
    if not cleaned:
        cleaned = fallback
    return cleaned[:max_len]


def sanitize_tag(value: str, *, max_len: int = 20) -> str:
    text = unicodedata.normalize("NFKC", (value or "").strip())
    cleaned = "".join(_ALLOWED_TOKEN_RE.findall(text))
    return cleaned[:max_len]

