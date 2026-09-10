#!/usr/bin/env bash
# Codifica la secuencia de fotogramas a VP9/WebM, midiendo antes de aceptar.
#
# Uso:
#   scripts/encode_demo_video.sh [<dir fotogramas>] [<dir salida>]
#
# Que se hereda de donde, para que nadie tenga que adivinarlo:
#
# De la receta de julio (archivo/handoffs/2026-07-26_HANDOFF_insertar-video-post.md):
# libvpx-vp9 con `-crf N -b:v 0` --sin el `-b:v 0`, `-crf` en libvpx no es calidad
# constante sino calidad restringida--, `-row-mt 1`, `-an`, y el poster de un fotograma
# TARDIO y representativo, no del inicio. Sigue valido descartar MP4/H.264: el WebM lo
# sirven Chrome, Firefox, Edge y Safari 14.1+, y un segundo formato solo anade peso.
#
# De la disciplina de la skill captura-video-difusion: maestro sin perdida en FFV1,
# escalera de CRF quedandose con el fichero MAS PEQUENO que pasa, y medir la entrega
# contra una referencia en vez de mirarla a ojo. NO se hereda su perfil de umbrales
# (VMAF>=97 / SSIM>=0.995 / PSNR>=42 dB): esta calibrado para un grafo 3D REDUCIDO 2:1
# a 1080p, y aqui no hay reduccion y el contenido es interfaz plana con bordes de texto
# duros, que es el peor caso para VP9 y el mejor para un SSIM global. Tampoco se hereda
# `-movflags +faststart`, que es de MP4 y en Matroska no existe: el equivalente es
# `-cues_to_front 1`.
#
# Y se anade un criterio que la skill no tiene y que aqui decide: el SSIM del RECORTE
# DE TEXTO. Un VMAF global de 97 convive perfectamente con texto de 13 px hecho papilla,
# porque el texto es una fraccion minima del area. Ese recorte es lo que protege lo
# unico que el video tiene que comunicar.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRAMES="${1:-$ROOT/build/frames}"
OUT="${2:-$ROOT/build/video}"

FPS=30
POSTER_FRAME=380          # plano de Antigravity con sus dos semanales
TEXT_CROP="1200:520:170:390"

# Umbrales, recalibrados para este contenido y esta resolucion.
MIN_VMAF=93.0
MIN_SSIM=0.990
MIN_PSNR=38.0
MIN_TEXT_SSIM=0.985
MAX_BYTES=$((1500 * 1024))
MAX_IDENTICAL_RUN=90      # los planos de espera SON el contenido: hacen falta para leer
MIN_DISTINCT_STATES=12

mkdir -p "$OUT"
count=$(find "$FRAMES" -name 'frame-*.png' | wc -l)
[ "$count" -gt 0 ] || { echo "ERROR: no hay fotogramas en $FRAMES" >&2; exit 2; }
echo "Fotogramas: $count"

# 1. Maestro bit-exacto de los PNG (RGB, rango completo).
ffmpeg -hide_banner -loglevel error -y -framerate $FPS -i "$FRAMES/frame-%04d.png" \
  -vf format=gbrp -c:v ffv1 -level 3 -g 1 -slicecrc 1 \
  -color_primaries bt709 -color_trc bt709 -colorspace bt709 -color_range pc \
  "$OUT/master-rgb-ffv1.mkv"

# El maestro tiene que decodificar a los MISMOS bytes que los PNG, o no es un maestro.
#
# Los dos lados se normalizan a gbrp antes de hashear, y no es un detalle: framemd5
# hashea el fotograma en su formato de pixel nativo, asi que un PNG en rgba y un FFV1 en
# gbrp dan hashes distintos aunque el contenido sea identico. Sin el `-vf format=gbrp` en
# el lado de los PNG, esta comprobacion reprueba SIEMPRE y no dice nada sobre la calidad.
ffmpeg -v error -i "$FRAMES/frame-%04d.png" -vf format=gbrp -f framemd5 - > "$OUT/frames.framemd5"
ffmpeg -v error -i "$OUT/master-rgb-ffv1.mkv" -vf format=gbrp -f framemd5 - > "$OUT/master.framemd5"
if ! diff -q <(grep -v '^#' "$OUT/frames.framemd5") <(grep -v '^#' "$OUT/master.framemd5") >/dev/null; then
  echo "ERROR: el maestro FFV1 no es bit-exacto respecto a los PNG." >&2
  exit 1
fi
echo "Maestro FFV1 bit-exacto."

# 2. Referencia yuv420p: MISMA conversion de color que la entrega, sin compresion. Medir
#    la entrega contra esta atribuye la perdida al codificador y no al submuestreo 4:2:0.
ffmpeg -hide_banner -loglevel error -y -i "$OUT/master-rgb-ffv1.mkv" \
  -vf "scale=in_range=full:out_range=tv:out_color_matrix=bt709:flags=accurate_rnd+full_chroma_int,format=yuv420p" \
  -c:v ffv1 -level 3 -g 1 -slicecrc 1 \
  -color_primaries bt709 -color_trc bt709 -colorspace bt709 -color_range tv \
  "$OUT/reference-yuv420p-ffv1.mkv"

# 3. Escalera de CRF. Se queda el mas pequeno que pase todos los criterios.
winner=""
printf '\n%-6s %-10s %-8s %-8s %-8s %-9s %s\n' CRF bytes VMAF SSIM PSNR txtSSIM veredicto
for crf in 28 31 34; do
  cand="$OUT/candidate-crf$crf.webm"
  ffmpeg -hide_banner -loglevel error -y -i "$OUT/reference-yuv420p-ffv1.mkv" \
    -c:v libvpx-vp9 -pix_fmt yuv420p -crf $crf -b:v 0 \
    -row-mt 1 -tile-columns 2 -threads 8 \
    -deadline good -cpu-used 1 -auto-alt-ref 1 -lag-in-frames 25 \
    -g 60 -keyint_min 60 -r $FPS \
    -color_primaries bt709 -color_trc bt709 -colorspace bt709 -color_range tv \
    -cues_to_front 1 -an "$cand"

  bytes=$(stat -c%s "$cand")
  vmaf=$(ffmpeg -v error -i "$cand" -i "$OUT/reference-yuv420p-ffv1.mkv" \
    -lavfi "[0:v][1:v]libvmaf=log_fmt=json:log_path=$OUT/vmaf-$crf.json" -f null - 2>&1 >/dev/null; \
    python3 -c "
import json,sys
d=json.load(open('$OUT/vmaf-$crf.json'))
print(f\"{d['pooled_metrics']['vmaf']['mean']:.2f}\")" 2>/dev/null || echo 0)
  ssim=$(ffmpeg -v error -i "$cand" -i "$OUT/reference-yuv420p-ffv1.mkv" \
    -lavfi "[0:v][1:v]ssim=stats_file=-" -f null - 2>/dev/null \
    | awk -F'All:' '/All:/{split($2,a," ");s+=a[1];n++} END{if(n)printf "%.4f", s/n; else print 0}')
  psnr=$(ffmpeg -v error -i "$cand" -i "$OUT/reference-yuv420p-ffv1.mkv" \
    -lavfi "[0:v][1:v]psnr=stats_file=-" -f null - 2>/dev/null \
    | awk -F'psnr_avg:' '/psnr_avg:/{split($2,a," ");if(a[1]!="inf"){s+=a[1];n++}} END{if(n)printf "%.2f", s/n; else print 99}')
  tssim=$(ffmpeg -v error -i "$cand" -i "$OUT/reference-yuv420p-ffv1.mkv" \
    -lavfi "[0:v]crop=${TEXT_CROP}[a];[1:v]crop=${TEXT_CROP}[b];[a][b]ssim=stats_file=-" -f null - 2>/dev/null \
    | awk -F'All:' '/All:/{split($2,a," ");s+=a[1];n++} END{if(n)printf "%.4f", s/n; else print 0}')

  verdict=$(python3 -c "
ok = (
    $bytes <= $MAX_BYTES
    and float('$vmaf') >= $MIN_VMAF
    and float('$ssim') >= $MIN_SSIM
    and float('$psnr') >= $MIN_PSNR
    and float('$tssim') >= $MIN_TEXT_SSIM
)
print('PASA' if ok else 'reprueba')")
  printf '%-6s %-10s %-8s %-8s %-8s %-9s %s\n' "$crf" "$bytes" "$vmaf" "$ssim" "$psnr" "$tssim" "$verdict"
  # El mas pequeno que pasa: la escalera va de menor a mayor CRF, o sea de mayor a menor
  # tamano, asi que el ultimo que pase es el mas pequeno.
  [ "$verdict" = "PASA" ] && winner="$cand"
done

[ -n "$winner" ] || { echo "ERROR: ningun CRF paso los umbrales." >&2; exit 1; }

# 4. Criterios estructurales sobre el ganador.
frames_read=$(ffprobe -v error -count_frames -select_streams v:0 \
  -show_entries stream=nb_read_frames -of csv=p=0 "$winner")
rate=$(ffprobe -v error -select_streams v:0 -show_entries stream=avg_frame_rate -of csv=p=0 "$winner")
[ "$frames_read" = "$count" ] || { echo "ERROR: $frames_read fotogramas leidos, $count esperados" >&2; exit 1; }
[ "$rate" = "$FPS/1" ] || { echo "ERROR: cadencia $rate, se esperaba $FPS/1" >&2; exit 1; }

ffmpeg -v error -i "$winner" -f framemd5 - | grep -v '^#' | awk '{print $NF}' > "$OUT/winner.md5"
python3 - "$OUT/winner.md5" "$MAX_IDENTICAL_RUN" "$MIN_DISTINCT_STATES" <<'PY'
import sys
lines = [l.strip() for l in open(sys.argv[1]) if l.strip()]
run = best = 1
for a, b in zip(lines, lines[1:]):
    run = run + 1 if a == b else 1
    best = max(best, run)
distinct = len(set(lines))
print(f"Carrera identica maxima: {best}   estados distintos: {distinct}")
if best > int(sys.argv[2]):
    sys.exit(f"ERROR: {best} fotogramas identicos seguidos, maximo {sys.argv[2]}")
if distinct < int(sys.argv[3]):
    sys.exit(f"ERROR: solo {distinct} estados visuales distintos, minimo {sys.argv[3]}")
PY

# 5. Cierre de bucle: el primer y el ultimo fotograma tienen que ser el MISMO fichero.
first=$(sha256sum "$FRAMES/frame-0000.png" | cut -d' ' -f1)
last=$(sha256sum "$(printf '%s/frame-%04d.png' "$FRAMES" $((count - 1)))" | cut -d' ' -f1)
[ "$first" = "$last" ] || { echo "ERROR: el bucle no cierra: primer y ultimo fotograma difieren" >&2; exit 1; }
echo "Bucle cerrado (primer y ultimo fotograma identicos)."

# 6. Poster, del mismo ratio EXACTO que el video para que no haya reflujo al arrancar.
poster_src=$(printf '%s/frame-%04d.png' "$FRAMES" "$POSTER_FRAME")
magick "$poster_src" -strip -define webp:method=6 -quality 84 "$OUT/demo-poster.webp"

geo=$(identify -format '%wx%h' "$OUT/demo-poster.webp")
vgeo=$(ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0:s=x "$winner")
[ "$geo" = "$vgeo" ] || { echo "ERROR: poster $geo y video $vgeo no coinciden" >&2; exit 1; }

command cp -f "$winner" "$OUT/ai-quota-hud-demo-$vgeo.webm"
command cp -f "$OUT/demo-poster.webp" "$OUT/demo-poster-$vgeo.webp"
printf '\nGanador: %s -> %s (%s B)\nPoster:  %s\n' \
  "$(basename "$winner")" "ai-quota-hud-demo-$vgeo.webm" "$(stat -c%s "$winner")" "demo-poster-$vgeo.webp"
