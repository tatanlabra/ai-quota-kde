from __future__ import annotations

import json
import os
import subprocess
from typing import Any

from ..paths import CACHE_DIR, HELPER_DEEPSEEK
from ..schema import Provider, ProviderWindow
from ..security import atomic_write

DEFAULT_CLP_PER_USD = 950.0
DEFAULT_CLP_PER_CNY = 132.0

# High-water-mark del saldo por moneda: la API no expone un techo, así que el % de
# saldo restante se deriva del pico observado (se eleva al recargar). Persistente.
PEAK_FILE = CACHE_DIR / "deepseek_peak.json"


def _load_peak(currency: str) -> float:
    try:
        data = json.loads(PEAK_FILE.read_text(encoding="utf-8"))
        if str(data.get("currency", "")).upper() == currency.upper():
            return float(data.get("peak", 0.0))
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    return 0.0


def _save_peak(currency: str, peak: float) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        atomic_write(PEAK_FILE, json.dumps({"currency": currency.upper(), "peak": peak}))
    except OSError:
        pass


def _remaining_percent(currency: str, total: float) -> float | None:
    """Devuelve el % CONSUMIDO (0-1) respecto al pico histórico de saldo.
    El anillo de la UI muestra 1 - percent = saldo restante. None si no hay base."""
    if total <= 0:
        # Saldo agotado o sin dato: si hubo pico, está 100% consumido.
        peak = _load_peak(currency)
        return 1.0 if peak > 0 else None
    peak = _load_peak(currency)
    ceiling = max(peak, total)
    if ceiling > total:
        # Pico mayor: hubo consumo desde la última recarga.
        _save_peak(currency, ceiling)
        return min(max(1.0 - total / ceiling, 0.0), 1.0)
    # total >= peak → recarga (o primera lectura): nuevo pico, saldo lleno.
    _save_peak(currency, total)
    return 0.0


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
            # Override opcional: techo fijo en CLP. Si no, high-water-mark de la API.
            budget_clp = _parse_amount(balance_cfg.get("budget_clp")) if balance_cfg.get("budget_clp") else 0.0

            note_bits = [f"{total:.2f} {currency}"]
            if granted > 0 or topped > 0:
                note_bits.append(f"gratis {granted:.2f} + recarga {topped:.2f}")
            if checked_at:
                note_bits.append(f"checked {checked_at}")
            if available is False:
                note_bits.append("no disponible para inferencia")

            if rate:
                clp = round(total * rate)
                if budget_clp > 0:
                    pct = min(max(1.0 - clp / budget_clp, 0.0), 1.0)
                else:
                    pct = _remaining_percent(currency, total)
                return Provider(
                    id="deepseek",
                    label="DEEPSEEK",
                    status="ok" if available else "degraded",
                    windows=[
                        ProviderWindow(
                            id="balance",
                            label="Saldo CLP",
                            used=float(clp),
                            limit=float(round(budget_clp)) if budget_clp > 0 else None,
                            unit="clp_estimated",
                            percent=pct,
                            confidence="configured_estimate",
                            source="api.deepseek.com/user/balance + configured FX",
                            note="; ".join(note_bits),
                        )
                    ],
                    error=None if available else "saldo insuficiente o cuenta no disponible",
                )
            return Provider(
                id="deepseek",
                label="DEEPSEEK",
                status="ok" if available else "degraded",
                windows=[
                    ProviderWindow(
                        id="balance",
                        label=f"Saldo {currency or 'original'}",
                        used=total,
                        limit=None,
                        unit=(currency.lower() if currency else "currency"),
                        percent=_remaining_percent(currency, total),
                        confidence="official",
                        source="api.deepseek.com/user/balance",
                        note="; ".join(note_bits + ["CLP no configurado"]),
                    )
                ],
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
                label="Saldo CLP",
                used=0.0,
                limit=None,
                unit="clp_estimated",
                percent=None,
                confidence="unknown",
                source="unavailable",
                note="sin datos DeepSeek",
            )
        ],
        error=f"deepseek sin saldo consultable ({reason})",
    )
