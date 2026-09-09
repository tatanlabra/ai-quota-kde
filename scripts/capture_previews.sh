#!/usr/bin/env bash
# Capturas HiDPI de las tres vistas del HUD, con datos ficticios y reproducibles.
#
# Usa la MISMA sonda que verifican los tests (tests/qml/layout_probe.py), no un
# renderizador aparte: lo que se publica es lo que los gates miden. Corre offscreen,
# asi que no depende de que haya sesion grafica ni captura ventanas ajenas.
#
# Los datos salen de `ai-quota-monitor sample`, que la sonda escribe en un directorio
# temporal: la cache real del usuario no se lee ni se toca, y cada linea del render
# queda rotulada "sample · datos ficticios". El README lo exige: nunca una captura con
# saldos reales.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UI="$ROOT/plasmoid/org.tatan.aiquota/contents/ui"
PROBE="$ROOT/tests/qml/layout_probe.py"

DEST="${1:-$ROOT/build/previews}"
LANG_CODE="${2:-es}"
SCALE="${3:-3}"

mkdir -p "$DEST"

shot() { # superficie ancho alto nombre
  local surface="$1" width="$2" height="$3" name="$4"
  QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software QT_SCALE_FACTOR="$SCALE" \
    python3 "$PROBE" "$UI" "$surface" "$width" --height "$height" \
      --sample --lang "$LANG_CODE" --image "$DEST/$name" >/dev/null
  python3 - "$DEST/$name" <<'PY'
import struct, sys, os
path = sys.argv[1]
with open(path, "rb") as fh:
    w, h = struct.unpack(">II", fh.read(33)[16:24])
print(f"  {os.path.basename(path):24} {w}x{h} px  {os.path.getsize(path)//1024} KB")
PY
}

# La barra del panel a la altura real de un panel de 40 px.
shot compact 216 40  "bar.png"
# El tooltip se dimensiona por su contenido; el alto es solo el lienzo.
shot tooltip 420 340 "tooltip.png"
# 500 px es donde el detalle de un proveedor cabe entero sin barra de desplazamiento.
shot popup   640 500 "popup-hidpi.png"

echo "Capturas en $DEST (idioma $LANG_CODE, escala ${SCALE}x)"
