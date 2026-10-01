"""
Workspace path helpers and Drive-safe atomic writes.

Centralises all path logic so that no other module builds workspace paths
by string concatenation.

Responsibility: utils/paths.py
Milestone: M0
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from splat360.constants import MANIFEST_FILENAME, WORKSPACE_DIRS


def workspace_root(base: Path, job_id: str) -> Path:
    """Return ``<base>/workspace/<job_id>``."""
    return base / "workspace" / job_id


def stage_dir(ws: Path, stage_name: str) -> Path:
    """Return the output directory for *stage_name* inside workspace *ws*.

    Creates the directory if it does not exist.
    """
    subdir = WORKSPACE_DIRS.get(stage_name, stage_name)
    if subdir:
        p = ws / subdir
    else:
        p = ws
    p.mkdir(parents=True, exist_ok=True)
    return p


def manifest_path(ws: Path) -> Path:
    """Return the path to ``manifest.json`` inside *ws*."""
    return ws / MANIFEST_FILENAME


def atomic_json_write(path: Path, data: Any) -> None:
    """Write *data* as JSON to *path* atomically.

    Writes to a temporary file in the same directory, then renames.  This
    prevents partial writes if the process is killed (important when the
    workspace is on Google Drive).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=str(path.parent), suffix=".tmp", prefix=".manifest_"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
            f.write("\n")
        # On Windows, target must not exist for os.replace to work — it does.
        os.replace(tmp, str(path))
    except BaseException:
        # Clean up the temp file on failure.
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
