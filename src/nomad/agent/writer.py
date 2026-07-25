from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from nomad.models import AnalysisDecision, DraftPost, HardDataPoint, NewsItem
from nomad.utils import utcnow

logger = logging.getLogger(__name__)


def _week_label(dt: datetime | None = None) -> str:
    dt = dt or utcnow()
    iso = dt.isocalendar()
    return f"Semana {iso.week}, {iso.year}"


def _format_data_line(d: HardDataPoint) -> str:
    val = d.value
    if isinstance(val, float):
        val_s = f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    else:
        val_s = str(val)
    unit = f" {d.unit}" if d.unit else ""
    period = f" ({d.period})" if d.period else ""
    return f"{d.name.replace('_', ' ')}: **{val_s}{unit}**{period} — {d.source}"


def build_analysis_md(
    decision: AnalysisDecision,
    news: list[NewsItem],
    data: list[HardDataPoint],
) -> str:
    # Separar datos globales de locales
    global_data = [d for d in data if d.source.startswith("MCP") or d.source == "IMF"]
    local_data = [d for d in data if not d.source.startswith("MCP") and d.source != "IMF"]
    
    news_lines = "\n".join(
        f"- [{n.title}]({n.url}) ({n.source})"
        + (f" — cifras: {', '.join(n.stats_mentions[:4])}" if n.stats_mentions else "")
        for n in news
    )
    data_lines = "\n".join(f"- {_format_data_line(d)}" for d in local_data) or "- _Sin datos duros numéricos_"
    
    # Sección de contexto global
    global_lines = ""
    if global_data:
        global_lines = "\n### Contexto Global\n\n"
        for d in global_data:
            global_lines += f"- {_format_data_line(d)}\n"
    
    gaps = "\n".join(f"- {g}" for g in decision.gaps) or "- Ninguno crítico"
    return f"""### Decisión del agente

- **Suficiente info:** {"sí" if decision.sufficient_info else "no"}
- **Interesante:** {"sí" if decision.interesting else "no"}
- **Confianza:** {decision.confidence.value} ({decision.confidence_score:.2f})
- **Ángulo:** {decision.narrative_angle}

### Insight

{decision.non_obvious_insight}

### Razonamiento

{decision.reasoning}

### Noticias seleccionadas

{news_lines}

### Datos duros

{data_lines}
{global_lines}
### Gaps

{gaps}
"""


def build_deep_analysis_md(
    decision: AnalysisDecision,
    news: list[NewsItem],
    data: list[HardDataPoint],
    mcp_data: dict[str, Any] | None = None,
) -> str:
    """Genera un análisis profundo con todos los datos, tablas y metodología."""
    
    # Separar datos por fuente
    local_data = [d for d in data if not d.source.startswith("MCP") and d.source != "IMF"]
    global_data = [d for d in data if d.source.startswith("MCP") or d.source == "IMF"]
    
    # Tabla de noticias
    news_table = "| # | Fuente | Titular | Cifras |\n|---|--------|---------|--------|\n"
    for i, n in enumerate(news[:10], 1):
        stats = ", ".join(n.stats_mentions[:3]) if n.stats_mentions else "-"
        news_table += f"| {i} | {n.source} | [{n.title[:60]}...]({n.url}) | {stats} |\n"
    
    # Tabla de datos locales
    local_table = "| Indicador | Valor | Unidad | Periodo | Fuente |\n|-----------|-------|--------|---------|--------|\n"
    for d in local_data[:15]:
        val = f"{d.value:,.2f}" if isinstance(d.value, float) else str(d.value)
        local_table += f"| {d.name.replace('_', ' ')} | {val} | {d.unit} | {d.period} | {d.source} |\n"
    
    # Tabla de datos globales (MCP)
    global_table = ""
    if global_data:
        global_table = "| Indicador | Valor | Unidad | Fuente |\n|-----------|-------|--------|--------|\n"
        for d in global_data[:10]:
            val = f"{d.value:,.2f}" if isinstance(d.value, float) else str(d.value)
            global_table += f"| {d.name.replace('_', ' ')} | {val} | {d.unit} | {d.source} |\n"
    
    # MCP detallado
    mcp_section = ""
    if mcp_data and "sources" in mcp_data:
        mcp_section = "\n### Datos MCP (mercados globales)\n\n"
        for source_name, source_data in mcp_data["sources"].items():
            if "error" in source_data:
                mcp_section += f"- **{source_name}**: Error - {source_data['error']}\n"
                continue
            mcp_section += f"- **{source_name}**:\n"
            for key, value in source_data.items():
                if key == "source":
                    continue
                if isinstance(value, list) and value:
                    mcp_section += f"  - {key}: {len(value)} items\n"
                    for item in value[:3]:
                        if isinstance(item, dict):
                            mcp_section += f"    - {item}\n"
                elif isinstance(value, dict) and value:
                    mcp_section += f"  - {key}: {len(value)} keys\n"
    
    # Metodología
    methodology = """
### Metodología

1. **Ingesta**: RSS (4 medios CR + 5 globales) + APIs (Hacienda, RECOPE) + MCP (news, world_intel, imf)
2. **Categorización**: Clasificación automática por keywords (seguridad, economía, política, desarrollo cantonal)
3. **Deduplicación**: Por URL normalizada + topic_key
4. **Análisis**: Agente multi-turn con Groq (Llama 3.3 70B)
   - Turno 1: Triage heurístico (clusters por tema)
   - Turno 2: Gate de suficiencia (≥2 fuentes + dato)
   - Turno 3: Refinamiento de insight (LLM)
   - Turno 4: Gate de interés (go/no-go)
5. **Redacción**: Post LinkedIn (≤280 palabras) + análisis profundo
"""
    
    return f"""# Análisis Profundo — {decision.theme}

**Categoría**: {decision.category.value}  
**Confianza**: {decision.confidence.value} ({decision.confidence_score:.2f})  
**Fecha**: {utcnow().strftime('%Y-%m-%d %H:%M')}

---

## 1. Decisión del Agente

- **Suficiente info**: {"sí" if decision.sufficient_info else "no"}
- **Interesante**: {"sí" if decision.interesting else "no"}
- **Ángulo narrativo**: {decision.narrative_angle}

## 2. Insight Principal

{decision.non_obvious_insight}

## 3. Noticias Analizadas

{news_table}

## 4. Datos Duros (Costa Rica)

{local_table}

## 5. Datos Globales (MCP)

{global_table or "_Sin datos MCP disponibles_"}

{mcp_section}

## 6. Análisis del Agente

{decision.reasoning}

## 7. Gaps Identificados

{chr(10).join(f"- {g}" for g in decision.gaps) or "- Ninguno crítico"}

{methodology}
"""


def build_linkedin_post_heuristic(
    decision: AnalysisDecision,
    news: list[NewsItem],
    data: list[HardDataPoint],
    *,
    max_words: int = 280,
) -> str:
    lead_news = news[0] if news else None
    lead_data = next(
        (d for d in data if isinstance(d.value, (int, float))),
        data[0] if data else None,
    )

    # Párrafo 1: gancho con dato o tensión
    if lead_data and isinstance(lead_data.value, (int, float)):
        hook = (
            f"Esta semana en Costa Rica no se entiende del todo sin un número a la mano: "
            f"{lead_data.name.replace('_', ' ')} en {lead_data.value}"
            f"{(' ' + lead_data.unit) if lead_data.unit else ''} "
            f"({lead_data.source})."
        )
    elif lead_news and lead_news.stats_mentions:
        hook = (
            f"Un dato que aparece en la cobertura —{lead_news.stats_mentions[0]}— "
            f"vale más que el titular si lo ponemos en contexto."
        )
    else:
        hook = (
            f"Lo que se está discutiendo en {decision.category.value.replace('_', ' ')} "
            "merece bajar del ruido al indicador."
        )

    # Párrafo 2: contexto noticia
    if lead_news:
        context = (
            f"La conversación mediática incluye piezas como «{lead_news.title}» "
            f"({lead_news.source}). No es un caso aislado: hay al menos {len(news)} "
            f"notas recientes en la misma órbita."
        )
    else:
        context = "Hay señales en la agenda pública, aunque la cobertura aún es dispersa."

    # Párrafo 3: insight
    insight = decision.non_obvious_insight.strip()

    # Párrafo 4: contexto global (si hay datos MCP)
    global_context = ""
    global_data = [d for d in data if d.source.startswith("MCP") or d.source == "IMF"]
    if global_data:
        global_lines = []
        for d in global_data[:2]:  # máximo 2 puntos globales
            if isinstance(d.value, (int, float)):
                global_lines.append(
                    f"{d.name.replace('_', ' ')}: {d.value}"
                    f"{(' ' + d.unit) if d.unit else ''}"
                )
            elif isinstance(d.value, str) and len(d.value) < 100:
                global_lines.append(d.value)
        if global_lines:
            global_context = f"\n\nEn el contexto global: {'. '.join(global_lines)}."

    # Bullets opcionales si hay varios datos
    bullets = ""
    numeric = [d for d in data if isinstance(d.value, (int, float))][:3]
    if len(numeric) >= 2:
        lines = []
        for d in numeric:
            lines.append(
                f"- {d.name.replace('_', ' ')}: {d.value}"
                f"{(' ' + d.unit) if d.unit else ''} ({d.source})"
            )
        bullets = "\n\n" + "\n".join(lines)

    # Pregunta final
    questions = {
        "economia": "¿Usted toma decisiones con el titular o con el indicador?",
        "seguridad": "¿Qué dato le haría falta para juzgar si una política de seguridad está funcionando en su cantón?",
        "politica": "¿Cuándo fue la última vez que un debate político en CR se cerró con una métrica y no con una frase?",
        "desarrollo_cantonal": "Si su municipalidad publicara un solo indicador cada mes, ¿cuál pediría usted?",
    }
    q = questions.get(decision.category.value, "¿Qué dato le cambiaría de opinión sobre este tema?")

    # Fuentes breves
    src_bits = []
    for n in news[:3]:
        src_bits.append(n.source)
    for d in data[:2]:
        src_bits.append(d.source)
    src_line = "Fuentes: " + ", ".join(dict.fromkeys(src_bits))

    post = f"""{hook}

{context}

{insight}{global_context}{bullets}

{q}

{src_line}"""

    words = post.split()
    if len(words) > max_words:
        post = " ".join(words[:max_words]) + "…"
    return post.strip()


def build_linkedin_post_llm(
    decision: AnalysisDecision,
    news: list[NewsItem],
    data: list[HardDataPoint],
    *,
    client: Any | None = None,
    model: str = "deepseek-chat",
    temperature: float = 0.5,
    persona: str = "",
    max_words: int = 280,
) -> str | None:
    if client is None:
        return None
    try:
        payload = {
            "theme": decision.theme,
            "category": decision.category.value,
            "insight": decision.non_obvious_insight,
            "angle": decision.narrative_angle,
            "news": [{"title": n.title, "source": n.source, "url": n.url, "stats": n.stats_mentions} for n in news],
            "data": [
                {"name": d.name, "value": d.value, "unit": d.unit, "source": d.source, "period": d.period}
                for d in data
            ],
        }
        system = (persona or "Analista CR LinkedIn") + (
            f"\nEscribe UN post en español de Costa Rica, máximo {max_words} palabras. "
            "Estructura: (1) gancho con dato, (2) contexto de la noticia, "
            "(3) insight no obvio, (4) opcional 2-3 bullets, (5) pregunta final. "
            "Cita fuentes por nombre al final. Sin hashtags excesivos. Sin emojis. "
            "Tono profesional-conversacional, no académico."
        )
        r = client.chat.completions.create(
            model=model,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": f"Redacta el post con este material:\n{payload}",
                },
            ],
        )
        text = (r.choices[0].message.content or "").strip()
        if text:
            words = text.split()
            if len(words) > max_words:
                text = " ".join(words[:max_words]) + "..."
        return text or None
    except Exception as exc:
        logger.warning("LLM writer falló: %s", exc)
        return None


def compose_draft(
    decision: AnalysisDecision,
    news: list[NewsItem],
    data: list[HardDataPoint],
    *,
    cfg: dict[str, Any],
    llm_client: Any = None,
    llm_model: str = "deepseek-chat",
    mcp_data: dict[str, Any] | None = None,
) -> DraftPost:
    voice = cfg.get("voice") or {}
    agent_cfg = cfg.get("agent") or {}
    max_words = int(voice.get("max_words", 280))
    persona = voice.get("persona", "")

    analysis_md = build_analysis_md(decision, news, data)
    deep_analysis_md = build_deep_analysis_md(decision, news, data, mcp_data=mcp_data)
    post = build_linkedin_post_llm(
        decision,
        news,
        data,
        client=llm_client,
        model=llm_model,
        temperature=float(agent_cfg.get("temperature", 0.4)) + 0.1,
        persona=persona,
        max_words=max_words,
    )
    if not post:
        post = build_linkedin_post_heuristic(
            decision, news, data, max_words=max_words
        )

    sources: list[dict[str, str]] = []
    for n in news:
        sources.append(
            {"title": n.title, "url": n.url, "source": n.source, "type": "news"}
        )
    for d in data:
        sources.append(
            {
                "title": d.name,
                "url": d.url or "",
                "source": d.source,
                "type": "data",
            }
        )

    return DraftPost(
        week_label=_week_label(),
        category=decision.category,
        theme=decision.theme,
        confidence=decision.confidence,
        confidence_score=decision.confidence_score,
        analysis_md=analysis_md,
        deep_analysis_md=deep_analysis_md,
        linkedin_post=post,
        sources=sources,
        news_ids=[n.id for n in news],
        data_ids=[d.id for d in data],
        decision=decision,
    )
