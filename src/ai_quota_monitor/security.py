from __future__ import annotations

import os
import stat
from pathlib import Path


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    try:
        with open(tmp, "wb") as fh:
            fh.write(content.encode("utf-8"))
            fh.flush()
            os.fsync(fh.fileno())
        tmp.rename(path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
    restrict(path)


def restrict(path: Path) -> None:
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600


def ensure_dirs(*paths: Path) -> None:
    for p in paths:
        p.mkdir(parents=True, exist_ok=True)
        p.chmod(stat.S_IRWXU)  # 0700
