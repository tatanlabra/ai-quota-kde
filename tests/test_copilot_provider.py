from __future__ import annotations

import json

from ai_quota_monitor.providers import copilot


def _event(timestamp: str, used: int = 128) -> str:
    return json.dumps(
        {
            "type": "model.model_call_success",
            "timestamp": timestamp,
            "data": {
                "quotaSnapshots": {
                    "chat": {
                        "entitlementRequests": 200,
                        "usedRequests": used,
                        "remainingPercentage": 100 - used // 2,
                        "resetDate": "2026-09-01T00:00:00Z",
                    }
                }
            },
        }
    )


def test_latest_chat_snapshot_becomes_observed_quota(tmp_path, monkeypatch):
    events = tmp_path / "session" / "events.jsonl"
    events.parent.mkdir()
    events.write_text(
        _event("2026-08-28T23:00:00Z", used=128)
        + "\nnot-json\n"
        + _event("2026-08-28T22:00:00Z", used=100)
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(copilot, "COPILOT_SESSIONS_DIR", tmp_path)

    provider = copilot.collect({})

    assert provider.status == "ok"
    window = provider.windows[0]
    assert window.id == "copilot_chat"
    assert window.used == 128
    assert window.limit == 200
    assert window.percent == 0.64
    assert window.reset_at == "2026-09-01T00:00:00Z"
    assert window.confidence == "local_observed"


def test_missing_snapshot_is_not_reported_as_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(copilot, "COPILOT_SESSIONS_DIR", tmp_path)

    provider = copilot.collect({})

    assert provider.status == "degraded"
    assert provider.windows[0].percent is None
    assert provider.windows[0].limit is None
    assert provider.windows[0].confidence == "unknown"


def test_invalid_entitlement_is_unknown(tmp_path, monkeypatch):
    events = tmp_path / "session" / "events.jsonl"
    events.parent.mkdir()
    events.write_text(
        json.dumps(
            {
                "type": "model.model_call_success",
                "timestamp": "2026-08-28T23:00:00Z",
                "data": {
                    "quotaSnapshots": {
                        "chat": {
                            "entitlementRequests": 0,
                            "usedRequests": 0,
                        }
                    }
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(copilot, "COPILOT_SESSIONS_DIR", tmp_path)

    provider = copilot.collect({})

    assert provider.status == "degraded"
    assert provider.windows[0].limit is None
