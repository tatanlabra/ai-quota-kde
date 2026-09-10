#!/usr/bin/env bash
# Teaser 1280x720 (y su variante 640x360) con la barra REAL del HUD.
#
# El teaser anterior era una ilustracion con cuatro donas, sin Copilot y con iconos
# que no son los del widget: un `</>` donde va el starburst de Claude. Este usa el
# producto de verdad --cinco proveedores, logotipos tenidos con su acento, anillos de
# reinicio-- compuesto sobre el mismo aire visual: degradado oscuro, halo y reflejo.
#
# Se renderiza a escala 6 (1296x240 con alfa) para que la barra solo se REDUZCA hasta
# los 922 px de la composicion, nunca se amplie. La variante de 640 sale del propio
# maestro por reduccion exacta 1:2, no de un render aparte: asi las dos no pueden
# derivar la una de la otra.
#
# Los nombres son heredados a proposito: scripts/verify_site_artifact.rb del blog
# exige literalmente teaser-ai-quota-hud-640.webp y el tema deriva ese sufijo en
# _includes/archive-single.html. Sobrescribir con el mismo nombre obliga a purgar la
# cache de borde de Cloudflare DESPUES de que el pipeline salga success.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UI="$ROOT/plasmoid/org.tatan.aiquota/contents/ui"
PROBE="$ROOT/tests/qml/layout_probe.py"
DEST="${1:-$ROOT/build/teaser}"

# Misma exigencia que capture_previews.sh, y por la misma razon: sin RHI los cuatro
# logotipos enmascarados saldrian negros, y un teaser con logos negros es peor que el
# que ya habia.
if ! ls /dev/dri/renderD* >/dev/null 2>&1; then
  echo "ERROR: no hay dispositivo de render (/dev/dri/renderD*) y RHI lo exige." >&2
  exit 2
fi

mkdir -p "$DEST"

W=1280; H=720          # lienzo final
BW=922                 # ancho de la barra compuesta
BX=179; BY=250         # esquina superior izquierda de la barra
PAD=48                 # aire transparente para que el halo no se recorte

QT_QPA_PLATFORM="${AIQ_CAPTURE_PLATFORM:-eglfs}" \
EGL_PLATFORM="${AIQ_CAPTURE_EGL_PLATFORM:-surfaceless}" \
QT_SCALE_FACTOR=6 \
  python3 "$PROBE" "$UI" compact 216 --height 40 --sample --lang es --no-hover \
    --image "$DEST/bar-alpha.png" > "$DEST/bar-alpha.json"
python3 "$ROOT/scripts/assert_render_is_rhi.py" "$DEST/bar-alpha.json" 6

# 1. La barra al ancho final, una sola reduccion Lanczos.
magick "$DEST/bar-alpha.png" -filter Lanczos -resize ${BW}x "$DEST/bar.png"
BH=$(identify -format '%h' "$DEST/bar.png")

# 2. Fondo: degradado lineal oscuro con un halo radial calido tenue encima.
magick -size ${W}x${H} gradient:'#0b0d18-#04050b' \
  \( -size ${W}x${H} radial-gradient:'#1b2340-#04050b' \
     -alpha set -channel A -evaluate multiply 0.55 +channel \) \
  -compose over -composite "$DEST/bg.png"

# 3. Halo: la propia barra, saturada y difuminada en dos radios.
#
# El margen transparente ANTES del blur no es decorativo: sin el, el difuminado se
# recorta en el borde del lienzo de origen y deja un rectangulo con cantos duros
# alrededor de la barra --se ve como un parche gris, no como un halo--. Con PAD px de
# aire el halo cae a cero dentro de la imagen. El compuesto se desplaza -PAD para que
# el halo siga centrado en la barra.
magick "$DEST/bar.png" -bordercolor none -border ${PAD} \
  -channel RGB -modulate 118,190 +channel -blur 0x26 "$DEST/glow-far.png"
magick "$DEST/bar.png" -bordercolor none -border ${PAD} \
  -channel RGB -modulate 112,155 +channel -blur 0x7  "$DEST/glow-near.png"

# 4. Reflejo: espejo vertical aplastado al 55 %, con la opacidad en degradado.
magick "$DEST/bar.png" -flip -resize 100%x55%\! \
  \( +clone -alpha extract \
     \( -size %[w]x%[h] gradient:'#595959-#000000' \) \
     -compose multiply -composite \) \
  -alpha off -compose copy_opacity -composite -blur 0x2 "$DEST/reflection.png"

# 5. Composicion. El halo va en `screen` para que sume luz sin tapar la barra.
magick "$DEST/bg.png" \
  "$DEST/glow-far.png"   -geometry +$((BX - PAD))+$((BY - PAD)) -compose screen -composite \
  "$DEST/glow-near.png"  -geometry +$((BX - PAD))+$((BY - PAD)) -compose screen -composite \
  "$DEST/bar.png"        -geometry +${BX}+${BY} -compose over   -composite \
  "$DEST/reflection.png" -geometry +${BX}+$((BY + BH + 8)) -compose over -composite \
  -background '#04050b' -alpha remove -alpha off -strip \
  -define webp:method=6 -quality 86 \
  "$DEST/teaser-ai-quota-hud.webp"

# 6. Variante movil: reduccion exacta 1:2 del maestro.
magick "$DEST/teaser-ai-quota-hud.webp" -filter Lanczos -resize 50% \
  -strip -define webp:method=6 -quality 84 \
  "$DEST/teaser-ai-quota-hud-640.webp"

identify -format '  %f %wx%h %[channels] %b\n' "$DEST"/teaser-ai-quota-hud*.webp
echo "Teaser en $DEST"
