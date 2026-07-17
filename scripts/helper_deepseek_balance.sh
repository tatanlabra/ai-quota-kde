#!/usr/bin/env bash
# Consulta saldo DeepSeek via /user/balance. Emite JSON saneado, nunca la key.
set -euo pipefail

SECRET_ENV="${DEEPSEEK_ENV_FILE:-$HOME/.config/ai-quota-monitor/secrets.env}"

emit() { printf '%s\n' "$1"; exit 0; }

if [[ ! -r "$SECRET_ENV" ]]; then
  emit '{"error":"secret_env_not_found"}'
fi

KEY=$(python3 - "$SECRET_ENV" <<'PY' 2>/dev/null || true
from pathlib import Path
import sys

path = Path(sys.argv[1])
for raw in path.read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    if key.strip() == "DEEPSEEK_API_KEY":
        value = value.strip().strip("'\"")
        if value:
            print(value, end="")
        break
PY
)

if [[ -z "${KEY:-}" ]]; then
  emit '{"error":"deepseek_key_not_found"}'
fi

RESP=$(curl \
  --silent \
  --max-time 8 \
  --fail-with-body \
  "https://api.deepseek.com/user/balance" \
  -H "Authorization: Bearer $KEY" \
  -H "Accept: application/json" \
  2>/dev/null) || emit '{"error":"api_request_failed"}'

printf '%s' "$RESP" | python3 -c '
import json
from datetime import datetime, timezone
import sys

data = json.load(sys.stdin)
infos = []
for item in data.get("balance_infos", []) or []:
    if not isinstance(item, dict):
        continue
    infos.append({
        "currency": str(item.get("currency", "")),
        "total_balance": str(item.get("total_balance", "0")),
        "granted_balance": str(item.get("granted_balance", "0")),
        "topped_up_balance": str(item.get("topped_up_balance", "0")),
    })
payload = {
    "source": "deepseek_api",
    "checked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "is_available": bool(data.get("is_available")),
    "balance_infos": infos,
}
print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
' 2>/dev/null || emit '{"error":"invalid_api_json"}'
