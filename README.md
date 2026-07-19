# Nomad CR

Pipeline para generar borradores semanales de análisis político y de datos de Costa Rica, con tono LinkedIn.

**Flujo:** RSS + APIs públicas → categorización/dedup → agente multi-turn → post markdown.

## Setup

```powershell
cd Nomad
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
copy .env.example .env
# opcional: OPENAI_API_KEY, BCCR_EMAIL, BCCR_TOKEN
```

## Comandos

```powershell
# Ingesta RSS (CRHoy, Nación, Financiero, etc.) + APIs (Hacienda, RECOPE, BCCR)
python -m nomad ingest

# Agente multi-turn: ¿hay info suficiente? ¿es interesante?
python -m nomad analyze

# Borrador markdown (análisis + post)
python -m nomad draft
python -m nomad draft --force   # ignora no-go del agente

# Pipeline completo (lunes 8am)
python -m nomad weekly
python -m nomad schedule-run --once

# Tras publicar en LinkedIn (cooldown 30 días)
python -m nomad publish data\drafts\YYYYMMDD_tema.json

python -m nomad status
```

## Estructura

```
config/settings.yaml     # feeds, APIs, voz, schedule
src/nomad/
  ingest/                # RSS + APIs CR
  process/               # categoría, dedupe, store JSON
  agent/                 # multi-turn + redacción LinkedIn
  pipeline.py
  cli.py
data/
  raw/                   # dumps de ingesta
  processed/items.json   # catálogo
  drafts/                # markdown + json
  history/published.json # posts ya usados (30 días)
```

## Agente multi-turn

1. **Triage heurístico** — clusters por tema (seguridad, economía, política, cantonal)
2. **Gate suficiencia** — ≥2 fuentes + dato/estadística
3. **Refine insight** — LLM si hay `OPENAI_API_KEY`, si no heurística
4. **Gate interés** — go/no-go para el post

Sin API key el sistema funciona completo en modo local (heurísticas + redacción plantilla).

## Fuentes de datos

- RSS configurables en `config/settings.yaml`
- [public-apis-cr](https://github.com/ruiznorlan/public-apis-cr): Hacienda TC, RECOPE, BCCR (token)
- Datasets cantonales/INEC: colocar CSV/JSON en `data/raw/inec/` (extensible)

## Voz del post

Conversacional, fundamentado, audiencia profesional LinkedIn/TikTok. Estructura: gancho con dato → contexto → insight → pregunta de diálogo. Confianza: alto / medio / bajo.
