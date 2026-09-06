from __future__ import annotations

import datetime as _dt
import logging
from typing import Any

from .schema import Provider, ProviderWindow, StatusReport

log = logging.getLogger(__name__)


# El tipo de cambio de DeepSeek se declara a mano en config.toml y no caduca solo:
# el presupuesto en pesos se calcula con el, asi que un valor viejo produce una cifra
# que parece medida y no lo es. Sesenta dias es el umbral, y el aviso viaja en el
# propio informe para que se vea en el widget y no solo en el fichero.
_FX_STALE_DAYS = 60


def _fx_staleness_warning(cfg: dict[str, Any]) -> str | None:
    balance_cfg = (
        cfg.get("providers", {}).get("deepseek", {}).get("balance", {})
        if isinstance(cfg, dict)
        else {}
    )
    checked = balance_cfg.get("rates_checked_at")
    if not checked:
        return None
    try:
        checked_date = _dt.date.fromisoformat(str(checked))
    except ValueError:
        return f"deepseek: rates_checked_at no es una fecha ISO ({checked!r})"
    age = (_dt.date.today() - checked_date).days
    if age <= _FX_STALE_DAYS:
        return None
    return (
        f"deepseek: el tipo de cambio se comprobo hace {age} dias "
        f"(rates_checked_at={checked_date.isoformat()}); "
        "el presupuesto en CLP se calcula con el"
    )


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
            # La actividad local es una observación de una ventana diaria, no una
            # cuota persistente. Si hoy no hay una fuente compatible, conservar el
            # conteo de otra corrida convertiría actividad vieja en un falso cero.
            if w.metric_kind == "activity":
                merged.append(w)
                continue
            old = prev_windows.get((prov.id, w.id))
            if old is not None:
                kept = old.model_copy(deep=True)
                kept.stale_since = old.stale_since or prev.generated_at
                merged.append(kept)
            else:
                merged.append(w)
        # Una respuesta sana es la autoridad sobre el conjunto de métricas: una
        # ventana ausente se retiró y no debe revivir desde una caché de otro esquema.
        # Solo un proveedor degradado puede haber omitido ventanas por un fallo puntual.
        if prov.status != "ok":
            for (pid, wid), old in prev_windows.items():
                if pid == prov.id and wid not in seen_ids and wid not in absent:
                    kept = old.model_copy(deep=True)
                    kept.stale_since = old.stale_since or prev.generated_at
                    merged.append(kept)
        prov.windows = merged
        # status se mantiene 'degraded' a propósito: el fetch en vivo está fallando
        # aunque mostremos datos preservados. La antigüedad la comunica stale_since.

    return fresh


def _network_allowed(cfg: dict[str, Any], online: bool | None) -> bool:
    if online is not None:
        return online
    general = cfg.get("general", {})
    if general.get("prefer_offline", True):
        return False
    return bool(general.get("network_enabled", False))


def _offline_provider(provider_id: str, label: str, windows: list[ProviderWindow], error: str) -> Provider:
    return Provider(
        id=provider_id,
        label=label,
        status="degraded",
        windows=windows,
        error=error,
    )


def _offline_claude() -> Provider:
    return _offline_provider(
        "claude",
        "CLAUDE",
        [
            ProviderWindow(
                id="session",
                label="Session (5h)",
                used=0.0,
                unit="percent",
                percent=None,
                metric_kind="quota",
                renewal_kind="unknown",
                confidence="unknown",
                source="unavailable",
                note="modo offline; valor previo se preserva si existe",
            ),
            ProviderWindow(
                id="weekly",
                label="Weekly (7d)",
                used=0.0,
                unit="percent",
                percent=None,
                metric_kind="quota",
                renewal_kind="unknown",
                confidence="unknown",
                source="unavailable",
                note="modo offline; valor previo se preserva si existe",
            ),
        ],
        "modo offline: Claude API no consultada",
    )


def _offline_codex() -> Provider:
    return _offline_provider(
        "codex",
        "CODEX",
        [
            ProviderWindow(
                id="weekly",
                label="Weekly (7d)",
                used=0.0,
                unit="percent",
                percent=None,
                metric_kind="quota",
                renewal_kind="unknown",
                confidence="unknown",
                source="unavailable",
                note="modo offline; valor previo se preserva si existe",
            ),
            ProviderWindow(
                id="credits",
                label="Credits",
                used=0.0,
                unit="credits",
                percent=None,
                metric_kind="balance",
                renewal_kind="none",
                confidence="unknown",
                source="unavailable",
                note="modo offline; valor previo se preserva si existe",
            ),
        ],
        "modo offline: Codex usage API no consultada",
    )


def _offline_deepseek() -> Provider:
    return _offline_provider(
        "deepseek",
        "DEEPSEEK",
        [
            ProviderWindow(
                id="balance",
                label="Saldo API",
                used=0.0,
                unit="currency",
                percent=None,
                metric_kind="balance",
                renewal_kind="none",
                confidence="unknown",
                source="unavailable",
                note="modo offline; saldo DeepSeek no consultado",
            )
        ],
        "modo offline: DeepSeek API no consultada",
    )


def collect_all(cfg: dict[str, Any], online: bool | None = None) -> StatusReport:
    providers: list[Provider] = []
    warnings: list[str] = []
    errors: list[str] = []
    network_used = False
    allow_network = _network_allowed(cfg, online)

    providers_cfg = cfg.get("providers", {})

    if providers_cfg.get("claude", {}).get("enabled", True):
        if allow_network:
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
        else:
            p = _offline_claude()
            providers.append(p)
            warnings.append(f"claude: {p.error}")

    if providers_cfg.get("codex", {}).get("enabled", True):
        if allow_network:
            try:
                from .providers.codex import collect as collect_codex
                p = collect_codex(cfg)
                providers.append(p)
                if p.status != "ok" and p.error:
                    warnings.append(f"codex: {p.error}")
            except Exception as exc:
                log.exception("codex provider falló")
                errors.append(f"codex: {exc}")
        else:
            p = _offline_codex()
            providers.append(p)
            warnings.append(f"codex: {p.error}")

    if providers_cfg.get("gemini", {}).get("enabled", True):
        try:
            from .providers.gemini import collect as collect_gemini
            # El conteo local de requests es offline y siempre corre; la cuota semanal
            # oficial de Antigravity (`agy /usage`) solo en el camino online del timer.
            p = collect_gemini(cfg, allow_network)
            providers.append(p)
            if any(w.confidence == "official" for w in p.windows):
                network_used = True
            if p.status != "ok" and p.error:
                warnings.append(f"gemini: {p.error}")
        except Exception as exc:
            log.exception("gemini provider falló")
            errors.append(f"gemini: {exc}")

    # Configuraciones existentes no tienen esta sección; no activar Copilot
    # implícitamente hasta que `config init` la haya declarado.
    if providers_cfg.get("copilot", {}).get("enabled", False):
        try:
            from .providers.copilot import collect as collect_copilot
            p = collect_copilot(cfg)
            providers.append(p)
            if p.status != "ok" and p.error:
                warnings.append(f"copilot: {p.error}")
        except Exception as exc:
            log.exception("copilot provider falló")
            errors.append(f"copilot: {exc}")

    if providers_cfg.get("deepseek", {}).get("enabled", True):
        if allow_network:
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
        else:
            p = _offline_deepseek()
            providers.append(p)
            warnings.append(f"deepseek: {p.error}")

    fx_warning = _fx_staleness_warning(cfg)
    if fx_warning:
        warnings.append(fx_warning)

    return StatusReport(
        network_used=network_used,
        providers=providers,
        warnings=warnings,
        errors=errors,
    )
