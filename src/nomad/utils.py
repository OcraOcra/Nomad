from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urldefrag, urlparse, urlunparse


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def normalize_url(url: str) -> str:
    if not url:
        return ""
    url, _ = urldefrag(url.strip())
    parsed = urlparse(url)
    # drop tracking params
    query = "&".join(
        p
        for p in (parsed.query or "").split("&")
        if p and not p.lower().startswith(("utm_", "fbclid", "gclid"))
    )
    clean = parsed._replace(query=query, fragment="")
    return urlunparse(clean).rstrip("/")


def slugify(text: str, max_len: int = 80) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text).strip("-")
    return text[:max_len].strip("-") or "item"


def topic_key(title: str, category: str = "") -> str:
    """Clave de tema para deduplicar y cooldown de 30 días."""
    stop = {
        "de", "la", "el", "en", "y", "a", "los", "las", "del", "un", "una",
        "por", "con", "para", "que", "se", "su", "al", "lo", "como", "mas",
        "más", "sobre", "entre", "desde", "hasta", "este", "esta", "estos",
        "cr", "costa", "rica",
    }
    words = [
        w
        for w in re.findall(r"[a-záéíóúñü0-9]+", title.lower())
        if w not in stop and len(w) > 2
    ]
    core = "-".join(words[:6]) or slugify(title)
    return f"{category}:{core}" if category else core


def content_hash(*parts: str) -> str:
    blob = "|".join(p.strip().lower() for p in parts if p)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, (int, float)):
        try:
            return datetime.utcfromtimestamp(value)
        except (OSError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    # ISO-ish
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        pass
    from dateutil import parser as date_parser

    try:
        return date_parser.parse(text).replace(tzinfo=None)
    except (ValueError, TypeError, OverflowError):
        return None


def within_days(dt: datetime | None, days: int, now: datetime | None = None) -> bool:
    if dt is None:
        return True
    now = now or utcnow()
    return dt >= now - timedelta(days=days)


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default if default is not None else {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


def extract_numbers(text: str) -> list[str]:
    """Extrae menciones numéricas / porcentajes / montos del texto."""
    patterns = [
        r"\d{1,3}(?:[.\s]\d{3})+(?:,\d+)?",  # 1.234.567
        r"\d+(?:[.,]\d+)?\s*%",
        r"(?:₡|\$|USD|colones)\s*\d[\d.,]*",
        r"\d+(?:[.,]\d+)?\s*(?:mil|millones|mm|pp|puntos?)",
        r"\b\d{4}\b",  # años
    ]
    found: list[str] = []
    for pat in patterns:
        found.extend(re.findall(pat, text, flags=re.IGNORECASE))
    # dedupe preserving order
    seen: set[str] = set()
    out: list[str] = []
    for x in found:
        k = x.strip()
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out[:20]


def strip_html(html: str) -> str:
    from bs4 import BeautifulSoup

    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()
