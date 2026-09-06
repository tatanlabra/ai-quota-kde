"""Geometry regression in real Qt, using synthetic long labels and cache notes.

falsified_by: 2026-09-06, extracted commit 1a7c8d5: popup at 612 logical px
extended beyond its viewport; tooltip at 360 px overflowed tiles and header.
Both return exit 1 with layout_probe.py; the repaired views return 0.
The September 6 follow-up also checks five clickable provider selectors, icon
containment inside the ring aperture, and metric fonts at least 10 pt with an
11 pt desktop font. Fifteen surface/width/scale combinations are covered.
This checks geometry and interaction, not actual Plasma popup placement,
translations, contrast perception, or human visual acceptance.
"""

import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "plasmoid/org.tatan.aiquota/contents/ui"
PROBE = ROOT / "tests/qml/layout_probe.py"


@pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None,
    reason="Native geometry test requires PySide6 and Plasma QML modules",
)
@pytest.mark.parametrize("scale", ["1", "1.25", "2"])
@pytest.mark.parametrize(
    ("surface", "width"),
    [
        ("popup", 528),
        ("popup", 792),
        ("tooltip", 360),
        ("tooltip", 572),
        ("compact", 216),
    ],
)
def test_text_stays_within_its_column_and_viewport(surface, width, scale):
    env = dict(
        os.environ,
        QT_QPA_PLATFORM="offscreen",
        QT_QUICK_BACKEND="software",
        QT_SCALE_FACTOR=scale,
    )
    run = subprocess.run(
        [sys.executable, str(PROBE), str(UI), surface, str(width)],
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    result = json.loads(run.stdout)
    if surface == "popup":
        assert result["selected_visits"] == [
            "claude",
            "codex",
            "gemini",
            "copilot",
            "deepseek",
        ], result
        assert result["text_count"] >= 25, result
    elif surface == "tooltip":
        assert result["text_count"] >= 12, result
    expected_icons = 1 if surface == "tooltip" else 5
    assert len(result["icons"]) == expected_icons, result
    for icon in result["icons"]:
        assert icon["source"] and icon["width"] > 0, icon
        assert (
            math.hypot(icon["width"], icon["height"]) / 2 <= icon["aperture"] + 0.01
        ), icon
    if surface != "compact":
        assert result["metric_fonts"] and min(result["metric_fonts"]) >= 10, result
    assert result["overflow"] == [], result
    for error in ("TypeError", "ReferenceError", "Binding loop", "recursive rearrange"):
        assert error not in run.stderr, run.stderr
