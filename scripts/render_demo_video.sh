#!/usr/bin/env bash
# Video de demostracion completo: fotogramas deterministas + codificacion medida.
#
# Uso:
#   scripts/render_demo_video.sh [<dir base>]     # por defecto build/
#
# Dos etapas, y las dos son reproducibles:
#   1. tests/qml/layout_probe.py con la superficie `stage` renderiza los 486 fotogramas
#      en UN solo proceso. Uno por fotograma costaria ~1,5 s de arranque cada uno, o sea
#      12 minutos; con el engine vivo son decenas de milisegundos.
#   2. scripts/encode_demo_video.sh hace el maestro FFV1, la referencia yuv420p y la
#      escalera de CRF, y se queda con el fichero mas pequeno que pasa los umbrales.
#
# El guion vive en tests/qml/demo_storyboard.py como DATO: cada fotograma es funcion
# pura de su indice, sin animaciones en QML ni timers, asi que dos corridas dan los
# mismos bytes. Eso es lo que hace posible el gate de determinismo de
# tests/test_demo_video.py en vez de mirar el video a ojo.
#
# El estado se muta con EVENTOS REALES --MouseMove sobre la celda de la barra,
# press+release sobre el selector del popup--, no escribiendo las propiedades finales:
# lo que se ve en el video son los manejadores del widget reaccionando de verdad, y cada
# fotograma comprueba que el estado que pedia el guion es el que quedo.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UI="$ROOT/plasmoid/org.tatan.aiquota/contents/ui"
PROBE="$ROOT/tests/qml/layout_probe.py"
BASE="${1:-$ROOT/build}"
FRAMES="$BASE/frames"
VIDEO="$BASE/video"

# Igual que capture_previews.sh, y por la misma razon: sin RHI los cuatro logotipos
# enmascarados saldrian negros. Un video de demostracion con los logos en negro es peor
# que no tener video.
if ! ls /dev/dri/renderD* >/dev/null 2>&1; then
  echo "ERROR: no hay dispositivo de render (/dev/dri/renderD*) y RHI lo exige." >&2
  exit 2
fi

read -r STAGE_W STAGE_H SCALE FRAME_COUNT FROZEN <<EOF
$(PYTHONPATH="$ROOT/src" python3 -c "
import sys
sys.path.insert(0, '$ROOT/tests/qml')
import demo_storyboard as sb
print(sb.STAGE_WIDTH, sb.STAGE_HEIGHT, sb.SCALE, sb.total_frames(), sb.FROZEN_NOW)")
EOF

echo "Guion: $FRAME_COUNT fotogramas, escenario ${STAGE_W}x${STAGE_H} a ${SCALE}x, reloj fijo en $FROZEN"
rm -rf "$FRAMES"
QT_QPA_PLATFORM="${AIQ_CAPTURE_PLATFORM:-eglfs}" \
EGL_PLATFORM="${AIQ_CAPTURE_EGL_PLATFORM:-surfaceless}" \
QT_SCALE_FACTOR="$SCALE" \
PYTHONPATH="$ROOT/src" \
  python3 "$PROBE" "$UI" stage "$STAGE_W" --height "$STAGE_H" \
    --sample --lang "${2:-es}" --frozen-now "$FROZEN" --sequence "$FRAMES" >/dev/null

bash "$ROOT/scripts/encode_demo_video.sh" "$FRAMES" "$VIDEO"
