"""El helper de Claude respeta el retry-after del endpoint de uso.

El endpoint limita por token y cada 429 trae retry-after de ~1 h (medido el 2026-10-03:
3153 s). Consultar antes solo gasta la cuota. Sin red: `curl` y `ccusage` son falsos y
cada invocación de `curl` queda anotada.
"""
from __future__ import annotations

import json
import stat
import subprocess
import time
from pathlib import Path

import pytest

HELPER = Path(__file__).resolve().parents[1] / "scripts" / "helper_claude_usage.sh"

FAKE_CURL = """#!/bin/sh
echo call >> "$CURL_LOG"
printf '%s\\n%s' "$FAKE_BODY" "$FAKE_TAIL"
"""


@pytest.fixture
def sandbox(tmp_path):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    cache = home / ".cache" / "ai-quota-monitor"
    cache.mkdir(parents=True)
    expires = int((time.time() + 3600) * 1000)
    (home / ".claude" / ".credentials.json").write_text(
        json.dumps({"claudeAiOauth": {"accessToken": "token-falso-de-prueba", "expiresAt": expires}})
    )
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for name, body in (("curl", FAKE_CURL), ("ccusage", "#!/bin/sh\necho null\n")):
        f = bindir / name
        f.write_text(body)
        f.chmod(0o755)
    log = tmp_path / "curl.log"
    log.touch()
    return {"home": home, "cache": cache, "bin": bindir, "log": log}


def _run(sb, body, tail, extra_env=None):
    env = {
        "HOME": str(sb["home"]),
        "PATH": f"{sb['bin']}:/usr/bin:/bin",
        "CURL_LOG": str(sb["log"]),
        "FAKE_BODY": body,
        "FAKE_TAIL": tail,
        **(extra_env or {}),
    }
    proc = subprocess.run([str(HELPER)], capture_output=True, text=True, env=env, timeout=30, check=True)
    return json.loads(proc.stdout)


def _curl_calls(sb):
    return len(sb["log"].read_text().splitlines())


def test_429_saves_retry_after_and_next_run_does_not_call_curl(sandbox):
    """falsified_by: 2026-10-03, quitando la rama `NOW < UNTIL` curl se llama dos veces."""
    before = int(time.time())
    out = _run(sandbox, '{"error":{"type":"rate_limit_error"}}', "429 120")
    assert out["error"] == "rate_limited"
    assert before + 120 <= out["retry_after_until"] <= int(time.time()) + 120
    backoff = sandbox["cache"] / "claude-oauth-backoff"
    assert stat.S_IMODE(backoff.stat().st_mode) == 0o600
    assert _curl_calls(sandbox) == 1

    again = _run(sandbox, "{}", "200 ")
    assert again == {"error": "rate_limited", "retry_after_until": out["retry_after_until"]}
    assert _curl_calls(sandbox) == 1
    assert not [p for p in sandbox["cache"].iterdir() if p.name.startswith(".claude-oauth-backoff.")]


def test_missing_retry_after_waits_one_hour(sandbox):
    before = int(time.time())
    out = _run(sandbox, "{}", "429 ")
    assert before + 3600 <= out["retry_after_until"] <= int(time.time()) + 3600


def test_expired_backoff_calls_again_and_200_clears_it(sandbox):
    backoff = sandbox["cache"] / "claude-oauth-backoff"
    backoff.write_text(f"{int(time.time()) - 5}\n")
    body = '{"five_hour":{"utilization":5.0,"resets_at":"2026-10-03T18:30:00Z"}}'
    out = _run(sandbox, body, "200 ")
    assert out["five_hour"]["utilization"] == 5.0
    assert _curl_calls(sandbox) == 1
    assert not backoff.exists()


def test_skip_flag_never_calls_curl(sandbox):
    out = _run(sandbox, "{}", "200 ", {"AIQ_CLAUDE_SKIP_OAUTH": "1"})
    assert out == {"error": "skipped"}
    assert _curl_calls(sandbox) == 0


def test_helper_does_not_leak_the_token(sandbox):
    out = _run(sandbox, '{"error":{"type":"rate_limit_error"}}', "429 60")
    assert "token-falso-de-prueba" not in json.dumps(out)
    assert "token-falso-de-prueba" not in (sandbox["cache"] / "claude-oauth-backoff").read_text()
