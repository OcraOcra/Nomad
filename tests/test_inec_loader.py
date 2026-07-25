"""Tests para inec_loader.py con fixtures pequeños."""

import sys
from pathlib import Path

import pytest

# Asegurar que src está en el path
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nomad.ingest.inec_loader import (
    parse_ids_cantonal,
    parse_ipc,
    parse_estadisticas_oij,
    _val,
    _safe_str,
    _norm,
)
from nomad.models import Category

FIXTURES = Path(__file__).parent / "fixtures"


class TestVal:
    """Tests para la función _val."""

    def test_int(self):
        assert _val(42) == 42.0

    def test_float(self):
        assert _val(3.14) == 3.14

    def test_string_number(self):
        assert _val("123.45") == 123.45

    def test_string_with_comma(self):
        # El formato "1.234,56" no se maneja directamente; usar formato estándar
        assert _val("1234,56") == 1234.56

    def test_none(self):
        assert _val(None) is None

    def test_empty_string(self):
        assert _val("") is None

    def test_dash(self):
        assert _val("-") is None

    def test_whitespace(self):
        assert _val("  42  ") == 42.0


class TestSafeStr:
    """Tests para la función _safe_str."""

    def test_string(self):
        assert _safe_str("hello") == "hello"

    def test_none(self):
        assert _safe_str(None) == ""

    def test_number(self):
        assert _safe_str(42) == "42"

    def test_whitespace(self):
        assert _safe_str("  hello  ") == "hello"


class TestNorm:
    """Tests para la función _norm."""

    def test_accent(self):
        assert _norm("Región") == "Region"

    def test_tilde(self):
        assert _norm("año") == "ano"

    def test_normal(self):
        assert _norm("hello") == "hello"


class TestParseIdsCantonal:
    """Tests para el parser de IDS cantonal."""

    def test_parse_sample(self):
        points = parse_ids_cantonal(FIXTURES / "ids_cantonal_sample.csv")
        assert len(points) == 5

    def test_values_correct(self):
        points = parse_ids_cantonal(FIXTURES / "ids_cantonal_sample.csv")
        # Primer punto: Escazu, IDS=10000
        assert points[0].value == 10000.0
        assert "Escazu" in points[0].name or "escazu" in points[0].name

    def test_category(self):
        points = parse_ids_cantonal(FIXTURES / "ids_cantonal_sample.csv")
        assert all(p.category == Category.DESARROLLO_CANTONAL for p in points)

    def test_source(self):
        points = parse_ids_cantonal(FIXTURES / "ids_cantonal_sample.csv")
        assert all(p.source == "INEC-IDS" for p in points)

    def test_period(self):
        points = parse_ids_cantonal(FIXTURES / "ids_cantonal_sample.csv")
        assert all(p.period == "2023" for p in points)


class TestParseIpc:
    """Tests para el parser de IPC."""

    def test_parse_sample(self):
        points = parse_ipc(FIXTURES / "ipc_sample.csv")
        assert len(points) > 0

    def test_has_interanual(self):
        points = parse_ipc(FIXTURES / "ipc_sample.csv")
        interanual = [p for p in points if "interanual" in p.name]
        assert len(interanual) > 0

    def test_has_nivel(self):
        points = parse_ipc(FIXTURES / "ipc_sample.csv")
        nivel = [p for p in points if "nivel" in p.name]
        assert len(nivel) > 0

    def test_category(self):
        points = parse_ipc(FIXTURES / "ipc_sample.csv")
        assert all(p.category == Category.ECONOMIA for p in points)

    def test_source(self):
        points = parse_ipc(FIXTURES / "ipc_sample.csv")
        assert all(p.source == "INEC-IPC" for p in points)


class TestParseOij:
    """Tests para el parser de estadísticas OIJ."""

    def test_parse_sample(self):
        points = parse_estadisticas_oij(FIXTURES / "oij_sample.csv")
        assert len(points) > 0

    def test_has_total(self):
        points = parse_estadisticas_oij(FIXTURES / "oij_sample.csv")
        total = [p for p in points if "total" in p.name.lower()]
        assert len(total) > 0

    def test_total_value(self):
        points = parse_estadisticas_oij(FIXTURES / "oij_sample.csv")
        total = [p for p in points if "total_registrados" in p.name]
        assert len(total) == 1
        assert total[0].value == 5  # 5 registros en el fixture

    def test_has_delitos(self):
        points = parse_estadisticas_oij(FIXTURES / "oij_sample.csv")
        delitos = [p for p in points if "homicidio" in p.name.lower()]
        assert len(delitos) > 0

    def test_category(self):
        points = parse_estadisticas_oij(FIXTURES / "oij_sample.csv")
        assert all(p.category == Category.SEGURIDAD for p in points)

    def test_source(self):
        points = parse_estadisticas_oij(FIXTURES / "oij_sample.csv")
        assert all(p.source in ("OIJ", "OIJ-Estadisticas") for p in points)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
