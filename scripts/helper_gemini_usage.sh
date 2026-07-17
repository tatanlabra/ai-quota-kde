#!/usr/bin/env bash
# Uso diario (request-count) de Gemini/Antigravity (agy). NO hay cuota oficial de Gemini,
# así que esto es una ESTIMACIÓN local: cuenta las peticiones de HOY desde los registros
# que existan. Fuentes intentadas (la que exista):
#   1) $XDG_DATA_HOME/antigravity/history.json   (.conversations[].messages[] role=user)
#   2) ~/.gemini/antigravity/conversations/*.json (mismo esquema)
#   3) ~/.gemini/antigravity-ide/brain/*/.system_generated/logs/transcript.jsonl
#      (source == USER_EXPLICIT, created_at = hoy)
#   + Gemini CLI: ~/.gemini/tmp/*/chats/session-*.jsonl (turnos con .tokens, archivo de hoy)
# Salida: JSON saneado, sin texto de conversación. Exit 0 siempre.
set -eu

TODAY=$(date +%Y-%m-%d)
AGY=0
CLI=0
CCUSAGE_STATUS="not_installed"
CCUSAGE_TOKENS="null"
CCUSAGE_COST_USD="null"
CCUSAGE_REQUESTS="null"

emit() { printf '%s\n' "$1"; exit 0; }
command -v jq >/dev/null 2>&1 || emit '{"error":"jq_not_found"}'

collect_ccusage() {
  command -v ccusage >/dev/null 2>&1 || return 0
  local out
  out=$(ccusage gemini daily --json --offline 2>/dev/null || ccusage gemini daily --json 2>/dev/null || true)
  [ -n "$out" ] || { CCUSAGE_STATUS="failed"; return 0; }
  local parsed
  parsed=$(printf '%s' "$out" | python3 -c '
import json
import sys

today = sys.argv[1]
try:
    data = json.load(sys.stdin)
except Exception:
    raise SystemExit(1)

tokens = 0.0
cost = 0.0
requests = 0.0
seen = False

def matches_today(obj):
    for key in ("date", "day", "timestamp", "created_at", "start", "startTime"):
        value = obj.get(key)
        if isinstance(value, str) and value.startswith(today):
            return True
    return False

def walk(obj, in_today=False):
    global tokens, cost, requests, seen
    if isinstance(obj, dict):
        here = in_today or matches_today(obj)
        if here:
            seen = True
            for key, value in obj.items():
                if not isinstance(value, (int, float)):
                    continue
                lk = key.lower()
                if "token" in lk:
                    tokens += float(value)
                elif "cost" in lk:
                    cost += float(value)
                elif "request" in lk or "message" in lk:
                    requests += float(value)
        for value in obj.values():
            walk(value, here)
    elif isinstance(obj, list):
        for value in obj:
            walk(value, in_today)

walk(data)
if not seen:
    print("empty null null null")
else:
    req = str(int(requests)) if requests > 0 else "null"
    print(f"ok {int(tokens)} {cost:.6f} {req}")
' "$TODAY" 2>/dev/null || true)
  if [ -z "$parsed" ]; then
    CCUSAGE_STATUS="parse_failed"
    return 0
  fi
  set -- $parsed
  CCUSAGE_STATUS="$1"
  CCUSAGE_TOKENS="$2"
  CCUSAGE_COST_USD="$3"
  CCUSAGE_REQUESTS="$4"
}

collect_ccusage

count_history_json() {
  local f="$1"
  [ -f "$f" ] || return 0
  local n
  n=$(jq -r --arg d "$TODAY" \
      '[.conversations[]?.messages[]? | select((.role==("user","USER")) and ((.timestamp // .created_at // "")|tostring|startswith($d)))] | length' \
      "$f" 2>/dev/null || echo 0)
  case "$n" in (''|*[!0-9]*) n=0;; esac
  AGY=$((AGY + n))
}

# 1) Ruta XDG (referencia del usuario)
count_history_json "${XDG_DATA_HOME:-$HOME/.local/share}/antigravity/history.json"

# 2) Conversaciones del install real de agy
if [ -d "$HOME/.gemini/antigravity/conversations" ]; then
  while IFS= read -r f; do count_history_json "$f"; done \
    < <(find "$HOME/.gemini/antigravity/conversations" -maxdepth 1 -type f -name '*.json' 2>/dev/null)
fi

# 3) Transcripts por-brain (source=USER_EXPLICIT hoy)
while IFS= read -r tf; do
  n=$(jq -r --arg d "$TODAY" \
      'select(((.created_at // "")|startswith($d)) and (.source=="USER_EXPLICIT")) | 1' \
      "$tf" 2>/dev/null | wc -l | tr -d ' ')
  case "$n" in (''|*[!0-9]*) n=0;; esac
  AGY=$((AGY + n))
done < <(find "$HOME/.gemini/antigravity-ide" -name 'transcript.jsonl' 2>/dev/null)

# 4) Gemini CLI: turnos (.tokens) en sesiones de hoy
while IFS= read -r sf; do
  n=$(jq -rc 'select(.tokens.total != null) | 1' "$sf" 2>/dev/null | wc -l | tr -d ' ')
  case "$n" in (''|*[!0-9]*) n=0;; esac
  CLI=$((CLI + n))
done < <(find "$HOME/.gemini/tmp" -path '*chats*' -name 'session-*.jsonl' -newermt "$TODAY 00:00" 2>/dev/null)

TOTAL=$((AGY + CLI))
if [ "$CCUSAGE_REQUESTS" != "null" ] && [ "$CCUSAGE_REQUESTS" -gt "$TOTAL" ] 2>/dev/null; then
  TOTAL="$CCUSAGE_REQUESTS"
fi

printf '{"source":"gemini-logs+ccusage","day":"%s","requests_today":%d,"agy_requests":%d,"cli_requests":%d,"ccusage":{"status":"%s","tokens":%s,"cost_usd":%s,"requests":%s}}\n' \
  "$TODAY" "$TOTAL" "$AGY" "$CLI" "$CCUSAGE_STATUS" "$CCUSAGE_TOKENS" "$CCUSAGE_COST_USD" "$CCUSAGE_REQUESTS"
