from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from typing import Any

from ..paths import CLAUDE_STATUSLINE_JSON, HELPER_CLAUDE
from ..schema import Confidence, Provider, ProviderWindow

API_SOURCE = "api.anthropic.com/api/oauth/usage"
STATUSLINE_SOURCE = "claude code statusline"

# La statusline reescribe su caché como mucho cada 60 s mientras hay una sesión de
# Claude Code activa. Pasado este margen no hay sesión: se consulta el endpoint por si
# el uso vino de claude.ai, y si falla se muestra el último valor marcado stale.
STATUSLINE_FRESH_SECONDS = 600


def _run_helper(skip_oauth: bool = False) -> dict[str, Any] | None:
    if not HELPER_CLAUDE.exists():
        return None
    env = {"HOME": os.environ.get("HOME", ""), "PATH": os.environ.get("PATH", "")}
    if skip_oauth:
        env["AIQ_CLAUDE_SKIP_OAUTH"] = "1"
    try:
        proc = subprocess.run(
            [str(HELPER_CLAUDE)],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
            env=env,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return None
        return json.loads(proc.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        return None


def _make_window(
    window_id: str, label: str, raw: dict[str, Any] | None, source: str = API_SOURCE
) -> ProviderWindow:
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
            source=source,
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


def _epoch_iso(value: Any, utc: bool = True) -> str | None:
    try:
        moment = datetime.fromtimestamp(float(value), tz=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None
    return moment.isoformat() if utc else moment.astimezone().isoformat()


def _statusline_snapshot(now: float) -> dict[str, Any] | None:
    """Lo que la statusline de Claude Code dejó en caché, con cada ventana ya en la forma
    del endpoint ({utilization 0-100, resets_at ISO}). Una ventana cuyo reinicio ya pasó
    se descarta: su porcentaje es de un ciclo cerrado, no del actual."""
    try:
        data = json.loads(CLAUDE_STATUSLINE_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    captured = data.get("captured_at")
    limits = data.get("rate_limits")
    if not isinstance(captured, (int, float)) or not isinstance(limits, dict):
        return None
    snap: dict[str, Any] = {"captured_at": float(captured)}
    for key in ("five_hour", "seven_day"):
        win = limits.get(key)
        if not isinstance(win, dict):
            continue
        pct = win.get("used_percentage")
        reset = win.get("resets_at")
        if not isinstance(pct, (int, float)) or not isinstance(reset, (int, float)) or reset <= now:
            continue
        snap[key] = {"utilization": float(pct), "resets_at": _epoch_iso(reset)}
    return snap if len(snap) > 1 else None


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
    now = time.time()
    snap = _statusline_snapshot(now)
    snap_fresh = snap is not None and now - snap["captured_at"] <= STATUSLINE_FRESH_SECONDS
    # Con la statusline al día no se consulta el endpoint: limita por token y cada 429
    # trae retry-after de 1 h (medido el 2026-10-03), que además deja sin datos al
    # /usage del propio Claude Code.
    raw = _run_helper(skip_oauth=snap_fresh)
    network_ok = raw is not None and "error" not in raw

    if raw is not None and isinstance(raw.get("five_hour"), dict):
        windows = [
            _make_window("session", "Session (5h)", raw.get("five_hour")),
            _make_window("weekly", "Weekly (7d)", raw.get("seven_day")),
        ]
    elif snap is not None:
        stale = None if snap_fresh else _epoch_iso(snap["captured_at"], utc=False)
        windows = []
        for wid, label, key in (("session", "Session (5h)", "five_hour"), ("weekly", "Weekly (7d)", "seven_day")):
            win = _make_window(wid, label, snap.get(key), source=STATUSLINE_SOURCE)
            if key in snap:
                win.stale_since = stale
            windows.append(win)
    else:
        windows = [
            _make_window("session", "Session (5h)", None),
            _make_window("weekly", "Weekly (7d)", None),
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
            source=API_SOURCE,
            note=f"${usd_used:.2f}/${usd_limit:.0f} {cur} gastado",
        ))

    _ERR_MSG = {
        "token_expired": "token expirado — abre Claude Code para refrescar",
        "token_rejected": "token rechazado — abre Claude Code para refrescar",
        "rate_limited": "rate limit de la API — usando caché, reintenta solo",
    }
    ok = network_ok or snap_fresh
    error = None
    if not ok:
        code = raw.get("error") if isinstance(raw, dict) else None
        error = _ERR_MSG.get(code, "helper falló o token inválido")
        retry_at = _epoch_iso(raw.get("retry_after_until"), utc=False) if isinstance(raw, dict) else None
        if code == "rate_limited" and retry_at:
            error = f"rate limit de la API — próximo intento {retry_at[11:16]}"

    return Provider(
        id="claude",
        label="CLAUDE",
        status="ok" if ok else "degraded",
        windows=windows,
        error=error,
        # Sin llamada al endpoint no hay saldo USD nuevo: que el merge conserve el previo.
        skipped_windows=["usd"] if snap_fresh and not network_ok else [],
    )
