from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..paths import COPILOT_SESSIONS_DIR, HELPER_COPILOT
from ..schema import Provider, ProviderWindow

OFFICIAL_SOURCE = "GitHub copilot_internal/user"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp if stamp.tzinfo is not None else None


def _run_helper() -> dict[str, Any] | None:
    """El helper consulta GitHub con `gh api`; solo el helper toca credenciales."""
    if not HELPER_COPILOT.exists():
        return None
    try:
        proc = subprocess.run(
            [str(HELPER_COPILOT)],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            env={"HOME": os.environ.get("HOME", ""), "PATH": os.environ.get("PATH", "")},
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return None
        return json.loads(proc.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        return None


def _official_window(raw: Any) -> ProviderWindow | None:
    chat = raw.get("chat") if isinstance(raw, dict) else None
    if not isinstance(chat, dict) or chat.get("unlimited") is True:
        return None
    entitlement = chat.get("entitlement")
    if not _is_number(entitlement) or entitlement <= 0:
        return None
    # percent_remaining trae decimales que `remaining` redondea: con la facturacion por
    # tokens una consulta puede costar 0,33 solicitudes (98,3 % libre con remaining=196).
    if _is_number(chat.get("percent_remaining")):
        free = chat["percent_remaining"] / 100
    elif _is_number(chat.get("remaining")):
        free = chat["remaining"] / entitlement
    else:
        return None
    free = min(max(free, 0.0), 1.0)
    reset = _parse_utc(raw.get("reset_at"))
    return ProviderWindow(
        id="copilot_chat",
        label="AI Credits / Premium requests",
        used=round(entitlement * (1 - free), 2),
        limit=float(entitlement),
        unit="requests",
        percent=round(1 - free, 4),
        reset_at=reset.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if reset else None,
        metric_kind="quota",
        renewal_kind="calendar_cutoff",
        confidence="official",
        source=OFFICIAL_SOURCE,
        note="saldo de la cuenta en GitHub: incluye CLI, VS Code y web",
    )


def _event_files() -> list[Path]:
    if not COPILOT_SESSIONS_DIR.is_dir():
        return []
    return list(COPILOT_SESSIONS_DIR.glob("*/events.jsonl"))


def _latest_snapshot() -> dict[str, Any] | None:
    latest: tuple[str, dict[str, Any]] | None = None
    for path in _event_files():
        try:
            with path.open(encoding="utf-8", errors="replace") as stream:
                for line in stream:
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if event.get("type") != "model.model_call_success":
                        continue
                    data = event.get("data")
                    snapshots = data.get("quotaSnapshots") if isinstance(data, dict) else None
                    timestamp = event.get("timestamp")
                    if not isinstance(snapshots, dict) or not isinstance(timestamp, str):
                        continue
                    if latest is None or timestamp > latest[0]:
                        latest = (timestamp, snapshots)
        except OSError:
            continue
    return latest[1] if latest else None


def _window(snapshot: dict[str, Any]) -> ProviderWindow | None:
    entitlement = snapshot.get("entitlementRequests")
    used = snapshot.get("usedRequests")
    if (
        not isinstance(entitlement, (int, float))
        or isinstance(entitlement, bool)
        or entitlement <= 0
        or not isinstance(used, (int, float))
        or isinstance(used, bool)
    ):
        return None

    used = max(0.0, float(used))
    entitlement = float(entitlement)
    percent = min(max(used / entitlement, 0.0), 1.0)
    reset_at = snapshot.get("resetDate")
    return ProviderWindow(
        id="copilot_chat",
        label="AI Credits / Premium requests",
        used=used,
        limit=entitlement,
        unit="requests",
        percent=percent,
        reset_at=reset_at if isinstance(reset_at, str) else None,
        metric_kind="quota",
        renewal_kind="calendar_cutoff",
        confidence="local_observed",
        source="Copilot CLI quotaSnapshots",
        note="saldo observado desde la última respuesta de Copilot",
    )


def collect(cfg: dict, allow_network: bool = False) -> Provider:
    official_error = None
    if allow_network:
        raw = _run_helper()
        window = _official_window(raw)
        if window is not None:
            return Provider(id="copilot", label="COPILOT", status="ok", windows=[window])
        official_error = "sin cuota en la respuesta"
        if isinstance(raw, dict) and raw.get("error"):
            official_error = raw["error"]
        elif raw is None:
            official_error = "helper no disponible"

    snapshots = _latest_snapshot()
    snapshot = snapshots.get("chat") if isinstance(snapshots, dict) else None
    window = _window(snapshot) if isinstance(snapshot, dict) else None
    reason = "sin snapshot local de cuota"
    if window is not None:
        # Un snapshot cuyo reinicio ya paso es el saldo de un ciclo cerrado, no el de
        # hoy. El 2026-10-04 el widget mostraba 128 de 200 usadas con reinicio el 1 de
        # septiembre, mientras GitHub decia 196 libres hasta el 1 de noviembre.
        reset = _parse_utc(window.reset_at)
        if reset is not None and reset <= _utcnow():
            reason = f"el ultimo snapshot local es de un ciclo cerrado (reinicio {window.reset_at})"
            window = None
    if official_error is not None:
        reason = f"GitHub: {official_error}; {reason}"

    if window is None:
        placeholder = ProviderWindow(
            id="copilot_chat",
            label="AI Credits / Premium requests",
            used=0.0,
            limit=None,
            unit="requests",
            percent=None,
            metric_kind="quota",
            renewal_kind="unknown",
            confidence="unknown",
            source="unavailable",
            note=reason,
        )
        return Provider(
            id="copilot",
            label="COPILOT",
            status="degraded",
            windows=[placeholder],
            error=reason,
        )

    return Provider(
        id="copilot",
        label="COPILOT",
        status="degraded" if official_error is not None else "ok",
        windows=[window],
        error=f"GitHub: {official_error}" if official_error is not None else None,
    )
