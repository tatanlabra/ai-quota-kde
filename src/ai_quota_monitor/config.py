from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from .paths import CONFIG_TOML
from .security import atomic_write, ensure_dirs, restrict

_DEFAULT_CONFIG = """\
[general]
timezone = "America/Santiago"
network_enabled = false
prefer_offline = true

# La presentacion se configura en el plasmoide (clic derecho -> Configurar), no aqui.
# La seccion [ui] existio con claves que ningun codigo leia, y la cadencia nunca se
# fijo desde este fichero: la fija ai-quota-monitor.timer. Ver OBSOLETE_KEYS.

[providers.claude]
enabled = true
label = "CLAUDE"
source = "api_official"

[providers.claude.session]
window_hours = 5
limit_tokens = 0
reset_policy = "five_hour_rolling"

[providers.claude.weekly]
window_days = 7
limit_tokens = 0
reset_policy = "seven_day_rolling"

[providers.codex]
enabled = true
label = "CODEX"
# Fuente oficial: snapshots rate_limits que Codex CLI persiste en ~/.codex/sessions.
source = "rollout_rate_limits"

[providers.codex.session]
window_hours = 5
reset_policy = "primary_rolling"

[providers.codex.weekly]
window_days = 7
reset_policy = "secondary_rolling"

[providers.gemini]
enabled = true
label = "ANTIGRAVITY / GEMINI"
# Actividad local separada de Antigravity y Gemini CLI. No representa una cuota.
source = "antigravity_gemini_logs"

[providers.gemini.activity]
cutoff_policy = "daily_local_midnight"

[providers.gemini.ccusage]
enabled = true
allow_npx = false

[providers.copilot]
enabled = true
label = "COPILOT"
source = "copilot_session_quota_snapshots"

[providers.deepseek]
enabled = true
label = "DEEPSEEK"
# Saldo oficial via helper Bash. Python consume solo JSON saneado.
source = "deepseek_balance_api"

[providers.deepseek.balance]
# Conversion manual/configurada; se marca como configured_estimate.
# Actualizar si el tipo de cambio queda stale.
clp_per_usd = 950.0
clp_per_cny = 132.0
rates_checked_at = "2026-06-20"
rates_source = "manual_config"
# Techo personal opcional en CLP. Es una estimación separada: saldo API × FX
# configurado contra este presupuesto local. Por defecto está oculto; usa un valor
# positivo para mostrarlo como métrica secundaria.
budget_clp = 0.0
"""


# Claves que existieron en config.toml y ya no lee nadie. Se declaran para que un
# fichero viejo no aparente configurar algo: `refresh_seconds` nunca fijo la cadencia
# (la fija el timer systemd) y toda la seccion [ui] se mudo a la config del plasmoide.
OBSOLETE_KEYS: tuple[tuple[str, str, str], ...] = (
    ("general", "refresh_seconds", "la cadencia la fija ai-quota-monitor.timer"),
    ("ui", "theme", "la presentacion se configura en el plasmoide"),
    ("ui", "show_costs", "la presentacion se configura en el plasmoide"),
    ("ui", "show_tokens", "la presentacion se configura en el plasmoide"),
    ("ui", "show_requests", "la presentacion se configura en el plasmoide"),
    ("ui", "compact_panel_text", "ahora es la opcion 'modo compacto' del plasmoide"),
)


def obsolete_keys_present(cfg: dict[str, Any]) -> list[str]:
    """Claves presentes en el config del usuario que ya no tienen consumidor."""
    found = []
    for section, key, why in OBSOLETE_KEYS:
        if isinstance(cfg.get(section), dict) and key in cfg[section]:
            found.append(f"[{section}] {key} — {why}")
    return found

def load() -> dict[str, Any]:
    if not CONFIG_TOML.exists():
        return tomllib.loads(_DEFAULT_CONFIG)
    cfg = tomllib.loads(CONFIG_TOML.read_text(encoding="utf-8"))
    # Habilitar proveedores nuevos en configuraciones antiguas sin reescribirlas.
    cfg.setdefault("providers", {}).setdefault(
        "copilot",
        {"enabled": True, "label": "COPILOT", "source": "copilot_session_quota_snapshots"},
    )
    return cfg


def init_config(force: bool = False) -> bool:
    if CONFIG_TOML.exists() and not force:
        return False
    ensure_dirs(CONFIG_TOML.parent)
    atomic_write(CONFIG_TOML, _DEFAULT_CONFIG)
    return True


def validate(cfg: dict[str, Any]) -> list[str]:
    errors = []
    if "general" not in cfg:
        errors.append("Sección [general] faltante")
    if "providers" not in cfg:
        errors.append("Sección [providers] faltante")
    return errors
