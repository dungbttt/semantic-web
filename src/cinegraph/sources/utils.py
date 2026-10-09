from __future__ import annotations

import re
from typing import Any


def clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"\\N", "N/A", "None", "null"}:
        return None
    return text


def number(value: Any, cast=float):
    text = clean(value)
    if not text:
        return None
    try:
        return cast(float(text))
    except (TypeError, ValueError, OverflowError):
        return None


def split_names(value: Any) -> list[str]:
    text = clean(value)
    if not text:
        return []
    return [item.strip() for item in re.split(r"[,|;]", text) if item.strip()]
