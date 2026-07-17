from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from typing import Any

from ..paths import HELPER_CODEX
from ..schema import Provider, ProviderWindow

# Si el snapshot (solo en fallback rollout) supera esta antigüedad, anotarlo.
SNAPSHOT_STALE_SECONDS = 6 * 3600

# Codex cambia el esquema de rate limit según el plan: hasta 2026-07 exponía dos ventanas
# (primary=5h + secondary=7d), y el plan 'prolite' pasó a exponer UNA SOLA ventana semanal
# en primary, con secondary=null. Por eso la identidad de una ventana se deduce de su
# duración real (window_minutes), nunca de su posición en el payload.
DAY_MINUTES = 24 * 60

# Mapeo posicional heredado: solo para payloads antiguos que no traen window_minutes.
_LEGACY_BY_POSITION = {
    "primary": ("session", "Session (5h)"),
    "secondary": ("weekly", "Weekly (7d)"),
}


def _fmt_duration(minutes: int) -> str:
    if minutes % DAY_MINUTES == 0:
        return f"{minutes // DAY_MINUTES}d"
    if minutes % 60 == 0:
        return f"{minutes // 60}h"
    return f"{minutes}m"


def _canonical(window_minutes: Any) -> tuple[str, str] | None:
    """(id, label) canónico a partir de la duración real de la ventana.

    Ventana de hasta 24h → 'session'; más larga → 'weekly'. La etiqueta se deriva del
    dato, así que dice la verdad aunque Codex cambie las duraciones (7d, 5h, 3h…).
    """
    try:
        minutes = int(window_minutes)
    except (TypeError, ValueError):
        return None
    if minutes <= 0:
        return None
    if minutes <= DAY_MINUTES:
        return ("session", f"Session ({_fmt_duration(minutes)})")
    return ("weekly", f"Weekly ({_fmt_duration(minutes)})")


def _run_helper() -> dict[str, Any] | None:
    """El helper devuelve uso oficial en vivo (wham/usage, CLI+Cloud) o, como fallback,
    el snapshot rate_limits de los rollouts locales. Solo el helper toca credenciales."""
    if not HELPER_CODEX.exists():
        return None
    try:
        proc = subprocess.run(
            [str(HELPER_CODEX)],
            capture_output=True,
            text=True,
            timeout=12,
            check=False,
            env={"HOME": os.environ.get("HOME", ""), "PATH": os.environ.get("PATH", "")},
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return None
        return json.loads(proc.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        return None


def _iso_utc(epoch: Any) -> str | None:
    try:
        return (
            datetime.fromtimestamp(int(epoch), tz=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )
    except (TypeError, ValueError, OSError):
        return None


def _make_window(window_id: str, label: str, win: dict[str, Any] | None, now: int, source: str) -> ProviderWindow:
    # win = {used_percent, reset_at} de primary (5h) o secondary (semana).
    if win and win.get("used_percent") is not None:
        used_pct = float(win["used_percent"])
        reset_at = win.get("reset_at")
        note = ""
        # Reset honesto: si la ventana ya se reinició, el faltante vuelve a 100%.
        if isinstance(reset_at, (int, float)) and now >= int(reset_at):
            used_pct = 0.0
            note = "ventana reiniciada"
        return ProviderWindow(
            id=window_id,
            label=label,
            used=round(used_pct, 1),
            limit=100.0,
            unit="percent",
            percent=min(used_pct / 100.0, 1.0),
            reset_at=_iso_utc(reset_at),
            confidence="official",
            source=source,
            note=note,
        )
    return ProviderWindow(
        id=window_id,
        label=label,
        used=0.0,
        limit=None,
        unit="percent",
        percent=None,
        confidence="unknown",
        source="unavailable",
        note="uso no disponible",
    )


def collect(cfg: dict) -> Provider:
    raw = _run_helper()
    ok = raw is not None and "error" not in raw
    now = int(datetime.now(tz=timezone.utc).timestamp())

    src_kind = raw.get("source") if ok else None  # "wham" (CLI+Cloud) | "rollout" (solo CLI)
    if src_kind == "wham":
        src_label = "chatgpt wham/usage (CLI+Cloud)"
    elif src_kind == "rollout":
        src_label = "codex rollout (solo CLI)"
    else:
        src_label = "codex"

    windows: list[ProviderWindow] = []
    absent: list[str] = []

    if ok:
        # Emite solo las ventanas que el upstream expone de verdad, identificadas por su
        # duración. Las canónicas que no aparecen se declaran ausentes: en este plan no
        # existen, y sin esa señal el merge las resucitaría desde la caché para siempre.
        seen: list[str] = []
        for position in ("primary", "secondary"):
            win = raw.get(position)
            if not isinstance(win, dict) or win.get("used_percent") is None:
                continue
            win_id, win_label = _canonical(win.get("window_minutes")) or _LEGACY_BY_POSITION[position]
            if win_id in seen:
                continue
            seen.append(win_id)
            windows.append(_make_window(win_id, win_label, win, now, src_label))
        absent = [w for w in ("session", "weekly") if w not in seen]
    else:
        # Fetch fallido: placeholders vacíos para que merge_preserving restaure el
        # último valor bueno de la caché en vez de dejar el widget en blanco.
        windows = [
            _make_window("session", "Session (5h)", None, now, src_label),
            _make_window("weekly", "Weekly (7d)", None, now, src_label),
        ]

    # Créditos restantes (solo wham): ventana informativa, sin porcentaje.
    if ok and raw.get("credits_balance") is not None:
        try:
            bal = float(raw["credits_balance"])
            windows.append(
                ProviderWindow(
                    id="credits",
                    label="Credits",
                    used=round(bal, 1),
                    limit=None,
                    unit="credits",
                    percent=None,
                    confidence="official",
                    source=src_label,
                    note="saldo agéntico",
                )
            )
        except (TypeError, ValueError):
            pass

    # Notas en la ventana de sesión: plan + aviso si es fallback CLI/stale.
    if ok:
        parts: list[str] = []
        plan = raw.get("plan_type")
        if plan:
            parts.append(f"plan {plan}")
        if src_kind == "rollout":
            parts.append("fallback CLI (sin Cloud)")
            snap_ts = raw.get("snapshot_ts")
            if snap_ts:
                try:
                    snap_dt = datetime.fromisoformat(str(snap_ts).replace("Z", "+00:00"))
                    age = now - int(snap_dt.timestamp())
                    if age > SNAPSHOT_STALE_SECONDS:
                        parts.append(f"snapshot {age // 3600}h atrás")
                except (ValueError, AttributeError):
                    pass
        if parts and windows and windows[0].note == "":
            windows[0].note = "; ".join(parts)

    error = None
    if not ok:
        reason = raw.get("error") if isinstance(raw, dict) else "helper no disponible"
        error = f"sin datos de Codex ({reason})"

    return Provider(
        id="codex",
        label="CODEX",
        status="ok" if ok else "degraded",
        windows=windows,
        error=error,
        absent_windows=absent,
    )
