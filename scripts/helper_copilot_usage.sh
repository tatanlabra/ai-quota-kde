#!/usr/bin/env bash
# Cuota de Copilot desde GitHub: GET /copilot_internal/user a traves de `gh api`.
#
# Por que esta fuente: hasta Copilot CLI 1.0.44 cada model.model_call_success traia
# quotaSnapshots en los eventos locales; desde la 1.0.81 ya no existe ese evento
# (medido el 2026-10-04 sobre 40 sesiones), y lo que queda --session.shutdown con
# totalPremiumRequests-- no trae ni cupo ni fecha de reinicio. Este endpoint es el que
# consultan los propios clientes de Copilot: interno y sin documentar, asi que si cambia
# de forma el script responde con un error y el colector conserva el ultimo valor bueno.
#
# gh guarda el token en el keyring; este script no lo lee ni lo imprime. La salida es
# solo la cuota (ni login, ni id, ni organizaciones). Exit 0 siempre.
# Esquema: {source, plan, reset_at, chat{entitlement,remaining,percent_remaining,unlimited},
#           premium_interactions{...}}
set -eu

emit() { printf '%s\n' "$1"; exit 0; }

command -v gh >/dev/null 2>&1 || emit '{"error":"gh_not_installed"}'
command -v jq >/dev/null 2>&1 || emit '{"error":"no_jq"}'

raw=$(timeout 10 gh api /copilot_internal/user 2>/dev/null) || emit '{"error":"gh_api_failed"}'

printf '%s' "$raw" | jq -ce '
  def quota: if type == "object"
    then {entitlement, remaining, percent_remaining, unlimited}
    else null end;
  {
    source: "github copilot_internal/user",
    plan: (.copilot_plan // null),
    reset_at: (.quota_reset_date_utc // null),
    chat: (.quota_snapshots.chat | quota),
    premium_interactions: (.quota_snapshots.premium_interactions | quota)
  }
' 2>/dev/null || emit '{"error":"unexpected_payload"}'
