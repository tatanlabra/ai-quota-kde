from __future__ import annotations

import logging
from typing import Any

from .schema import Provider, ProviderWindow, StatusReport

log = logging.getLogger(__name__)


def _is_usable(win: ProviderWindow) -> bool:
    """Una ventana es 'usable' si trae dato real (no un placeholder de fallo)."""
    return win.confidence != "unknown" and win.source != "unavailable"


def merge_preserving(prev: StatusReport | None, fresh: StatusReport) -> StatusReport:
    """Funde el reporte fresco con el previo conservando el último valor bueno.

    Si una ventana fresca llega vacía/degradada (un blip de red o token expirado)
    pero el reporte anterior tenía un valor usable para esa misma ventana, se conserva
    el valor previo y se marca con `stale_since` = generated_at del reporte anterior.
    Así un fallo transitorio nunca borra el conteo (p.ej. Claude con token expirado).
    """
    if prev is None:
        return fresh

    prev_windows: dict[tuple[str, str], ProviderWindow] = {}
    for p in prev.providers:
        for w in p.windows:
            if _is_usable(w):
                prev_windows[(p.id, w.id)] = w

    for prov in fresh.providers:
        # El upstream respondió OK y declaró que estas ventanas ya no existen: preservarlas
        # produciría un fantasma congelado (un valor viejo que nunca vuelve a refrescarse).
        absent = set(prov.absent_windows)
        merged: list[ProviderWindow] = []
        seen_ids: set[str] = set()
        for w in prov.windows:
            seen_ids.add(w.id)
            if _is_usable(w) or w.id in absent:
                merged.append(w)
                continue
            old = prev_windows.get((prov.id, w.id))
            if old is not None:
                kept = old.model_copy(deep=True)
                kept.stale_since = old.stale_since or prev.generated_at
                merged.append(kept)
            else:
                merged.append(w)
        # Conserva ventanas que existían antes y desaparecieron del fetch fresco
        # (p.ej. la API dejó de devolver 'usd'/'credits' por un error puntual).
        for (pid, wid), old in prev_windows.items():
            if pid == prov.id and wid not in seen_ids and wid not in absent:
                kept = old.model_copy(deep=True)
                kept.stale_since = old.stale_since or prev.generated_at
                merged.append(kept)
        prov.windows = merged
        # status se mantiene 'degraded' a propósito: el fetch en vivo está fallando
        # aunque mostremos datos preservados. La antigüedad la comunica stale_since.

    return fresh


def collect_all(cfg: dict[str, Any]) -> StatusReport:
    providers: list[Provider] = []
    warnings: list[str] = []
    errors: list[str] = []
    network_used = False

    providers_cfg = cfg.get("providers", {})

    if providers_cfg.get("claude", {}).get("enabled", True):
        try:
            from .providers.claude import collect as collect_claude
            p = collect_claude(cfg)
            providers.append(p)
            if p.status != "ok" and p.error:
                warnings.append(f"claude: {p.error}")
            # Si tiene datos oficiales, usó red
            if any(w.confidence == "official" for w in p.windows):
                network_used = True
        except Exception as exc:
            log.exception("claude provider falló")
            errors.append(f"claude: {exc}")

    if providers_cfg.get("codex", {}).get("enabled", True):
        try:
            from .providers.codex import collect as collect_codex
            p = collect_codex(cfg)
            providers.append(p)
            if p.status != "ok" and p.error:
                warnings.append(f"codex: {p.error}")
        except Exception as exc:
            log.exception("codex provider falló")
            errors.append(f"codex: {exc}")

    if providers_cfg.get("gemini", {}).get("enabled", True):
        try:
            from .providers.gemini import collect as collect_gemini
            p = collect_gemini(cfg)
            providers.append(p)
            if p.status != "ok" and p.error:
                warnings.append(f"gemini: {p.error}")
        except Exception as exc:
            log.exception("gemini provider falló")
            errors.append(f"gemini: {exc}")

    if providers_cfg.get("deepseek", {}).get("enabled", True):
        try:
            from .providers.deepseek import collect as collect_deepseek
            p = collect_deepseek(cfg)
            providers.append(p)
            if p.status != "ok" and p.error:
                warnings.append(f"deepseek: {p.error}")
            if any(w.confidence in {"official", "configured_estimate"} for w in p.windows):
                network_used = True
        except Exception as exc:
            log.exception("deepseek provider falló")
            errors.append(f"deepseek: {exc}")

    return StatusReport(
        network_used=network_used,
        providers=providers,
        warnings=warnings,
        errors=errors,
    )
