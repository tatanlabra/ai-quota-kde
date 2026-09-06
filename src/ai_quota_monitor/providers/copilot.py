from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ..paths import COPILOT_SESSIONS_DIR
from ..schema import Provider, ProviderWindow


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


def collect(cfg: dict) -> Provider:
    snapshots = _latest_snapshot()
    snapshot = snapshots.get("chat") if isinstance(snapshots, dict) else None
    window = _window(snapshot) if isinstance(snapshot, dict) else None
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
            note="sin snapshot local de cuota",
        )
        return Provider(
            id="copilot",
            label="COPILOT",
            status="degraded",
            windows=[placeholder],
            error="sin snapshot local de cuota",
        )

    return Provider(
        id="copilot",
        label="COPILOT",
        status="ok",
        windows=[window],
    )
