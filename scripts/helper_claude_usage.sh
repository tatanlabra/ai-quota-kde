#!/usr/bin/env bash
# Lee accessToken de .credentials.json y llama api.anthropic.com/api/oauth/usage.
# Adjunta además el bloque activo de `ccusage` (uso local de Claude Code) como fuente
# resiliente: si el token OAuth expira o la API falla, el conteo local sobrevive.
# Salida: JSON con {five_hour, seven_day, extra_usage?, ccusage?} — sin credenciales.
# Este script es el único que toca el archivo de credenciales de Claude.
set -euo pipefail

CREDS="$HOME/.claude/.credentials.json"

# ── OAuth usage (porcentaje oficial 5h/7d) ──────────────────────────────────
# El token OAuth tiene TTL ~8h y solo Claude Code lo refresca (usa el refreshToken).
# Aquí NO lo refrescamos (evitamos pelear con Claude Code por el archivo): si está
# expirado, emitimos token_expired y dejamos que ccusage + caché stale cubran el hueco.
OAUTH='{"error":"credentials_not_found"}'
if [[ -f "$CREDS" ]]; then
  # Imprime el accessToken solo si no está expirado; "EXPIRED" si venció; "" si falta.
  TOKEN=$(python3 -c "
import json, sys, time
try:
    d = json.load(open('$CREDS'))
    o = d['claudeAiOauth']
    tok = o.get('accessToken') or ''
    exp = o.get('expiresAt')
    if exp is not None:
        exp_s = exp / 1000 if exp > 1e12 else exp
        if time.time() >= exp_s - 60:   # margen de 60s
            print('EXPIRED', end=''); sys.exit(0)
    print(tok, end='')
except Exception:
    print('', end='')
    sys.exit(1)
" 2>/dev/null) || TOKEN=""

  if [[ "$TOKEN" == "EXPIRED" ]]; then
    OAUTH='{"error":"token_expired"}'
  elif [[ -z "$TOKEN" ]]; then
    OAUTH='{"error":"empty_token"}'
  else
    # Capturamos cuerpo + código HTTP para distinguir 429 (rate limit) de 401/403
    # (token rechazado) y de fallos de red. La usage endpoint limita agresivamente.
    RESP=$(curl --silent --max-time 6 -w $'\n%{http_code}' \
      "https://api.anthropic.com/api/oauth/usage" \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" \
      2>/dev/null) || RESP=$'\n000'
    CODE="${RESP##*$'\n'}"
    BODY="${RESP%$'\n'*}"
    case "$CODE" in
      200) OAUTH="$BODY" ;;
      429) OAUTH='{"error":"rate_limited"}' ;;
      401|403) OAUTH='{"error":"token_rejected"}' ;;
      *)   OAUTH='{"error":"api_request_failed"}' ;;
    esac
  fi
fi

# ── ccusage (uso local de Claude Code, siempre disponible offline) ──────────
CCUSAGE='null'
if command -v ccusage >/dev/null 2>&1; then
  CCUSAGE=$(timeout 10 ccusage blocks --json 2>/dev/null || echo 'null')
fi

# ── Fusión: OAuth + bloque activo de ccusage ────────────────────────────────
OAUTH_JSON="$OAUTH" CCUSAGE_JSON="$CCUSAGE" python3 <<'PY'
import json, os

def _load(s):
    try:
        return json.loads(s)
    except Exception:
        return None

oauth = _load(os.environ.get("OAUTH_JSON", ""))
out = oauth if isinstance(oauth, dict) else {"error": "oauth_invalid"}

cc = _load(os.environ.get("CCUSAGE_JSON", "null"))
if isinstance(cc, dict):
    blocks = cc.get("blocks") or []
    active = next((b for b in blocks if isinstance(b, dict) and b.get("isActive")), None)
    if active:
        tc = active.get("tokenCounts") or {}
        total = active.get("totalTokens")
        if total is None:
            total = sum(v for v in tc.values() if isinstance(v, (int, float)))
        proj = active.get("projection") or {}
        br = active.get("burnRate") or {}
        out["ccusage"] = {
            "total_tokens": total,
            "cost_usd": active.get("costUSD"),
            "reset_at": active.get("endTime"),
            "burn_per_min": br.get("tokensPerMinute"),
            "projection_cost": proj.get("totalCost"),
            "models": active.get("models") or [],
        }

print(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
PY
