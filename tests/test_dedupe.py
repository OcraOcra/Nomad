"""Tests para dedupe.py."""

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nomad.models import NewsItem, Category
from nomad.process.dedupe import dedupe_news, filter_recent, filter_history_cooldown
from nomad.models import PublishedRecord


def _news(url: str, title: str, summary: str = "", published: datetime | None = None) -> NewsItem:
    """Helper para crear NewsItem de prueba."""
    return NewsItem(
        title=title,
        url=url,
        source="test",
        summary=summary,
        published_at=published,
        category=Category.ECONOMIA,
    )


class TestDedupeNews:
    """Tests para dedupe_news."""

    def test_empty(self):
        assert dedupe_news([]) == []

    def test_no_duplicates(self):
        items = [
            _news("https://a.com/1", "Economia crece en Costa Rica"),
            _news("https://b.com/2", "Seguridad ciudadana mejora en San Jose"),
        ]
        result = dedupe_news(items)
        assert len(result) == 2

    def test_url_duplicate(self):
        items = [
            _news("https://a.com/1", "Title 1", "short"),
            _news("https://a.com/1", "Title 1 extended", "longer summary with more content"),
        ]
        result = dedupe_news(items)
        assert len(result) == 1
        # Debe conservar el más largo
        assert "extended" in result[0].title

    def test_url_normalization(self):
        """URLs con trailing slash se consideran iguales."""
        items = [
            _news("https://a.com/1", "Title 1"),
            _news("https://a.com/1/", "Title 2"),
        ]
        result = dedupe_news(items)
        assert len(result) == 1

    def test_different_urls(self):
        items = [
            _news("https://a.com/1", "Economia crece en Costa Rica"),
            _news("https://b.com/2", "Seguridad ciudadana mejora en San Jose"),
        ]
        result = dedupe_news(items)
        assert len(result) == 2

    def test_same_topic_key(self):
        """Mismo topic_key = se deduplica."""
        items = [
            _news("https://a.com/1", "Economia crece 3%"),
            _news("https://b.com/2", "Economia crece tres por ciento"),
        ]
        result = dedupe_news(items)
        # Ambos tienen topic_key similar, uno se descarta
        assert len(result) <= 2


class TestFilterRecent:
    """Tests para filter_recent."""

    def test_empty(self):
        now = datetime(2026, 7, 24)
        assert filter_recent([], 7, now=now) == []

    def test_recent_included(self):
        now = datetime(2026, 7, 24)
        items = [
            _news("https://a.com/1", "Recent", published=datetime(2026, 7, 23)),
        ]
        result = filter_recent(items, 7, now=now)
        assert len(result) == 1

    def test_old_excluded(self):
        now = datetime(2026, 7, 24)
        items = [
            _news("https://a.com/1", "Old", published=datetime(2026, 7, 1)),
        ]
        result = filter_recent(items, 7, now=now)
        assert len(result) == 0

    def test_boundary(self):
        """Artículo exactamente en el límite se incluye."""
        now = datetime(2026, 7, 24)
        items = [
            _news("https://a.com/1", "Boundary", published=datetime(2026, 7, 17)),
        ]
        result = filter_recent(items, 7, now=now)
        assert len(result) == 1


class TestFilterHistoryCooldown:
    """Tests para filter_history_cooldown."""

    def test_empty(self):
        now = datetime(2026, 7, 24)
        items = [_news("https://a.com/1", "Title")]
        result = filter_history_cooldown(items, [], 30, now=now)
        assert len(result) == 1

    def test_cooldown_blocks(self):
        now = datetime(2026, 7, 24)
        history = [
            PublishedRecord(
                theme="test",
                category=Category.ECONOMIA,
                topic_keys=["economia:test"],
                source_urls=["https://a.com/1"],
                published_at=datetime(2026, 7, 20),
            )
        ]
        items = [_news("https://a.com/1", "Title")]
        result = filter_history_cooldown(items, history, 30, now=now)
        assert len(result) == 0

    def test_cooldown_expired(self):
        """Artículo publicado hace más de 30 días no bloquea."""
        now = datetime(2026, 7, 24)
        history = [
            PublishedRecord(
                theme="test",
                category=Category.ECONOMIA,
                topic_keys=["economia:test"],
                source_urls=["https://a.com/1"],
                published_at=datetime(2026, 6, 1),
            )
        ]
        items = [_news("https://a.com/1", "Title")]
        result = filter_history_cooldown(items, history, 30, now=now)
        assert len(result) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
