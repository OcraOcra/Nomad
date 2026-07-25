"""Convierte datos MCP crudos en HardDataPoint para el catálogo."""

import logging
from datetime import datetime
from typing import Any

from nomad.models import Category, HardDataPoint
from nomad.utils import utcnow

logger = logging.getLogger(__name__)


def mcp_to_hard_data_points(mcp_data: dict[str, Any]) -> list[HardDataPoint]:
    """
    Convierte la respuesta de ingest_mcp_sources() en lista de HardDataPoint.
    
    Cada fuente MCP (news, world_intel, imf) tiene estructura diferente.
    Esta función extrae los puntos clave y los normaliza.
    
    Args:
        mcp_data: Diccionario retornado por ingest_mcp_sources()
    
    Returns:
        Lista de HardDataPoint listos para inyectar al catálogo
    """
    if not mcp_data or "sources" not in mcp_data:
        return []
    
    points: list[HardDataPoint] = []
    sources = mcp_data["sources"]
    
    # === NEWS ===
    news = sources.get("news", {})
    if "error" not in news:
        # Breaking news → HardDataPoint de contexto global
        breaking = news.get("breaking_news", [])
        if breaking:
            # Resumir headlines como un solo punto de contexto
            headlines = [a.get("title", "") for a in breaking[:5] if a.get("title")]
            if headlines:
                points.append(HardDataPoint(
                    name="global_breaking_news",
                    value=f"{len(headlines)} titulares globales",
                    unit="headlines",
                    period=utcnow().strftime("%Y-%m-%d"),
                    source="MCP-News",
                    url="",
                    category=Category.ECONOMIA,
                    meta={
                        "type": "global_context",
                        "headlines": headlines,
                    },
                ))
        
        # Market data → puntos numéricos
        market = news.get("market_data", {})
        if isinstance(market, dict):
            for symbol, data in market.items():
                if isinstance(data, dict) and data.get("price"):
                    try:
                        price = float(str(data["price"]).replace(",", ""))
                        points.append(HardDataPoint(
                            name=f"global_market_{symbol.lower()}",
                            value=price,
                            unit=data.get("currency", "USD"),
                            period=utcnow().strftime("%Y-%m-%d"),
                            source="MCP-News",
                            url="",
                            category=Category.ECONOMIA,
                            meta={
                                "type": "market_data",
                                "change": data.get("change"),
                                "change_pct": data.get("change_pct"),
                            },
                        ))
                    except (ValueError, TypeError):
                        pass
        
        # Financial news → contexto adicional
        financial = news.get("financial_news", [])
        if financial:
            fin_headlines = [a.get("title", "") for a in financial[:3] if a.get("title")]
            if fin_headlines:
                points.append(HardDataPoint(
                    name="global_financial_news",
                    value=f"{len(fin_headlines)} noticias financieras",
                    unit="headlines",
                    period=utcnow().strftime("%Y-%m-%d"),
                    source="MCP-News",
                    url="",
                    category=Category.ECONOMIA,
                    meta={
                        "type": "financial_context",
                        "headlines": fin_headlines,
                    },
                ))
    
    # === WORLD INTEL ===
    intel = sources.get("world_intel", {})
    if "error" not in intel:
        # Risk assessments
        risks = intel.get("risk_assessments", [])
        if risks:
            high_risks = [r for r in risks if r.get("level") == "high"]
            if high_risks:
                risk_regions = list(set(r.get("region", "") for r in high_risks if r.get("region")))
                points.append(HardDataPoint(
                    name="global_risk_assessment",
                    value=len(high_risks),
                    unit="alertas",
                    period=utcnow().strftime("%Y-%m-%d"),
                    source="MCP-Intel",
                    url="",
                    category=Category.POLITICA,
                    meta={
                        "type": "geopolitical_risk",
                        "regions": risk_regions[:5],
                        "summaries": [r.get("summary", "") for r in high_risks[:3]],
                    },
                ))
        
        # Geopolitical events
        events = intel.get("geopolitical_events", [])
        if events:
            event_summaries = [e.get("summary", e.get("title", "")) for e in events[:5] if e.get("summary") or e.get("title")]
            if event_summaries:
                points.append(HardDataPoint(
                    name="global_geopolitical_events",
                    value=f"{len(event_summaries)} eventos",
                    unit="eventos",
                    period=utcnow().strftime("%Y-%m-%d"),
                    source="MCP-Intel",
                    url="",
                    category=Category.POLITICA,
                    meta={
                        "type": "geopolitical_context",
                        "events": event_summaries,
                    },
                ))
        
        # Stability indices
        stability = intel.get("stability_indices", {})
        if isinstance(stability, dict):
            for country, idx in stability.items():
                if isinstance(idx, (int, float)):
                    points.append(HardDataPoint(
                        name=f"global_stability_{country.lower()}",
                        value=round(idx, 2),
                        unit="índice",
                        period=utcnow().strftime("%Y-%m-%d"),
                        source="MCP-Intel",
                        url="",
                        category=Category.POLITICA,
                        meta={"type": "stability_index", "country": country},
                    ))
    
    # === IMF ===
    imf = sources.get("imf", {})
    if "error" not in imf:
        # GDP data
        gdp = imf.get("gdp_data", {})
        if isinstance(gdp, dict):
            for country, years in gdp.items():
                if isinstance(years, dict):
                    latest_year = max(years.keys()) if years else None
                    if latest_year:
                        try:
                            gdp_val = float(str(years[latest_year]).replace(",", ""))
                            points.append(HardDataPoint(
                                name=f"imf_gdp_{country.lower()}",
                                value=gdp_val,
                                unit="USD billions",
                                period=str(latest_year),
                                source="IMF",
                                url="",
                                category=Category.ECONOMIA,
                                meta={"type": "gdp", "country": country},
                            ))
                        except (ValueError, TypeError):
                            pass
        
        # Inflation data
        inflation = imf.get("inflation_data", {})
        if isinstance(inflation, dict):
            for country, data in inflation.items():
                if isinstance(data, dict):
                    # Buscar el año más reciente disponible
                    year_keys = sorted(
                        [k for k in data.keys() if k.isdigit() and len(k) == 4],
                        reverse=True,
                    )
                    latest_key = year_keys[0] if year_keys else None
                    latest = data.get("latest") or (data.get(latest_key) if latest_key else None)
                    if latest is not None:
                        try:
                            infl_val = float(str(latest).replace(",", ""))
                            points.append(HardDataPoint(
                                name=f"imf_inflation_{country.lower()}",
                                value=infl_val,
                                unit="%",
                                period=latest_key or "unknown",
                                source="IMF",
                                url="",
                                category=Category.ECONOMIA,
                                meta={"type": "inflation", "country": country},
                            ))
                        except (ValueError, TypeError):
                            pass
        
        # Fiscal indicators
        fiscal = imf.get("fiscal_indicators", {})
        if isinstance(fiscal, dict):
            for country, indicators in fiscal.items():
                if isinstance(indicators, dict):
                    for indicator_name, val in indicators.items():
                        try:
                            fiscal_val = float(str(val).replace(",", ""))
                            points.append(HardDataPoint(
                                name=f"imf_{indicator_name}_{country.lower()}",
                                value=fiscal_val,
                                unit="%",
                                period="2024",
                                source="IMF",
                                url="",
                                category=Category.ECONOMIA,
                                meta={"type": "fiscal", "country": country, "indicator": indicator_name},
                            ))
                        except (ValueError, TypeError):
                            pass
    
    logger.info(f"MCP: {len(points)} HardDataPoint ({len(points)} globales)")
    return points
