# AI Quota HUD for KDE Plasma 6

Código de apoyo al artículo [Cuotas de IA en 3 cucharadas](https://3cucharadas.cl/ia/productividad/ai-quota-hud-kde/), mantenido también como widget de uso local.

Widget local-first para mirar las ventanas de cuota de Claude Code, Codex y Copilot CLI,
las cuotas disponibles de Antigravity y la actividad observada separadamente de Gemini CLI y el saldo oficial
opcional de DeepSeek. La interfaz lee una caché JSON local; un timer de usuario la
actualiza cada cinco minutos.

![Licencia MIT](https://img.shields.io/badge/license-MIT-blue.svg)
![KDE Plasma 6](https://img.shields.io/badge/KDE-Plasma%206-1d99f3.svg)

## Instalación

Requiere Linux, KDE Plasma 6, Python 3.11+, `python-venv`, `curl` y `jq`.
`gettext` (`xgettext`, `msgmerge`, `msgfmt`, `msginit`) es necesario para compilar
las traducciones del plasmoide. `ccusage` es opcional.

```bash
git clone https://github.com/tatanlabra/ai-quota-kde.git
cd ai-quota-kde
scripts/install-user.sh
ai-quota-monitor doctor
```

La instalación no usa `sudo`: crea un entorno virtual en
`~/.local/share/ai-quota-monitor/`, un wrapper en `~/.local/bin/`, instala el
plasmoide y habilita un timer de `systemd --user`.

Para actualizar el plasmoide de una instalación existente hace falta reemplazar el
paquete y recargar la shell; editar el repo no toca lo instalado:

```bash
bash scripts/build_locale.sh
kpackagetool6 --type Plasma/Applet --upgrade plasmoid/org.tatan.aiquota
systemctl --user restart plasma-plasmashell.service
```

Para mirar la interfaz sin leer proveedores reales:

```bash
ai-quota-monitor sample --write-cache
plasmawindowed org.tatan.aiquota
```

Los valores de `sample` están marcados como ficticios. `--write-cache` reemplaza la
caché local hasta el siguiente refresco: úsalo en una instalación de demostración.
`ai-quota-monitor sample` permite inspeccionar el JSON sin escribirlo.

## Arquitectura de datos

El colector y la interfaz estan separados y solo se comunican por un fichero:

- `ai-quota-monitor.timer` dispara `ai-quota-monitor.service` cada 300 s. Esa unidad es
  la vía normal de recolección y escritura atómica de
  `~/.cache/ai-quota-monitor/status.json`. Los comandos CLI de refresco y de ejemplo
  también pueden escribir esa caché cuando se invocan explícitamente.
- El plasmoide vigila ese fichero con `FolderListModel` y lo lee con `cat` cuando cambia
  (250 ms de rebote), mas un temporizador de respaldo cada 300 s. No arranca Python ni
  abre conexiones: antes levantaba el venv con typer, rich y pydantic ~1440 veces al dia
  para leer 7 KB, y ademas lanzaba una recoleccion en vivo al cargar y al abrir el popup.
- El boton de refresco arranca la misma unidad con `systemctl --user start`. systemd
  deduplica, asi que pulsarlo mientras el colector corre se une al trabajo en curso.
- La compuerta anti-429 vive en la unidad (`StartLimitIntervalSec=600`,
  `StartLimitBurst=4`), no en el QML: la interfaz no puede saltarsela. El widget se
  autolimita a 2 arranques manuales por ventana para dejarle cupo al temporizador.

Medido el 2026-09-06 con `plasmoidviewer`: 11 muestras de recoleccion en vivo lanzadas
por el propio widget antes del cambio, 0 despues; la recarga tras una escritura de la
cache tarda 274 ms.

## Fuentes y privacidad

| Proveedor | Fuente | Clasificación |
|---|---|---|
| Claude | API de uso de Claude Code y `ccusage` local | oficial + observada localmente |
| Codex | endpoint que usa Codex y fallback de snapshots locales | oficial |
| Antigravity / Gemini | `agy /usage` (cuota semanal por grupo) + conteos separados en logs locales | cuota oficial por grupo + actividad observada |
| Copilot CLI | `quotaSnapshots.chat` en `~/.copilot/session-state/*/events.jsonl` | observación local del último snapshot oficial expuesto por el CLI |
| DeepSeek | API de saldo, opt-in | saldo oficial; presupuesto CLP opcional y estimado |

Copilot se lee sin abrir una sesión nueva ni consultar la red: el proveedor reutiliza el
último evento estructurado `model.model_call_success` y calcula
`usedRequests / entitlementRequests`. La ausencia de snapshot se muestra como dato
desconocido, nunca como cero. El bucket se etiqueta como `AI Credits / Premium requests`
porque Copilot puede presentar cualquiera de esos esquemas según el plan.

Antigravity **no tiene una cuota, tiene dos**, independientes y con relojes distintos:
`gemini-weekly` (modelos de Google) y `3p-weekly` (Claude/GPT facturados por Google). El
colector las expone como dos `ProviderWindow` de `metric_kind="quota"` —
`antigravity_gemini_weekly` y `antigravity_claude_gpt_weekly` — con el `reset_at` RFC3339
absoluto que devuelve el propio CLI, sin recalcularlo.

Tres detalles que importan al mantenerlo:

- `agy /usage` entrega `remaining_fraction` (lo **restante**); `percent` es lo **usado**, así
  que la conversión invierte: `percent = 1 - remaining_fraction`. Un grupo agotado es
  `percent = 1.0`, no `0.0`.
- Son `metric_kind="quota"` y no `"activity"` a propósito: el colector no preserva las
  ventanas de actividad tras un fetch fallido, así que como actividad parpadearían a un cero
  falso cada vez que se cayera la red.
- La consulta es client-side y cuesta 0 tokens, pero **es una request de red de ~4 s**, así
  que vive solo dentro de `refresh --online` (el timer de 5 min) y nunca en el camino de una
  delegación. La etiqueta de `3p-weekly` dice «Antigravity Claude/GPT» para que no se
  confunda con la cuota directa de Claude, que es otra ventana con otro reloj.

Los helpers Bash son los únicos componentes que leen credenciales. Entregan JSON
saneado al proceso Python y nunca escriben tokens en la caché. El widget no recibe
credenciales. Caché y configuración usan permisos `0600`; sus directorios, `0700`.

El comando de refresco sin `--online` prefiere fuentes locales; el timer instalado
invoca explícitamente `refresh --online`. El widget solo lee el resultado y nunca
consulta las APIs por su cuenta. Para habilitar DeepSeek, crea:

```bash
install -d -m 700 ~/.config/ai-quota-monitor
printf 'DEEPSEEK_API_KEY=tu_clave\n' > ~/.config/ai-quota-monitor/secrets.env
chmod 600 ~/.config/ai-quota-monitor/secrets.env
```

No añadas ese archivo al repositorio.

El tooltip HD y el popup usan la misma línea de métrica: muestran fuente,
confianza y renovación local. Un halo blanco de siete segmentos aparece solamente
para una ventana oficial semanal de ciclo `7d` con `reset_at` válido; indica días
restantes, no consumo. Antigravity mantiene la cuota oficial verificable manualmente
en `/usage`, sin automatizar su TUI. DeepSeek no expone vencimiento de saldo: las
recargas no vencen y los créditos gratuitos se revisan en Billing.

La actividad Agy/Gemini distingue `0 observado` de `sin registro compatible`: la
primera se basa en logs locales presentes y la segunda se marca como `SIN DATO`.
La instalación actual de Antigravity guarda transcripts bajo
`~/.gemini/antigravity-cli/`; el helper conserva además las rutas históricas. Para
saldo DeepSeek se requiere deliberadamente `DEEPSEEK_API_KEY` en el archivo privado
`~/.config/ai-quota-monitor/secrets.env`; el widget nunca busca claves en otros
proyectos, variables ajenas ni perfiles del navegador.

Para ver el presupuesto personal secundario de DeepSeek, configura un
`budget_clp` positivo junto al tipo de cambio manual; el saldo USD oficial siempre
permanece separado y sin porcentaje.

## Comandos

```bash
ai-quota-monitor doctor
ai-quota-monitor config init
ai-quota-monitor config validate
ai-quota-monitor sample
ai-quota-monitor sample --write-cache
ai-quota-monitor refresh --offline
ai-quota-monitor refresh --online
ai-quota-monitor status
ai-quota-monitor status --json
```

## Arquitectura

```text
helpers saneados -> paquete Python -> ~/.cache/ai-quota-monitor/status.json
                                      ^
systemd --user timer -----------------+
                                      |
plasmoide KDE ------------------------+  (solo lectura + refresh manual)
```

El QML lee la caché con `cat` y solicita el refresco mediante
`systemctl --user start ai-quota-monitor.service`. El servicio invoca el wrapper
`~/.local/bin/ai-quota-monitor`; el QML no arranca el intérprete Python.

## Lectura del widget

- El panel muestra cinco donas con iconos propios. Pasar por una dona muestra el
  proveedor correspondiente; hacer clic abre su detalle.
- El tooltip usa texto legible y resume solo ese proveedor. El popup mantiene los
  cinco selectores visibles y permite recorrer el detalle completo sin apilar cinco
  columnas de texto. También se puede seleccionar con el teclado.
- Los iconos caben dentro del hueco calculado de los anillos. Los arcos coloreados
  representan cuota disponible, y el anillo blanco segmentado cuenta días al reset.
  Saldo y actividad sin porcentaje conservan su icono, sin inventar un arco de cuota.

El icono Copilot procede de [GitHub Octicons](https://github.com/primer/octicons),
con licencia en [octicons-MIT.txt](plasmoid/org.tatan.aiquota/contents/licenses/octicons-MIT.txt).
Las fuentes Orbitron incluyen su [licencia OFL](plasmoid/org.tatan.aiquota/contents/licenses/orbitron-OFL.txt),
obtenida del [catálogo oficial de Google Fonts](https://github.com/google/fonts/tree/main/ofl/orbitron).

## Desarrollo y pruebas

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest -q
for script in scripts/*.sh; do bash -n "$script"; done
```

Las pruebas geométricas e interactivas requieren PySide6 y los módulos QML de
Plasma/Kirigami; se omiten explícitamente si PySide6 no está instalado.

Los fixtures crudos están excluidos deliberadamente. No subas logs de conversación,
exports del navegador, archivos de autenticación ni capturas con saldos reales.

### Capturas: los tests van por software, la publicación por GPU

No es un detalle de configuración, y confundirlo publicó cuatro logotipos en negro:

```bash
# Tests de geometría: offscreen + renderizador software. Deterministas, rápidos,
# sin GPU. Es lo que corre pytest.
PYTHONPATH=src python -m pytest -q

# Capturas para publicar: eglfs + EGL_PLATFORM=surfaceless, o sea RHI sobre GPU.
scripts/capture_previews.sh build/previews es 3
```

`Kirigami.Icon` con `isMask: true` **no tiñe** bajo `QSGSoftwareRenderer`, así que con el
renderizador software los cuatro logotipos enmascarados salen negros (Codex, blanco) y
ningún test de geometría puede verlo: una silueta negra tiene la misma anchura, altura y
apertura que una teñida. `scripts/capture_previews.sh` aborta si no encuentra
`/dev/dri/renderD*` y comprueba en cada captura que el render salió por RHI, a la escala
pedida y sin desborde de texto. `tests/test_qml_icon_tint.py` mide el color del píxel
dentro del disco central de cada dona sobre el artefacto que produce ese script, y se
salta explícitamente si la máquina no tiene dispositivo de render.

Medición completa, tabla de las ocho combinaciones de plataforma y backend, y por qué
`eglfs` gana a `wayland` (una pantalla bloqueada cuelga el grab): `docs/capturas-rhi-2026-09-09.md`.

### Video de demostración y teaser

Las dos piezas de difusión también se generan por script, no a mano:

```bash
scripts/render_demo_video.sh    # 486 fotogramas + escalera de CRF + póster
scripts/render_teaser.sh        # teaser 1280x720 y su variante 640x360
```

El video **no** es una grabación de pantalla: es una secuencia renderizada por la misma
sonda que verifican los tests, con el guion en `tests/qml/demo_storyboard.py` como dato y
el reloj congelado. Cada fotograma es función pura de su índice, así que dos corridas dan
la misma imagen y `tests/test_demo_video.py` puede comprobarlo en vez de que alguien mire
el video a ojo. El estado se muta con eventos reales —`MouseMove` sobre la celda de la
barra, `press`+`release` sobre el selector del popup— y cada fotograma comprueba que el
estado que pedía el guion es el que quedó: si un clic no prende, el render falla en voz
alta.

Por qué no se graba la pantalla, qué se hereda de la skill de captura y qué no, y la
escalera de CRF medida: `docs/video-demo-2026-09-09.md`.

## Gobernanza de datos

- `tests/fixtures/sanitized/` puede versionarse si no contiene identificadores,
  tokens, saldos reales ni fragmentos de conversación.
- `tests/fixtures/raw/` es solo local y está ignorado por Git.
- Capturas HTML, carpetas `*_files/`, exports de dashboards, logs crudos,
  screenshots privadas y archivos de autenticación no pertenecen al repositorio.
- Runtime local: `~/.cache/ai-quota-monitor/` y
  `~/.config/ai-quota-monitor/` deben mantenerse con permisos privados.

## Desinstalación

```bash
scripts/uninstall-user.sh
```

Conserva caché y configuración. Para borrarlas también:

```bash
scripts/uninstall-user.sh --purge-data
```

## Troubleshooting

- `doctor` indica qué CLI o helper falta sin modificar el sistema.
- Si el widget no aparece, ejecuta `plasmawindowed org.tatan.aiquota` y revisa el error.
- Si la caché queda antigua, revisa `systemctl --user status ai-quota-monitor.timer` y
  `journalctl --user -u ai-quota-monitor.service -n 30`.
- Un proveedor degradado conserva el último valor válido y lo marca como caché antigua.
- Si un cambio del QML no se ve, comprueba que el paquete instalado sea el del repo
  (`diff -rq plasmoid/org.tatan.aiquota ~/.local/share/plasma/plasmoids/org.tatan.aiquota`):
  `plasmashell` sirve la copia instalada, no el árbol de trabajo.

## English

AI Quota HUD is a local-first KDE Plasma 6 widget for official Claude Code and Codex
quota windows, available Antigravity quotas, separately observed CLI activity, Copilot
snapshots, and an optional official
DeepSeek balance. Install it with
`scripts/install-user.sh`, run `ai-quota-monitor doctor`, and use
`ai-quota-monitor sample --write-cache` for a credential-free demo.

The Plasma widget only reads sanitized local JSON. Credentials stay inside dedicated
helper scripts. The installed timer explicitly opts into online refresh; the widget
itself stays local. No raw conversation logs or browser
exports belong in the repository. The installation uses user-local paths and requires
no `sudo`. See the Spanish sections above for the complete command and security guide.

MIT © 2026 Cristian Labra
