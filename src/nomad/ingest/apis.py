from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from nomad.models import Category, HardDataPoint
from nomad.utils import utcnow

logger = logging.getLogger(__name__)


def _get_json(client: httpx.Client, url: str) -> Any | None:
    try:
        r = client.get(url)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        logger.warning("API fail %s: %s", url, exc)
        return None


def _nested_number(obj: Any) -> tuple[float | None, str]:
    """Extrae (valor, fecha) de escalares o dicts {valor/fecha} de Hacienda."""
    if obj is None:
        return None, "actual"
    if isinstance(obj, (int, float)):
        return float(obj), "actual"
    if isinstance(obj, str):
        try:
            return float(obj.replace(",", ".")), "actual"
        except ValueError:
            return None, "actual"
    if isinstance(obj, dict):
        period = str(obj.get("fecha") or obj.get("date") or "actual")
        for key in ("valor", "value", "monto", "precio", "colones", "dolares"):
            if obj.get(key) is not None:
                try:
                    return float(str(obj[key]).replace(",", ".")), period
                except ValueError:
                    continue
        # a veces el dict es el wrapper venta/compra
        return None, period
    return None, "actual"


def fetch_hacienda_tipo_cambio(client: httpx.Client, url: str) -> list[HardDataPoint]:
    data = _get_json(client, url)
    if not data:
        return []
    points: list[HardDataPoint] = []
    # Formato actual: dolar.venta={fecha,valor}, dolar.compra=..., euro={fecha,colones,dolares}
    dolar = data.get("dolar") or data.get("dólar") or {}
    if isinstance(dolar, dict):
        for side, name in (("venta", "tipo_cambio_usd_venta"), ("compra", "tipo_cambio_usd_compra")):
            val, period = _nested_number(dolar.get(side))
            if val is None and side in dolar and not isinstance(dolar.get(side), dict):
                val, period = _nested_number(dolar)
            if val is not None:
                points.append(
                    HardDataPoint(
                        name=name,
                        value=val,
                        unit="CRC/USD",
                        period=period,
                        source="Ministerio de Hacienda",
                        url=url,
                        category=Category.ECONOMIA,
                        meta={"raw": dolar.get(side)},
                    )
                )
    euro = data.get("euro") or {}
    if isinstance(euro, dict):
        val, period = _nested_number(euro.get("colones") if "colones" in euro else euro)
        if val is None:
            val, period = _nested_number(euro)
        # colones es escalar dentro de euro
        if euro.get("colones") is not None:
            try:
                val = float(str(euro["colones"]).replace(",", "."))
                period = str(euro.get("fecha") or "actual")
            except ValueError:
                pass
        if val is not None:
            points.append(
                HardDataPoint(
                    name="tipo_cambio_eur_colones",
                    value=val,
                    unit="CRC/EUR",
                    period=period,
                    source="Ministerio de Hacienda",
                    url=url,
                    category=Category.ECONOMIA,
                    meta={"raw": euro},
                )
            )
    return points


def fetch_recope_precios(client: httpx.Client, url: str) -> list[HardDataPoint]:
    data = _get_json(client, url)
    if data is None:
        return []
    points: list[HardDataPoint] = []
    rows = data if isinstance(data, list) else data.get("data") or data.get("precios") or [data]
    if not isinstance(rows, list):
        rows = [rows]
    for row in rows:
        if not isinstance(row, dict):
            continue
        product = (
            row.get("nomprod")
            or row.get("producto")
            or row.get("nombre")
            or row.get("descripcion")
            or row.get("Producto")
            or "combustible"
        )
        price = (
            row.get("preciototal")
            or row.get("precio")
            or row.get("precio_consumidor")
            or row.get("Precio")
            or row.get("valor")
        )
        if price is None:
            continue
        try:
            value = float(str(price).replace(",", ".").replace(" ", ""))
        except ValueError:
            value = str(price)
        period = str(
            row.get("fechaupd") or row.get("fecha") or row.get("Fecha") or "actual"
        )
        slug = (
            str(product)
            .lower()
            .replace("(", "")
            .replace(")", "")
            .strip()
        )
        slug = "_".join(slug.split())[:40]
        points.append(
            HardDataPoint(
                name=f"recope_{slug}",
                value=value,
                unit="CRC/L" if isinstance(value, float) else "",
                period=period,
                source="RECOPE",
                url=url,
                category=Category.ECONOMIA,
                meta={"raw": row},
            )
        )
    return points


def fetch_bccr_indicator(
    client: httpx.Client,
    *,
    indicator_code: int,
    name: str,
    email: str,
    token: str,
    wsdl_base: str,
    start: str | None = None,
    end: str | None = None,
) -> list[HardDataPoint]:
    """Consulta indicador BCCR vía endpoint HTTP del web service (si hay credenciales)."""
    if not email or not token:
        logger.info("BCCR omitido (%s): faltan BCCR_EMAIL / BCCR_TOKEN", name)
        return []

    # Endpoint REST-friendly del ASMX
    base = wsdl_base.rstrip("/")
    if base.endswith(".asmx"):
        endpoint = f"{base}/ObtenerIndicadoresEconomicos"
    else:
        endpoint = base

    today = utcnow().strftime("%d/%m/%Y")
    params = {
        "Indicador": indicator_code,
        "FechaInicio": start or today,
        "FechaFinal": end or today,
        "Nombre": "NomadCR",
        "SubNiveles": "N",
        "CorreoElectronico": email,
        "Token": token,
    }
    try:
        r = client.get(endpoint, params=params)
        r.raise_for_status()
        text = r.text
    except Exception as exc:
        logger.warning("BCCR %s fail: %s", name, exc)
        return []

    points: list[HardDataPoint] = []
    try:
        root = ET.fromstring(text)
        # Buscar nodos NUM_VALOR / DES_FECHA en cualquier namespace
        values = []
        dates = []
        for el in root.iter():
            tag = el.tag.split("}")[-1].upper()
            if tag in ("NUM_VALOR", "NUMVALOR") and el.text:
                values.append(el.text.strip())
            if tag in ("DES_FECHA", "DESFECHA", "FECHA") and el.text:
                dates.append(el.text.strip())
        if not values:
            # a veces viene como JSON
            try:
                import json

                data = json.loads(text)
                # estructura variable
                logger.debug("BCCR JSON keys: %s", list(data)[:5] if isinstance(data, dict) else type(data))
            except Exception:
                pass
        for i, val in enumerate(values):
            try:
                num = float(val.replace(",", "."))
            except ValueError:
                continue
            points.append(
                HardDataPoint(
                    name=name,
                    value=num,
                    unit="",
                    period=dates[i] if i < len(dates) else today,
                    source="BCCR",
                    url=endpoint,
                    category=Category.ECONOMIA,
                    meta={"indicator": indicator_code},
                )
            )
    except ET.ParseError as exc:
        logger.warning("BCCR XML parse %s: %s", name, exc)
    return points[-5:]  # últimos valores


def fetch_public_hard_data(
    api_cfg: dict[str, Any],
    *,
    timeout: float = 25.0,
    user_agent: str = "NomadCR/1.0",
    bccr_email: str | None = None,
    bccr_token: str | None = None,
) -> list[HardDataPoint]:
    points: list[HardDataPoint] = []
    headers = {"User-Agent": user_agent, "Accept": "application/json, text/xml, */*"}
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
        hacienda = api_cfg.get("hacienda") or {}
        if hacienda.get("tipo_cambio"):
            points.extend(fetch_hacienda_tipo_cambio(client, hacienda["tipo_cambio"]))

        recope = api_cfg.get("recope") or {}
        if recope.get("precio_consumidor"):
            points.extend(fetch_recope_precios(client, recope["precio_consumidor"]))

        bccr = api_cfg.get("bccr") or {}
        indicators = bccr.get("indicators") or {}
        wsdl = bccr.get("wsdl") or ""
        for name, code in indicators.items():
            points.extend(
                fetch_bccr_indicator(
                    client,
                    indicator_code=int(code),
                    name=f"bccr_{name}",
                    email=bccr_email or "",
                    token=bccr_token or "",
                    wsdl_base=wsdl,
                )
            )

        # Snapshot sintético de contexto cantonal/INEC cuando no hay API live:
        # se documenta como placeholder para enriquecer con datasets locales.
        points.append(
            HardDataPoint(
                name="contexto_datos_abiertos",
                value="Disponible vía INEC / datos abiertos (cargar datasets locales en data/raw/inec)",
                unit="",
                period="referencia",
                source="INEC / catálogo public-apis-cr",
                url="https://github.com/ruiznorlan/public-apis-cr",
                category=Category.DESARROLLO_CANTONAL,
                meta={"note": "Enriquecer con CSV/JSON locales de indicadores cantonales"},
            )
        )

    logger.info("Hard data points: %d", len(points))
    return points
