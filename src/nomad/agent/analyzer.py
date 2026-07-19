from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from typing import Any

from nomad.models import (
    AnalysisDecision,
    Catalog,
    Category,
    Confidence,
    HardDataPoint,
    NewsItem,
)
from nomad.agent.llm import get_llm_client

logger = logging.getLogger(__name__)

PERSONA = """Eres un analista de política y datos de Costa Rica.
Conversacional pero siempre fundamentado. Audiencia: profesionales en LinkedIn
y redes (TikTok). No académico. Conectas noticias con datos duros (INEC, BCCR,
Hacienda, RECOPE) y buscas insights no obvios."""


def _cluster_by_category(news: list[NewsItem]) -> dict[str, list[NewsItem]]:
    groups: dict[str, list[NewsItem]] = defaultdict(list)
    for n in news:
        groups[n.category.value].append(n)
    return groups


def _rank_clusters(groups: dict[str, list[NewsItem]]) -> list[tuple[str, list[NewsItem], float]]:
    ranked = []
    for cat, items in groups.items():
        if cat == Category.OTRO.value:
            continue
        # Solo notas con score de categoría decente (evita falsos positivos)
        strong = [
            i
            for i in items
            if i.category_scores.get(cat, 0) >= 2.0
            or (i.stats_mentions and i.category_scores.get(cat, 0) >= 1.5)
        ]
        pool = strong if len(strong) >= 2 else items
        pool = sorted(
            pool,
            key=lambda i: (
                i.category_scores.get(cat, 0) + 0.5 * len(i.stats_mentions),
                i.published_at or i.fetched_at,
            ),
            reverse=True,
        )
        score = len(pool) * 1.0
        score += sum(0.4 * len(i.stats_mentions) for i in pool)
        score += sum(0.15 * max(i.category_scores.get(cat, 0), 0) for i in pool)
        ranked.append((cat, pool, score))
    ranked.sort(key=lambda x: x[2], reverse=True)
    return ranked


def _pick_related_data(hard: list[HardDataPoint], category: str) -> list[HardDataPoint]:
    preferred = {
        Category.ECONOMIA.value: [
            "tipo_cambio", "bccr", "recope", "inflacion", "tbp",
            "cba", "pobreza", "canasta", "empresas", "trabajadores",
        ],
        Category.SEGURIDAD.value: [
            "contexto", "aseguramiento", "c14", "nacimiento", "defuncion",
        ],
        Category.DESARROLLO_CANTONAL.value: [
            "contexto", "inec", "ipm", "pobreza", "nacimiento", "defuncion",
            "canton", "educacion",
        ],
        Category.POLITICA.value: [
            "tipo_cambio", "bccr", "hacienda", "deficit", "pobreza", "cba",
        ],
    }
    keys = preferred.get(category, [])
    scored: list[tuple[float, HardDataPoint]] = []
    for d in hard:
        s = 0.0
        blob = f"{d.name} {d.source} {d.category.value}".lower()
        for k in keys:
            if k in blob:
                s += 2.0
        if d.category.value == category:
            s += 1.5
        if d.value is not None and not (
            isinstance(d.value, str) and "Disponible" in d.value
        ):
            s += 1.0
        if s > 0:
            scored.append((s, d))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [d for _, d in scored[:8]]


def _heuristic_decision(
    news: list[NewsItem],
    hard: list[HardDataPoint],
    *,
    min_sources: int = 2,
    min_hard: int = 1,
) -> AnalysisDecision:
    clusters = _rank_clusters(_cluster_by_category(news))
    if not clusters:
        return AnalysisDecision(
            sufficient_info=False,
            interesting=False,
            confidence=Confidence.BAJO,
            confidence_score=0.15,
            gaps=["No hay noticias categorizadas en temas prioritarios"],
            reasoning="Sin clusters viables tras categorización.",
        )

    cat, items, score = clusters[0]
    top_items = items[:5]
    related = _pick_related_data(hard, cat)
    numeric_hard = [
        d
        for d in related
        if isinstance(d.value, (int, float))
        or (isinstance(d.value, str) and re.search(r"\d", d.value))
    ]

    # tema legible: mejor titular del cluster (no bag-of-words ruidoso)
    lead = max(
        top_items,
        key=lambda i: i.category_scores.get(cat, 0) + 0.3 * len(i.stats_mentions),
    )
    theme = f"{cat.replace('_', ' ')} | {lead.title[:100]}"

    n_sources = len({i.source for i in top_items})
    n_urls = len(top_items)
    has_stats_in_news = sum(1 for i in top_items if i.stats_mentions) >= 1
    hard_ok = len(numeric_hard) >= min_hard or has_stats_in_news

    sufficient = n_urls >= min_sources and hard_ok
    # interesante si hay tensión multi-fuente o dato + noticia
    interesting = sufficient and (n_sources >= 2 or (n_urls >= 3 and hard_ok))

    conf_score = 0.2
    conf_score += min(0.25, 0.08 * n_urls)
    conf_score += min(0.2, 0.1 * n_sources)
    conf_score += min(0.2, 0.08 * len(numeric_hard))
    conf_score += 0.1 if has_stats_in_news else 0
    conf_score += min(0.15, score / 30)
    conf_score = round(min(conf_score, 0.95), 2)

    if conf_score >= 0.75:
        confidence = Confidence.ALTO
    elif conf_score >= 0.45:
        confidence = Confidence.MEDIO
    else:
        confidence = Confidence.BAJO

    gaps = []
    if n_urls < min_sources:
        gaps.append(f"Pocas noticias del tema ({n_urls} < {min_sources})")
    if not numeric_hard:
        gaps.append("Pocos datos duros numéricos enlazables (BCCR/Hacienda/RECOPE/INEC)")
    if n_sources < 2:
        gaps.append("Una sola fuente mediática — riesgo de sesgo")

    # insight heuristic
    insight = _craft_heuristic_insight(cat, top_items, numeric_hard)
    angle = _craft_angle(cat, top_items, numeric_hard)

    return AnalysisDecision(
        sufficient_info=sufficient,
        interesting=interesting,
        confidence=confidence,
        confidence_score=conf_score,
        selected_news_ids=[i.id for i in top_items],
        selected_data_ids=[d.id for d in related[:4]],
        theme=theme,
        category=Category(cat),
        narrative_angle=angle,
        non_obvious_insight=insight,
        gaps=gaps,
        reasoning=(
            f"Cluster '{cat}' score={score:.1f}, {n_urls} notas, "
            f"{n_sources} medios, {len(numeric_hard)} datos numéricos."
        ),
    )


def _craft_angle(cat: str, news: list[NewsItem], data: list[HardDataPoint]) -> str:
    headlines = "; ".join(n.title for n in news[:3])
    data_bits = ", ".join(
        f"{d.name}={d.value}{(' ' + d.unit) if d.unit else ''}" for d in data[:3] if d.value is not None
    )
    return (
        f"En {cat.replace('_', ' ')}, la conversación mediática gira en torno a: {headlines}. "
        f"El ancla cuantitativa disponible: {data_bits or 'menciones estadísticas en notas'}."
    )


def _craft_heuristic_insight(
    cat: str, news: list[NewsItem], data: list[HardDataPoint]
) -> str:
    if cat == Category.ECONOMIA.value and data:
        tc = next((d for d in data if "tipo_cambio" in d.name and isinstance(d.value, (int, float))), None)
        fuel = next((d for d in data if "recope" in d.name and isinstance(d.value, (int, float))), None)
        if tc and fuel:
            return (
                f"Mientras el tipo de cambio ronda {tc.value} {tc.unit}, el precio al consumidor "
                f"de combustibles ({fuel.name}: {fuel.value}) sigue siendo el termómetro cotidiano "
                "del bolsillo — la narrativa macro y la micro no siempre se mueven al unísono."
            )
        if tc:
            return (
                f"El tipo de cambio ({tc.value} {tc.unit}) es el dato que amarra casi cualquier "
                "debate de precios, salarios en dólares y competitividad — útil para bajar la "
                "noticia del día a una variable que la gente sí siente."
            )
    if cat == Category.SEGURIDAD.value:
        return (
            "La cobertura de seguridad suele concentrarse en el hecho delictivo; el ángulo menos "
            "obvio es preguntar qué indicadores cantonales (empleo juvenil, densidad, fiscalización) "
            "acompañan el patrón territorial — aunque esos datos no salgan en el titular."
        )
    if cat == Category.POLITICA.value:
        return (
            "En política costarricense el ciclo mediático premia la disputa; el valor está en "
            "atar el proyecto o la pugna a un indicador fiscal o regulatorio que mida si el "
            "ruido se traduce en capacidad de ejecución."
        )
    if cat == Category.DESARROLLO_CANTONAL.value:
        return (
            "Lo cantonal se discute como anécdota local, pero es donde se juega la calidad del "
            "Estado: agua, residuos, vialidad. Cruzar la noticia municipal con un indicador de "
            "servicio o inversión vuelve legible la brecha centro-periferia."
        )
    stats = []
    for n in news:
        stats.extend(n.stats_mentions[:2])
    if stats:
        return (
            f"Las propias notas ya cargan cifras ({', '.join(stats[:4])}); el insight está en "
            "no repetir el número sino explicar qué decisión pública o privada mueve."
        )
    return (
        "Hay masa crítica de cobertura, pero el cruce con datos duros aún es débil: "
        "el post gana si aporta al menos un indicador externo al ciclo de titulares."
    )


def _llm_refine(
    decision: AnalysisDecision,
    news: list[NewsItem],
    data: list[HardDataPoint],
    *,
    client: Any | None = None,
    model: str = "deepseek-chat",
    temperature: float = 0.4,
) -> AnalysisDecision:
    if client is None:
        logger.info("Sin LLM disponible: se usa decision heuristica multi-turn local")
        return decision

    selected_news = [n for n in news if n.id in decision.selected_news_ids]
    selected_data = [d for d in data if d.id in decision.selected_data_ids]
    payload = {
        "decision_previa": decision.model_dump(mode="json"),
        "noticias": [
            {
                "id": n.id,
                "title": n.title,
                "summary": n.summary[:400],
                "source": n.source,
                "url": n.url,
                "stats": n.stats_mentions,
                "category": n.category.value,
            }
            for n in selected_news
        ],
        "datos": [
            {
                "id": d.id,
                "name": d.name,
                "value": d.value,
                "unit": d.unit,
                "period": d.period,
                "source": d.source,
            }
            for d in selected_data
        ],
    }

    system = (
        PERSONA
        + "\nRespondes SOLO JSON válido con las claves: sufficient_info (bool), "
        "interesting (bool), confidence (alto|medio|bajo), confidence_score (0-1), "
        "theme (str), narrative_angle (str), non_obvious_insight (str), "
        "gaps (list[str]), reasoning (str). "
        "Criterio: hay suficiente info si >=2 fuentes y al menos un dato o estadística. "
        "interesting si el cruce noticia+dato no es obvio para un profesional en CR."
    )
    user = (
        "Turno de revisión del analista. Evalúa si conviene un post semanal.\n"
        f"{json.dumps(payload, ensure_ascii=False, default=str)}"
    )

    try:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        r1 = client.chat.completions.create(
            model=model,
            temperature=temperature,
            messages=messages,
            response_format={"type": "json_object"},
        )
        content1 = r1.choices[0].message.content or "{}"
        messages.append({"role": "assistant", "content": content1})
        messages.append(
            {
                "role": "user",
                "content": (
                    "Turno 2: si sufficient_info e interesting son true, mejora "
                    "non_obvious_insight para que no repita el titular y conecte "
                    "explícitamente un dato duro. Si no, explica el gap principal. "
                    "Devuelve el mismo JSON actualizado."
                ),
            }
        )
        r2 = client.chat.completions.create(
            model=model,
            temperature=temperature,
            messages=messages,
            response_format={"type": "json_object"},
        )
        content2 = r2.choices[0].message.content or content1
        data_out = json.loads(content2)

        conf_raw = str(data_out.get("confidence", decision.confidence.value)).lower()
        conf = {
            "alto": Confidence.ALTO,
            "high": Confidence.ALTO,
            "medio": Confidence.MEDIO,
            "medium": Confidence.MEDIO,
            "bajo": Confidence.BAJO,
            "low": Confidence.BAJO,
        }.get(conf_raw, decision.confidence)

        return AnalysisDecision(
            sufficient_info=bool(data_out.get("sufficient_info", decision.sufficient_info)),
            interesting=bool(data_out.get("interesting", decision.interesting)),
            confidence=conf,
            confidence_score=float(data_out.get("confidence_score", decision.confidence_score)),
            selected_news_ids=decision.selected_news_ids,
            selected_data_ids=decision.selected_data_ids,
            theme=str(data_out.get("theme") or decision.theme),
            category=decision.category,
            narrative_angle=str(data_out.get("narrative_angle") or decision.narrative_angle),
            non_obvious_insight=str(
                data_out.get("non_obvious_insight") or decision.non_obvious_insight
            ),
            gaps=list(data_out.get("gaps") or decision.gaps),
            reasoning=str(data_out.get("reasoning") or decision.reasoning),
        )
    except Exception as exc:
        logger.warning("LLM refine falló, se mantiene heurística: %s", exc)
        return decision


class AnalysisAgent:
    """Agente multi-turn: triage heuristico -> refinamiento LLM -> go/no-go."""

    def __init__(self, cfg: dict[str, Any], llm_client=None, llm_model: str = "deepseek-chat"):
        self.cfg = cfg.get("agent") or {}
        self.llm_client = llm_client
        self.llm_model = llm_model
        self.max_turns = int(self.cfg.get("max_turns", 4))
        self.min_sources = int(self.cfg.get("min_sources_for_post", 2))
        self.min_hard = int(self.cfg.get("min_hard_data_points", 1))
        self.temperature = float(self.cfg.get("temperature", 0.4))
        self.turns_log: list[dict[str, Any]] = []

    def run(self, catalog: Catalog) -> AnalysisDecision:
        news = catalog.news
        hard = catalog.hard_data

        # Turn 1 — triage local
        d1 = _heuristic_decision(
            news, hard, min_sources=self.min_sources, min_hard=self.min_hard
        )
        self.turns_log.append({"turn": 1, "name": "triage_heuristico", "decision": d1.model_dump()})

        # Turn 2 — ¿suficiente info?
        if not d1.sufficient_info:
            d1.reasoning += " | STOP: información insuficiente para post fundamentado."
            self.turns_log.append({"turn": 2, "name": "gate_suficiencia", "go": False})
            return d1
        self.turns_log.append({"turn": 2, "name": "gate_suficiencia", "go": True})

        # Turn 3 — refinamiento insight (LLM o refuerzo heurístico)
        d2 = _llm_refine(
            d1,
            news,
            hard,
            client=self.llm_client,
            model=self.llm_model,
            temperature=self.temperature,
        )
        self.turns_log.append({"turn": 3, "name": "refine_insight", "decision": d2.model_dump()})

        # Turn 4 — ¿es interesante?
        if not d2.interesting:
            d2.reasoning += " | STOP: cruce noticia+dato poco interesante esta semana."
            self.turns_log.append({"turn": 4, "name": "gate_interes", "go": False})
            return d2

        self.turns_log.append({"turn": 4, "name": "gate_interes", "go": True})
        return d2

    def selected_payload(
        self, catalog: Catalog, decision: AnalysisDecision
    ) -> tuple[list[NewsItem], list[HardDataPoint]]:
        news = [n for n in catalog.news if n.id in set(decision.selected_news_ids)]
        data = [d for d in catalog.hard_data if d.id in set(decision.selected_data_ids)]
        # fallback si IDs no matchean (reproceso)
        if not news:
            clusters = _rank_clusters(_cluster_by_category(catalog.news))
            if clusters:
                news = clusters[0][1][:5]
        if not data:
            data = _pick_related_data(catalog.hard_data, decision.category.value)
        return news, data
