from __future__ import annotations

import json
import re
from pathlib import Path

from typer.testing import CliRunner

from ai_quota_monitor import cli


ROOT = Path(__file__).resolve().parents[1]
LEGACY_PROJECT_PATH = "/".join(("incubadora", "ai" + "-quota-kde"))
LEGACY_SOURCE_EXPR = '"incubadora" / "' + "ai" + '-quota-kde" / "src"'


def test_public_tree_has_no_private_absolute_paths():
    text_suffixes = {".py", ".sh", ".service", ".timer", ".qml", ".json"}
    text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for folder in ("src", "scripts", "systemd", "plasmoid")
        for path in (ROOT / folder).rglob("*")
        if path.is_file() and path.suffix in text_suffixes
    )
    text += (ROOT / "README.md").read_text()
    text += "\n".join(path.read_text() for path in (ROOT / "po").glob("*.po*"))
    assert not re.search(r"/home/[a-zA-Z0-9_.-]+/", text)
    assert "/opt/entornos" not in text
    assert "penta-agent" not in text
    assert LEGACY_PROJECT_PATH not in text


def test_qml_reaches_the_collector_only_through_its_systemd_unit():
    """El widget dejo de invocar el CLI: lee la cache y, para refrescar, arranca la unidad.

    falsified_by: 2026-09-06. Sobre v0.2.0-hud-pre-refactor este test falla en la
    primera asercion, porque main.qml llevaba
    `sh -lc '$HOME/.local/bin/ai-quota-monitor refresh --online'` en la linea 14 y lo
    ejecutaba al cargar, al abrir el popup y en el boton. Medido con plasmoidviewer:
    11 muestras de `refresh --online` con el PPID del propio widget antes del cambio,
    0 despues.
    """
    ui = ROOT / "plasmoid/org.tatan.aiquota/contents/ui"
    qml_sources = {path.name: path.read_text() for path in sorted(ui.rglob("*.qml"))}
    joined = "\n".join(qml_sources.values())

    # Ningun QML invoca el CLI del colector, ni en linea ni a traves de un login shell.
    assert "ai-quota-monitor status" not in joined
    assert "ai-quota-monitor refresh" not in joined
    assert "--online" not in joined
    assert "sh -lc" not in joined

    main_qml = qml_sources["main.qml"]
    assert "systemctl --user start ai-quota-monitor.service" in main_qml
    assert "toolTipItem: QuotaTooltip" in main_qml
    assert LEGACY_PROJECT_PATH not in joined

    # La lectura es un `cat` de la cache, sin intermediarios.
    assert 'cat -- "$HOME/.cache/ai-quota-monitor/status.json"' in qml_sources["StatusFile.qml"]

    service = (ROOT / "systemd/ai-quota-monitor.service").read_text()
    assert "ExecStart=%h/.local/bin/ai-quota-monitor refresh --online" in service
    assert "WorkingDirectory=" not in service


def test_the_collector_unit_rate_limits_manual_starts():
    """El limite anti-429 lo aplica systemd, no la interfaz, que no puede saltarselo.

    falsified_by: 2026-09-06. Sin estas dos directivas la unidad corre con los
    valores por omision, medidos en vivo antes del cambio:
    StartLimitIntervalUSec=10s y StartLimitBurst=5, que no acotan nada en la ventana
    de 10 minutos que importa. Con ellas, `systemctl --user show` devuelve 10min/4.
    """
    service = (ROOT / "systemd/ai-quota-monitor.service").read_text()
    unit_section = service.split("[Service]", 1)[0]
    # Han de ir en [Unit]: en [Service] systemd las ignora sin avisar.
    assert "StartLimitIntervalSec=600" in unit_section
    assert "StartLimitBurst=4" in unit_section


def test_sample_is_explicitly_sanitized(monkeypatch, tmp_path):
    status = tmp_path / "status.json"
    monkeypatch.setattr(cli, "STATUS_JSON", status)
    monkeypatch.setattr(cli, "CACHE_DIR", tmp_path)
    result = CliRunner().invoke(cli.app, ["sample", "--write-cache"])
    assert result.exit_code == 0
    payload = json.loads(status.read_text())
    assert payload["network_used"] is False
    assert {p["id"] for p in payload["providers"]} == {"claude", "codex", "gemini", "copilot", "deepseek"}
    assert all(window["source"] == "sample" for provider in payload["providers"] for window in provider["windows"])


def test_private_exports_are_ignored():
    ignored = (ROOT / ".gitignore").read_text()
    assert "*.html" in ignored
    assert "*_files/" in ignored
    assert "tests/fixtures/raw/" in ignored


def test_gemini_helper_keeps_ccusage_offline_only():
    helper = (ROOT / "scripts/helper_gemini_usage.sh").read_text(encoding="utf-8")
    assert "ccusage gemini daily --json --offline" in helper
    assert "ccusage gemini daily --json 2>" not in helper


def test_governance_doctor_reports_data_boundaries():
    result = CliRunner().invoke(cli.app, ["doctor"])
    assert result.exit_code == 0
    assert "Gobernanza de datos del repositorio" in result.stdout
    assert "tests/fixtures/raw/ ignorado" in result.stdout
    assert "exports HTML ignorados" in result.stdout


def test_workspace_mcp_quota_uses_canonical_source_when_present():
    workspace = ROOT.parents[1]
    quota_server = workspace / "herramientas" / "mcp-quota" / "quota_server.py"
    if not quota_server.exists():
        return
    text = quota_server.read_text(encoding="utf-8")
    assert '"activos" / "ai-quota-kde" / "src"' in text
    assert LEGACY_SOURCE_EXPR not in text


def test_config_defaults_do_not_advertise_keys_nobody_reads():
    """Una clave en el config por omision promete una configuracion que no existe.

    falsified_by: 2026-09-06. Antes de esto, `_DEFAULT_CONFIG` escribia
    refresh_seconds, [ui] theme, show_costs, show_tokens, show_requests y
    compact_panel_text en el config de cada instalacion nueva, y `rg` sobre src/
    no encontraba un solo lector para ninguna. El caso rojo se reproduce con
    `git show v0.2.0-hud-pre-refactor:src/ai_quota_monitor/config.py`.
    """
    from ai_quota_monitor import config as cfg_mod

    defaults = cfg_mod._DEFAULT_CONFIG
    for orphan in ("refresh_seconds", "theme", "show_costs", "show_tokens",
                   "show_requests", "compact_panel_text"):
        assert orphan not in defaults, orphan

    # Un config antiguo no se rompe: se declara, con su motivo.
    legacy = {"general": {"refresh_seconds": 60}, "ui": {"compact_panel_text": "worst-provider"}}
    reported = cfg_mod.obsolete_keys_present(legacy)
    assert len(reported) == 2
    assert any("refresh_seconds" in line and "timer" in line for line in reported)
    # Un config limpio no inventa avisos.
    assert cfg_mod.obsolete_keys_present({"general": {"timezone": "America/Santiago"}}) == []
