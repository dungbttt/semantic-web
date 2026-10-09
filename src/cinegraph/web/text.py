"""Text normalization shared by search and suggestions."""

import re
import unicodedata


def normalize_text(text: str) -> str:
    text = text.casefold().replace("đ", "d")
    decomposed = unicodedata.normalize("NFKD", text)
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", plain).strip()
