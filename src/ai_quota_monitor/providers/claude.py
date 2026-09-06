from __future__ import annotations

import json
import os
import subprocess
from typing import Any

from ..paths import HELPER_CLAUDE
from ..schema import Confidence, Provider, ProviderWindow


def _run_helper() -> dict[str, Any] | None:
    if not HELPER_CLAUDE.exists():
        return None
    try:
        proc = subprocess.run(
            [str(HELPER_CLAUDE)],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
            env={"HOME": os.environ.get("HOME", ""), "PATH": os.environ.get("PATH", "")},
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return None
        return json.loads(proc.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        return None


def _make_window(window_id: str, label: str, raw: dict[str, Any] | None) -> ProviderWindow:
    if raw and "error" not in raw:
        # utilization viene como 0-100 (ya en porcentaje), no 0-1
        pct_raw = raw.get("utilization")
        reset = raw.get("resets_at")
        if pct_raw is not None:
            used_val = round(float(pct_raw), 1)
            pct_ratio = used_val / 100.0
        else:
            used_val = 0.0
            pct_ratio = None
        return ProviderWindow(
            id=window_id,
            label=label,
            used=used_val,
            limit=100.0,
            unit="percent",
            percent=pct_ratio,
            reset_at=reset,
            metric_kind="quota",
            renewal_kind="rolling" if reset else "unknown",
            cycle_days=7 if window_id == "weekly" else None,
            confidence="official",
            source="api.anthropic.com/api/oauth/usage",
        )
    return ProviderWindow(
        id=window_id,
        label=label,
        used=0.0,
        limit=None,
        unit="percent",
        percent=None,
        metric_kind="quota",
        renewal_kind="unknown",
        confidence="unknown",
        source="unavailable",
        note="API no disponible o token expirado",
    )


def _ccusage_window(cc: dict[str, Any]) -> ProviderWindow:
    """Ventana informativa de uso local de Claude Code (ccusage). Sin % de plan
    (no se conoce el límite), pero sobrevive a la expiración del token OAuth."""
    tokens = cc.get("total_tokens") or 0
    cost = cc.get("cost_usd")
    proj_cost = cc.get("projection_cost")
    bits = []
    if cost is not None:
        bits.append(f"${float(cost):.2f} en curso")
    if proj_cost is not None:
        bits.append(f"~${float(proj_cost):.2f} proyec.")
    return ProviderWindow(
        id="local",
        label="Claude Code (5h)",
        used=float(tokens),
        limit=None,
        unit="tokens",
        percent=None,
        reset_at=cc.get("reset_at"),
        metric_kind="activity",
        renewal_kind="rolling" if cc.get("reset_at") else "unknown",
        confidence="local_observed",
        source="ccusage",
        note=" · ".join(bits),
    )


def collect(cfg: dict) -> Provider:
    raw = _run_helper()
    network_ok = raw is not None and "error" not in raw

    if raw is not None and isinstance(raw.get("five_hour"), dict):
        five_hour = raw.get("five_hour")
        seven_day = raw.get("seven_day")
    else:
        five_hour = None
        seven_day = None

    windows = [
        _make_window("session", "Session (5h)", five_hour),
        _make_window("weekly", "Weekly (7d)", seven_day),
    ]

    # Fuente local resiliente: el conteo de Claude Code nunca queda totalmente en
    # blanco aunque expire el token. No alimenta el % (no hay límite conocido).
    cc = raw.get("ccusage") if isinstance(raw, dict) else None
    if isinstance(cc, dict):
        windows.append(_ccusage_window(cc))

    extra = raw.get("extra_usage") if raw else None
    if extra and extra.get("is_enabled"):
        # Saldo extra de Claude en USD. monthly_limit y used_credits vienen en CENTAVOS
        # (p.ej. monthly_limit=3000 = $30). utilization (0-100) es null cuando used=0.
        usd_limit = float(extra.get("monthly_limit") or 0) / 100.0
        usd_used = float(extra.get("used_credits") or 0) / 100.0
        util = extra.get("utilization")
        if util is not None:
            ex_pct = float(util) / 100.0
        elif usd_limit > 0:
            ex_pct = min(usd_used / usd_limit, 1.0)
        else:
            ex_pct = None
        cur = extra.get("currency", "USD")
        windows.append(ProviderWindow(
            id="usd",
            label="USD",
            used=round(usd_used, 2),
            limit=round(usd_limit, 2) if usd_limit > 0 else None,
            unit="usd",
            percent=ex_pct,
            reset_at=None,
            metric_kind="quota",
            renewal_kind="none",
            confidence="official",
            source="api.anthropic.com/api/oauth/usage",
            note=f"${usd_used:.2f}/${usd_limit:.0f} {cur} gastado",
        ))

    _ERR_MSG = {
        "token_expired": "token expirado — abre Claude Code para refrescar",
        "token_rejected": "token rechazado — abre Claude Code para refrescar",
        "rate_limited": "rate limit de la API — usando caché, reintenta solo",
    }
    if network_ok:
        error = None
    else:
        code = raw.get("error") if isinstance(raw, dict) else None
        error = _ERR_MSG.get(code, "helper falló o token inválido")

    return Provider(
        id="claude",
        label="CLAUDE",
        status="ok" if network_ok else "degraded",
        windows=windows,
        error=error,
    )
