#!/usr/bin/env bash
# Desinstala los artefactos creados por install-user.sh. Conserva datos por defecto.
set -euo pipefail

PURGE_DATA=0
if [[ "${1:-}" == "--purge-data" ]]; then
  PURGE_DATA=1
elif [[ $# -gt 0 ]]; then
  echo "Uso: scripts/uninstall-user.sh [--purge-data]" >&2
  exit 2
fi

VENV_DIR="${AI_QUOTA_VENV_DIR:-$HOME/.local/share/ai-quota-monitor/venv}"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"

if command -v systemctl >/dev/null 2>&1; then
  systemctl --user disable --now ai-quota-monitor.timer 2>/dev/null || true
fi
rm -f "$SYSTEMD_USER_DIR/ai-quota-monitor.service" "$SYSTEMD_USER_DIR/ai-quota-monitor.timer"
if command -v systemctl >/dev/null 2>&1; then
  systemctl --user daemon-reload 2>/dev/null || true
fi

if command -v kpackagetool6 >/dev/null 2>&1; then
  kpackagetool6 -t Plasma/Applet -r org.tatan.aiquota 2>/dev/null || true
fi

rm -f "$HOME/.local/bin/ai-quota-monitor"
rm -rf "$VENV_DIR"

if ((PURGE_DATA)); then
  rm -rf "$HOME/.cache/ai-quota-monitor" "$HOME/.config/ai-quota-monitor"
  echo "Desinstalación completa; caché y configuración eliminadas."
else
  echo "Desinstalación completa; caché y configuración conservadas."
fi
