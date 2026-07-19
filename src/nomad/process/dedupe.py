from __future__ import annotations

from datetime import datetime, timedelta

from nomad.models import NewsItem, PublishedRecord
from nomad.utils import normalize_url, topic_key


def dedupe_news(items: list[NewsItem]) -> list[NewsItem]:
    """Deduplica por URL normalizada y por topic_key similar el mismo día."""
    by_url: dict[str, NewsItem] = {}
    for item in items:
        url = normalize_url(item.url)
        if not url:
            continue
        item.url = url
        prev = by_url.get(url)
        if prev is None:
            by_url[url] = item
            continue
        # conservar el más completo / reciente
        if len(item.summary) > len(prev.summary):
            by_url[url] = item
        elif item.published_at and prev.published_at and item.published_at > prev.published_at:
            by_url[url] = item

    # segunda pasada: topic_key
    by_topic: dict[str, NewsItem] = {}
    for item in by_url.values():
        tk = item.topic_key or topic_key(item.title, item.category.value)
        item.topic_key = tk
        prev = by_topic.get(tk)
        if prev is None:
            by_topic[tk] = item
            continue
        # preferir fuentes con más peso implícito (resumen + stats)
        score_new = len(item.summary) + 20 * len(item.stats_mentions)
        score_old = len(prev.summary) + 20 * len(prev.stats_mentions)
        if score_new > score_old:
            by_topic[tk] = item

    return sorted(
        by_topic.values(),
        key=lambda x: x.published_at or x.fetched_at,
        reverse=True,
    )


def filter_recent(items: list[NewsItem], lookback_days: int, now: datetime | None = None) -> list[NewsItem]:
    now = now or datetime.utcnow()
    cutoff = now - timedelta(days=lookback_days)
    out: list[NewsItem] = []
    for item in items:
        dt = item.published_at or item.fetched_at
        if dt >= cutoff:
            out.append(item)
    return out


def filter_history_cooldown(
    items: list[NewsItem],
    history: list[PublishedRecord],
    cooldown_days: int = 30,
    now: datetime | None = None,
) -> list[NewsItem]:
    """Excluye temas ya publicados en la ventana de cooldown."""
    now = now or datetime.utcnow()
    cutoff = now - timedelta(days=cooldown_days)
    blocked_topics: set[str] = set()
    blocked_urls: set[str] = set()
    for rec in history:
        if rec.published_at >= cutoff:
            blocked_topics.update(rec.topic_keys)
            blocked_urls.update(normalize_url(u) for u in rec.source_urls)

    return [
        i
        for i in items
        if i.topic_key not in blocked_topics and normalize_url(i.url) not in blocked_urls
    ]
