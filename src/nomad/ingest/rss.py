from __future__ import annotations

import logging
from typing import Any

import feedparser
import httpx

from nomad.models import NewsItem, SourceType
from nomad.utils import normalize_url, parse_dt, strip_html, utcnow

logger = logging.getLogger(__name__)


def fetch_rss_feed(
    name: str,
    url: str,
    *,
    region: str = "local",
    timeout: float = 25.0,
    user_agent: str = "NomadCR/1.0",
    client: httpx.Client | None = None,
) -> list[NewsItem]:
    headers = {"User-Agent": user_agent, "Accept": "application/rss+xml, application/xml, text/xml, */*"}
    owns = client is None
    client = client or httpx.Client(timeout=timeout, follow_redirects=True, headers=headers)
    items: list[NewsItem] = []
    try:
        resp = client.get(url)
        if resp.status_code >= 400:
            logger.warning("RSS %s HTTP %s (%s)", name, resp.status_code, url)
            return items
        parsed = feedparser.parse(resp.content)
        if getattr(parsed, "bozo", False) and not parsed.entries:
            logger.warning("RSS bozo %s: %s", name, getattr(parsed, "bozo_exception", ""))
        for entry in parsed.entries:
            link = normalize_url(getattr(entry, "link", "") or "")
            title = (getattr(entry, "title", "") or "").strip()
            if not link or not title:
                continue
            summary_raw = (
                getattr(entry, "summary", None)
                or getattr(entry, "description", None)
                or ""
            )
            if isinstance(summary_raw, list):
                summary_raw = " ".join(str(x) for x in summary_raw)
            summary = strip_html(str(summary_raw))[:1200]

            published = None
            if getattr(entry, "published_parsed", None):
                try:
                    import time

                    published = parse_dt(time.strftime("%Y-%m-%dT%H:%M:%S", entry.published_parsed))
                except Exception:
                    published = parse_dt(getattr(entry, "published", None))
            else:
                published = parse_dt(getattr(entry, "published", None) or getattr(entry, "updated", None))

            items.append(
                NewsItem(
                    title=title,
                    summary=summary,
                    url=link,
                    source=name,
                    source_type=SourceType.RSS,
                    published_at=published,
                    fetched_at=utcnow(),
                    region=region,
                    raw={
                        "feed_url": url,
                        "id": getattr(entry, "id", None),
                        "tags": [t.get("term") for t in getattr(entry, "tags", []) or [] if isinstance(t, dict)],
                    },
                )
            )
    except Exception as exc:
        logger.error("Error RSS %s (%s): %s", name, url, exc)
    finally:
        if owns:
            client.close()
    logger.info("RSS %s: %d items", name, len(items))
    return items


def fetch_all_rss(feeds: list[dict[str, Any]], **kwargs: Any) -> list[NewsItem]:
    all_items: list[NewsItem] = []
    timeout = kwargs.get("timeout", 25.0)
    user_agent = kwargs.get("user_agent", "NomadCR/1.0")
    with httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": user_agent}) as client:
        for feed in feeds:
            all_items.extend(
                fetch_rss_feed(
                    feed["name"],
                    feed["url"],
                    region=feed.get("region", "local"),
                    timeout=timeout,
                    user_agent=user_agent,
                    client=client,
                )
            )
    return all_items
