# AI Quota HUD for KDE Plasma 6

Widget local-first para mirar en un solo lugar las ventanas de uso de Claude Code,
Codex y Gemini, además del saldo opcional de DeepSeek. La interfaz lee una caché JSON
local; un timer de usuario la actualiza cada cinco minutos.

![Licencia MIT](https://img.shields.io/badge/license-MIT-blue.svg)
![KDE Plasma 6](https://img.shields.io/badge/KDE-Plasma%206-1d99f3.svg)

## Instalación

Requiere Linux, KDE Plasma 6, Python 3.11+, `python-venv`, `curl` y `jq`.
`ccusage` es opcional.

```bash
git clone https://github.com/tatanlabra/ai-quota-kde.git
cd ai-quota-kde
scripts/install-user.sh
ai-quota-monitor doctor
```

La instalación no usa `sudo`: crea un entorno virtual en
`~/.local/share/ai-quota-monitor/`, un wrapper en `~/.local/bin/`, instala el
plasmoide y habilita un timer de `systemd --user`.

Para mirar la interfaz sin leer proveedores reales:

```bash
ai-quota-monitor sample --write-cache
plasmawindowed org.tatan.aiquota
```

Los valores de `sample` están marcados como ficticios.

## Fuentes y privacidad

| Proveedor | Fuente | Clasificación |
|---|---|---|
| Claude | API de uso de Claude Code y `ccusage` local | oficial + observada localmente |
| Codex | endpoint que usa Codex y fallback de snapshots locales | oficial |
| Gemini | conteo de solicitudes en logs locales | estimación configurada |
| DeepSeek | API de saldo, opt-in | oficial, conversión CLP estimada |

Los helpers Bash son los únicos componentes que leen credenciales. Entregan JSON
saneado al proceso Python y nunca escriben tokens en la caché. El widget no recibe
credenciales. Caché y configuración usan permisos `0600`; sus directorios, `0700`.

El modo offline es el valor predeterminado. Para habilitar DeepSeek, crea:

```bash
install -d -m 700 ~/.config/ai-quota-monitor
printf 'DEEPSEEK_API_KEY=tu_clave\n' > ~/.config/ai-quota-monitor/secrets.env
chmod 600 ~/.config/ai-quota-monitor/secrets.env
```

No añadas ese archivo al repositorio.

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

El QML llama exclusivamente a `~/.local/bin/ai-quota-monitor`; no contiene rutas al
clon ni al intérprete Python. El servicio usa el mismo wrapper.

## Desarrollo y pruebas

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/python -m pytest -q
for script in scripts/*.sh; do bash -n "$script"; done
```

Los fixtures crudos están excluidos deliberadamente. No subas logs de conversación,
exports del navegador, archivos de autenticación ni capturas con saldos reales.

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

## English

AI Quota HUD is a local-first KDE Plasma 6 widget for viewing Claude Code, Codex and
Gemini usage windows, plus an optional DeepSeek balance. Install it with
`scripts/install-user.sh`, run `ai-quota-monitor doctor`, and use
`ai-quota-monitor sample --write-cache` for a credential-free demo.

The Plasma widget only reads sanitized local JSON. Credentials stay inside dedicated
helper scripts, offline mode is the default, and no raw conversation logs or browser
exports belong in the repository. The installation uses user-local paths and requires
no `sudo`. See the Spanish sections above for the complete command and security guide.

MIT © 2026 Cristian Labra
