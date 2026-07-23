from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from nomad.agent import AnalysisAgent, compose_draft
from nomad.agent.llm import get_llm_client
from nomad.config import ROOT, get_config
from nomad.ingest import fetch_all_rss, fetch_public_hard_data, load_inec_data
from nomad.ingest.scrapers import scrape_all
from nomad.models import Catalog, DraftPost, PublishedRecord
from nomad.process import (
    append_history,
    categorize_all,
    dedupe_news,
    filter_history_cooldown,
    filter_recent,
    load_catalog,
    load_history,
    merge_catalog,
    save_catalog,
    save_draft_markdown,
    save_history,
)
from nomad.process.freshness import check_freshness, Freshness
from nomad.utils import utcnow, write_json

logger = logging.getLogger(__name__)


def run_ingest(cfg: dict[str, Any] | None = None, env=None, paths: dict[str, Path] | None = None) -> Catalog:
    cfg, env, paths = _resolve(cfg, env, paths)
    ing = cfg.get("ingestion") or {}
    timeout = float(ing.get("request_timeout_seconds", 25))
    ua = ing.get("user_agent", "NomadCR/1.0")

    logger.info("Ingesta RSS...")
    news = fetch_all_rss(cfg.get("rss_feeds") or [], timeout=timeout, user_agent=ua)
    news = categorize_all(news)

    logger.info("Scrapers CRHoy / AmeliaRueda...")
    scraped = scrape_all()
    scraped = categorize_all(scraped)
    news.extend(scraped)

    news = dedupe_news(news)
    news = filter_recent(news, int(ing.get("lookback_days", 7)))

    history = load_history(paths["history_file"])
    cooldown = int((cfg.get("schedule") or {}).get("history_cooldown_days", 30))
    news = filter_history_cooldown(news, history, cooldown_days=cooldown)

    logger.info("Ingesta APIs publicas...")
    hard = fetch_public_hard_data(
        cfg.get("public_apis") or {},
        timeout=timeout,
        user_agent=ua,
        bccr_email=env.bccr_email,
        bccr_token=env.bccr_token,
    )

    logger.info("Ingesta INEC datasets...")
    inec_dir = paths.get("raw_dir", ROOT / "data" / "raw") / "inec"
    inec_data = load_inec_data(inec_dir)
    hard.extend(inec_data)

    catalog = load_catalog(paths["catalog_file"])
    catalog = merge_catalog(catalog, news, hard)
    # persist solo el subset reciente procesado + hard
    fresh = Catalog(news=news, hard_data=hard, updated_at=utcnow())
    save_catalog(paths["catalog_file"], fresh)

    # raw dump
    raw_path = paths["raw_dir"] / f"ingest_{utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    write_json(
        raw_path,
        {
            "news_count": len(news),
            "hard_count": len(hard),
            "news": [n.model_dump(mode="json") for n in news],
            "hard_data": [d.model_dump(mode="json") for d in hard],
        },
    )
    logger.info("Catalogo: %d noticias, %d datos -> %s", len(news), len(hard), paths["catalog_file"])
    return fresh


def run_analyze(
    catalog: Catalog | None = None,
    cfg: dict[str, Any] | None = None,
    env=None,
    paths: dict[str, Path] | None = None,
) -> tuple[Any, Catalog]:
    cfg, env, paths = _resolve(cfg, env, paths)
    if catalog is None:
        catalog = load_catalog(paths["catalog_file"])
    llm_result = get_llm_client(cfg, env)
    if llm_result:
        llm_client, llm_model, _ = llm_result
    else:
        llm_client, llm_model = None, "deepseek-chat"
    agent = AnalysisAgent(cfg, llm_client=llm_client, llm_model=llm_model)
    decision = agent.run(catalog)
    log_path = paths["processed_dir"] / f"agent_turns_{utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    write_json(log_path, agent.turns_log)
    logger.info(
        "Decision: sufficient=%s interesting=%s conf=%s theme=%s",
        decision.sufficient_info,
        decision.interesting,
        decision.confidence.value,
        decision.theme,
    )
    return decision, catalog


def run_draft(
    decision=None,
    catalog: Catalog | None = None,
    cfg: dict[str, Any] | None = None,
    env=None,
    paths: dict[str, Path] | None = None,
    force: bool = False,
) -> DraftPost | None:
    cfg, env, paths = _resolve(cfg, env, paths)
    if catalog is None:
        catalog = load_catalog(paths["catalog_file"])
    if decision is None:
        decision, catalog = run_analyze(catalog, cfg, env, paths)

    if not force and not (decision.sufficient_info and decision.interesting):
        # borrador de "no-go" para transparencia
        from nomad.agent.writer import build_analysis_md

        stub = DraftPost(
            week_label="",
            category=decision.category,
            theme=decision.theme or "sin-tema",
            confidence=decision.confidence,
            confidence_score=decision.confidence_score,
            analysis_md=build_analysis_md(decision, [], []),
            linkedin_post=(
                "_No se generó post: el agente determinó que no hay información "
                "suficiente o el cruce no es lo bastante interesante esta semana._\n\n"
                f"Gaps: {'; '.join(decision.gaps) or 'n/a'}"
            ),
            decision=decision,
        )
        path = save_draft_markdown(paths["drafts_dir"], stub)
        logger.warning("No-go draft guardado en %s", path)
        return stub

    llm_result = get_llm_client(cfg, env)
    llm_client, llm_model = (llm_result[0], llm_result[1]) if llm_result else (None, "llama-3.3-70b-versatile")

    agent = AnalysisAgent(cfg, llm_client=llm_client, llm_model=llm_model)
    news, data = agent.selected_payload(catalog, decision)
    draft = compose_draft(decision, news, data, cfg=cfg, llm_client=llm_client, llm_model=llm_model)

    # Agregar seccion de frescura de datos al analisis
    alerts = check_freshness(catalog)
    expired = [a for a in alerts if a["status"] == Freshness.EXPIRED]
    warning = [a for a in alerts if a["status"] == Freshness.WARNING]
    if expired or warning:
        health_md = "\n### Frescura de datos\n\n"
        if expired:
            health_md += "**Vencidos:**\n"
            for a in expired:
                health_md += f"- {a['name']}: {a['period']} ({a.get('age_months', '?')} meses, ciclo {a['cycle_months']}m)\n"
        if warning:
            health_md += "\n**Por vencer:**\n"
            for a in warning:
                health_md += f"- {a['name']}: {a['period']} ({a.get('age_months', '?')} meses, ciclo {a['cycle_months']}m)\n"
        draft.analysis_md += health_md

    path = save_draft_markdown(paths["drafts_dir"], draft)
    logger.info("Borrador guardado: %s (confianza=%s)", path, draft.confidence.value)
    return draft


def run_weekly(
    cfg: dict[str, Any] | None = None,
    env=None,
    paths: dict[str, Path] | None = None,
    force: bool = False,
) -> DraftPost | None:
    """Pipeline completo: ingesta → análisis multi-turn → redacción → markdown."""
    cfg, env, paths = _resolve(cfg, env, paths)
    catalog = run_ingest(cfg, env, paths)
    decision, catalog = run_analyze(catalog, cfg, env, paths)
    return run_draft(decision, catalog, cfg, env, paths, force=force)


def mark_published(
    draft: DraftPost,
    cfg: dict[str, Any] | None = None,
    env=None,
    paths: dict[str, Path] | None = None,
    notes: str = "",
) -> PublishedRecord:
    cfg, env, paths = _resolve(cfg, env, paths)
    topic_keys = []
    # recuperar topic keys del catálogo si existen
    catalog = load_catalog(paths["catalog_file"])
    id_set = set(draft.news_ids)
    for n in catalog.news:
        if n.id in id_set and n.topic_key:
            topic_keys.append(n.topic_key)
    if not topic_keys and draft.theme:
        from nomad.utils import topic_key

        topic_keys.append(topic_key(draft.theme, draft.category.value))

    rec = PublishedRecord(
        theme=draft.theme,
        category=draft.category,
        topic_keys=topic_keys,
        source_urls=[s.get("url", "") for s in draft.sources if s.get("url")],
        draft_id=draft.id,
        notes=notes,
    )
    append_history(paths["history_file"], rec)
    logger.info("Publicado registrado en historial: %s", rec.theme)
    return rec


def _resolve(cfg, env, paths):
    if cfg is None or env is None or paths is None:
        c, e, p = get_config()
        return cfg or c, env or e, paths or p
    return cfg, env, paths
