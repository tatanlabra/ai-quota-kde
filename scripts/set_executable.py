#!/usr/bin/env python3
"""Establece permisos ejecutables en los helper scripts."""
import os, stat, pathlib
scripts = [
    pathlib.Path(__file__).parent / "helper_claude_usage.sh",
    pathlib.Path(__file__).parent / "helper_codex_usage.sh",
    pathlib.Path(__file__).parent / "helper_gemini_usage.sh",
    pathlib.Path(__file__).parent / "install-user.sh",
]
for s in scripts:
    if s.exists():
        s.stat()  # check exists
        mode = stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP
        os.chmod(s, mode)
        print(f"OK {s.name}")
    else:
        print(f"MISSING {s.name}")
