"""El servicio avisa cuando una cuota oficial lleva más de 30 min sin dato fresco.

Sin esto el 2026-10-03 Claude estuvo horas congelado en 0 %/0 % con el uso real en
6 %/1 %: el servicio salía 0, OnFailure= nunca se disparaba y solo stale_since lo
delataba. El aviso tiene que saltar con eso y callar con lo demás: la primera corrida
sin red tras una suspensión, lo que se omitió a propósito y lo que no es cuota.
"""

from __future__ import annotations

import datetime as dt
import json

from typer.testing import CliRunner

from ai_quota_monitor import cli, collector
from ai_quota_monitor.collector import persistently_stale
from ai_quota_monitor.schema import Provider, ProviderWindow, StatusReport

NOW = dt.datetime.fromisoformat("2026-10-04T12:00:00-03:00")
OLD = "2026-10-04T11:00:00-03:00"  # una hora antes de NOW


def _claude(stale_since=None, *, status="degraded", skipped=(), **window):
    fields = dict(id="session", label="5h", used=6.0, limit=100.0, unit="percent",
                  percent=0.06, confidence="official", stale_since=stale_since)
    fields.update(window)
    return Provider(id="claude", label="CLAUDE", status=status, error="rate limit de la API",
                    windows=[ProviderWindow(**fields)], skipped_windows=list(skipped))


def _report(*providers, at="2026-10-04T11:55:00-03:00"):
    return StatusReport(generated_at=at, providers=list(providers))


def test_quota_stale_two_runs_and_over_30_min_is_reported():
    """falsified_by: 2026-10-04. Cambiar `>` por `<` en la comparación con max_age
    deja esto en rojo y pone en verde el de menos de 30 min."""
    found = persistently_stale(_report(_claude(OLD)), _report(_claude(OLD)), now=NOW)
    assert found == ["CLAUDE · 5h: sin dato fresco desde 2026-10-04 11:00 (rate limit de la API)"]


def test_first_stale_run_after_a_long_suspend_does_not_alert():
    """falsified_by: 2026-10-04. Quitar la condición de la corrida anterior lo pone en
    rojo: stale_since apunta a antes de dormir, ocho horas atrás."""
    before_sleep = "2026-10-04T04:00:00-03:00"
    prev = _report(_claude(None, status="ok"), at=before_sleep)
    assert persistently_stale(prev, _report(_claude(before_sleep)), now=NOW) == []


def test_stale_for_less_than_30_min_does_not_alert():
    recent = "2026-10-04T11:40:00-03:00"
    assert persistently_stale(_report(_claude(recent)), _report(_claude(recent)), now=NOW) == []


def test_window_skipped_on_purpose_does_not_alert():
    """falsified_by: 2026-10-04. Sin el filtro de skipped_windows, el saldo USD que no
    se consulta mientras la statusline está al día avisaría siempre."""
    report = _report(_claude(OLD, status="ok", skipped=["session"]))
    assert persistently_stale(_report(_claude(OLD)), report, now=NOW) == []


def test_only_official_quota_windows_count():
    """falsified_by: 2026-10-04. Sin el filtro de metric_kind/confidence, la actividad
    local y el saldo viejos avisan."""
    for window in ({"metric_kind": "activity"}, {"metric_kind": "balance"},
                   {"confidence": "local_observed"}, {"confidence": "configured_estimate"}):
        prev, report = _report(_claude(OLD, **window)), _report(_claude(OLD, **window))
        assert persistently_stale(prev, report, now=NOW) == [], window


def test_unreadable_stale_since_is_reported_not_swallowed():
    found = persistently_stale(_report(_claude("ayer")), _report(_claude("ayer")), now=NOW)
    assert len(found) == 1 and "ilegible" in found[0]


def _wire_refresh(monkeypatch, tmp_path, fresh):
    status = tmp_path / "status.json"
    # Corrida anterior ya vieja: stale_since de hace días, mucho más de 30 min atrás.
    status.write_text(_report(_claude("2026-10-01T08:00:00-03:00")).model_dump_json())
    monkeypatch.setattr(cli, "STATUS_JSON", status)
    monkeypatch.setattr(cli, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cli.config, "load", lambda: {})
    monkeypatch.setattr(collector, "collect_all", lambda cfg, online=None: fresh())
    return status


def _failed_fetch():
    return _report(Provider(id="claude", label="CLAUDE", status="degraded", error="429",
                            windows=[ProviderWindow(id="session", label="5h", used=0.0,
                                                    unit="percent", confidence="unknown",
                                                    source="unavailable")]))


def test_online_refresh_writes_the_cache_and_then_exits_75(monkeypatch, tmp_path):
    """falsified_by: 2026-10-04. Sin el `raise typer.Exit(75)` sale 0 y el aviso no
    llega nunca, que es exactamente el fallo del 2026-10-03."""
    status = _wire_refresh(monkeypatch, tmp_path, _failed_fetch)
    result = CliRunner().invoke(cli.app, ["refresh", "--online"])
    assert result.exit_code == 75, result.output
    assert "CLAUDE · 5h: sin dato fresco desde 2026-10-01 08:00" in result.output
    saved = json.loads(status.read_text())
    assert saved["providers"][0]["windows"][0]["stale_since"] == "2026-10-01T08:00:00-03:00"


def test_offline_refresh_never_fails_for_old_data(monkeypatch, tmp_path):
    """quota_status.sh refresca con --offline y lee cualquier salida != 0 como fallo.
    falsified_by: 2026-10-04. Evaluar el criterio también en --offline lo pone en rojo."""
    _wire_refresh(monkeypatch, tmp_path, _failed_fetch)
    result = CliRunner().invoke(cli.app, ["refresh", "--offline"])
    assert result.exit_code == 0, result.output


def test_online_refresh_with_fresh_data_exits_0(monkeypatch, tmp_path):
    def fresh():
        return _report(_claude(None, status="ok"))
    _wire_refresh(monkeypatch, tmp_path, fresh)
    result = CliRunner().invoke(cli.app, ["refresh", "--online"])
    assert result.exit_code == 0, result.output
