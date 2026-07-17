#!/usr/bin/env bash
# Uso REAL de Codex. Prioridad:
#   1) Oficial EN VIVO (CLI + Cloud): GET chatgpt.com/backend-api/wham/usage vía _codex_wham.py
#      (token de ~/.codex/auth.json). Es lo mismo que muestra la página de analytics de Codex.
#   2) Fallback: snapshot rate_limits de los rollouts locales (solo CLI, puede quedar stale).
# Salida: JSON saneado en stdout (sin token, sin texto de conversación). Exit 0 siempre.
# Esquema unificado: {source, snapshot_ts, plan_type,
#                     primary{used_percent,reset_at,window_minutes}, secondary{...},
#                     credits_balance}.
# window_minutes es obligatorio: identifica la ventana (5h=300 vs semanal=10080). Codex
# cambia qué ventana va en primary según el plan, así que la posición no la identifica.
set -eu

DIR="$(cd "$(dirname "$0")" && pwd)"
SESSIONS="${CODEX_SESSIONS_DIR:-$HOME/.codex/sessions}"

emit() { printf '%s\n' "$1"; exit 0; }

# ── 1) Fuente oficial en vivo (incluye Codex Cloud) ──────────────────────────
if [ -f "$HOME/.codex/auth.json" ]; then
  WHAM=$(python3 "$DIR/_codex_wham.py" 2>/dev/null) || true
  if [ -n "${WHAM:-}" ]; then emit "$WHAM"; fi
fi

# ── 2) Fallback: rollout rate_limits (solo CLI) ──────────────────────────────
command -v jq >/dev/null 2>&1 || emit '{"error":"wham_failed_and_no_jq"}'
[ -d "$SESSIONS" ] || emit '{"error":"no_source"}'

best=$(
  find "$SESSIONS" -name 'rollout-*.jsonl' -printf '%T@\t%p\n' 2>/dev/null \
    | sort -rn | head -8 | cut -f2- \
    | while IFS= read -r f; do
        tac "$f" 2>/dev/null | jq -cr '
          select(.type=="event_msg" and .payload.type=="token_count"
                  and .payload.rate_limits != null)
          | .timestamp + "\t" + ({
              source: "rollout",
              snapshot_ts: .timestamp,
              plan_type: (.payload.rate_limits.plan_type // null),
              primary:   {used_percent:   (.payload.rate_limits.primary.used_percent // null),
                          reset_at:       (.payload.rate_limits.primary.resets_at // null),
                          window_minutes: (.payload.rate_limits.primary.window_minutes // null)},
              secondary: {used_percent:   (.payload.rate_limits.secondary.used_percent // null),
                          reset_at:       (.payload.rate_limits.secondary.resets_at // null),
                          window_minutes: (.payload.rate_limits.secondary.window_minutes // null)},
              credits_balance: null
            } | tojson)
        ' 2>/dev/null | head -1
      done \
    | sort -r | head -1
)

[ -n "$best" ] || emit '{"error":"no_rate_limits_snapshot"}'
printf '%s\n' "${best#*$'\t'}"
