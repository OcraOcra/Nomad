"""Health checks: RSS, MCP servers, API keys."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

from nomad.config import load_yaml_config

# Cargar variables de entorno desde .env
load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class CheckResult:
    name: str
    status: str  # "ok", "warn", "fail"
    message: str
    elapsed_ms: int = 0


@dataclass
class HealthReport:
    checks: list[CheckResult] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)

    @property
    def ok(self) -> bool:
        return all(c.status != "fail" for c in self.checks)

    @property
    def summary(self) -> str:
        lines = []
        for c in self.checks:
            icon = {"ok": "\u2705", "warn": "\u26a0\ufe0f", "fail": "\u274c"}.get(c.status, "?")
            lines.append(f"{icon} {c.name}: {c.message}")
        elapsed = int((time.time() - self.started_at) * 1000)
        lines.append(f"\nHealth check: {elapsed}ms | {'OK' if self.ok else 'FAIL'}")
        return "\n".join(lines)


# ── RSS globales ──────────────────────────────────────────────────


def check_global_rss(timeout: float = 10.0) -> CheckResult:
    cfg = load_yaml_config()
    feeds = cfg.get("rss_feeds") or []
    global_feeds = [f for f in feeds if isinstance(f, dict) and f.get("region") == "global"]

    if not global_feeds:
        return CheckResult(
            name="Global RSS",
            status="warn",
            message="No hay feeds globales configurados",
        )

    active = 0
    total = len(global_feeds)
    errors: list[str] = []

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        for feed in global_feeds:
            url = feed.get("url", "")
            name = feed.get("name", url[:40])
            try:
                r = client.head(url)
                if r.status_code < 400:
                    active += 1
                else:
                    errors.append(f"{name}: HTTP {r.status_code}")
            except Exception as e:
                errors.append(f"{name}: {type(e).__name__}")

    if active == total:
        return CheckResult(
            name="Global RSS",
            status="ok",
            message=f"{active}/{total} activos",
        )
    elif active > 0:
        return CheckResult(
            name="Global RSS",
            status="warn",
            message=f"{active}/{total} activos. Errores: {'; '.join(errors[:3])}",
        )
    else:
        return CheckResult(
            name="Global RSS",
            status="fail",
            message=f"0/{total} activos. Errores: {'; '.join(errors[:3])}",
        )


# ── MCP servers ──────────────────────────────────────────────────


def check_mcp_servers(timeout: int = 15) -> list[CheckResult]:
    from nomad.mcp.wrappers import NewsWrapper, IntelWrapper, IMFWrapper
    from nomad.mcp.client import MCPClient
    from nomad.mcp.servers import get_server_command, get_server_path

    results: list[CheckResult] = []
    wrappers = {
        "news": NewsWrapper,
        "world_intel": IntelWrapper,
        "imf": IMFWrapper,
    }

    for name, wrapper_class in wrappers.items():
        start = time.time()
        try:
            wrapper = wrapper_class(timeout=timeout)
            command = get_server_command(name)
            server_path = get_server_path(name)

            if not command or not server_path:
                results.append(CheckResult(
                    name=f"MCP {name}",
                    status="fail",
                    message="Servidor no encontrado o no configurado",
                    elapsed_ms=int((time.time() - start) * 1000),
                ))
                continue

            # Solo verificar que arranca y handshake
            client = MCPClient(server_path, command, timeout=timeout)
            try:
                client.start()
                elapsed = int((time.time() - start) * 1000)
                results.append(CheckResult(
                    name=f"MCP {name}",
                    status="ok",
                    message="Servidor OK, handshake completado",
                    elapsed_ms=elapsed,
                ))
            except TimeoutError:
                results.append(CheckResult(
                    name=f"MCP {name}",
                    status="warn",
                    message="Timeout en handshake (servidor puede estar lento)",
                    elapsed_ms=elapsed,
                ))
            except Exception as e:
                results.append(CheckResult(
                    name=f"MCP {name}",
                    status="fail",
                    message=str(e)[:100],
                    elapsed_ms=elapsed,
                ))
            finally:
                client.stop()

        except Exception as e:
            results.append(CheckResult(
                name=f"MCP {name}",
                status="fail",
                message=str(e)[:100],
                elapsed_ms=int((time.time() - start) * 1000),
            ))

    return results


# ── API Keys externas ────────────────────────────────────────────


def check_alpha_vantage(timeout: float = 10.0) -> CheckResult:
    key = os.getenv("ALPHA_VANTAGE_API_KEY")
    if not key:
        return CheckResult(
            name="Alpha Vantage",
            status="warn",
            message="Sin API Key",
        )

    start = time.time()
    try:
        r = httpx.get(
            "https://www.alphavantage.co/query",
            params={"function": "GLOBAL_QUOTE", "symbol": "SPY", "apikey": key},
            timeout=timeout,
        )
        elapsed = int((time.time() - start) * 1000)
        data = r.json()

        if "Global Quote" in data:
            return CheckResult(
                name="Alpha Vantage",
                status="ok",
                message="API funcional",
                elapsed_ms=elapsed,
            )
        elif "Error Message" in data:
            return CheckResult(
                name="Alpha Vantage",
                status="fail",
                message=f"Error: {data['Error Message'][:80]}",
                elapsed_ms=elapsed,
            )
        elif "Note" in data:
            return CheckResult(
                name="Alpha Vantage",
                status="warn",
                message=f"Rate limit: {data['Note'][:80]}",
                elapsed_ms=elapsed,
            )
        else:
            return CheckResult(
                name="Alpha Vantage",
                status="warn",
                message=f"Respuesta inesperada: {str(data)[:80]}",
                elapsed_ms=elapsed,
            )
    except Exception as e:
        return CheckResult(
            name="Alpha Vantage",
            status="fail",
            message=str(e)[:100],
            elapsed_ms=int((time.time() - start) * 1000),
        )


def check_eia(timeout: float = 10.0) -> CheckResult:
    key = os.getenv("EIA_API_KEY")
    if not key:
        return CheckResult(
            name="EIA",
            status="warn",
            message="Sin API Key",
        )

    start = time.time()
    try:
        r = httpx.get(
            "https://api.eia.gov/v2/petroleum/pri/spt/data/",
            params={
                "api_key": key,
                "frequency": "daily",
                "data[0]": "value",
                "facets[series][]": "RBRTE",
                "length": 1,
            },
            timeout=timeout,
        )
        elapsed = int((time.time() - start) * 1000)
        data = r.json()

        if r.status_code == 200 and "response" in data:
            return CheckResult(
                name="EIA",
                status="ok",
                message="API funcional",
                elapsed_ms=elapsed,
            )
        elif "error" in str(data).lower():
            return CheckResult(
                name="EIA",
                status="fail",
                message=f"Error: {str(data)[:80]}",
                elapsed_ms=elapsed,
            )
        else:
            return CheckResult(
                name="EIA",
                status="warn",
                message=f"Respuesta inesperada: {str(data)[:80]}",
                elapsed_ms=elapsed,
            )
    except Exception as e:
        return CheckResult(
            name="EIA",
            status="fail",
            message=str(e)[:100],
            elapsed_ms=int((time.time() - start) * 1000),
        )


# ── Runner completo ──────────────────────────────────────────────


def run_health_check(
    skip_rss: bool = False,
    skip_mcp: bool = False,
    skip_keys: bool = False,
) -> HealthReport:
    """Ejecuta todas las verificaciones de salud."""
    report = HealthReport()

    if not skip_rss:
        report.checks.append(check_global_rss())

    if not skip_mcp:
        report.checks.extend(check_mcp_servers())

    if not skip_keys:
        report.checks.append(check_alpha_vantage())
        report.checks.append(check_eia())

    return report
