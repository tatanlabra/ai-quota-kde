from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from .paths import CONFIG_TOML
from .security import atomic_write, ensure_dirs, restrict

_DEFAULT_CONFIG = """\
[general]
timezone = "America/Santiago"
refresh_seconds = 60
network_enabled = false
prefer_offline = true

[ui]
theme = "cyberpunk"
show_costs = true
show_tokens = true
show_requests = true
compact_panel_text = "worst-provider"

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
label = "GEMINI"
# Antigravity (agy) / Gemini CLI: conteo diario de requests desde logs locales (estimación).
source = "gemini_logs"

[providers.gemini.daily]
limit_requests = 1000
reset_policy = "daily_local_midnight"

[providers.gemini.ccusage]
enabled = true
allow_npx = false

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
# Techo de presupuesto en CLP: el anillo = saldo_actual / budget_clp.
# 100% = budget_clp lleno; se descarga con el uso y vuelve a tope al recargar
# (cap 100%). Poner 0 o quitar la linea para volver al high-water-mark automatico.
budget_clp = 10000.0
"""


def load() -> dict[str, Any]:
    if not CONFIG_TOML.exists():
        return tomllib.loads(_DEFAULT_CONFIG)
    return tomllib.loads(CONFIG_TOML.read_text(encoding="utf-8"))


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
