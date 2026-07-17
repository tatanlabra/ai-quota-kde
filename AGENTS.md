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
