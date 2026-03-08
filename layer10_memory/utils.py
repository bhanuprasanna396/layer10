from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime


_WHITESPACE = re.compile(r"\s+")
_NON_ALNUM = re.compile(r"[^a-z0-9_\-/# ]+")


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def stable_id(prefix: str, *parts: str) -> str:
    payload = "||".join(parts).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()[:16]
    return f"{prefix}_{digest}"


def normalize_text(text: str) -> str:
    lowered = text.lower().strip()
    lowered = _NON_ALNUM.sub("", lowered)
    return _WHITESPACE.sub(" ", lowered)


def canonical_person_name(name: str) -> str:
    name = normalize_text(name)
    return name.replace("@", "").strip()


def safe_excerpt(text: str, start: int | None, end: int | None, width: int = 220) -> str:
    if start is None or end is None:
        return text[:width]
    left = max(0, start - width // 2)
    right = min(len(text), end + width // 2)
    return text[left:right]
