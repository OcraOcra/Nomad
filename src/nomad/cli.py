from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.table import Table

# permitir `python -m nomad.cli` desde src/
ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nomad.config import get_config
from nomad.pipeline import mark_published, run_analyze, run_draft, run_ingest, run_weekly
from nomad.process import load_catalog, load_history
from nomad.utils import read_json

app = typer.Typer(help="Nomad CR - analisis politico y datos para posts LinkedIn", no_args_is_help=True)
console = Console(legacy_windows=False, force_terminal=True)


def _setup_log(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[
            RichHandler(
                console=console,
                rich_tracebacks=True,
                show_path=False,
                markup=False,
            )
        ],
    )
    # Evitar caracteres que rompen cp1252 en Windows
    for name in ("nomad", "httpx", "httpcore"):
        logging.getLogger(name).setLevel(level)


@app.command("ingest")
def cmd_ingest(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    """Raspa RSS + consume APIs públicas y guarda catálogo JSON."""
    _setup_log(verbose)
    catalog = run_ingest()
    table = Table(title="Ingesta")
    table.add_column("Tipo")
    table.add_column("Cantidad")
    table.add_row("Noticias", str(len(catalog.news)))
    table.add_row("Datos duros", str(len(catalog.hard_data)))
    by_cat: dict[str, int] = {}
    for n in catalog.news:
        by_cat[n.category.value] = by_cat.get(n.category.value, 0) + 1
    for k, v in sorted(by_cat.items(), key=lambda x: -x[1]):
        table.add_row(f"  · {k}", str(v))
    console.print(table)


@app.command("analyze")
def cmd_analyze(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    """Corre el agente multi-turn sobre el catálogo actual."""
    _setup_log(verbose)
    decision, _ = run_analyze()
    console.print(
        Panel(
            f"[bold]{decision.theme}[/bold]\n\n"
            f"Suficiente: {decision.sufficient_info} | Interesante: {decision.interesting}\n"
            f"Confianza: {decision.confidence.value} ({decision.confidence_score:.2f})\n\n"
            f"{decision.non_obvious_insight}\n\n"
            f"[dim]{decision.reasoning}[/dim]",
            title="Decisión del agente",
        )
    )


@app.command("draft")
def cmd_draft(
    force: bool = typer.Option(False, "--force", help="Genera post aunque el agente diga no-go"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Genera borrador markdown (análisis + post LinkedIn)."""
    _setup_log(verbose)
    draft = run_draft(force=force)
    if not draft:
        console.print("[yellow]Sin borrador[/yellow]")
        raise typer.Exit(1)
    console.print(
        Panel(
            draft.linkedin_post,
            title=f"Post · confianza {draft.confidence.value}",
        )
    )
    if draft.markdown_path:
        console.print(f"[green]Guardado:[/green] {draft.markdown_path}")


@app.command("weekly")
def cmd_weekly(
    force: bool = typer.Option(False, "--force"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Pipeline completo semanal (lunes 8am): ingest → analyze → draft."""
    _setup_log(verbose)
    draft = run_weekly(force=force)
    if draft and draft.markdown_path:
        console.print(f"[bold green]Borrador semanal:[/bold green] {draft.markdown_path}")
        console.print(
            f"Confianza: [bold]{draft.confidence.value}[/bold] ({draft.confidence_score:.2f})"
        )
    else:
        console.print("[yellow]Pipeline terminó sin post publicable[/yellow]")


@app.command("publish")
def cmd_publish(
    draft_json: Path = typer.Argument(..., help="Ruta al .json del draft"),
    notes: str = typer.Option("", "--notes"),
) -> None:
    """Marca un draft como publicado (entra al cooldown de 30 dias)."""
    _setup_log()
    from nomad.models import DraftPost

    raw = read_json(draft_json)
    draft = DraftPost.model_validate(raw)
    rec = mark_published(draft, notes=notes)
    console.print(f"[green]Historico actualizado:[/green] {rec.theme} @ {rec.published_at}")


@app.command("health")
def cmd_health(
    skip_rss: bool = typer.Option(False, "--skip-rss", help="Omitir verificacion RSS"),
    skip_mcp: bool = typer.Option(False, "--skip-mcp", help="Omitir verificacion MCP"),
    skip_keys: bool = typer.Option(False, "--skip-keys", help="Omitir verificacion API keys"),
    skip_freshness: bool = typer.Option(False, "--skip-freshness", help="Omitir verificacion frescura"),
) -> None:
    """Verifica salud completa: frescura de datos, RSS, MCP, API keys."""
    _setup_log()
    import time as _time
    from nomad.process.freshness import check_freshness, Freshness
    from nomad.health import run_health_check

    cfg, _, paths = get_config()

    # 1. Frescura de datos (existente)
    if not skip_freshness:
        catalog = load_catalog(paths["catalog_file"])
        alerts = check_freshness(catalog)

        if alerts:
            from rich.table import Table
            table = Table(title="Frescura de Datos")
            table.add_column("Dataset")
            table.add_column("Periodo mas reciente")
            table.add_column("Estado")
            table.add_column("Ciclo esperado")

            for a in alerts:
                status = a["status"]
                if status == Freshness.EXPIRED:
                    icon = "[bold red]VENCIDO[/bold red]"
                elif status == Freshness.WARNING:
                    icon = "[yellow]PROXIMO[/yellow]"
                else:
                    icon = "[green]FRESCO[/green]"
                table.add_row(a["name"], a["period"], icon, f"{a['cycle_months']} meses")

            console.print(table)
            console.print()
            expired = [a for a in alerts if a["status"] == Freshness.EXPIRED]
            warning = [a for a in alerts if a["status"] == Freshness.WARNING]
            if expired:
                console.print(f"[red]{len(expired)} datasets VENCIDOS[/red]")
                for a in expired:
                    console.print(f"  - {a['message']}")
            if warning:
                console.print(f"[yellow]{len(warning)} datasets por vencer[/yellow]")
                for a in warning:
                    console.print(f"  - {a['message']}")
        else:
            console.print("[green]Sin alertas de frescura.[/green]")
        console.print()

    # 2. Health checks nuevos (RSS, MCP, API keys)
    report = run_health_check(
        skip_rss=skip_rss,
        skip_mcp=skip_mcp,
        skip_keys=skip_keys,
    )

    console.print(report.summary)
    console.print()

    if not report.ok:
        raise typer.Exit(1)


@app.command("test-mcp")
def cmd_test_mcp(
    source: str = typer.Option(
        None,
        "--source",
        "-s",
        help="Fuente a probar: news, world_intel, imf, all",
    ),
    timeout: int = typer.Option(30, "--timeout", "-t", help="Timeout en segundos"),
) -> None:
    """Prueba wrappers MCP individuales o todos."""
    import time as _time
    _setup_log()
    from nomad.mcp.wrappers import NewsWrapper, IntelWrapper, IMFWrapper
    from nomad.mcp.servers import get_server_command, get_server_path

    wrappers_map = {
        "news": NewsWrapper,
        "world_intel": IntelWrapper,
        "imf": IMFWrapper,
    }

    if source and source != "all":
        if source not in wrappers_map:
            console.print(f"[red]Error: fuente '{source}' no existe[/red]")
            console.print(f"Fuentes disponibles: {', '.join(wrappers_map.keys())}, all")
            raise typer.Exit(1)
        sources_to_test = {source: wrappers_map[source]}
    else:
        sources_to_test = wrappers_map

    console.print(f"[cyan]Probando {len(sources_to_test)} fuente(s) MCP...[/cyan]\n")

    results: dict[str, str] = {}

    for name, wrapper_class in sources_to_test.items():
        console.print(f"[bold]{name}[/bold]")
        start = _time.time()

        command = get_server_command(name)
        server_path = get_server_path(name)
        if not command or not server_path:
            console.print("  [red]FAIL[/red]: Servidor no encontrado o no configurado")
            results[name] = "fail"
            console.print()
            continue

        try:
            wrapper = wrapper_class(timeout=timeout)
            data = wrapper.fetch()
            elapsed = int((_time.time() - start) * 1000)

            total_items = 0
            for key, value in data.items():
                if key == "source":
                    continue
                if isinstance(value, list):
                    total_items += len(value)
                elif isinstance(value, dict):
                    total_items += len(value)

            if total_items > 0:
                console.print(f"  [green]OK[/green]: {total_items} items ({elapsed}ms)")
                results[name] = "ok"
            else:
                console.print(f"  [yellow]WARN[/yellow]: API respondio pero sin datos ({elapsed}ms)")
                results[name] = "warn"

            for key, value in data.items():
                if key == "source":
                    continue
                if isinstance(value, list):
                    console.print(f"  - {key}: {len(value)} items")
                    for item in value[:3]:
                        if isinstance(item, dict):
                            title = item.get("title", item.get("name", str(item)[:60]))
                            console.print(f"    * {title}")
                        else:
                            console.print(f"    * {str(item)[:60]}")
                elif isinstance(value, dict):
                    console.print(f"  - {key}: {len(value)} keys")
                    for i, (k, v) in enumerate(value.items()):
                        if i >= 3:
                            break
                        console.print(f"    * {k}: {v}")
                else:
                    console.print(f"  - {key}: {value}")

            for key, value in data.items():
                if key.endswith("_error"):
                    console.print(f"  [yellow]! {key}: {value}[/yellow]")

        except Exception as e:
            elapsed = int((_time.time() - start) * 1000)
            console.print(f"  [red]FAIL[/red]: {str(e)[:100]} ({elapsed}ms)")
            results[name] = "fail"

        console.print()

    console.print("[bold]Resumen MCP:[/bold]")
    for name, status in results.items():
        icon = {"ok": "[green]OK[/green]", "warn": "[yellow]WARN[/yellow]", "fail": "[red]FAIL[/red]"}.get(status, "?")
        console.print(f"  {icon} {name}")


@app.command("status")
def cmd_status() -> None:
    """Resumen de catálogo, drafts e historial."""
    _setup_log()
    cfg, _, paths = get_config()
    catalog = load_catalog(paths["catalog_file"])
    history = load_history(paths["history_file"])
    drafts = list(paths["drafts_dir"].glob("*.md")) if paths["drafts_dir"].exists() else []
    console.print(
        Panel(
            f"Noticias en catálogo: {len(catalog.news)}\n"
            f"Datos duros: {len(catalog.hard_data)}\n"
            f"Drafts: {len(drafts)}\n"
            f"Publicados (historial): {len(history)}\n"
            f"Cooldown: {paths['data_dir']}",
            title="Nomad CR status",
        )
    )


@app.command("schedule-run")
def cmd_schedule(
    once: bool = typer.Option(True, "--once/--loop", help="Ejecutar una vez o loop scheduler"),
) -> None:
    """Ejecuta el job semanal (o deja un loop que corre lunes 8:00 CR)."""
    _setup_log()
    cfg, _, _ = get_config()
    sched = cfg.get("schedule") or {}
    day = (sched.get("weekly_draft_day") or "monday").lower()
    hour = int(sched.get("weekly_draft_hour") or 8)

    if once:
        console.print("[cyan]Ejecutando weekly ahora (--once)[/cyan]")
        run_weekly()
        return

    import schedule
    import time

    getattr(schedule.every(), day).at(f"{hour:02d}:00").do(lambda: run_weekly())
    console.print(f"[cyan]Scheduler activo: cada {day} a las {hour:02d}:00[/cyan]")
    while True:
        schedule.run_pending()
        time.sleep(30)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
