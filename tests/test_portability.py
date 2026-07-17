from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from ai_quota_monitor import cli


ROOT = Path(__file__).resolve().parents[1]


def test_public_tree_has_no_private_absolute_paths():
    text_suffixes = {".py", ".sh", ".service", ".timer", ".qml", ".json"}
    text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for folder in ("src", "scripts", "systemd", "plasmoid")
        for path in (ROOT / folder).rglob("*")
        if path.is_file() and path.suffix in text_suffixes
    )
    assert "/home/ende" not in text
    assert "/opt/entornos" not in text
    assert "penta-agent" not in text


def test_qml_and_systemd_use_installed_wrapper():
    qml = (ROOT / "plasmoid/org.tatan.aiquota/contents/ui/main.qml").read_text()
    service = (ROOT / "systemd/ai-quota-monitor.service").read_text()
    assert "$HOME/.local/bin/ai-quota-monitor" in qml
    assert "ExecStart=%h/.local/bin/ai-quota-monitor refresh --online" in service
    assert "WorkingDirectory=" not in service


def test_sample_is_explicitly_sanitized(monkeypatch, tmp_path):
    status = tmp_path / "status.json"
    monkeypatch.setattr(cli, "STATUS_JSON", status)
    monkeypatch.setattr(cli, "CACHE_DIR", tmp_path)
    result = CliRunner().invoke(cli.app, ["sample", "--write-cache"])
    assert result.exit_code == 0
    payload = json.loads(status.read_text())
    assert payload["network_used"] is False
    assert all(window["source"] == "sample" for provider in payload["providers"] for window in provider["windows"])


def test_private_exports_are_ignored():
    ignored = (ROOT / ".gitignore").read_text()
    assert "*.html" in ignored
    assert "*_files/" in ignored
    assert "tests/fixtures/raw/" in ignored
