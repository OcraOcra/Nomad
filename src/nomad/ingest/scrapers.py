from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

import httpx
from bs4 import BeautifulSoup

from nomad.models import NewsItem, SourceType
from nomad.utils import normalize_url, utcnow

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-CR,es;q=0.9",
}


def _extract_articles(html: str, base_url: str, link_selector: str, title_selector: str | None = None) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    articles: list[dict[str, str]] = []
    seen: set[str] = set()

    for link in soup.select(link_selector):
        href = link.get("href", "")
        if not href:
            continue
        full_url = href if href.startswith("http") else base_url.rstrip("/") + "/" + href.lstrip("/")
        full_url = normalize_url(full_url)
        if full_url in seen or not full_url:
            continue
        seen.add(full_url)

        if title_selector:
            title_el = link.select_one(title_selector) if title_selector != "self" else link
        else:
            title_el = link
        title = (title_el.get_text(strip=True) if title_el else "") or link.get("title", "") or link.get("aria-label", "")
        if not title or len(title) < 10:
            continue

        articles.append({"url": full_url, "title": title})
    return articles


def scrape_crhoy(client: httpx.Client | None = None) -> list[NewsItem]:
    """Scrapea titulares de la homepage de CRHoy."""
    url = "https://www.crhoy.com/"
    owns = client is None
    client = client or httpx.Client(timeout=25, follow_redirects=True, headers=HEADERS)
    items: list[NewsItem] = []
    try:
        resp = client.get(url)
        resp.raise_for_status()
        # CRHoy usa h2/h3 con links a articulos, o cards con titulos
        articles = _extract_articles(
            resp.text,
            "https://www.crhoy.com",
            "a[href*='/nacionales/'], a[href*='/sucesos/'], a[href*='/economia/'], a[href*='/politica/'], a[href*='/mundo/'] h2, a[href*='/nacionales/'] h3, a[href*='/sucesos/'] h3",
        )
        if not articles:
            # fallback: buscar cualquier link de articulo
            articles = _extract_articles(
                resp.text,
                "https://www.crhoy.com",
                "article a[hreflang], .title a, h2 a, h3 a",
            )

        for art in articles[:25]:
            items.append(
                NewsItem(
                    title=art["title"],
                    url=art["url"],
                    source="CRHoy",
                    source_type=SourceType.RSS,
                    fetched_at=utcnow(),
                )
            )
    except Exception as exc:
        logger.warning("Scraper CRHoy: %s", exc)
    finally:
        if owns:
            client.close()
    logger.info("Scraper CRHoy: %d items", len(items))
    return items


def scrape_ameliarueda(client: httpx.Client | None = None) -> list[NewsItem]:
    """Scrapea titulares de la homepage de AmeliaRueda (SPA, contenido limitado sin JS)."""
    url = "https://ameliarueda.com/"
    owns = client is None
    client = client or httpx.Client(timeout=25, follow_redirects=True, headers=HEADERS)
    items: list[NewsItem] = []
    try:
        resp = client.get(url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        seen: set[str] = set()

        # Links con texto real en /noticia/ y /reportajes/
        for link in soup.select("a[href]"):
            href = link.get("href", "")
            if not href:
                continue
            full_url = href if href.startswith("http") else "https://ameliarueda.com" + href if href.startswith("/") else ""
            full_url = normalize_url(full_url)
            if full_url in seen or not full_url:
                continue
            title = link.get_text(strip=True)
            if not title or len(title) < 15:
                continue
            # solo URLs de contenido, no navegacion
            if any(p in href for p in ("/noticia/", "/reportajes/", "/nota/")):
                seen.add(full_url)
                items.append(
                    NewsItem(
                        title=title,
                        url=full_url,
                        source="AmeliaRueda",
                        source_type=SourceType.RSS,
                        fetched_at=utcnow(),
                    )
                )

        # h2 con texto (sin link directo), usar como titulo y buscar link cercano
        for h2 in soup.select("h2"):
            title = h2.get_text(strip=True)
            if not title or len(title) < 15:
                continue
            # buscar link en el h2 o en el padre
            parent_link = h2.find_parent("a")
            if parent_link:
                href = parent_link.get("href", "")
                full_url = href if href.startswith("http") else "https://ameliarueda.com" + href
                full_url = normalize_url(full_url)
                if full_url and full_url not in seen:
                    seen.add(full_url)
                    items.append(
                        NewsItem(
                            title=title,
                            url=full_url,
                            source="AmeliaRueda",
                            source_type=SourceType.RSS,
                            fetched_at=utcnow(),
                        )
                    )
    except Exception as exc:
        logger.warning("Scraper AmeliaRueda: %s", exc)
    finally:
        if owns:
            client.close()
    logger.info("Scraper AmeliaRueda: %d items", len(items))
    return items


def scrape_all() -> list[NewsItem]:
    """Ejecuta todos los scrapers en paralelo."""
    items: list[NewsItem] = []
    with httpx.Client(timeout=25, follow_redirects=True, headers=HEADERS) as client:
        items.extend(scrape_crhoy(client))
        items.extend(scrape_ameliarueda(client))
    return items
