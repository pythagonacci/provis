from typing import List, Dict, Any
import re
from ..config import settings

def _strip_markup(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", str(text or ""))
    text = re.sub(r"^[\-\•\*\s]+", "", text).strip()
    return re.sub(r"\s+", " ", text).strip()

def _truncate(text: str, max_chars: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= max_chars else (text[: max_chars - 1].rstrip() + "…")

def validate_and_normalize_slides(slides: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Ensure each slide has title + list[str] bullets, enforce limits."""
    out: List[Dict[str, Any]] = []
    for s in slides:
        title = _truncate(_strip_markup(s.get("title")), settings.TITLE_MAX_CHARS) or "Untitled"
        bullets_in = s.get("bullets") or []
        if not isinstance(bullets_in, list):
            bullets_in = []
        bullets: List[str] = []
        for b in bullets_in:
            if not isinstance(b, str):
                continue
            clean = _truncate(_strip_markup(b), settings.BULLET_MAX_CHARS)
            if clean:  # fixed colon bug
                bullets.append(clean)
        bullets = bullets[: settings.MAX_BULLETS]
        out.append({"title": title, "bullets": bullets})
    return out
