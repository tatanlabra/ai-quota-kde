from __future__ import annotations

from ai_quota_monitor.providers import deepseek


def _win(provider, window_id):
    return next((w for w in provider.windows if w.id == window_id), None)


def _raw(total: str = "10.50", currency: str = "USD"):
    return {
        "source": "deepseek_api",
        "checked_at": "2026-06-20T12:00:00Z",
        "is_available": True,
        "balance_infos": [
            {
                "currency": currency,
                "total_balance": total,
                "granted_balance": "0",
                "topped_up_balance": total,
            }
        ],
    }


def test_deepseek_balance_stays_official_and_has_no_renewal(monkeypatch):
    monkeypatch.setattr(deepseek, "_run_helper", _raw)

    p = deepseek.collect({"providers": {"deepseek": {"balance": {"clp_per_usd": 1000}}}})
    bal = _win(p, "balance")

    assert p.status == "ok"
    assert bal is not None
    assert bal.used == 10.5
    assert bal.unit == "usd"
    assert bal.percent is None
    assert bal.metric_kind == "balance"
    assert bal.renewal_kind == "none"
    assert bal.confidence == "official"
    assert "recarga sin vencimiento" in bal.note


def test_deepseek_optional_budget_is_separate_estimate(monkeypatch):
    monkeypatch.setattr(deepseek, "_run_helper", lambda: _raw("10.00"))
    cfg = {"providers": {"deepseek": {"balance": {"clp_per_usd": 1000, "budget_clp": 20000}}}}

    p = deepseek.collect(cfg)
    bal, budget = _win(p, "balance"), _win(p, "budget")

    assert bal.confidence == "official" and bal.percent is None
    assert budget is not None
    assert budget.used == 10000.0
    assert budget.limit == 20000.0
    assert budget.percent == 0.5
    assert budget.confidence == "configured_estimate"
    assert budget.metric_kind == "quota"
    assert budget.renewal_kind == "none"


def test_deepseek_degraded_when_helper_unavailable(monkeypatch):
    monkeypatch.setattr(deepseek, "_run_helper", lambda: {"error": "secret_env_not_found"})

    p = deepseek.collect({})
    bal = _win(p, "balance")

    assert p.status == "degraded"
    assert p.error is not None
    assert bal is not None
    assert bal.label == "Saldo API"
    assert bal.confidence == "unknown"
    assert bal.metric_kind == "balance"


def test_deepseek_keeps_original_currency_without_rate(monkeypatch):
    monkeypatch.setattr(deepseek, "_run_helper", lambda: _raw("2.25", currency="EUR"))

    p = deepseek.collect({})
    bal = _win(p, "balance")

    assert p.status == "ok"
    assert bal is not None
    assert bal.used == 2.25
    assert bal.unit == "eur"
    assert bal.confidence == "official"
    assert _win(p, "budget") is None


def test_fx_rate_older_than_two_months_is_reported_as_a_warning():
    """Un tipo de cambio declarado a mano no caduca solo, y el presupuesto en CLP se calcula con el.

    falsified_by: 2026-09-06. Antes de este aviso, `rates_checked_at = "2026-06-20"`
    llevaba 78 dias en config.toml sin que nada lo dijera, mientras el widget mostraba
    "Presupuesto CLP 29% usado" como si fuera una medicion. Con 59 dias el informe no
    debe traer aviso: el umbral tiene que distinguir, no avisar siempre.
    """
    import datetime as dt

    from ai_quota_monitor.collector import _fx_staleness_warning

    def cfg_for(days_ago: int) -> dict:
        checked = dt.date.today() - dt.timedelta(days=days_ago)
        return {
            "providers": {
                "deepseek": {"balance": {"rates_checked_at": checked.isoformat()}}
            }
        }

    assert _fx_staleness_warning(cfg_for(61)) is not None
    assert "61" in _fx_staleness_warning(cfg_for(61))
    assert _fx_staleness_warning(cfg_for(59)) is None
    assert _fx_staleness_warning({}) is None
    # Una fecha corrupta se declara, no se traga en silencio.
    bad = {"providers": {"deepseek": {"balance": {"rates_checked_at": "ayer"}}}}
    assert "no es una fecha ISO" in _fx_staleness_warning(bad)
