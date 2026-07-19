from __future__ import annotations

import re
from collections import defaultdict

from nomad.models import Category, NewsItem
from nomad.utils import extract_numbers, topic_key

# Palabras clave ponderadas por categoría (es-CR)
CATEGORY_KEYWORDS: dict[Category, list[tuple[str, float]]] = {
    Category.SEGURIDAD: [
        ("homicidio", 3.0),
        ("asesinato", 2.5),
        ("narco", 2.5),
        ("narcotráfico", 2.8),
        ("oij", 2.0),
        ("fuerza pública", 2.0),
        ("policía", 1.5),
        ("policia", 1.5),
        ("inseguridad", 2.5),
        ("violencia", 2.0),
        ("extorsión", 2.5),
        ("extorsion", 2.5),
        ("sicariato", 3.0),
        ("arma", 1.2),
        ("drogas", 1.8),
        ("cárcel", 1.5),
        ("carcel", 1.5),
        ("delincuencia", 2.2),
        ("robo", 1.5),
        ("asalto", 1.8),
        ("feminicidio", 2.5),
        ("seguridad ciudadana", 2.5),
    ],
    Category.DESARROLLO_CANTONAL: [
        ("cantón", 2.5),
        ("canton", 2.5),
        ("municipalidad", 2.5),
        ("alcalde", 2.0),
        ("concejo municipal", 2.2),
        ("infraestructura", 1.8),
        ("acueducto", 1.8),
        ("asada", 2.0),
        ("vivienda", 1.5),
        ("urbanismo", 1.8),
        ("plan regulador", 2.2),
        ("recolección de basura", 1.8),
        ("residuos", 1.5),
        ("calle", 1.0),
        ("puente", 1.2),
        ("comunidad", 1.0),
        ("distrito", 1.5),
        ("mideplan", 1.5),
        ("índice de desarrollo", 2.5),
        ("ids", 1.2),
    ],
    Category.POLITICA: [
        ("asamblea", 2.5),
        ("diputado", 2.2),
        ("diputada", 2.2),
        ("presidente", 1.8),
        ("casa presidencial", 2.0),
        ("gobierno", 1.5),
        ("ministerio", 1.3),
        ("proyecto de ley", 2.5),
        ("reforma", 1.5),
        ("elecciones", 2.5),
        ("tse", 2.0),
        ("partido", 1.8),
        ("contraloría", 2.0),
        ("sala iv", 2.2),
        ("sala constitucional", 2.2),
        ("veto", 1.8),
        ("moción", 1.5),
        ("gabinete", 1.8),
        ("corrupción", 2.2),
        ("corrupcion", 2.2),
        ("plebiscito", 2.0),
        ("referéndum", 2.0),
    ],
    Category.ECONOMIA: [
        ("inflación", 2.5),
        ("inflacion", 2.5),
        ("tipo de cambio", 2.5),
        ("colón", 1.5),
        ("colon", 1.5),
        ("dólar", 1.5),
        ("dolar", 1.5),
        ("bccr", 2.5),
        ("banco central", 2.5),
        ("pib", 2.5),
        ("desempleo", 2.5),
        ("empleo", 1.8),
        ("salario", 1.8),
        ("tasa básica", 2.2),
        ("tbp", 2.0),
        ("hacienda", 1.8),
        ("impuesto", 1.8),
        ("iva", 1.5),
        ("exportación", 2.0),
        ("exportacion", 2.0),
        ("turismo", 1.5),
        ("combustible", 2.0),
        ("recope", 2.2),
        ("gasolina", 2.0),
        ("déficit", 2.0),
        ("deficit", 2.0),
        ("deuda", 1.8),
        ("inversión", 1.5),
        ("inversion", 1.5),
        ("ine", 1.2),
        ("inec", 2.0),
        ("canasta básica", 2.2),
        ("canasta basica", 2.2),
        ("crecimiento económico", 2.5),
        ("mercado laboral", 2.2),
    ],
}


def score_categories(text: str) -> dict[str, float]:
    blob = text.lower()
    scores: dict[str, float] = defaultdict(float)
    for cat, kws in CATEGORY_KEYWORDS.items():
        for kw, w in kws:
            if kw in blob:
                # count rough occurrences
                n = len(re.findall(re.escape(kw), blob))
                scores[cat.value] += w * min(n, 3)
    return dict(scores)


def assign_category(item: NewsItem) -> NewsItem:
    text = f"{item.title}. {item.summary}"
    scores = score_categories(text)
    item.category_scores = scores
    if scores:
        best = max(scores, key=scores.get)  # type: ignore[arg-type]
        item.category = Category(best) if scores[best] >= 1.5 else Category.OTRO
    else:
        item.category = Category.OTRO
    item.stats_mentions = extract_numbers(text)
    item.keywords = _top_keywords(text)
    item.topic_key = topic_key(item.title, item.category.value)
    return item


def _top_keywords(text: str, n: int = 8) -> list[str]:
    stop = {
        "de", "la", "el", "en", "y", "a", "los", "las", "del", "un", "una",
        "por", "con", "para", "que", "se", "su", "al", "lo", "como", "mas",
        "más", "sobre", "este", "esta", "costa", "rica", "según", "tras",
        "entre", "desde", "hasta", "fue", "ser", "han", "hay", "the", "and",
    }
    words = re.findall(r"[a-záéíóúñü]{4,}", text.lower())
    freq: dict[str, int] = defaultdict(int)
    for w in words:
        if w not in stop:
            freq[w] += 1
    return [w for w, _ in sorted(freq.items(), key=lambda x: (-x[1], x[0]))[:n]]


def categorize_all(items: list[NewsItem]) -> list[NewsItem]:
    return [assign_category(i) for i in items]
