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
def cmd_health() -> None:
    """Verifica la frescura de los datos cargados y muestra alertas."""
    _setup_log()
    from nomad.process.freshness import check_freshness, Freshness

    cfg, _, paths = get_config()
    catalog = load_catalog(paths["catalog_file"])
    alerts = check_freshness(catalog)

    if not alerts:
        console.print("[green]Sin alertas de frescura.[/green]")
        return

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

        table.add_row(
            a["name"],
            a["period"],
            icon,
            f"{a['cycle_months']} meses",
        )

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
