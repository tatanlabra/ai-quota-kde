from __future__ import annotations

import json
import time

import pytest

from ai_quota_monitor.providers import claude


def _win(provider, window_id):
    return next((w for w in provider.windows if w.id == window_id), None)


@pytest.fixture(autouse=True)
def _statusline_cache(tmp_path, monkeypatch):
    """Cada test parte sin caché de statusline: la real de ~/.cache no debe colarse."""
    path = tmp_path / "claude-rate-limits.json"
    monkeypatch.setattr(claude, "CLAUDE_STATUSLINE_JSON", path)
    return path


def _write_statusline(path, age_s, five=None, seven=None):
    now = time.time()
    limits = {}
    if five is not None:
        limits["five_hour"] = {"used_percentage": five[0], "resets_at": int(now + five[1])}
    if seven is not None:
        limits["seven_day"] = {"used_percentage": seven[0], "resets_at": int(now + seven[1])}
    path.write_text(json.dumps({"captured_at": int(now - age_s), "rate_limits": limits}))


def _spy(monkeypatch, payload):
    calls = []
    monkeypatch.setattr(claude, "_run_helper", lambda **kw: calls.append(kw) or payload)
    return calls


def test_oauth_ok_populates_official_percent(monkeypatch):
    monkeypatch.setattr(
        claude,
        "_run_helper",
        lambda **_: {
            "five_hour": {"utilization": 18.0, "resets_at": "2026-06-22T17:00:00Z"},
            "seven_day": {"utilization": 31.0, "resets_at": "2026-06-29T07:00:00Z"},
        },
    )
    p = claude.collect({})
    assert p.status == "ok"
    s = _win(p, "session")
    assert s.percent == 0.18
    assert s.confidence == "official"
    assert s.metric_kind == "quota"
    assert s.renewal_kind == "rolling"
    assert _win(p, "weekly").cycle_days == 7


def test_ccusage_fallback_keeps_local_count_when_token_dies(monkeypatch):
    """Token OAuth caído: no hay % oficial, pero el conteo local de ccusage sobrevive."""
    monkeypatch.setattr(
        claude,
        "_run_helper",
        lambda **_: {
            "error": "api_request_failed",
            "ccusage": {
                "total_tokens": 441118,
                "cost_usd": 1.21,
                "reset_at": "2026-06-23T06:00:00.000Z",
                "projection_cost": 43.81,
            },
        },
    )
    p = claude.collect({})
    # status degraded (fetch en vivo falla) pero hay ventana local usable.
    assert p.status == "degraded"
    local = _win(p, "local")
    assert local is not None
    assert local.used == 441118
    assert local.confidence == "local_observed"
    assert local.source == "ccusage"
    # las ventanas oficiales quedan 'unknown' → merge_preserving restaurará la caché.
    assert _win(p, "session").confidence == "unknown"


def test_token_expired_gives_actionable_error_and_keeps_ccusage(monkeypatch):
    """Token OAuth expirado: error accionable, ventanas oficiales 'unknown'
    (para que merge_preserving restaure la caché) y ccusage local presente."""
    monkeypatch.setattr(
        claude,
        "_run_helper",
        lambda **_: {
            "error": "token_expired",
            "ccusage": {"total_tokens": 12345, "cost_usd": 0.5},
        },
    )
    p = claude.collect({})
    assert p.status == "degraded"
    assert p.error is not None and "abre Claude Code" in p.error
    assert _win(p, "session").confidence == "unknown"
    local = _win(p, "local")
    assert local is not None and local.used == 12345 and local.confidence == "local_observed"


def test_ccusage_attached_alongside_official(monkeypatch):
    monkeypatch.setattr(
        claude,
        "_run_helper",
        lambda **_: {
            "five_hour": {"utilization": 10.0, "resets_at": None},
            "seven_day": {"utilization": 20.0, "resets_at": None},
            "ccusage": {"total_tokens": 1000, "cost_usd": 0.05},
        },
    )
    p = claude.collect({})
    assert p.status == "ok"
    assert _win(p, "session").percent == 0.10
    assert _win(p, "local").used == 1000


def test_fresh_statusline_gives_official_percent_without_calling_endpoint(monkeypatch, _statusline_cache):
    """falsified_by: 2026-10-03, forzando snap_fresh=False el helper recibe skip_oauth=False."""
    _write_statusline(_statusline_cache, age_s=30, five=(42.5, 3600), seven=(12.0, 86400))
    calls = _spy(monkeypatch, {"error": "skipped", "ccusage": {"total_tokens": 10}})
    p = claude.collect({})
    assert calls == [{"skip_oauth": True}]
    assert p.status == "ok" and p.error is None
    s = _win(p, "session")
    assert s.percent == 0.425 and s.confidence == "official"
    assert s.source == claude.STATUSLINE_SOURCE and s.stale_since is None
    assert _win(p, "weekly").percent == 0.12
    assert p.skipped_windows == ["usd"]
    assert _win(p, "local").used == 10


def test_stale_statusline_asks_endpoint_and_shows_last_value_on_429(monkeypatch, _statusline_cache):
    _write_statusline(_statusline_cache, age_s=3600, five=(30.0, 600), seven=(20.0, 86400))
    until = int(time.time() + 900)
    calls = _spy(monkeypatch, {"error": "rate_limited", "retry_after_until": until})
    p = claude.collect({})
    assert calls == [{"skip_oauth": False}]
    assert p.status == "degraded"
    assert "próximo intento" in p.error
    s = _win(p, "session")
    assert s.percent == 0.30 and s.stale_since is not None
    assert p.skipped_windows == []


def test_endpoint_ok_wins_over_stale_statusline(monkeypatch, _statusline_cache):
    _write_statusline(_statusline_cache, age_s=3600, five=(30.0, 600), seven=(20.0, 86400))
    _spy(monkeypatch, {
        "five_hour": {"utilization": 50.0, "resets_at": "2026-10-03T18:30:00Z"},
        "seven_day": {"utilization": 25.0, "resets_at": "2026-10-09T22:00:00Z"},
    })
    p = claude.collect({})
    assert p.status == "ok"
    s = _win(p, "session")
    assert s.percent == 0.5 and s.source == claude.API_SOURCE and s.stale_since is None


def test_window_whose_reset_already_passed_is_ignored(monkeypatch, _statusline_cache):
    """Un % de un ciclo ya cerrado no describe el actual: esa ventana queda 'unknown'."""
    _write_statusline(_statusline_cache, age_s=30, five=(90.0, -10), seven=(15.0, 86400))
    _spy(monkeypatch, {"error": "skipped"})
    p = claude.collect({})
    assert _win(p, "session").confidence == "unknown"
    assert _win(p, "weekly").percent == 0.15


def test_corrupt_statusline_cache_falls_back_to_endpoint(monkeypatch, _statusline_cache):
    _statusline_cache.write_text("{no es json")
    calls = _spy(monkeypatch, {"error": "rate_limited"})
    p = claude.collect({})
    assert calls == [{"skip_oauth": False}]
    assert p.status == "degraded" and _win(p, "session").confidence == "unknown"
