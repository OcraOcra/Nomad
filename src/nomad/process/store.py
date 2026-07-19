from __future__ import annotations

from pathlib import Path

from nomad.models import Catalog, DraftPost, HardDataPoint, NewsItem, PublishedRecord
from nomad.utils import read_json, utcnow, write_json


def load_catalog(path: Path) -> Catalog:
    raw = read_json(path, default=None)
    if not raw:
        return Catalog()
    return Catalog.model_validate(raw)


def save_catalog(path: Path, catalog: Catalog) -> None:
    catalog.updated_at = utcnow()
    write_json(path, catalog.model_dump(mode="json"))


def merge_catalog(
    catalog: Catalog,
    news: list[NewsItem],
    hard_data: list[HardDataPoint],
) -> Catalog:
    by_url = {n.url: n for n in catalog.news}
    for n in news:
        by_url[n.url] = n
    catalog.news = list(by_url.values())

    # hard data: reemplazar por nombre+period
    key = lambda d: f"{d.name}|{d.period}|{d.source}"
    by_k = {key(d): d for d in catalog.hard_data}
    for d in hard_data:
        by_k[key(d)] = d
    catalog.hard_data = list(by_k.values())
    catalog.updated_at = utcnow()
    return catalog


def load_history(path: Path) -> list[PublishedRecord]:
    raw = read_json(path, default=[])
    if not isinstance(raw, list):
        return []
    return [PublishedRecord.model_validate(r) for r in raw]


def save_history(path: Path, records: list[PublishedRecord]) -> None:
    write_json(path, [r.model_dump(mode="json") for r in records])


def append_history(path: Path, record: PublishedRecord) -> list[PublishedRecord]:
    hist = load_history(path)
    hist.append(record)
    save_history(path, hist)
    return hist


def save_draft_markdown(drafts_dir: Path, draft: DraftPost) -> Path:
    drafts_dir.mkdir(parents=True, exist_ok=True)
    stamp = draft.created_at.strftime("%Y%m%d")
    safe_theme = "".join(c if c.isalnum() or c in "-_" else "-" for c in draft.theme.lower())[:50]
    path = drafts_dir / f"{stamp}_{safe_theme or draft.id[:8]}.md"
    conf = draft.confidence.value.upper()
    sources_md = "\n".join(
        f"- [{s.get('title') or s.get('name') or 'fuente'}]({s.get('url', '')}) — {s.get('source', '')}"
        for s in draft.sources
    )
    body = f"""# Borrador semanal — {draft.week_label or stamp}

**Tema:** {draft.theme}  
**Categoría:** {draft.category.value}  
**Confianza:** {conf} ({draft.confidence_score:.2f})  
**Generado:** {draft.created_at.isoformat()}

---

## Análisis

{draft.analysis_md}

---

## Post LinkedIn (listo para publicar)

{draft.linkedin_post}

---

## Fuentes

{sources_md or "_Sin fuentes_"}

---

## Metadata

- draft_id: `{draft.id}`
- news_ids: {", ".join(draft.news_ids) or "—"}
- data_ids: {", ".join(draft.data_ids) or "—"}
"""
    path.write_text(body, encoding="utf-8")
    draft.markdown_path = str(path)
    # también JSON al lado
    json_path = path.with_suffix(".json")
    write_json(json_path, draft.model_dump(mode="json"))
    return path
