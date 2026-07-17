from __future__ import annotations

from ai_quota_monitor.providers import deepseek


def _win(provider, window_id):
    return next((w for w in provider.windows if w.id == window_id), None)


def test_deepseek_balance_converts_usd_to_clp(monkeypatch):
    monkeypatch.setattr(
        deepseek,
        "_run_helper",
        lambda: {
            "source": "deepseek_api",
            "checked_at": "2026-06-20T12:00:00Z",
            "is_available": True,
            "balance_infos": [
                {
                    "currency": "USD",
                    "total_balance": "10.50",
                    "granted_balance": "0",
                    "topped_up_balance": "10.50",
                }
            ],
        },
    )

    p = deepseek.collect({"providers": {"deepseek": {"balance": {"clp_per_usd": 1000}}}})
    bal = _win(p, "balance")

    assert p.status == "ok"
    assert bal is not None
    assert bal.used == 10500
    assert bal.unit == "clp_estimated"
    assert bal.confidence == "configured_estimate"
    assert "10.50 USD" in bal.note


def test_deepseek_degraded_when_helper_unavailable(monkeypatch):
    monkeypatch.setattr(deepseek, "_run_helper", lambda: {"error": "secret_env_not_found"})

    p = deepseek.collect({})
    bal = _win(p, "balance")

    assert p.status == "degraded"
    assert p.error is not None
    assert bal is not None
    assert bal.confidence == "unknown"


def test_deepseek_keeps_original_currency_without_rate(monkeypatch):
    monkeypatch.setattr(
        deepseek,
        "_run_helper",
        lambda: {
            "source": "deepseek_api",
            "checked_at": "2026-06-20T12:00:00Z",
            "is_available": True,
            "balance_infos": [{"currency": "EUR", "total_balance": "2.25"}],
        },
    )

    p = deepseek.collect({})
    bal = _win(p, "balance")

    assert p.status == "ok"
    assert bal is not None
    assert bal.used == 2.25
    assert bal.unit == "eur"
    assert bal.confidence == "official"
