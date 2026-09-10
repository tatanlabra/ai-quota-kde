# Las capturas necesitan GPU: por qué, y qué se rompió por no saberlo

Fecha de la medición: 2026-09-09. Este es el documento que hay que citar la próxima vez
que alguien proponga volver a renderizar las capturas del HUD por `offscreen`.

## Lo que pasó

Entre el 6 y el 8 de septiembre se publicaron cuatro imágenes del HUD en el blog con
**cuatro de los cinco logotipos sin teñir**: negros los de Claude, Copilot y DeepSeek, y
blanco el de Codex. En el popup quedaban casi invisibles, oscuro sobre oscuro. El widget
en el panel siempre estuvo bien; lo que mentía era la captura.

El defecto **ya estaba registrado en este repo** y se perdió:
`docs/layout-validation-2026-09-06.md:31-34` dice «Software rendering alone did not show
SVG mask colours faithfully», y la validación del 6 de septiembre se apoyó en capturas
nativas Wayland/RHI. Dos días después, el commit `74bd40a` sustituyó ese flujo por
`scripts/capture_previews.sh` con `QT_QUICK_BACKEND=software`, y el defecto conocido
llegó al blog.

## El mecanismo

`Kirigami.Icon` con `isMask: true` recolorea a través de un `QSGMaterial` con shaders
RHI (`IconMaterial`/`IconNode` en `libKirigamiPrimitives.so.6.30.0`, que importa
`QSGMaterialShader::setShaderFileName` y `RenderState::rhi()`). `QSGSoftwareRenderer` no
tiene nodo equivalente, así que degrada a dibujar la textura tal cual, sin el uniform de
color. El contraste que aísla la causa: `ShadowedRectangle`, en la misma librería, **sí**
trae `SoftwareRectangleNode` y una propiedad `softwareRendering`; `Icon` no trae ninguno.

## La tabla

Disco central de cada dona en `bar.png` a escala 3, misma escena y mismo código,
cambiando solo el entorno:

| plataforma | `QT_QUICK_BACKEND` | api | claude | codex | copilot | deepseek |
|---|---|---|---|---|---|---|
| `offscreen` | `software` | Software | `#000000` | `#ffffff` | `#000000` | `#000000` |
| `offscreen` | vacío | Software | `#000000` | `#ffffff` | `#000000` | `#000000` |
| `offscreen` + `QSG_RHI_BACKEND=opengl` | vacío | Software | `#000000` | `#ffffff` | `#000000` | `#000000` |
| `offscreen` + `QSG_RHI_BACKEND=vulkan` | vacío | Software | `#000000` | `#ffffff` | `#000000` | `#000000` |
| `vnc` | vacío | Software | `#000000` | `#ffffff` | `#000000` | `#000000` |
| `xcb` (`DISPLAY=:1`) | vacío | OpenGL | `#ff7518` | `#57ff8d` | `#c084fc` | `#fff36d` |
| `wayland` | vacío | OpenGL | `#ff7518` | `#57ff8d` | `#c084fc` | `#fff36d` |
| **`eglfs` + `EGL_PLATFORM=surfaceless`** | vacío | OpenGL | `#ff7518` | `#57ff8d` | `#c084fc` | `#fff36d` |

`gemini` está declarado `mask: false` a propósito y conserva el `#4285f4` de su PNG: su
comportamiento era correcto en las ocho filas, y ése es el control negativo que prueba
que el criterio de medición puede pasar.

`offscreen` fuerza `GraphicsApi.Software` y **no se corrige desde el entorno**: ni
vaciando `QT_QUICK_BACKEND`, ni pidiendo un backend RHI explícito. Hay que salir de esa
plataforma.

## Por qué `eglfs` y no `wayland`

Las tres plataformas RHI tiñen igual, pero `wayland` y `xcb` exigen mapear una ventana, y
**una pantalla bloqueada deja de presentarla**: `grabToImage()` nunca completa y el
proceso se cuelga hasta el timeout. Medido el mismo día: los comandos que funcionaron con
la sesión desbloqueada colgaron una hora más tarde con `LockedHint=yes`
(`loginctl show-session`, y `org.freedesktop.ScreenSaver GetActive` → `true`).

Dos intentos de ocultar la ventana fallaron y quedan anotados en el código para que nadie
los repita: `setOpacity(0)` hace que el compositor no la renderice, así que
`grabToImage()` devuelve un **puntero nulo** (`Attempt to retrieve 'ready' from null
object`) y el proceso se cuelga sin guardar nada; `Qt.ToolTip` sin padre corre el mismo
riesgo de no mapearse en Wayland.

`eglfs` con `EGL_PLATFORM=surfaceless` no abre ventana, no pide DRM master, no depende del
estado de la sesión y deja `plasmashell` y `kwin_wayland` intactos: cero bytes de stderr.
Lo único que necesita es un dispositivo de render (`/dev/dri/renderD*`), y de ahí la
guarda del script. Descartado: `QT_QPA_EGLFS_INTEGRATION=none`, que aborta con SIGABRT.

## El DPI, que no era obvio

`eglfs` deriva su DPI lógico del panel real: `logicalDpi=100` sobre 1920x1080 a 143,91 DPI
físico, frente a los 96 de `offscreen`. Con eso, y **sin que cambiara una línea de QML**,
el tooltip pasaba de 310 a 318 px lógicos, o sea la imagen publicada de 1260x930 a
1260x954 — lo que habría puesto rojo V2 del blog y habría exigido renombrar
`tooltip-en-1260x930.png`. La sonda fija ahora `QT_FONT_DPI=96` con `setdefault`, así que
la geometría no depende del monitor de la máquina ni de la plataforma Qt: `offscreen` y
`eglfs` dan el mismo alto y lo que miden los tests es lo que se publica.

## Por qué los tests siguen en software

Deliberado. Los 93 tests de geometría son deterministas, rápidos y **no necesitan GPU**;
`eglfs` sí la necesita y no correría en un contenedor sin `/dev/dri`. La separación es
segura porque está medida: el JSON de la sonda es idéntico entre
`offscreen`+`software` y `eglfs`+RHI en las tres superficies (alto 40,0 / 310,0 / 500,0;
textos 0 / 18 / 33; `overflow` vacío en las seis corridas). La única diferencia entre
backends son los píxeles de los iconos enmascarados.

## Lo que lo blinda

`tests/test_qml_icon_tint.py` mide el **artefacto que produce el script de publicación**,
no un render paralelo: si alguien vuelve a poner el backend software en
`capture_previews.sh`, el gate se pone rojo. Comprobado en las dos direcciones:

- Con `AIQ_CAPTURE_PLATFORM=offscreen`: 9 errores (el propio script aborta en
  `scripts/assert_render_is_rhi.py`) y 2 tests estáticos que siguen pasando.
- Contra el `bar.png` publicado: claude, codex, copilot y deepseek reprueban con **0 %**
  de cobertura y dominante `#000000`; gemini pasa. Contra el nuevo: los cinco pasan con
  cobertura del 17,5 % al 30,6 %.

Conteos de la firma del defecto en lo publicado, con umbral de alfa > 250:
`bar.png` 1452 negros y 299 blancos; `popup-hidpi.png` y `popup-en-1920x1500.png` 2597 y
6 cada uno; los dos tooltip, cero y cero (su único icono es gemini). Tras el arreglo,
cero en las seis imágenes.

## Y una aserción que estaba muerta

`DonutGauge.qml` calculaba el ancho del icono como
`contentSize * Math.min(1, iconScale)`. Ese techo recortaba en silencio cualquier valor
mayor que 1, y con ello **desactivaba el invariante de contención** que
`test_qml_layout_runtime.py` cree comprobar: medido, un `iconScale: 1.10` daba cociente
`1.00000` y el invariante salía **verde**. Sin el `Math.min` da `1.10000` y sale **rojo**.
Quitarlo, además de permitir el `iconScale: 1.0` de esta versión, convirtió una aserción
inerte en un gate vivo.
