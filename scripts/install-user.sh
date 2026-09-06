#!/usr/bin/env bash
# Instala ai-quota-monitor para el usuario actual, sin sudo ni paquetes globales.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PYTHON="${PYTHON:-python3}"
VENV_DIR="${AI_QUOTA_VENV_DIR:-$HOME/.local/share/ai-quota-monitor/venv}"
SKIP_PLASMOID=0
SKIP_SYSTEMD=0

usage() {
  cat <<'EOF'
Uso: scripts/install-user.sh [opciones]

  --skip-plasmoid       no instala el widget Plasma
  --skip-systemd        no instala ni habilita el timer de usuario
  --venv-dir RUTA       cambia la ruta del entorno virtual
  -h, --help            muestra esta ayuda
EOF
}

while (($#)); do
  case "$1" in
    --skip-plasmoid) SKIP_PLASMOID=1; shift ;;
    --skip-systemd) SKIP_SYSTEMD=1; shift ;;
    --venv-dir)
      [[ $# -ge 2 ]] || { echo "Falta la ruta para --venv-dir" >&2; exit 2; }
      VENV_DIR="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Opción desconocida: $1" >&2; usage >&2; exit 2 ;;
  esac
done

"$PYTHON" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))' || {
  echo "Se requiere Python 3.11 o posterior: $PYTHON" >&2
  exit 1
}

echo "=== ai-quota-monitor install-user ==="
echo "Proyecto: $PROJECT_DIR"
echo "Entorno:  $VENV_DIR"

echo "[1/5] Creando entorno Python local..."
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  "$PYTHON" -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/python" -m pip install --quiet -e "$PROJECT_DIR"

echo "[2/5] Instalando wrapper estable..."
install -d -m 700 "$HOME/.local/bin"
cat > "$HOME/.local/bin/ai-quota-monitor" <<EOF
#!/usr/bin/env bash
exec "$VENV_DIR/bin/ai-quota-monitor" "\$@"
EOF
chmod 700 "$HOME/.local/bin/ai-quota-monitor"
chmod 700 "$SCRIPT_DIR"/helper_*.sh "$SCRIPT_DIR/_codex_wham.py"

echo "[3/5] Inicializando directorios privados..."
install -d -m 700 "$HOME/.cache/ai-quota-monitor" "$HOME/.config/ai-quota-monitor"
"$HOME/.local/bin/ai-quota-monitor" config init >/dev/null

echo "[4/5] Instalando plasmoide..."
if ((SKIP_PLASMOID)); then
  echo "  omitido por --skip-plasmoid"
elif ! command -v kpackagetool6 >/dev/null 2>&1; then
  echo "  kpackagetool6 no está disponible; se omite el plasmoide" >&2
else
  # El .mo tiene que estar compilado ANTES de empaquetar: kpackagetool6 copia el
  # arbol tal cual, asi que un catalogo viejo se instala igual de silenciosamente.
  bash "$PROJECT_DIR/scripts/build_locale.sh"

  PLASMOID_DIR="$PROJECT_DIR/plasmoid/org.tatan.aiquota"
  if kpackagetool6 -t Plasma/Applet -l 2>/dev/null | grep -q "org.tatan.aiquota"; then
    kpackagetool6 -t Plasma/Applet -u "$PLASMOID_DIR"
  else
    kpackagetool6 -t Plasma/Applet -i "$PLASMOID_DIR"
  fi
fi

echo "[5/5] Instalando timer systemd de usuario..."
if ((SKIP_SYSTEMD)); then
  echo "  omitido por --skip-systemd"
elif ! command -v systemctl >/dev/null 2>&1; then
  echo "  systemctl no está disponible; se omite el timer" >&2
else
  SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
  install -d -m 700 "$SYSTEMD_USER_DIR"
  install -m 644 "$PROJECT_DIR/systemd/ai-quota-monitor.service" "$SYSTEMD_USER_DIR/"
  install -m 644 "$PROJECT_DIR/systemd/ai-quota-monitor.timer" "$SYSTEMD_USER_DIR/"
  systemctl --user daemon-reload
  systemctl --user enable --now ai-quota-monitor.timer
fi

echo
echo "Instalación completa. Siguiente paso: ai-quota-monitor doctor"
echo "UI con datos ficticios: ai-quota-monitor sample --write-cache"
