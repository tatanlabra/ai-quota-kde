from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timedelta
from typing import Any

from ..paths import HELPER_GEMINI
from ..schema import Provider, ProviderWindow


def _run_helper() -> dict[str, Any] | None:
    if not HELPER_GEMINI.exists():
        return None
    try:
        proc = subprocess.run(
            [str(HELPER_GEMINI)],
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


def _next_local_midnight_iso() -> str:
    now = datetime.now().astimezone()
    nxt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return nxt.isoformat()


def collect(cfg: dict) -> Provider:
    gem_cfg = cfg.get("providers", {}).get("gemini", {})
    daily_cfg = gem_cfg.get("daily", {})
    limit = daily_cfg.get("limit_requests", 1000)

    raw = _run_helper()
    ok = raw is not None and "error" not in raw

    if ok:
        used = int(raw.get("requests_today", 0) or 0)
        pct = min(used / limit, 1.0) if limit and limit > 0 else None
        bits = []
        if raw.get("agy_requests") is not None:
            bits.append(f"agy {raw['agy_requests']}")
        if raw.get("cli_requests") is not None:
            bits.append(f"cli {raw['cli_requests']}")
        ccusage = raw.get("ccusage")
        if isinstance(ccusage, dict):
            status = ccusage.get("status")
            if status == "ok":
                tokens = ccusage.get("tokens")
                cost = ccusage.get("cost_usd")
                cc_bits = []
                if isinstance(tokens, (int, float)) and tokens > 0:
                    cc_bits.append(f"{int(tokens)} tokens")
                if isinstance(cost, (int, float)) and cost > 0:
                    cc_bits.append(f"USD {cost:.4f}")
                if cc_bits:
                    bits.append("ccusage " + ", ".join(cc_bits))
                else:
                    bits.append("ccusage ok")
            elif status and status != "not_installed":
                bits.append(f"ccusage {status}")
        note = "; ".join(bits + ["estimación local (sin cuota oficial)"])
        win = ProviderWindow(
            id="daily",
            label="Daily (req)",
            used=float(used),
            limit=float(limit),
            unit="requests",
            percent=pct,
            reset_at=_next_local_midnight_iso(),
            confidence="configured_estimate",
            source="agy/gemini logs",
            note=note,
        )
        return Provider(id="gemini", label="GEMINI", status="ok", windows=[win], error=None)

    reason = raw.get("error") if isinstance(raw, dict) else "helper no disponible"
    return Provider(
        id="gemini",
        label="GEMINI",
        status="degraded",
        windows=[
            ProviderWindow(
                id="daily",
                label="Daily (req)",
                used=0.0,
                limit=float(limit),
                unit="requests",
                percent=None,
                confidence="unknown",
                source="unavailable",
                note="sin datos agy/gemini (en preparación)",
            )
        ],
        error=f"gemini sin datos ({reason})",
    )
