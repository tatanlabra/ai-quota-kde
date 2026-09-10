#!/usr/bin/env bash
# Capturas HiDPI de las tres vistas del HUD, con datos ficticios y reproducibles.
#
# Usa la MISMA sonda que verifican los tests (tests/qml/layout_probe.py), no un
# renderizador aparte: lo que se publica es lo que los gates miden.
#
# Corre con backend RHI sobre GPU, sin ventana y sin compositor:
# QT_QPA_PLATFORM=eglfs con EGL_PLATFORM=surfaceless. No es una preferencia:
# Kirigami.Icon con isMask: true no tine bajo QSGSoftwareRenderer --su IconMaterial
# solo existe como material RHI, sin el fallback que si tiene ShadowedRectangle--,
# asi que con el renderizador software los cuatro logotipos enmascarados salen
# negros (codex, blanco) y el defecto es INVISIBLE para los tests de geometria: una
# silueta negra tiene la misma anchura, altura y apertura que una tenida.
#
# Por que eglfs y no wayland/xcb, que tambien tinen: con compositor hay que mapear
# una ventana, y una pantalla BLOQUEADA deja de presentarla, asi que grabToImage()
# nunca completa y el proceso se cuelga hasta el timeout. Medido el 2026-09-09: los
# mismos comandos que funcionaron con la sesion desbloqueada colgaron una hora mas
# tarde con LockedHint=yes. eglfs+surfaceless no abre ventana, no pide DRM master y
# no depende del estado de la sesion; deja plasmashell y kwin intactos. Lo que si
# necesita es acceso a la GPU (/dev/dri): en un contenedor sin GPU esto no corre, y
# por eso los tests de geometria siguen yendo por offscreen+software a proposito.
#
# Medido el 2026-09-09 con las tres plataformas. NO volver a offscreen: se
# publicaron dos imagenes con logotipos negros por hacerlo (commit 74bd40a), y
# docs/layout-validation-2026-09-06.md:31-34 ya lo habia registrado antes.
# Detalle y tabla de la medicion en docs/capturas-rhi-2026-09-09.md.
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

# La GPU es el unico requisito real. Sin ella no hay RHI, y sin RHI los logotipos
# enmascarados saldrian negros: se aborta en vez de publicar un artefacto falso.
if ! ls /dev/dri/renderD* >/dev/null 2>&1; then
  echo "ERROR: no hay dispositivo de render (/dev/dri/renderD*) y RHI lo exige." >&2
  echo "       Sin RHI los logotipos enmascarados saldrian negros. No se captura nada." >&2
  exit 2
fi
PLATFORM="${AIQ_CAPTURE_PLATFORM:-eglfs}"
EGL_PLATFORM_VALUE="${AIQ_CAPTURE_EGL_PLATFORM:-surfaceless}"

shot() { # superficie ancho alto nombre
  local surface="$1" width="$2" height="$3" name="$4"
  # El JSON no se descarta: es lo que permite comprobar CON QUE se renderizo.
  QT_QPA_PLATFORM="$PLATFORM" EGL_PLATFORM="$EGL_PLATFORM_VALUE" QT_SCALE_FACTOR="$SCALE" \
    python3 "$PROBE" "$UI" "$surface" "$width" --height "$height" \
      --sample --lang "$LANG_CODE" --image "$DEST/$name" > "$DEST/${name%.png}.json"
  python3 "$ROOT/scripts/assert_render_is_rhi.py" "$DEST/${name%.png}.json" "$SCALE"
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
