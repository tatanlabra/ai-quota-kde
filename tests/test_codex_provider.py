from __future__ import annotations

import time

from ai_quota_monitor.providers import codex


def _snapshot(primary_pct, secondary_pct, primary_reset, secondary_reset, source="wham", credits=362.62):
    # Esquema unificado que emite el helper (wham/usage o fallback rollout).
    return {
        "source": source,
        "snapshot_ts": "2026-06-09T03:07:19Z",
        "plan_type": "plus",
        "primary": {"used_percent": primary_pct, "reset_at": primary_reset},
        "secondary": {"used_percent": secondary_pct, "reset_at": secondary_reset},
        "credits_balance": credits,
    }


def _win(provider, window_id):
    return next((w for w in provider.windows if w.id == window_id), None)


def test_codex_percent_windows(monkeypatch):
    now = int(time.time())
    snap = _snapshot(53.0, 88.0, now + 3600, now + 7 * 86400)
    monkeypatch.setattr(codex, "_run_helper", lambda: snap)

    p = codex.collect({})
    assert p.id == "codex"
    assert p.status == "ok"

    sess, week = _win(p, "session"), _win(p, "weekly")
    assert sess.unit == "percent" and week.unit == "percent"
    assert sess.used == 53.0
    assert abs(sess.percent - 0.53) < 1e-9
    assert abs(week.percent - 0.88) < 1e-9
    assert sess.confidence == "official"
    assert "wham" in sess.source.lower() or "cli+cloud" in sess.source.lower()
    assert sess.reset_at is not None and sess.reset_at.endswith("Z")
    assert sess.metric_kind == "quota" and sess.renewal_kind == "rolling"
    assert week.cycle_days == 7
    assert "plus" in sess.note


def test_codex_credits_window(monkeypatch):
    now = int(time.time())
    snap = _snapshot(53.0, 88.0, now + 3600, now + 7 * 86400, credits=362.62)
    monkeypatch.setattr(codex, "_run_helper", lambda: snap)

    cred = _win(codex.collect({}), "credits")
    assert cred is not None
    assert cred.unit == "credits"
    assert cred.used == 362.6
    assert cred.percent is None  # saldo, no porcentaje


def test_codex_window_reset_zeroes_usage(monkeypatch):
    now = int(time.time())
    # primary ya se reinició (reset_at en el pasado) → faltante 100%, used 0
    snap = _snapshot(50.0, 88.0, now - 10, now + 7 * 86400)
    monkeypatch.setattr(codex, "_run_helper", lambda: snap)

    sess = _win(codex.collect({}), "session")
    assert sess.used == 0.0
    assert sess.percent == 0.0
    assert "reiniciada" in sess.note


def test_codex_rollout_fallback_note(monkeypatch):
    now = int(time.time())
    snap = _snapshot(18.0, 83.0, now + 3600, now + 7 * 86400, source="rollout", credits=None)
    monkeypatch.setattr(codex, "_run_helper", lambda: snap)

    p = codex.collect({})
    sess = _win(p, "session")
    assert "fallback CLI" in sess.note
    assert _win(p, "credits") is None  # rollout no trae créditos


def test_codex_degraded_when_no_snapshot(monkeypatch):
    monkeypatch.setattr(codex, "_run_helper", lambda: {"error": "no_rate_limits_snapshot"})
    p = codex.collect({})
    assert p.status == "degraded"
    assert p.error is not None
    assert _win(p, "session").percent is None


# ── Identidad de ventana por duración, no por posición ────────────────────────
# Codex mueve la ventana semanal a 'primary' según el plan. Estos tests fijan que la
# ventana se identifique por window_minutes, que es lo único que la determina.

def _snapshot_v2(primary=None, secondary=None, source="wham", plan="prolite", credits=0.0):
    now = int(time.time())
    def win(spec):
        if spec is None:
            return {"used_percent": None, "reset_at": None, "window_minutes": None}
        used, minutes = spec
        return {"used_percent": used, "reset_at": now + 3600, "window_minutes": minutes}
    return {
        "source": source,
        "snapshot_ts": "2026-07-14T03:57:32Z",
        "plan_type": plan,
        "primary": win(primary),
        "secondary": win(secondary),
        "credits_balance": credits,
    }


def test_codex_prolite_exposes_only_weekly_window(monkeypatch):
    # Plan 'prolite' (real, 2026-07): una sola ventana SEMANAL en primary, secondary null.
    monkeypatch.setattr(codex, "_run_helper", lambda: _snapshot_v2(primary=(5.0, 10080)))
    p = codex.collect({})

    week = _win(p, "weekly")
    assert week is not None and week.used == 5.0
    assert week.label == "Weekly (7d)"
    # El 5% es semanal: NO debe aparecer disfrazado de ventana de 5h.
    assert _win(p, "session") is None
    # Y se declara ausente para que el merge no resucite un valor viejo de la caché.
    assert p.absent_windows == ["session"]


def test_codex_window_identity_follows_duration_not_position(monkeypatch):
    # Aunque la semanal venga en primary y la de 5h en secondary, cada una se clasifica
    # por su duración real.
    monkeypatch.setattr(
        codex, "_run_helper", lambda: _snapshot_v2(primary=(88.0, 10080), secondary=(53.0, 300))
    )
    p = codex.collect({})

    assert _win(p, "weekly").used == 88.0
    assert _win(p, "session").used == 53.0
    assert _win(p, "session").label == "Session (5h)"
    assert p.absent_windows == []


def test_codex_legacy_payload_falls_back_to_positional(monkeypatch):
    # Payload antiguo (sin window_minutes): se mantiene el mapeo posicional histórico.
    snap = _snapshot(53.0, 88.0, int(time.time()) + 3600, int(time.time()) + 7 * 86400)
    monkeypatch.setattr(codex, "_run_helper", lambda: snap)
    p = codex.collect({})

    assert _win(p, "session").used == 53.0
    assert _win(p, "weekly").used == 88.0
    assert p.absent_windows == []
