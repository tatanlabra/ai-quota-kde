from __future__ import annotations

from ai_quota_monitor.providers import deepseek


def _win(provider, window_id):
    return next((w for w in provider.windows if w.id == window_id), None)


def _raw(total: str, granted: str = "0", topped: str = "0", currency: str = "USD"):
    return {
        "source": "deepseek_api",
        "checked_at": "2026-06-22T12:00:00Z",
        "is_available": True,
        "balance_infos": [
            {
                "currency": currency,
                "total_balance": total,
                "granted_balance": granted,
                "topped_up_balance": topped,
            }
        ],
    }


def test_first_read_sets_full_balance(monkeypatch):
    """La primera lectura define el pico → saldo lleno (0% consumido)."""
    monkeypatch.setattr(deepseek, "_run_helper", lambda: _raw("10.00", topped="10.00"))
    p = deepseek.collect({"providers": {"deepseek": {"balance": {"clp_per_usd": 1000}}}})
    bal = _win(p, "balance")
    assert bal.percent == 0.0  # consumido 0 → remaining 100%


def test_consumption_lowers_remaining(monkeypatch):
    """Tras fijar el pico, una caída de saldo reduce el % restante."""
    cfg = {"providers": {"deepseek": {"balance": {"clp_per_usd": 1000}}}}
    monkeypatch.setattr(deepseek, "_run_helper", lambda: _raw("10.00", topped="10.00"))
    deepseek.collect(cfg)  # pico = 10
    monkeypatch.setattr(deepseek, "_run_helper", lambda: _raw("4.00", topped="4.00"))
    p = deepseek.collect(cfg)
    bal = _win(p, "balance")
    # consumido = 1 - 4/10 = 0.6
    assert abs(bal.percent - 0.6) < 1e-6


def test_topup_raises_ceiling(monkeypatch):
    """Una recarga por encima del pico previo eleva el techo y vuelve a 100%."""
    cfg = {"providers": {"deepseek": {"balance": {"clp_per_usd": 1000}}}}
    monkeypatch.setattr(deepseek, "_run_helper", lambda: _raw("10.00", topped="10.00"))
    deepseek.collect(cfg)
    monkeypatch.setattr(deepseek, "_run_helper", lambda: _raw("25.00", topped="25.00"))
    p = deepseek.collect(cfg)
    bal = _win(p, "balance")
    assert bal.percent == 0.0


def test_budget_override_used_when_configured(monkeypatch):
    """Si hay budget_clp, el % se calcula contra ese techo fijo en CLP."""
    cfg = {"providers": {"deepseek": {"balance": {"clp_per_usd": 1000, "budget_clp": 20000}}}}
    monkeypatch.setattr(deepseek, "_run_helper", lambda: _raw("10.00", topped="10.00"))
    p = deepseek.collect(cfg)
    bal = _win(p, "balance")
    # clp = 10*1000 = 10000; consumido = 1 - 10000/20000 = 0.5
    assert abs(bal.percent - 0.5) < 1e-6
    assert bal.limit == 20000.0


def test_note_shows_granted_and_topped(monkeypatch):
    monkeypatch.setattr(deepseek, "_run_helper", lambda: _raw("12.00", granted="2.00", topped="10.00"))
    p = deepseek.collect({"providers": {"deepseek": {"balance": {"clp_per_usd": 1000}}}})
    bal = _win(p, "balance")
    assert "gratis 2.00 + recarga 10.00" in bal.note
