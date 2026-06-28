import re

try:
    from pypinyin import Style, lazy_pinyin
except ImportError:  # pragma: no cover - dependency is installed in production update.
    Style = None
    lazy_pinyin = None


def pinyin_initials(value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        return ""

    if lazy_pinyin is None or Style is None:
        return _normalize_without_pinyin(text)

    parts = lazy_pinyin(text, style=Style.FIRST_LETTER, errors="default")
    return _normalize_without_pinyin("".join(parts))


def _normalize_without_pinyin(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()
