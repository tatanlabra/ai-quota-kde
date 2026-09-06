from __future__ import annotations

from ai_quota_monitor.providers import gemini


def _win(provider, window_id):
    return next((w for w in provider.windows if w.id == window_id), None)


def test_antigravity_and_gemini_cli_activity_are_separate(monkeypatch):
    monkeypatch.setattr(
        gemini,
        "_run_helper",
        lambda: {
            "agy_requests": 3,
            "cli_requests": 5,
            "agy_observed": True,
            "cli_observed": True,
            "agy_sources": 1,
            "cli_sources": 1,
            "requests_today": 99,
            "ccusage": {"status": "ok", "tokens": 123, "cost_usd": 0.02},
        },
    )

    provider = gemini.collect({})
    agy = _win(provider, "antigravity_activity")
    cli = _win(provider, "gemini_cli_activity")

    assert provider.label == "ANTIGRAVITY / GEMINI"
    assert agy.used == 3 and cli.used == 5
    assert agy.percent is None and cli.percent is None
    assert agy.limit is None and cli.limit is None
    assert agy.metric_kind == cli.metric_kind == "activity"
    assert agy.renewal_kind == cli.renewal_kind == "calendar_cutoff"
    assert agy.confidence == cli.confidence == "local_observed"
    assert "1000" not in cli.note


def test_zero_is_local_observed_only_with_explicit_source_evidence(monkeypatch):
    monkeypatch.setattr(
        gemini,
        "_run_helper",
        lambda: {"agy_requests": 0, "cli_requests": 0, "agy_observed": True,
                 "cli_observed": False, "agy_sources": 2, "cli_sources": 0},
    )

    provider = gemini.collect({})
    agy = _win(provider, "antigravity_activity")
    cli = _win(provider, "gemini_cli_activity")

    assert provider.status == "ok"
    assert agy.used == 0 and agy.confidence == "local_observed"
    assert agy.renewal_kind == "calendar_cutoff"
    assert cli.used == 0 and cli.confidence == "unknown"
    assert cli.renewal_kind == "unknown"
    assert cli.reset_at is None


def test_antigravity_failure_never_emits_a_configured_quota(monkeypatch):
    monkeypatch.setattr(gemini, "_run_helper", lambda: {"error": "jq_not_found"})
    # Sin red no se consulta `agy /usage`, así que tampoco hay cuota oficial que mostrar.
    monkeypatch.setattr(gemini, "_run_agy_usage", lambda: None)

    provider = gemini.collect({})
    # La invariante es la misma para toda ventana: un fallo no inventa un porcentaje.
    for win in provider.windows:
        assert win.percent is None
        assert win.limit is None
        assert win.confidence == "unknown"

    # El metric_kind sí depende de la ventana, y no es cosmético: collector.merge_preserving
    # preserva el último valor bueno de una cuota, pero deja pasar la actividad diaria
    # (un conteo de ayer sería un falso positivo). Ver test_antigravity_quota.py.
    kinds = {win.id: win.metric_kind for win in provider.windows}
    assert kinds["antigravity_activity"] == "activity"
    assert kinds["gemini_cli_activity"] == "activity"
    assert kinds["antigravity_gemini_weekly"] == "quota"
    assert kinds["antigravity_claude_gpt_weekly"] == "quota"
