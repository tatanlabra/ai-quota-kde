from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ai_quota_monitor import collector
from ai_quota_monitor.providers import copilot
from ai_quota_monitor.schema import Provider, ProviderWindow, StatusReport

HELPER = Path(__file__).resolve().parents[1] / "scripts" / "helper_copilot_usage.sh"
# El fixture de abajo es de un ciclo que reiniciaba el 1 de septiembre; el reloj se fija
# dentro de ese ciclo para que el test no dependa del dia en que se corre.
INSIDE_AUGUST_CYCLE = datetime(2026, 8, 29, tzinfo=timezone.utc)


def _event(timestamp: str, used: int = 128) -> str:
    return json.dumps(
        {
            "type": "model.model_call_success",
            "timestamp": timestamp,
            "data": {
                "quotaSnapshots": {
                    "chat": {
                        "entitlementRequests": 200,
                        "usedRequests": used,
                        "remainingPercentage": 100 - used // 2,
                        "resetDate": "2026-09-01T00:00:00Z",
                    }
                }
            },
        }
    )


def test_latest_chat_snapshot_becomes_observed_quota(tmp_path, monkeypatch):
    events = tmp_path / "session" / "events.jsonl"
    events.parent.mkdir()
    events.write_text(
        _event("2026-08-28T23:00:00Z", used=128)
        + "\nnot-json\n"
        + _event("2026-08-28T22:00:00Z", used=100)
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(copilot, "COPILOT_SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(copilot, "_utcnow", lambda: INSIDE_AUGUST_CYCLE)

    provider = copilot.collect({})

    assert provider.status == "ok"
    window = provider.windows[0]
    assert window.id == "copilot_chat"
    assert window.used == 128
    assert window.limit == 200
    assert window.percent == 0.64
    assert window.reset_at == "2026-09-01T00:00:00Z"
    assert window.confidence == "local_observed"


def test_missing_snapshot_is_not_reported_as_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(copilot, "COPILOT_SESSIONS_DIR", tmp_path)

    provider = copilot.collect({})

    assert provider.status == "degraded"
    assert provider.windows[0].percent is None
    assert provider.windows[0].limit is None
    assert provider.windows[0].confidence == "unknown"


def test_invalid_entitlement_is_unknown(tmp_path, monkeypatch):
    events = tmp_path / "session" / "events.jsonl"
    events.parent.mkdir()
    events.write_text(
        json.dumps(
            {
                "type": "model.model_call_success",
                "timestamp": "2026-08-28T23:00:00Z",
                "data": {
                    "quotaSnapshots": {
                        "chat": {
                            "entitlementRequests": 0,
                            "usedRequests": 0,
                        }
                    }
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(copilot, "COPILOT_SESSIONS_DIR", tmp_path)

    provider = copilot.collect({})

    assert provider.status == "degraded"
    assert provider.windows[0].limit is None


def _write_august_snapshot(tmp_path):
    events = tmp_path / "session" / "events.jsonl"
    events.parent.mkdir()
    events.write_text(_event("2026-08-28T23:00:00Z", used=128) + "\n", encoding="utf-8")


GITHUB_ANSWER = {
    "source": "github copilot_internal/user",
    "plan": "individual",
    "reset_at": "2026-11-01T00:00:00.000Z",
    "chat": {"entitlement": 200, "remaining": 196, "percent_remaining": 98.3, "unlimited": False},
    "premium_interactions": {"entitlement": 0, "remaining": 0, "percent_remaining": 0.0, "unlimited": False},
}


def test_a_closed_cycle_is_not_shown_as_the_current_balance(tmp_path, monkeypatch):
    """falsified_by: 2026-10-04. Sin la regla del ciclo cerrado, el snapshot de agosto
    sale como saldo vigente (128 de 200 con reinicio el 1 de septiembre), que es lo que
    el widget mostraba ese dia mientras GitHub decia 196 libres."""
    _write_august_snapshot(tmp_path)
    monkeypatch.setattr(copilot, "COPILOT_SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(copilot, "_utcnow", lambda: datetime(2026, 10, 4, tzinfo=timezone.utc))

    provider = copilot.collect({})

    assert provider.status == "degraded"
    assert provider.windows[0].percent is None
    assert provider.windows[0].confidence == "unknown"
    assert "ciclo cerrado" in provider.error


def test_online_quota_comes_from_github(tmp_path, monkeypatch):
    monkeypatch.setattr(copilot, "COPILOT_SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(copilot, "_run_helper", lambda: GITHUB_ANSWER)

    provider = copilot.collect({}, allow_network=True)

    assert provider.status == "ok"
    window = provider.windows[0]
    assert window.confidence == "official"
    assert window.limit == 200
    # percent_remaining manda sobre remaining: 98,3 % libre son 3,4 usadas, no 4.
    assert window.percent == pytest.approx(0.017)
    assert window.used == pytest.approx(3.4)
    assert window.reset_at == "2026-11-01T00:00:00Z"


def test_offline_never_asks_github(tmp_path, monkeypatch):
    def forbidden():
        raise AssertionError("el camino offline no debe llamar al helper")

    monkeypatch.setattr(copilot, "COPILOT_SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(copilot, "_run_helper", forbidden)

    assert copilot.collect({}, allow_network=False).status == "degraded"


@pytest.mark.parametrize(
    "answer",
    [None, {"error": "gh_api_failed"}, {**GITHUB_ANSWER, "chat": None},
     {**GITHUB_ANSWER, "chat": {**GITHUB_ANSWER["chat"], "unlimited": True}}],
)
def test_a_failed_github_read_keeps_the_last_good_value(tmp_path, monkeypatch, answer):
    """Ni el blip de red ni el snapshot local de un ciclo cerrado pueden pisar la cuota
    oficial de la corrida anterior: llegan como placeholder y merge_preserving conserva
    el valor previo marcado con stale_since."""
    _write_august_snapshot(tmp_path)
    monkeypatch.setattr(copilot, "COPILOT_SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(copilot, "_utcnow", lambda: datetime(2026, 10, 4, tzinfo=timezone.utc))
    monkeypatch.setattr(copilot, "_run_helper", lambda: answer)

    fresh_provider = copilot.collect({}, allow_network=True)
    assert fresh_provider.status == "degraded"
    assert fresh_provider.error.startswith("GitHub: ")

    official = copilot._official_window(GITHUB_ANSWER)
    prev = StatusReport(
        generated_at="2026-10-04T09:00:00-03:00",
        providers=[Provider(id="copilot", label="COPILOT", status="ok", windows=[official])],
    )
    merged = collector.merge_preserving(prev, StatusReport(providers=[fresh_provider]))
    kept = merged.providers[0].windows[0]
    assert kept.confidence == "official"
    assert kept.percent == pytest.approx(0.017)
    assert kept.stale_since == "2026-10-04T09:00:00-03:00"


def _fake_gh(tmp_path, body: str, code: int = 0) -> dict[str, str]:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    payload = tmp_path / "payload.txt"
    payload.write_text(body, encoding="utf-8")
    gh = bindir / "gh"
    gh.write_text(f"#!/bin/sh\ncat '{payload}'\nexit {code}\n", encoding="utf-8")
    gh.chmod(0o755)
    return {"HOME": str(tmp_path), "PATH": f"{bindir}:{os.environ['PATH']}"}


def _run(env):
    proc = subprocess.run([str(HELPER)], capture_output=True, text=True, env=env, timeout=30, check=False)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_helper_keeps_only_the_quota(tmp_path):
    """La respuesta de GitHub trae login, id y organizaciones; nada de eso sale."""
    answer = {
        "login": "someone",
        "id": 12345,
        "organization_list": [{"login": "acme"}],
        "analytics_tracking_id": "abc",
        "copilot_plan": "individual",
        "quota_reset_date_utc": "2026-11-01T00:00:00.000Z",
        "quota_snapshots": {
            "chat": {"entitlement": 200, "remaining": 196, "percent_remaining": 98.3,
                     "unlimited": False, "quota_id": "chat", "timestamp_utc": "x"},
        },
    }
    out = _run(_fake_gh(tmp_path, json.dumps(answer)))
    assert set(out) == {"source", "plan", "reset_at", "chat", "premium_interactions"}
    assert out["chat"] == {"entitlement": 200, "remaining": 196, "percent_remaining": 98.3, "unlimited": False}
    assert out["premium_interactions"] is None
    for private in ("someone", "12345", "acme", "abc"):
        assert private not in json.dumps(out)


@pytest.mark.parametrize(
    ("body", "code", "error"),
    [("", 1, "gh_api_failed"), ("<html>rate limited</html>", 0, "unexpected_payload")],
)
def test_helper_reports_failures_as_json(tmp_path, body, code, error):
    assert _run(_fake_gh(tmp_path, body, code)) == {"error": error}


def test_the_collector_asks_github_only_online(tmp_path, monkeypatch):
    """falsified_by: 2026-10-04. Llamar collect_copilot(cfg) sin allow_network deja el
    camino online sin cuota oficial y esto reprueba."""
    calls = {"n": 0}

    def helper():
        calls["n"] += 1
        return GITHUB_ANSWER

    monkeypatch.setattr(copilot, "COPILOT_SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(copilot, "_run_helper", helper)
    cfg = {
        "general": {"prefer_offline": True, "network_enabled": False},
        "providers": {name: {"enabled": name == "copilot"}
                      for name in ("claude", "codex", "gemini", "copilot", "deepseek")},
    }

    offline = collector.collect_all(cfg)
    assert calls["n"] == 0
    assert offline.network_used is False

    online = collector.collect_all(cfg, online=True)
    assert calls["n"] == 1
    assert online.network_used is True
    assert online.providers[0].windows[0].confidence == "official"
