from __future__ import annotations

import pytest

from ai_quota_monitor.providers import deepseek


@pytest.fixture(autouse=True)
def _isolated_deepseek_peak(tmp_path, monkeypatch):
    """Redirige el high-water-mark de DeepSeek a un archivo temporal para que los
    tests sean deterministas y no contaminen ~/.cache del usuario."""
    monkeypatch.setattr(deepseek, "PEAK_FILE", tmp_path / "deepseek_peak.json")
    monkeypatch.setattr(deepseek, "CACHE_DIR", tmp_path)
    yield
