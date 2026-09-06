from __future__ import annotations

from pathlib import Path

HOME = Path.home()

CACHE_DIR = HOME / ".cache" / "ai-quota-monitor"
CONFIG_DIR = HOME / ".config" / "ai-quota-monitor"
STATUS_JSON = CACHE_DIR / "status.json"
CONFIG_TOML = CONFIG_DIR / "config.toml"

CLAUDE_CREDS = HOME / ".claude" / ".credentials.json"
CLAUDE_PROJECTS_DIR = HOME / ".claude" / "projects"

# Codex — fuente oficial: snapshots de rate_limits en los rollouts del CLI.
# Codex CLI persiste cada rate-limit recibido de la API en eventos token_count.
CODEX_SESSIONS_DIR = HOME / ".codex" / "sessions"

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
HELPER_CLAUDE = SCRIPTS_DIR / "helper_claude_usage.sh"
HELPER_CODEX = SCRIPTS_DIR / "helper_codex_usage.sh"
HELPER_GEMINI = SCRIPTS_DIR / "helper_gemini_usage.sh"
HELPER_DEEPSEEK = SCRIPTS_DIR / "helper_deepseek_balance.sh"

DEEPSEEK_ENV_FILE = CONFIG_DIR / "secrets.env"

# Gemini / Antigravity (agy) — uso local (conteo diario de requests)
GEMINI_DIR = HOME / ".gemini"
ANTIGRAVITY_DIR = HOME / ".local" / "share" / "antigravity"

# GitHub Copilot CLI — snapshots locales de cuota incluidos en eventos de respuestas.
COPILOT_SESSIONS_DIR = HOME / ".copilot" / "session-state"
