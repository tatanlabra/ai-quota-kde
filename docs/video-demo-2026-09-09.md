# El video de demostración: por qué se renderiza y no se graba

Fecha: 2026-09-09. El video anterior era una grabación de pantalla de julio con
Spectacle, y mostraba el diseño de entonces: cuatro agentes y ninguna fila de
selectores. Este se renderiza.

## Por qué no se graba la pantalla

No hay grabador desatendido en esta máquina, y no por falta de herramientas sino por la
combinación concreta:

| herramienta | por qué no |
|---|---|
| Spectacle | graba, pero la selección de región y el arranque/parada son manuales, y deja el indicador rojo en la bandeja |
| OBS, Kooha | pasan por el portal de escritorio, que abre un diálogo |
| `wf-recorder`, `grim`, `slurp` | son de wlroots; KWin no implementa sus protocolos |

Y grabar el panel real exigiría además sustituir temporalmente
`~/.cache/ai-quota-monitor/status.json` por datos ficticios, porque el README prohíbe
publicar capturas con saldos reales. Es reversible, pero es tocar el estado de la
persona usuaria para hacer una imagen.

## Por qué la skill de captura no sirve como pipeline

`penta-agent/skills/captura-video-difusion` es Playwright sobre páginas web. Su lanzador
aborta explícitamente ante cualquier otra cosa
(`throw new Error('This adapter is specific to the local Penta-RAG viewer')`), no tiene
entrada para fotogramas externos, y su `--resume-scratch --encode-only` exige un
`capture-receipt.json` con 300 hashes ya verificados.

Lo que sí se hereda de ella, y está anotado en `scripts/encode_demo_video.sh`: maestro
sin pérdida en FFV1, escalera de CRF quedándose con el fichero más pequeño que pasa, y
**medir antes de aceptar**. Lo que no se hereda, con su razón: su perfil de umbrales
(VMAF ≥97 / SSIM ≥0,995 / PSNR ≥42 dB) está calibrado para un grafo 3D reducido 2:1 a
1080p; aquí no hay reducción y el contenido es interfaz plana con bordes de texto duros,
que es el peor caso para VP9 y el mejor para un SSIM global. Y `-movflags +faststart` es
de MP4: en Matroska el equivalente es `-cues_to_front 1`, y heredarlo tal cual habría
sido copiar sin leer.

## Cómo se renderiza

`tests/qml/DemoStage.qml` es un lienzo de 736x576 px lógicos con un panel de escritorio
falso abajo y las tres vistas del HUD encima —barra compacta, visor emergente y vista
detallada—, **compartiendo el mismo objeto de estado**. Por eso `hoveredProvider` y
`selectedProvider` se propagan igual que en el widget instalado: lo que se ve es el
widget reaccionando, no una animación dibujada aparte.

Vive en `tests/qml/` y no en `contents/ui/` por dos razones: necesita colores literales
y tamaños absolutos que `tests/test_qml_style_gates.py` prohíbe con razón en el árbol que
se empaqueta, y no es parte del widget —nadie debería instalarlo—. Los gates de estilo
solo recorren `contents/ui` y `contents/config`, así que queda fuera por diseño.

`tests/qml/demo_storyboard.py` es el guion **como dato**: 15 planos, 486 fotogramas a
30 fps, 16,2 s. Cada fotograma es función pura de su índice. No hay `Behavior`, ni
`NumberAnimation`, ni `Timer` en el escenario, así que no hay reloj del que
desincronizarse y dos corridas dan los mismos bytes.

Solo se interpolan dos cosas, y las calcula Python: la opacidad y el desplazamiento
vertical de las dos capas flotantes, con `smoothstep`. Todo lo demás es corte duro,
porque en el widget real el cambio de proveedor **es** instantáneo; interpolarlo sería
mentir sobre el producto en la pieza que sirve para enseñarlo. Por eso se quitó el
atenuado de la columna de detalle que el diseño inicial proponía.

El estado se muta con eventos reales: `QEvent.MouseMove` al centro de la celda de la
barra —que enciende `containsMouse` y `onEntered`— y `press`+`release` sobre
`select-<proveedor>` en el popup. Y cada fotograma **comprueba** que el estado que pedía
el guion es el que quedó: si un clic no prende, el render falla en voz alta en vez de
producir un video donde el selector nunca cambia.

Un proceso, no uno por fotograma: el arranque con `--sample` cuesta ~1,5 s, así que 486
procesos serían 12 minutos; con el engine vivo son decenas de milisegundos por fotograma.

## Dos trampas medidas

**Una excepción dentro de un slot de Qt no termina el proceso.** Python la imprime y el
bucle de eventos sigue, así que el comando se cuelga hasta el timeout y parece que el
render tarda cuando en realidad ya falló. Ocurrió con un `AttributeError`; de ahí el
`try/except` explícito que sale con código.

**`framemd5` hashea el fotograma en su formato de píxel nativo.** Un PNG en `rgba` y un
FFV1 en `gbrp` dan hashes distintos aunque el contenido sea idéntico, así que la
comprobación de que el maestro es bit-exacto reprobaba **siempre** y no decía nada. Los
dos lados se normalizan a `gbrp` antes de comparar.

## La escalera de CRF, medida

486 fotogramas, 1472x1152, contra la referencia `yuv420p` sin compresión:

| CRF | bytes | VMAF | SSIM | PSNR | SSIM del recorte de texto | veredicto |
|---|---|---|---|---|---|---|
| 28 | 1 111 120 | 96,85 | 0,9992 | 56,95 dB | 0,9991 | pasa |
| 31 | 990 291 | 96,70 | 0,9990 | 55,58 dB | 0,9989 | pasa |
| **34** | **881 611** | 96,44 | 0,9987 | 54,20 dB | 0,9986 | **gana** |

El criterio que decide y que la skill no tiene es el **SSIM del recorte de texto**
(`crop=1200:520:170:390` sobre las líneas de métrica de Antigravity). Un VMAF global de
97 convive perfectamente con texto de 13 px hecho papilla, porque el texto es una
fracción mínima del área; ese recorte es lo que protege lo único que el video tiene que
comunicar.

Se rechazó a propósito el criterio de la skill de `maximumIdenticalRun <= 1`: en un
recorrido de interfaz las esperas estáticas **son** el contenido, porque hacen falta para
leer. En su lugar hay un mínimo de estados visuales distintos (172 medidos, mínimo 12) y
un máximo de tiempo congelado expresado **en segundos** y no en fotogramas —3,5 s—,
porque lo que decide si un video parece roto es cuánto tiempo lleva sin cambiar. La
carrera más larga del guion es de 92 fotogramas, 3,07 s, y la produce
`select-gemini` + `popup-hold-gemini`: el clic no cambia el estado visual porque Gemini
ya estaba seleccionado, así que los dos planos se leen como uno. Es el plano de
Antigravity con sus dos cuotas semanales en relojes distintos, o sea la tesis del post, y
merece ser el más largo.

Un detalle que costó un rojo: el umbral estaba escrito primero en **fotogramas** (90) y
reprobaba el guion real por dos. Reescribirlo en segundos no fue subir el umbral para
que pasara: fue ponerlo en la unidad de la propiedad que se quiere garantizar.

## El bucle y el póster

El primer y el último fotograma son **byte a byte idénticos** (`frame-0000.png` y
`frame-0485.png`, los dos del plano de reposo), así que el salto de `loop` es invisible
sin gastar un plano en volver al inicio. Se comprueba con `sha256sum`, que es más fuerte
y más simple que el SSIM ≥0,9999 que propone la skill.

El póster sale del fotograma 380 —Antigravity con sus dos semanales— y tiene **el mismo
tamaño exacto** que el video, 1472x1152. No es un detalle estético: el póster anterior
medía 1920x1500 (relación 1,28) mientras el video medía 816x373 (2,19), y esa
discrepancia provocaba un reflujo de 237 px en cuanto empezaba la reproducción. Con las
mismas dimensiones y los atributos `width`/`height` en el `<video>`, el navegador reserva
la caja antes de pedir un solo byte.

## Reproducirlo

```bash
scripts/render_demo_video.sh          # fotogramas + escalera + póster
PYTHONPATH=src python -m pytest -q tests/test_demo_video.py
```

El gate de determinismo renderiza cuatro fotogramas dos veces y compara los sha256; se
salta explícitamente si la máquina no tiene `/dev/dri/renderD*`.
