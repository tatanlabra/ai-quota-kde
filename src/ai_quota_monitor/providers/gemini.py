from __future__ import annotations

import json
import os
import shutil
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


# ── Cuota oficial de Antigravity ──────────────────────────────────────────────
#
# `agy -p "/usage"` es un comando client-side: medido el 2026-08-17 devuelve
# total_tokens=0, tarda ~6 s, y NO crea un brain/transcript nuevo (129 -> 129 dirs),
# así que no contamina el conteo local de requests que calcula helper_gemini_usage.sh.
# Aun así es una request de red, y este workspace ya se comió un HTTP 429 por recolectar
# cuota en vivo: se invoca SOLO en el camino online (`refresh --online`, timer de 5 min),
# nunca desde una delegación.
#
# Antigravity expone DOS cuotas semanales independientes, con relojes distintos:
#   gemini-weekly -> modelos de Google (Gemini Flash/Pro)
#   3p-weekly     -> modelos de terceros (Claude Opus/Sonnet, GPT-OSS)
# El bucket 3p ES Claude, pero facturado por Google en el plan de Antigravity: es una
# ventana distinta de la cuota directa de Claude, así que la etiqueta lo dice explícito
# para que no queden dos cosas llamadas "Claude" indistinguibles en el widget.
AGY_USAGE_TIMEOUT_S = 20

_ANTIGRAVITY_BUCKETS: tuple[tuple[str, str, str], ...] = (
    ("gemini-weekly", "antigravity_gemini_weekly", "Antigravity Gemini (7d)"),
    ("3p-weekly", "antigravity_claude_gpt_weekly", "Antigravity Claude/GPT (7d)"),
)


def _run_agy_usage() -> dict[str, Any] | None:
    """Lee las cuotas semanales de Antigravity. None = no consultable."""
    exe = shutil.which("agy")
    if not exe:
        return None
    try:
        proc = subprocess.run(
            [exe, "-p", "/usage", "--output-format", "json", "--print-timeout", "15s"],
            capture_output=True,
            text=True,
            timeout=AGY_USAGE_TIMEOUT_S,
            check=False,
            env={"HOME": os.environ.get("HOME", ""), "PATH": os.environ.get("PATH", "")},
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return None
        data = json.loads(proc.stdout)
        return data if isinstance(data, dict) else None
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError, ValueError):
        return None


def _usage_buckets(usage: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(usage, dict):
        return {}
    groups = (usage.get("command") or {}).get("data", {}).get("groups") or []
    out: dict[str, dict[str, Any]] = {}
    for group in groups:
        if not isinstance(group, dict):
            continue
        for bucket in group.get("buckets") or []:
            bucket_id = bucket.get("id") if isinstance(bucket, dict) else None
            if isinstance(bucket_id, str):
                out[bucket_id] = bucket
    return out


def _unavailable_quota_window(window_id: str, label: str, note: str) -> ProviderWindow:
    """Placeholder de cuota NO usable, para que el merge preserve el último valor bueno.

    metric_kind DEBE ser "quota", nunca "activity": collector.merge_preserving deja pasar
    las ventanas de actividad sin preservarlas (una actividad diaria vieja sería un falso
    conteo), así que una cuota marcada como actividad parpadearía a cero cada vez que
    fallara la red.
    """
    return ProviderWindow(
        id=window_id,
        label=label,
        used=0.0,
        limit=None,
        unit="percent",
        percent=None,
        reset_at=None,
        metric_kind="quota",
        renewal_kind="unknown",
        cycle_days=7,
        confidence="unknown",
        source="unavailable",
        note=note,
    )


def _antigravity_quota_windows(
    usage: dict[str, Any] | None, unavailable_note: str
) -> list[ProviderWindow]:
    """Convierte los buckets de `agy /usage` en ventanas de cuota.

    INVERSIÓN: `remaining_fraction` es la fracción RESTANTE; `percent` del esquema es la
    fracción USADA. Con 0.0 restante la cuota está agotada -> percent = 1.0. Sin invertir,
    el widget pintaría el grupo agotado como si estuviera intacto.
    """
    buckets = _usage_buckets(usage)
    windows: list[ProviderWindow] = []
    for bucket_id, window_id, label in _ANTIGRAVITY_BUCKETS:
        bucket = buckets.get(bucket_id)
        remaining = bucket.get("remaining_fraction") if isinstance(bucket, dict) else None
        if not isinstance(remaining, (int, float)) or isinstance(remaining, bool):
            windows.append(_unavailable_quota_window(window_id, label, unavailable_note))
            continue
        remaining = min(max(float(remaining), 0.0), 1.0)
        used_fraction = 1.0 - remaining
        reset_at = bucket.get("reset_time")
        note = str(bucket.get("description") or "").strip()
        windows.append(
            ProviderWindow(
                id=window_id,
                label=label,
                used=round(used_fraction * 100.0, 2),
                limit=100.0,
                unit="percent",
                percent=used_fraction,
                # RFC3339 absoluto tal cual lo entrega agy: nunca recalculado desde el
                # "refreshes in N days" de la descripción, que envejece en la caché.
                reset_at=reset_at if isinstance(reset_at, str) and reset_at else None,
                metric_kind="quota",
                renewal_kind="rolling",
                cycle_days=7,
                confidence="official",
                source="agy /usage",
                note=note,
            )
        )
    return windows


def _next_local_midnight_iso() -> str:
    now = datetime.now().astimezone()
    nxt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return nxt.isoformat()


def _observed(raw: dict[str, Any], key: str, requests: int) -> bool:
    """Distingue un cero medido de la ausencia de una fuente compatible.

    Los helpers nuevos emiten `<key>_observed`. Para una caché/helper viejo, solo
    un conteo positivo prueba observación; un cero sin evidencia queda como unknown.
    """
    value = raw.get(f"{key}_observed")
    if isinstance(value, bool):
        return value
    return requests > 0


def collect(cfg: dict, allow_network: bool = False) -> Provider:
    raw = _run_helper()
    ok = raw is not None and "error" not in raw
    # El default es offline: la cuota externa solo se consulta cuando el llamador
    # declara el camino online (`refresh --online`).
    quota_windows = _antigravity_quota_windows(
        _run_agy_usage() if allow_network else None,
        "modo offline; valor previo se preserva si existe"
        if not allow_network
        else "agy /usage no consultable",
    )
    quota_ok = any(w.confidence == "official" for w in quota_windows)

    if ok:
        agy_requests = int(raw.get("agy_requests", 0) or 0)
        cli_requests = int(raw.get("cli_requests", 0) or 0)
        agy_observed = _observed(raw, "agy", agy_requests)
        cli_observed = _observed(raw, "cli", cli_requests)
        agy_sources = int(raw.get("agy_sources", 0) or 0)
        cli_sources = int(raw.get("cli_sources", 0) or 0)
        cli_bits = ["conteo local; sin cuota oficial"]
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
                    cli_bits.append("ccusage " + ", ".join(cc_bits))
                else:
                    cli_bits.append("ccusage ok")
            elif status and status != "not_installed":
                cli_bits.append(f"ccusage {status}")
        cutoff = _next_local_midnight_iso()
        # NO es ilimitado: Antigravity corta por cuota semanal por grupo de modelos
        # (verificado 2026-08-17, gemini-weekly al 0% con reset a 5 días). Esta ventana
        # sigue siendo un conteo local de requests; la cuota real va en las ventanas
        # `antigravity_*_weekly`.
        agy_note = "requests locales; la cuota semanal real va en las ventanas oficiales"
        if agy_observed:
            agy_note += f"; {agy_sources} fuente(s) compatible(s)"
        else:
            agy_note = "sin registro local compatible hoy"
        if cli_observed:
            cli_bits.append(f"{cli_sources} fuente(s) compatible(s)")
        else:
            cli_bits = ["sin registro local compatible hoy"]
        windows = [
            ProviderWindow(
                id="antigravity_activity",
                label="Antigravity (hoy)",
                used=float(agy_requests),
                limit=None,
                unit="requests",
                percent=None,
                reset_at=cutoff if agy_observed else None,
                metric_kind="activity",
                renewal_kind="calendar_cutoff" if agy_observed else "unknown",
                confidence="local_observed" if agy_observed else "unknown",
                source="agy transcript logs" if agy_observed else "unavailable",
                note=agy_note,
            ),
            ProviderWindow(
                id="gemini_cli_activity",
                label="Gemini CLI (hoy)",
                used=float(cli_requests),
                limit=None,
                unit="requests",
                percent=None,
                reset_at=cutoff if cli_observed else None,
                metric_kind="activity",
                renewal_kind="calendar_cutoff" if cli_observed else "unknown",
                confidence="local_observed" if cli_observed else "unknown",
                source="gemini cli logs" if cli_observed else "unavailable",
                note="; ".join(cli_bits),
            ),
        ]
        local_ok = agy_observed or cli_observed
        return Provider(
            id="gemini",
            label="ANTIGRAVITY / GEMINI",
            status="ok" if (quota_ok or local_ok) else "degraded",
            windows=quota_windows + windows,
            error=None if (quota_ok or local_ok) else "sin registros locales compatibles",
        )

    reason = raw.get("error") if isinstance(raw, dict) else "helper no disponible"
    return Provider(
        id="gemini",
        label="ANTIGRAVITY / GEMINI",
        # La cuota oficial y el conteo local son fuentes independientes: que el helper
        # local falle no invalida un /usage que sí respondió.
        status="ok" if quota_ok else "degraded",
        windows=quota_windows + [
            ProviderWindow(
                id="antigravity_activity",
                label="Antigravity (hoy)",
                used=0.0,
                limit=None,
                unit="requests",
                percent=None,
                metric_kind="activity",
                renewal_kind="unknown",
                confidence="unknown",
                source="unavailable",
                note="sin actividad local consultable",
            ),
            ProviderWindow(
                id="gemini_cli_activity",
                label="Gemini CLI (hoy)",
                used=0.0,
                limit=None,
                unit="requests",
                percent=None,
                metric_kind="activity",
                renewal_kind="unknown",
                confidence="unknown",
                source="unavailable",
                note="sin actividad local consultable",
            ),
        ],
        error=None if quota_ok else f"antigravity/gemini sin datos ({reason})",
    )
