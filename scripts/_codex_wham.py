#!/usr/bin/env python3
"""Uso REAL de Codex desde el endpoint oficial que alimenta
chatgpt.com/codex/cloud/settings/analytics:  GET /backend-api/wham/usage.
Refleja el límite agéntico COMPARTIDO (Codex CLI + Codex Cloud), no solo el CLI.

Lee el token de ~/.codex/auth.json (único punto que toca credenciales). Imprime SOLO un
JSON saneado (sin token, sin PII, sin texto). Exit 0 + JSON si hay dato; exit 1 si falla
(para que el helper caiga al fallback de rollouts).
"""
from __future__ import annotations

import base64
import json
import ssl
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

AUTH = Path.home() / ".codex" / "auth.json"
URL = "https://chatgpt.com/backend-api/wham/usage"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


def _fail() -> None:
    sys.exit(1)


def main() -> None:
    try:
        data = json.loads(AUTH.read_text())
    except (OSError, ValueError):
        _fail()
    tok_obj = data.get("tokens", {}) if isinstance(data.get("tokens"), dict) else {}
    token = tok_obj.get("access_token") or data.get("access_token")
    account_id = tok_obj.get("account_id") or data.get("account_id")
    if not token:
        _fail()
    if not account_id:
        try:
            p = token.split(".")[1]
            p += "=" * (-len(p) % 4)
            claims = json.loads(base64.urlsafe_b64decode(p))
            account_id = claims.get("https://api.openai.com/auth", {}).get("chatgpt_account_id")
        except Exception:
            account_id = None

    headers = {"Authorization": f"Bearer {token}", "User-Agent": UA, "Accept": "application/json"}
    if account_id:
        headers["chatgpt-account-id"] = account_id

    try:
        req = urllib.request.Request(URL, headers=headers)
        with urllib.request.urlopen(req, timeout=6, context=ssl.create_default_context()) as r:
            j = json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, ValueError, OSError):
        _fail()

    rl = j.get("rate_limit") or {}
    pw = rl.get("primary_window") or {}
    sw = rl.get("secondary_window") or {}
    if pw.get("used_percent") is None and sw.get("used_percent") is None:
        _fail()

    bal = (j.get("credits") or {}).get("balance")
    try:
        bal = round(float(bal), 2) if bal is not None else None
    except (TypeError, ValueError):
        bal = None

    def window(w: dict) -> dict:
        # La duración es la que identifica la ventana: según el plan, primary_window
        # puede ser la de 5h (300 min) o la semanal (10080 min). Sin este dato, el
        # consumidor solo puede adivinar por posición, y adivina mal.
        secs = w.get("limit_window_seconds")
        try:
            minutes = int(secs) // 60 if secs else None
        except (TypeError, ValueError):
            minutes = None
        return {
            "used_percent": w.get("used_percent"),
            "reset_at": w.get("reset_at"),
            "window_minutes": minutes,
        }

    out = {
        "source": "wham",
        "snapshot_ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "plan_type": j.get("plan_type"),
        "primary": window(pw),
        "secondary": window(sw),
        "credits_balance": bal,
    }
    print(json.dumps(out))


if __name__ == "__main__":
    main()
