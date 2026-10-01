"""
Job, workspace paths, manifest read/write, and fingerprint storage.

A *Job* represents a single reconstruction attempt for one video segment.
Its state is persisted in ``manifest.json`` inside the workspace directory.

Responsibility: job.py
Milestone: M0
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from splat360.config import PipelineConfig, config_to_dict
from splat360.constants import (
    MANIFEST_FILENAME,
    STAGE_ORDER,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_RUNNING,
    STATUS_SKIPPED,
    VERSION,
    WORKSPACE_DIRS,
)
from splat360.utils.logging import get_logger
from splat360.utils.paths import atomic_json_write

log = get_logger("job")


# ---------------------------------------------------------------------------
# Manifest helpers
# ---------------------------------------------------------------------------


def _empty_stage_entry() -> dict[str, Any]:
    return {
        "status": STATUS_PENDING,
        "fingerprint": None,
        "started_at": None,
        "finished_at": None,
        "duration_s": None,
        "error": None,
    }


def _new_manifest(
    job_id: str, source: str, cfg: PipelineConfig
) -> dict[str, Any]:
    """Create a fresh manifest dict."""
    return {
        "job_id": job_id,
        "version": VERSION,
        "source": source,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "config_snapshot": config_to_dict(cfg),
        "stages": {name: _empty_stage_entry() for name in STAGE_ORDER},
    }


# ---------------------------------------------------------------------------
# Job class
# ---------------------------------------------------------------------------


class Job:
    """Represents a single pipeline run.

    Parameters
    ----------
    workspace:
        Root directory of this job (e.g. ``workspace/<job_id>``).
    cfg:
        The resolved pipeline config.
    source:
        The video URL or local path that created this job.
    job_id:
        Optional explicit ID.  Generated if omitted.
    """

    def __init__(
        self,
        workspace: Path,
        cfg: PipelineConfig,
        source: str = "",
        job_id: str | None = None,
    ) -> None:
        self.job_id = job_id or uuid.uuid4().hex[:12]
        self.workspace = Path(workspace)
        self.cfg = cfg
        self.source = source

        # Load or create manifest
        self._manifest_path = self.workspace / MANIFEST_FILENAME
        if self._manifest_path.is_file():
            self._manifest = self._read_manifest()
            log.info("Resumed job %s from %s", self.job_id, self._manifest_path)
        else:
            self.workspace.mkdir(parents=True, exist_ok=True)
            self._manifest = _new_manifest(self.job_id, source, cfg)
            self._write_manifest()
            log.info("Created new job %s at %s", self.job_id, self.workspace)

    # ------------------------------------------------------------------
    # Manifest I/O
    # ------------------------------------------------------------------

    def _read_manifest(self) -> dict[str, Any]:
        with open(self._manifest_path, encoding="utf-8") as f:
            return json.load(f)  # type: ignore[no-any-return]

    def _write_manifest(self) -> None:
        atomic_json_write(self._manifest_path, self._manifest)

    @property
    def manifest(self) -> dict[str, Any]:
        """Return a *copy* of the current manifest."""
        return json.loads(json.dumps(self._manifest))  # type: ignore[no-any-return]

    # ------------------------------------------------------------------
    # Stage directories
    # ------------------------------------------------------------------

    def stage_dir(self, stage_name: str) -> Path:
        """Return (and create) the output directory for *stage_name*."""
        subdir = WORKSPACE_DIRS.get(stage_name, stage_name)
        p = self.workspace / subdir if subdir else self.workspace
        p.mkdir(parents=True, exist_ok=True)
        return p

    # ------------------------------------------------------------------
    # Stage lifecycle — called by stages/base.py
    # ------------------------------------------------------------------

    def stage_status(self, stage_name: str) -> str:
        """Return the current status string for *stage_name*."""
        entry = self._manifest["stages"].get(stage_name)
        if entry is None:
            return STATUS_PENDING
        status = entry.get("status", STATUS_PENDING)
        return str(status)

    def stage_fingerprint(self, stage_name: str) -> str | None:
        """Return the stored fingerprint for *stage_name*, or None."""
        entry = self._manifest["stages"].get(stage_name)
        if entry is None:
            return None
        fp = entry.get("fingerprint")
        return str(fp) if fp is not None else None

    def mark_running(self, stage_name: str) -> None:
        """Mark a stage as currently running."""
        entry = self._manifest["stages"].setdefault(stage_name, _empty_stage_entry())
        entry["status"] = STATUS_RUNNING
        entry["started_at"] = datetime.now(timezone.utc).isoformat()
        entry["error"] = None
        self._write_manifest()

    def mark_done(self, stage_name: str, fingerprint: str, duration_s: float) -> None:
        """Mark a stage as successfully completed."""
        entry = self._manifest["stages"].setdefault(stage_name, _empty_stage_entry())
        entry["status"] = STATUS_DONE
        entry["fingerprint"] = fingerprint
        entry["finished_at"] = datetime.now(timezone.utc).isoformat()
        entry["duration_s"] = round(duration_s, 3)
        entry["error"] = None
        self._write_manifest()

    def mark_failed(self, stage_name: str, error_msg: str) -> None:
        """Mark a stage as failed, recording the error message."""
        entry = self._manifest["stages"].setdefault(stage_name, _empty_stage_entry())
        entry["status"] = STATUS_FAILED
        entry["finished_at"] = datetime.now(timezone.utc).isoformat()
        entry["error"] = error_msg
        self._write_manifest()

    def mark_skipped(self, stage_name: str, reason: str = "unchanged") -> None:
        """Mark a stage as skipped (cache hit)."""
        entry = self._manifest["stages"].setdefault(stage_name, _empty_stage_entry())
        entry["status"] = STATUS_SKIPPED
        entry["error"] = None
        # Keep existing fingerprint and timing
        self._write_manifest()

    def update_manifest_stage(self, stage_name: str, data: dict[str, Any]) -> None:
        """Update arbitrary data for a stage in the manifest."""
        entry = self._manifest["stages"].setdefault(stage_name, _empty_stage_entry())
        entry.update(data)
        self._write_manifest()
