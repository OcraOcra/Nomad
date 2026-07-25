"""Tests para categorize.py."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nomad.models import NewsItem, Category
from nomad.process.categorize import categorize_all, assign_category, score_categories


def _news(title: str, summary: str = "") -> NewsItem:
    """Helper para crear NewsItem de prueba."""
    return NewsItem(
        title=title,
        url="https://test.com/1",
        source="test",
        summary=summary,
        category=Category.OTRO,
    )


class TestScoreCategories:
    """Tests para score_categories."""

    def test_seguridad_keywords(self):
        scores = score_categories("OIJ investiga homicidio en San Jose")
        assert scores.get("seguridad", 0) > 0

    def test_economia_keywords(self):
        scores = score_categories("Tipo de cambio sube por inflacion")
        assert scores.get("economia", 0) > 0

    def test_politica_keywords(self):
        scores = score_categories("Asamblea aprueba proyecto de ley")
        assert scores.get("politica", 0) > 0

    def test_desarrollo_keywords(self):
        scores = score_categories("Municipalidad inaugura acueducto en el canton")
        assert scores.get("desarrollo_cantonal", 0) > 0

    def test_no_match(self):
        scores = score_categories("Noticia sin palabras clave relevantes")
        # Puede tener scores bajos por palabras ambiguas
        assert all(v < 2.0 for v in scores.values())

    def test_multiple_keywords(self):
        scores = score_categories("Homicidio y robo aumentan la inseguridad")
        assert scores.get("seguridad", 0) > 2.0


class TestAssignCategory:
    """Tests para assign_category."""

    def test_seguridad(self):
        item = _news("OIJ investiga homicidio en San Jose")
        result = assign_category(item)
        assert result.category == Category.SEGURIDAD

    def test_economia(self):
        item = _news("Tipo de cambio sube por intervencion del Banco Central")
        result = assign_category(item)
        assert result.category == Category.ECONOMIA

    def test_politica(self):
        item = _news("Diputados aprueban reforma en la Asamblea")
        result = assign_category(item)
        assert result.category == Category.POLITICA

    def test_desarrollo_cantonal(self):
        item = _news("Municipalidad inaugura nuevo acueducto en el canton")
        result = assign_category(item)
        assert result.category == Category.DESARROLLO_CANTONAL

    def test_otro(self):
        item = _news("El atardecer en la playa fue hermoso ayer")
        result = assign_category(item)
        assert result.category == Category.OTRO

    def test_stats_mentions(self):
        item = _news("Inflacion sube 2.5% y desempleo baja a 8%")
        result = assign_category(item)
        assert len(result.stats_mentions) > 0

    def test_keywords(self):
        item = _news("Economia de Costa Rica crece 3%")
        result = assign_category(item)
        assert len(result.keywords) > 0


class TestCategorizeAll:
    """Tests para categorize_all."""

    def test_empty(self):
        assert categorize_all([]) == []

    def test_assigns_categories(self):
        items = [
            _news("Homicidio en San Jose"),
            _news("Tipo de cambio sube"),
            _news("Diputados aprueban ley"),
        ]
        result = categorize_all(items)
        assert len(result) == 3
        cats = {item.category for item in result}
        assert len(cats) > 1  # Al menos 2 categorías diferentes


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
