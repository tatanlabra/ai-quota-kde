from __future__ import annotations

from ai_quota_monitor.providers import claude


def _win(provider, window_id):
    return next((w for w in provider.windows if w.id == window_id), None)


def test_oauth_ok_populates_official_percent(monkeypatch):
    monkeypatch.setattr(
        claude,
        "_run_helper",
        lambda: {
            "five_hour": {"utilization": 18.0, "resets_at": "2026-06-22T17:00:00Z"},
            "seven_day": {"utilization": 31.0, "resets_at": "2026-06-29T07:00:00Z"},
        },
    )
    p = claude.collect({})
    assert p.status == "ok"
    s = _win(p, "session")
    assert s.percent == 0.18
    assert s.confidence == "official"


def test_ccusage_fallback_keeps_local_count_when_token_dies(monkeypatch):
    """Token OAuth caído: no hay % oficial, pero el conteo local de ccusage sobrevive."""
    monkeypatch.setattr(
        claude,
        "_run_helper",
        lambda: {
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
        lambda: {
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
        lambda: {
            "five_hour": {"utilization": 10.0, "resets_at": None},
            "seven_day": {"utilization": 20.0, "resets_at": None},
            "ccusage": {"total_tokens": 1000, "cost_usd": 0.05},
        },
    )
    p = claude.collect({})
    assert p.status == "ok"
    assert _win(p, "session").percent == 0.10
    assert _win(p, "local").used == 1000
