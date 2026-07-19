from __future__ import annotations

import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from nomad.models import Catalog, HardDataPoint

logger = logging.getLogger(__name__)


class Freshness(str, Enum):
    FRESH = "fresh"
    WARNING = "warning"
    EXPIRED = "expired"


EXPECTED_CYCLES: dict[str, dict[str, Any]] = {
    "INEC-CBA": {"months": 1, "desc": "Canasta Basica Alimentaria", "name": "CBA"},
    "INEC-IPC": {"months": 1, "desc": "Indice de Precios al Consumidor", "name": "IPC"},
    "INEC-ENAHO": {"months": 12, "desc": "Pobreza por linea de pobreza (ENAHO)", "name": "Pobreza"},
    "INEC-ENAHO-IPM": {"months": 12, "desc": "Pobreza Multidimensional (IPM)", "name": "IPM"},
    "INEC-CCSS": {"months": 3, "desc": "Empresas y Trabajadores CCSS", "name": "Empleo CCSS"},
    "INEC-IDS": {"months": 12, "desc": "Indice de Desarrollo Social Cantonal", "name": "IDS"},
    "INEC-ArcGIS": {"months": 12, "desc": "Indicadores Cantonales (ArcGIS)", "name": "Ind. Cantonales"},
    "BCCR-PIB-Cantonal": {"months": 12, "desc": "PIB Cantonal", "name": "PIB Cantonal"},
    "INEC-C14-CCSS": {"months": 12, "desc": "Incapacidad CCSS", "name": "C-14"},
    "OIJ": {"months": 1, "desc": "Estadisticas delictivas OIJ", "name": "OIJ"},
    "BCCR-CST": {"months": 12, "desc": "Cuenta Satelite Turismo", "name": "Turismo"},
    "Ministerio de Hacienda": {"months": 0, "desc": "Tipo de cambio (API en vivo)", "name": "TC Hacienda"},
    "RECOPE": {"months": 0, "desc": "Precios combustibles (API en vivo)", "name": "RECOPE"},
    "INEC": {"months": 12, "desc": "Nacimientos y Defunciones", "name": "Nac/Def"},
}


def _parse_period_to_date(period: str) -> datetime | None:
    """Convierte strings de periodo a fecha aproximada para comparacion."""
    import re

    period = period.strip().lower()
    now = datetime.utcnow()

    # "junio_2026" or "2026-06" or "junio 2026"
    m = re.search(r"(\d{4})", period)
    if not m:
        return None
    year = int(m.group(1))

    # intentar extraer mes
    meses = {
        "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
        "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
        "septiembre": 9, "setiembre": 9, "octubre": 10,
        "noviembre": 11, "diciembre": 12,
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
        "jan": 1, "feb": 2, "mar": 3, "apr": 4,
        "may": 5, "jun": 6, "jul": 7, "aug": 8,
        "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }
    month = 7  # default: mid-year
    for name, num in meses.items():
        if name in period:
            month = num
            break

    # "I_trim_2026", "II_trim_2026"
    tm = re.search(r"(i|ii|iii|iv)_?trim", period)
    if tm:
        roman = {"i": 1, "ii": 2, "iii": 3, "iv": 4}
        q = roman.get(tm.group(1), 1)
        month = q * 3 - 2

    # "2026-07-18" or "2026/07/18"
    dm = re.search(r"(\d{4})[/-](\d{2})(?:[/-](\d{2}))?", period)
    if dm:
        year = int(dm.group(1))
        month = int(dm.group(2))

    try:
        return datetime(year, month, 1)
    except (ValueError, TypeError):
        return datetime(year, 7, 1)


def check_freshness(catalog: Catalog) -> list[dict[str, Any]]:
    """Revisa la frescura de cada fuente de datos. Devuelve lista de alertas."""

    # Agrupar datos por source, encontrar el mas reciente por fuente
    latest: dict[str, datetime] = {}
    best_period: dict[str, str] = {}
    for d in catalog.hard_data:
        src = d.source
        if src not in EXPECTED_CYCLES:
            continue
        pd = _parse_period_to_date(d.period)
        if pd is None:
            continue
        if src not in latest or pd > latest[src]:
            latest[src] = pd
            best_period[src] = d.period

    now = datetime.utcnow()
    alerts: list[dict[str, Any]] = []

    for src, info in EXPECTED_CYCLES.items():
        months = info.get("months", 0)
        if months == 0:
            continue  # APIs en vivo, no aplica

        display = info.get("name", src)
        desc = info.get("desc", "")
        last_dt = latest.get(src)
        last_period = best_period.get(src, "sin datos")

        if last_dt is None:
            alerts.append({
                "source": src,
                "name": display,
                "desc": desc,
                "period": "sin datos",
                "status": Freshness.EXPIRED,
                "cycle_months": months,
                "message": f"{display}: sin datos cargados",
            })
            continue

        age_months = (now.year - last_dt.year) * 12 + (now.month - last_dt.month)
        # ajustar: si estamos en el mismo mes, considerar la diferencia de dias
        if now.day > 15:
            age_months += 0.5

        status: Freshness
        if age_months <= months:
            status = Freshness.FRESH
        elif age_months <= months + months * 0.5:
            status = Freshness.WARNING
        else:
            status = Freshness.EXPIRED

        alerts.append({
            "source": src,
            "name": display,
            "desc": desc,
            "period": last_period,
            "status": status,
            "cycle_months": months,
            "age_months": round(age_months, 1),
            "message": f"{display}: {last_period} ({age_months:.0f} meses, ciclo {months}m)",
        })

    alerts.sort(key=lambda a: (a["status"] == Freshness.EXPIRED, a["status"] == Freshness.WARNING), reverse=True)
    return alerts
