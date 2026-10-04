# AGENTS.md

## Objetivo
Widget KDE Plasma 6 local-first para visualizar uso de Claude Code, Codex y Gemini CLI.

## Reglas obligatorias
- No leer ni exponer credenciales directamente desde Python (usar helper scripts).
- No imprimir contenidos de logs brutos de IA.
- No subir fixtures crudos al repositorio (tests/fixtures/raw/ está en .gitignore).
- No ejecutar comandos destructivos.
- No instalar paquetes globales sin mostrar alternativa local.
- No inventar cuotas oficiales — marcar estimados como `local_observed`.
- Mantener modo offline por defecto (`prefer_offline = true`).
- Implementar `doctor` y `sample` antes de tocar datos reales.
- Escritura atómica a caché: write .tmp → fsync → rename.
- Permisos 0600 en todos los archivos bajo ~/.cache/ai-quota-monitor/ y ~/.config/ai-quota-monitor/.

## Flujo
1. Diagnosticar entorno (doctor).
2. Un cambio por vez.
3. Tests antes de instalar plasmoide.
4. Detenerse antes de tocar credenciales o cambiar config global.

## Lecciones operativas

- **Tres trampas de QML que `qmllint` no ve, las tres encontradas ejecutando.** Del 2026-09-06
  y 2026-09-08, sobre el plasmoide del HUD. (1) Un singleton llamado `Palette` lo **eclipsa**
  `QtQuick.Palette`: el plasmoide carga, ningún gate estático falla y el journal repite
  `TypeError: Property 'deepOf' of object QtQuick/Palette is not a function` mientras todo se
  dibuja sin color. `qmllint` calla porque resuelve el nombre contra el tipo de QtQuick. No
  bautizar un singleton como un tipo de QtQuick; se llamó `HudPalette`. (2) `{}` en un binding
  se lee como **bloque de código vacío**, no como objeto: una tabla de traducción vacía dejaba
  la propiedad `undefined` y la vista se rendía sin valores ni insignias. Cualquier literal de
  objeto insertado en un binding va entre paréntesis. (3) `Qt.formatDate` y `Qt.formatDateTime`
  con un formato escrito a mano usan el locale **C**, no el del escritorio: con la interfaz ya
  traducida seguían diciendo `Sat 12 Sep` donde tocaba `sáb 12 sept`. Medido con
  `QLocale("es_CL")` sobre la misma fecha; la vía correcta es
  `d.toLocaleDateString(Qt.locale(), fmt)`. Con el enum (`Locale.ShortFormat`) sí respeta el
  locale. Síntoma delator: una interfaz traducida a medias donde lo que queda en inglés son
  justo las fechas.
- **Borrar los marcadores `#, fuzzy` de un `.po` en bloque publica las adivinanzas de
  `msgmerge`.** Medido el 2026-09-08: al añadir `Antigravity (today)`, msgmerge la casó por
  parecido con una entrada obsoleta y propuso «Antigravity / Gemini», que no es su traducción;
  una regex que limpiaba los marcadores la aceptó en silencio y entró al `.mo` compilado. El
  control correcto **no** es borrar las entradas obsoletas `#~` —son de donde salen esos
  casamientos, pero también su razón de ser: una cadena que vuelve recupera su traducción—
  sino un gate que prohíba que una entrada llegue marcada como adivinanza, de modo que tras
  cada `msgmerge` o se revisa una por una o el test está rojo.
- **Una captura de un widget con máscaras de Kirigami necesita GPU, y una pantalla bloqueada
  cuelga el `grabToImage`.** El 2026-09-09 se descubrió que cuatro de los cinco logotipos del
  HUD llevaban dos días publicados en negro (el de Codex, blanco) con los 93 tests verdes:
  `Kirigami.Icon` con `isMask: true` recolorea a través de un `QSGMaterial` con shaders RHI y
  `QSGSoftwareRenderer` no tiene nodo equivalente, así que dibuja la textura sin el uniform de
  color. El contraste que aísla la causa: `ShadowedRectangle`, en la misma librería, **sí** trae
  `SoftwareRectangleNode`. `QT_QPA_PLATFORM=offscreen` fuerza `GraphicsApi.Software` y **no se
  corrige desde el entorno** —ni vaciando `QT_QUICK_BACKEND` ni pidiendo `QSG_RHI_BACKEND`—;
  `vnc` tampoco. Tiñen `xcb`, `wayland` y `eglfs`, pero las dos primeras exigen mapear una
  ventana y con `LockedHint=yes` el compositor deja de presentarla, así que `grabToImage()`
  nunca completa y el proceso se cuelga hasta el timeout: los mismos comandos funcionaron a las
  22:00 y colgaron a las 22:50. Lo que sirve desatendido es
  `QT_QPA_PLATFORM=eglfs EGL_PLATFORM=surfaceless`, que no abre ventana, no pide DRM master y
  deja `plasmashell` y `kwin` intactos; solo necesita `/dev/dri/renderD*`. Dos «mejoras» que
  fallan: `setOpacity(0)` hace que el compositor no renderice y `grabToImage()` devuelve un
  puntero **nulo**, y `Qt.ToolTip` sin padre corre el mismo riesgo de no mapearse. Trampa
  aparte: `eglfs` deriva el DPI lógico del panel real (100 frente a los 96 de `offscreen`) y con
  eso una vista creció 24 px sin cambiar una línea de QML, lo que habría puesto rojo el
  manifiesto del blog; se fija `QT_FONT_DPI=96`. Síntoma delator: una imagen que parece bien
  salvo que se mire el color de un píxel, con toda la geometría verde. Detalle en
  `activos/ai-quota-kde/docs/capturas-rhi-2026-09-09.md`.
- **Una excepción dentro de un slot de Qt no termina el proceso.** Python la imprime y el bucle
  de eventos sigue corriendo, así que el comando agota el timeout y **parece que la tarea tarda
  cuando en realidad ya falló**. Medido el 2026-09-09 con un `AttributeError` dentro de un
  `QTimer.singleShot`. Todo trabajo hecho dentro de un slot va en `try/except` que llame a
  `app.exit(<código>)`. Síntoma delator: un proceso Qt que no imprime nada y muere por timeout,
  con la traza ya escrita en stderr.

- **El endpoint de uso de Claude limita por token, y sondearlo congela el widget sin que nada
  falle.** Medido el 2026-10-03: `/api/oauth/usage` devolvía 429 con `retry-after: 3153` y el
  widget llevaba 1,5 h mostrando 0 %/0 % mientras el uso real era 6 %/1 %. La única lectura buena
  llegó 75 s después de que Claude Code renovara el token OAuth, con el timer sondeando cada 300 s
  toda la noche; un 429 no movió el plazo de espera. El servicio salía `0/SUCCESS` en cada 429, así
  que ni `OnFailure=` ni el journal lo delataban: solo `stale_since` en `status.json`. Claude Code
  ya trae el mismo % en el campo `rate_limits` de la entrada de su statusline (de las cabeceras
  `anthropic-ratelimit-unified-*`), con 0 llamadas extra; desde ese día es la fuente primaria y el
  endpoint es respaldo con espera persistida. Síntoma delator: `stale_since` de horas en una ventana
  `official` y `retry-after` cercano a 3600 en una consulta a mano (token por stdin, `-H @-`).
  Desde el 2026-10-04 `refresh --online` sale 75 cuando una cuota oficial lleva más de 30 min
  vieja en dos corridas, y `OnFailure=` avisa una vez.
