from __future__ import annotations

import json
import os
import subprocess
from typing import Any

from ..paths import HELPER_DEEPSEEK
from ..schema import Provider, ProviderWindow

DEFAULT_CLP_PER_USD = 950.0
DEFAULT_CLP_PER_CNY = 132.0

def _run_helper() -> dict[str, Any] | None:
    if not HELPER_DEEPSEEK.exists():
        return None
    try:
        proc = subprocess.run(
            [str(HELPER_DEEPSEEK)],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            env={"HOME": os.environ.get("HOME", ""), "PATH": os.environ.get("PATH", "")},
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return None
        return json.loads(proc.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        return None


def _rate_for(currency: str, balance_cfg: dict[str, Any]) -> float | None:
    cur = currency.upper()
    if cur == "USD":
        value = balance_cfg.get("clp_per_usd", DEFAULT_CLP_PER_USD)
    elif cur == "CNY":
        value = balance_cfg.get("clp_per_cny", DEFAULT_CLP_PER_CNY)
    else:
        return None
    try:
        rate = float(value)
    except (TypeError, ValueError):
        return None
    return rate if rate > 0 else None


def _parse_amount(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _best_balance(raw: dict[str, Any]) -> dict[str, Any] | None:
    infos = raw.get("balance_infos")
    if not isinstance(infos, list) or not infos:
        return None
    valid = [info for info in infos if isinstance(info, dict)]
    if not valid:
        return None
    return next((info for info in valid if str(info.get("currency", "")).upper() == "USD"), valid[0])


def collect(cfg: dict) -> Provider:
    raw = _run_helper()
    ok = raw is not None and "error" not in raw
    balance_cfg = cfg.get("providers", {}).get("deepseek", {}).get("balance", {})

    if ok:
        info = _best_balance(raw)
        if info:
            currency = str(info.get("currency") or "").upper()
            total = _parse_amount(info.get("total_balance"))
            granted = _parse_amount(info.get("granted_balance"))
            topped = _parse_amount(info.get("topped_up_balance"))
            rate = _rate_for(currency, balance_cfg)
            checked_at = raw.get("checked_at")
            available = raw.get("is_available")
            # Presupuesto personal opcional: nunca se infiere desde un máximo histórico.
            budget_clp = _parse_amount(balance_cfg.get("budget_clp")) if balance_cfg.get("budget_clp") else 0.0

            note_bits = [f"{total:.2f} {currency}"]
            if granted > 0 or topped > 0:
                note_bits.append(f"gratis {granted:.2f} + recarga {topped:.2f}")
            if checked_at:
                note_bits.append(f"checked {checked_at}")
            if available is False:
                note_bits.append("no disponible para inferencia")

            # /user/balance es la fuente de verdad: no comunica una cuota, ni el
            # vencimiento del crédito gratuito. Nunca lo convertimos en porcentaje.
            windows = [
                ProviderWindow(
                    id="balance",
                    label=f"Saldo {currency or 'original'}",
                    used=total,
                    limit=None,
                    unit=(currency.lower() if currency else "currency"),
                    percent=None,
                    metric_kind="balance",
                    renewal_kind="none",
                    confidence="official",
                    source="api.deepseek.com/user/balance",
                    note="; ".join(note_bits + ["recarga sin vencimiento; crédito gratis: Billing"]),
                )
            ]

            # El presupuesto CLP sigue siendo útil para planificación personal, pero
            # es otro dato: saldo API × FX manual contra un techo local explícito.
            if rate and budget_clp > 0:
                balance_clp = round(total * rate)
                spent_clp = min(max(budget_clp - balance_clp, 0.0), budget_clp)
                windows.append(
                    ProviderWindow(
                        id="budget",
                        label="Presupuesto CLP",
                        used=float(round(spent_clp)),
                        limit=float(round(budget_clp)),
                        unit="clp_estimated",
                        percent=spent_clp / budget_clp,
                        metric_kind="quota",
                        renewal_kind="none",
                        confidence="configured_estimate",
                        source="saldo API × FX configurado / presupuesto local",
                        note=(
                            f"saldo estimado ${balance_clp:,} CLP; "
                            f"FX {rate:.2f} {currency}/CLP configurado"
                        ),
                    )
                )
            return Provider(
                id="deepseek",
                label="DEEPSEEK",
                status="ok" if available else "degraded",
                windows=windows,
                error=None if available else "saldo insuficiente o cuenta no disponible",
            )

    reason = raw.get("error") if isinstance(raw, dict) else "helper no disponible"
    return Provider(
        id="deepseek",
        label="DEEPSEEK",
        status="degraded",
        windows=[
            ProviderWindow(
                id="balance",
                label="Saldo API",
                used=0.0,
                limit=None,
                unit="currency",
                percent=None,
                metric_kind="balance",
                renewal_kind="none",
                confidence="unknown",
                source="unavailable",
                note="sin saldo DeepSeek consultable",
            )
        ],
        error=f"deepseek sin saldo consultable ({reason})",
    )
