# Nomad CR

Pipeline semanal de analisis politico y de datos de Costa Rica para posts de LinkedIn.

**Flujo:** RSS + APIs publicas + INEC datasets -> categorizacion/dedup -> agente multi-turn (Groq) -> post markdown.

## Setup

```powershell
cd Nomad
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
copy .env.example .env
```

Editar `.env`:
```
GROQ_API_KEY=gsk_...      # https://console.groq.com (gratis)
```

## Comandos

```powershell
# Pipeline semanal completo
python -m nomad weekly

# Forzar post aunque el agente diga no-go
python -m nomad weekly --force

# Ver frescura de datos INEC
python -m nomad health

# Solo ingesta
python -m nomad ingest

# Ver estado del catalogo
python -m nomad status

# Marcar draft como publicado (cooldown 30 dias)
python -m nomad publish data\drafts\archivo.json
```

## Datos INEC cargados (1,420 puntos)

| Dataset | Puntos | Ciclo |
|---------|--------|-------|
| Pobreza ENAHO 2010-2025 | 192 | Anual |
| Indicadores Cantonales ArcGIS | 486 | Anual |
| IDS Dimensiones | 420 | Anual |
| PIB Cantonal | 84 | Anual |
| IPM Multidimensional | 67 | Anual |
| OIJ Estadisticas | 33 | Mensual |
| IDS Cantonal | 30 | Anual |
| CBA Junio 2026 | 18 | Mensual |
| Empresas Q1 2026 | 18 | Trimestral |
| Trabajadores Q1 2026 | 18 | Trimestral |
| IPC (12 meses) | 13 | Mensual |
| Turismo CST 2021 | 1 | Anual |
| APIs (Hacienda, RECOPE) | 8 | En vivo |

## Agente multi-turn

1. **Triage heuristico** -- clusters por tema
2. **Gate suficiencia** -- >=2 fuentes + dato/estadistica
3. **Refine insight** -- LLM (Groq, DeepSeek, OpenAI)
4. **Gate interes** -- go/no-go para el post

Prioridad LLM: Groq > DeepSeek > OpenAI > heuristico local.

## Fuentes

- RSS: La Nacion, El Financiero, Delfino, Semanario Universidad
- APIs: Hacienda (TC), RECOPE (combustibles)
- INEC: datos cantonales cargados en `data/raw/inec/`

## GitHub Actions

Workflow semanal: lunes 8:00 AM CR. Requiere secret `GROQ_API_KEY` en Settings > Secrets > Actions.
