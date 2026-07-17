from __future__ import annotations

from ai_quota_monitor.collector import merge_preserving
from ai_quota_monitor.schema import Provider, ProviderWindow, StatusReport


def _good_claude():
    return Provider(
        id="claude",
        label="CLAUDE",
        status="ok",
        windows=[
            ProviderWindow(id="session", label="5h", used=18.0, limit=100.0,
                           unit="percent", percent=0.18, confidence="official"),
            ProviderWindow(id="weekly", label="7d", used=31.0, limit=100.0,
                           unit="percent", percent=0.31, confidence="official"),
        ],
    )


def _failed_claude():
    return Provider(
        id="claude",
        label="CLAUDE",
        status="degraded",
        error="helper falló o token inválido",
        windows=[
            ProviderWindow(id="session", label="5h", used=0.0, unit="percent",
                           percent=None, confidence="unknown", source="unavailable"),
            ProviderWindow(id="weekly", label="7d", used=0.0, unit="percent",
                           percent=None, confidence="unknown", source="unavailable"),
        ],
    )


def test_failed_fetch_preserves_previous_value():
    prev = StatusReport(generated_at="2026-06-22T10:00:00-04:00", providers=[_good_claude()])
    fresh = StatusReport(generated_at="2026-06-22T10:02:00-04:00", providers=[_failed_claude()])

    merged = merge_preserving(prev, fresh)
    w = next(w for w in merged.providers[0].windows if w.id == "session")
    assert w.percent == 0.18                       # valor preservado
    assert w.stale_since == "2026-06-22T10:00:00-04:00"
    # status se mantiene degraded: el fetch en vivo sigue fallando.
    assert merged.providers[0].status == "degraded"


def test_fresh_good_value_overrides_and_clears_stale():
    prev = StatusReport(generated_at="2026-06-22T10:00:00-04:00", providers=[_good_claude()])
    fresh_good = _good_claude()
    fresh_good.windows[0].percent = 0.42
    fresh = StatusReport(generated_at="2026-06-22T10:02:00-04:00", providers=[fresh_good])

    merged = merge_preserving(prev, fresh)
    w = next(w for w in merged.providers[0].windows if w.id == "session")
    assert w.percent == 0.42
    assert w.stale_since is None


def test_no_previous_report_returns_fresh():
    fresh = StatusReport(providers=[_failed_claude()])
    merged = merge_preserving(None, fresh)
    assert merged is fresh


def test_absent_window_is_not_resurrected():
    # Codex dejó de exponer la ventana de 5h (plan prolite). El fetch fresco va OK y la
    # declara ausente: preservarla dejaría un fantasma congelado que nunca se refresca.
    prev_codex = Provider(
        id="codex", label="CODEX", status="ok",
        windows=[
            ProviderWindow(id="session", label="Session (5h)", used=1.0, limit=100.0,
                           unit="percent", percent=0.01, confidence="official"),
            ProviderWindow(id="weekly", label="Weekly (7d)", used=9.0, limit=100.0,
                           unit="percent", percent=0.09, confidence="official"),
        ],
    )
    fresh_codex = Provider(
        id="codex", label="CODEX", status="ok",
        absent_windows=["session"],
        windows=[
            ProviderWindow(id="weekly", label="Weekly (7d)", used=5.0, limit=100.0,
                           unit="percent", percent=0.05, confidence="official"),
        ],
    )
    prev = StatusReport(generated_at="2026-07-09T10:00:00-04:00", providers=[prev_codex])
    fresh = StatusReport(generated_at="2026-07-14T00:00:00-04:00", providers=[fresh_codex])

    merged = merge_preserving(prev, fresh)
    ids = [w.id for w in merged.providers[0].windows]
    assert "session" not in ids                     # el fantasma no vuelve
    assert merged.providers[0].windows[0].percent == 0.05   # y la semanal sí se refresca
    assert merged.providers[0].windows[0].stale_since is None


def test_window_dropped_in_fresh_is_recovered():
    prev_prov = _good_claude()
    prev_prov.windows.append(
        ProviderWindow(id="usd", label="USD", used=5.0, limit=30.0, unit="usd",
                       percent=0.16, confidence="official")
    )
    prev = StatusReport(generated_at="2026-06-22T10:00:00-04:00", providers=[prev_prov])
    fresh = StatusReport(generated_at="2026-06-22T10:02:00-04:00", providers=[_failed_claude()])

    merged = merge_preserving(prev, fresh)
    usd = next((w for w in merged.providers[0].windows if w.id == "usd"), None)
    assert usd is not None and usd.percent == 0.16
    assert usd.stale_since == "2026-06-22T10:00:00-04:00"
