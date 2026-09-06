from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from . import collector, config
from .paths import (
    CACHE_DIR,
    CLAUDE_CREDS,
    CODEX_SESSIONS_DIR,
    CONFIG_DIR,
    CONFIG_TOML,
    GEMINI_DIR,
    HELPER_CLAUDE,
    HELPER_CODEX,
    HELPER_DEEPSEEK,
    HELPER_GEMINI,
    SCRIPTS_DIR,
    DEEPSEEK_ENV_FILE,
    STATUS_JSON,
)
from .schema import StatusReport
from .security import atomic_write, ensure_dirs

app = typer.Typer(name="ai-quota-monitor", add_completion=False, no_args_is_help=True)
console = Console()
log = logging.getLogger(__name__)
logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")


# ── doctor ────────────────────────────────────────────────────────────────────

@app.command()
def doctor() -> None:
    """Diagnostica el entorno sin modificar nada."""
    ok_sym, warn_sym, fail_sym = "✅", "⚠️ ", "❌"

    def chk(label: str, cond: bool, note: str = "") -> None:
        sym = ok_sym if cond else fail_sym
        console.print(f"  {sym} {label}" + (f"  — {note}" if note else ""))

    console.print("[bold cyan]ai-quota-monitor doctor[/bold cyan]")
    console.print()

    console.print("[bold]Archivos de datos[/bold]")
    chk("~/.claude/.credentials.json", CLAUDE_CREDS.exists(), "necesario para Claude API oficial")
    has_rollout = (
        CODEX_SESSIONS_DIR.exists()
        and next(CODEX_SESSIONS_DIR.rglob("rollout-*.jsonl"), None) is not None
    )
    chk("rollouts Codex (~/.codex/sessions)", has_rollout, "fuente oficial rate_limits")
    chk("~/.gemini (agy/Gemini)", GEMINI_DIR.exists(), "actividad local por día; no es cuota oficial")
    console.print()

    console.print("[bold]Scripts helper[/bold]")
    chk("helper_claude_usage.sh", HELPER_CLAUDE.exists() and HELPER_CLAUDE.stat().st_mode & 0o111 != 0)
    chk("helper_codex_usage.sh", HELPER_CODEX.exists() and HELPER_CODEX.stat().st_mode & 0o111 != 0)
    chk("helper_gemini_usage.sh", HELPER_GEMINI.exists() and HELPER_GEMINI.stat().st_mode & 0o111 != 0)
    chk("helper_deepseek_balance.sh", HELPER_DEEPSEEK.exists() and HELPER_DEEPSEEK.stat().st_mode & 0o111 != 0)
    console.print()

    console.print("[bold]Caché y config[/bold]")
    chk("~/.cache/ai-quota-monitor/", CACHE_DIR.exists())
    chk("~/.config/ai-quota-monitor/config.toml", CONFIG_TOML.exists())
    chk("status.json", STATUS_JSON.exists())
    stale_keys = config.obsolete_keys_present(config.load())
    if stale_keys:
        console.print(f"  {warn_sym} claves sin consumidor en config.toml:")
        for entry in stale_keys:
            console.print(f"      {entry}", markup=False)
    console.print()

    console.print("[bold]Herramientas del sistema[/bold]")
    for tool in ("python3", "curl", "jq", "ccusage", "kpackagetool6", "plasmawindowed", "systemctl"):
        chk(tool, shutil.which(tool) is not None)
    chk(
        "DeepSeek env seguro",
        DEEPSEEK_ENV_FILE.exists(),
        "opcional; necesario solo para consultar saldo DeepSeek",
    )
    console.print()

    console.print("[bold]Seguridad — sin secretos en caché[/bold]")
    if STATUS_JSON.exists():
        txt = STATUS_JSON.read_text(encoding="utf-8")
        suspicious = re.findall(r'"(?:access_token|bearer|api_key|secret|refresh_token)"\s*:\s*"[^"]{20,}', txt, re.I)
        found = len(suspicious) > 0
        chk("status.json sin credenciales", not found, "grep básico de patrones sensibles")
        chk("status.json permisos 0600", STATUS_JSON.stat().st_mode & 0o077 == 0)
    if CACHE_DIR.exists():
        chk("~/.cache/ai-quota-monitor/ permisos 0700", CACHE_DIR.stat().st_mode & 0o077 == 0)
    if CONFIG_DIR.exists():
        chk("~/.config/ai-quota-monitor/ permisos 0700", CONFIG_DIR.stat().st_mode & 0o077 == 0)

    console.print()
    console.print("[bold]Gobernanza de datos del repositorio[/bold]")
    repo_root = SCRIPTS_DIR.parent
    gitignore = repo_root / ".gitignore"
    ignored = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    chk("tests/fixtures/raw/ ignorado", "tests/fixtures/raw/" in ignored)
    chk("exports HTML ignorados", "*.html" in ignored and "*_files/" in ignored)
    tracked_like_raw = [
        path
        for path in (repo_root / "tests" / "fixtures" / "raw").rglob("*")
        if path.is_file() and path.name != ".gitkeep"
    ] if (repo_root / "tests" / "fixtures" / "raw").exists() else []
    chk("sin fixtures crudos locales", not tracked_like_raw, f"{len(tracked_like_raw)} archivo(s) raw")


# ── config init ───────────────────────────────────────────────────────────────

@app.command("config")
def config_cmd(
    action: str = typer.Argument(..., help="init | validate"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    """Gestión de configuración."""
    if action == "init":
        created = config.init_config(force=force)
        if created:
            console.print(f"[green]Config creada:[/green] {CONFIG_TOML}")
        else:
            console.print(f"[yellow]Config ya existe:[/yellow] {CONFIG_TOML}  (usa --force para sobrescribir)")
    elif action == "validate":
        if not CONFIG_TOML.exists():
            console.print("[red]No existe config.toml — ejecuta: ai-quota-monitor config init[/red]")
            raise typer.Exit(1)
        cfg = config.load()
        errs = config.validate(cfg)
        if errs:
            for e in errs:
                console.print(f"[red]✗[/red] {e}")
            raise typer.Exit(1)
        console.print("[green]Config válida[/green]")
    else:
        console.print(f"[red]Acción desconocida: {action}[/red]")
        raise typer.Exit(1)


# ── sample ────────────────────────────────────────────────────────────────────

@app.command()
def sample(write_cache: bool = typer.Option(False, "--write-cache")) -> None:
    """Genera datos ficticios para probar la UI sin proveedores reales."""
    from .schema import Provider, ProviderWindow, StatusReport

    now = datetime.now(timezone.utc)

    def reset_after(**delta: int) -> str:
        return (now + timedelta(**delta)).isoformat().replace("+00:00", "Z")

    def next_local_midnight() -> str:
        local_now = datetime.now().astimezone()
        return (local_now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).isoformat()

    report = StatusReport(
        network_used=False,
        providers=[
            Provider(id="claude", label="CLAUDE", status="ok", windows=[
                ProviderWindow(id="session", label="Session (5h)", used=42.0, limit=100.0,
                               unit="percent", percent=0.42, reset_at=reset_after(hours=4),
                               metric_kind="quota", renewal_kind="rolling",
                               confidence="official", source="sample", note="datos ficticios"),
                ProviderWindow(id="weekly", label="Weekly (7d)", used=57.0, limit=100.0,
                               unit="percent", percent=0.57, reset_at=reset_after(days=4),
                               metric_kind="quota", renewal_kind="rolling", cycle_days=7,
                               confidence="official", source="sample", note="datos ficticios"),
                ProviderWindow(id="local", label="Claude Code (5h)", used=123456, limit=None,
                               unit="tokens", percent=None, reset_at=reset_after(hours=4),
                               metric_kind="activity", renewal_kind="rolling",
                               confidence="local_observed", source="sample",
                               note="$1.23 ficticios"),
                ProviderWindow(id="usd", label="USD", used=0.0, limit=30.0,
                               unit="usd", percent=0.0, confidence="official",
                               source="sample", note="presupuesto ficticio"),
            ]),
            Provider(id="codex", label="CODEX", status="ok", windows=[
                ProviderWindow(id="weekly", label="Weekly (7d)", used=36.0, limit=100.0,
                               unit="percent", percent=0.36, reset_at=reset_after(days=5),
                               metric_kind="quota", renewal_kind="rolling", cycle_days=7,
                               confidence="official", source="sample", note="datos ficticios"),
                ProviderWindow(id="credits", label="Credits", used=120.0, limit=None,
                               unit="credits", percent=None, confidence="official",
                               source="sample", note="saldo ficticio"),
            ]),
            Provider(id="gemini", label="ANTIGRAVITY / GEMINI", status="ok", windows=[
                ProviderWindow(id="antigravity_gemini_weekly", label="Antigravity Gemini (7d)",
                               used=25, limit=100, unit="percent", percent=0.25,
                               reset_at=reset_after(days=6), metric_kind="quota",
                               renewal_kind="rolling", cycle_days=7,
                               confidence="official", source="sample", note="datos ficticios"),
                ProviderWindow(id="antigravity_claude_gpt_weekly", label="Antigravity Claude/GPT (7d)",
                               used=48, limit=100, unit="percent", percent=0.48,
                               reset_at=reset_after(days=3), metric_kind="quota",
                               renewal_kind="rolling", cycle_days=7,
                               confidence="official", source="sample", note="datos ficticios"),
                ProviderWindow(id="antigravity_activity", label="Antigravity (hoy)", used=12,
                               unit="requests", percent=None, reset_at=next_local_midnight(),
                               metric_kind="activity", renewal_kind="calendar_cutoff",
                               confidence="local_observed", source="sample", note="datos ficticios"),
                ProviderWindow(id="gemini_cli_activity", label="Gemini CLI (hoy)", used=7,
                               unit="requests", percent=None, reset_at=next_local_midnight(),
                               metric_kind="activity", renewal_kind="calendar_cutoff",
                               confidence="local_observed", source="sample", note="datos ficticios"),
            ]),
            Provider(id="copilot", label="COPILOT", status="ok", windows=[
                ProviderWindow(id="copilot_chat", label="AI Credits / Premium requests",
                               used=64, limit=200, unit="requests", percent=0.32,
                               reset_at=reset_after(days=7), metric_kind="quota",
                               renewal_kind="calendar_cutoff", confidence="official",
                               source="sample", note="datos ficticios"),
            ]),
            Provider(id="deepseek", label="DEEPSEEK", status="ok", windows=[
                ProviderWindow(id="balance", label="Saldo USD", used=7.5,
                               unit="usd", percent=None, metric_kind="balance", renewal_kind="none",
                               confidence="official", source="sample", note="saldo ficticio"),
                ProviderWindow(id="budget", label="Presupuesto CLP", used=2500, limit=10000,
                               unit="clp_estimated", percent=0.25, metric_kind="quota", renewal_kind="none",
                               confidence="configured_estimate", source="sample", note="estimación ficticia"),
            ]),
        ],
        warnings=[],
        errors=[],
    )
    out = report.model_dump_json(indent=2)
    if write_cache:
        ensure_dirs(CACHE_DIR)
        atomic_write(STATUS_JSON, out)
        console.print(f"[green]Sample escrito en:[/green] {STATUS_JSON}")
    else:
        console.print(out)


# ── refresh ───────────────────────────────────────────────────────────────────

@app.command()
def refresh(offline: bool = typer.Option(True, "--offline/--online")) -> None:
    """Recolecta datos y actualiza la caché JSON."""
    cfg = config.load()
    report = collector.collect_all(cfg, online=not offline)
    # Preserva el último valor bueno: un fallo transitorio (token expirado, timeout)
    # no debe borrar el conteo previo. Ver collector.merge_preserving.
    prev: StatusReport | None = None
    if STATUS_JSON.exists():
        try:
            prev = StatusReport.model_validate_json(STATUS_JSON.read_text(encoding="utf-8"))
        except Exception:
            prev = None
    report = collector.merge_preserving(prev, report)
    ensure_dirs(CACHE_DIR)
    atomic_write(STATUS_JSON, report.model_dump_json(indent=2))
    if report.errors:
        for e in report.errors:
            console.print(f"[yellow]⚠[/yellow] {e}")
    console.print(f"[green]✓[/green] Caché actualizada: {STATUS_JSON}")


# ── status ────────────────────────────────────────────────────────────────────

@app.command()
def status(
    json_output: bool = typer.Option(False, "--json"),
    pretty: bool = typer.Option(False, "--pretty"),
) -> None:
    """Imprime el estado actual de uso."""
    if not STATUS_JSON.exists():
        console.print("[red]Sin caché — ejecuta:[/red] ai-quota-monitor refresh", err=True)
        raise typer.Exit(1)
    data = STATUS_JSON.read_text(encoding="utf-8")

    if json_output:
        print(data)
        return

    report = StatusReport.model_validate_json(data)

    table = Table(title="AI Quota HUD", show_header=True, header_style="bold cyan")
    table.add_column("Provider", style="bold")
    table.add_column("Window")
    table.add_column("Used", justify="right")
    table.add_column("Limit", justify="right")
    table.add_column("Percent", justify="right")
    table.add_column("Confidence")

    for prov in report.providers:
        for w in prov.windows:
            pct_str = f"{w.percent*100:.0f}%" if w.percent is not None else "—"
            lim_str = f"{w.limit:.0f}" if w.limit is not None else "—"
            color = "green"
            if w.percent is not None:
                if w.percent >= 0.9:
                    color = "red"
                elif w.percent >= 0.7:
                    color = "yellow"
            table.add_row(
                prov.label,
                w.label,
                f"{w.used:.0f}",
                lim_str,
                f"[{color}]{pct_str}[/{color}]",
                w.confidence,
            )

    console.print(table)
    if report.warnings:
        for warn in report.warnings:
            console.print(f"[yellow]⚠[/yellow] {warn}")


if __name__ == "__main__":
    app()
