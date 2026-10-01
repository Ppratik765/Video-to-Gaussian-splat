"""
Tests for caching: skip-when-unchanged, rerun-when-config-changes, rerun-with-force.

Uses a minimal concrete Stage subclass to exercise the base class logic.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from splat360.config import PipelineConfig, load_config
from splat360.errors import StageFailed
from splat360.job import Job
from splat360.stages.base import Stage, StageResult
from splat360.utils.hashing import hash_dict

# ---------------------------------------------------------------------------
# Minimal test stage
# ---------------------------------------------------------------------------


class _CountingStage(Stage):
    """A stage that counts how many times ``run()`` is called."""

    def __init__(self) -> None:
        self.run_count = 0
        self._fp_extra = ""

    @property
    def name(self) -> str:
        return "s0_ingest"  # use a real stage name to match manifest

    def run(self, job: Job, cfg: PipelineConfig) -> StageResult:
        self.run_count += 1
        # Write a marker file so outputs "exist"
        (job.stage_dir(self.name) / "done.txt").write_text("ok")
        return StageResult(success=True, message="counted")

    def fingerprint(self, job: Job, cfg: PipelineConfig) -> str:
        return hash_dict({"key": "value", "extra": self._fp_extra})


class _FailingStage(Stage):
    @property
    def name(self) -> str:
        return "s0_ingest"

    def run(self, job: Job, cfg: PipelineConfig) -> StageResult:
        raise RuntimeError("intentional failure")

    def fingerprint(self, job: Job, cfg: PipelineConfig) -> str:
        return hash_dict({"fail": True})


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.fixture
def cfg() -> PipelineConfig:
    return load_config()


class TestCachingSkipUnchanged:
    def test_skip_when_unchanged(self, tmp_path: Path, cfg: PipelineConfig) -> None:
        ws = tmp_path / "job"
        job = Job(workspace=ws, cfg=cfg, source="test.mp4")

        stage = _CountingStage()

        # First run — should execute
        result1 = stage.execute(job, cfg)
        assert stage.run_count == 1
        assert not result1.skipped

        # Second run — same fingerprint, should skip
        result2 = stage.execute(job, cfg)
        assert stage.run_count == 1  # NOT incremented
        assert result2.skipped

    def test_rerun_when_config_changes(self, tmp_path: Path, cfg: PipelineConfig) -> None:
        ws = tmp_path / "job"
        job = Job(workspace=ws, cfg=cfg, source="test.mp4")

        stage = _CountingStage()

        # First run
        stage.execute(job, cfg)
        assert stage.run_count == 1

        # Change the fingerprint (simulates config change)
        stage._fp_extra = "changed"
        result = stage.execute(job, cfg)
        assert stage.run_count == 2
        assert not result.skipped

    def test_rerun_with_force(self, tmp_path: Path) -> None:
        cfg_normal = load_config()
        cfg_force = load_config(force=True)

        ws = tmp_path / "job"
        job = Job(workspace=ws, cfg=cfg_normal, source="test.mp4")

        stage = _CountingStage()

        # First run
        stage.execute(job, cfg_normal)
        assert stage.run_count == 1

        # Force re-run even though fingerprint is unchanged
        result = stage.execute(job, cfg_force)
        assert stage.run_count == 2
        assert not result.skipped


class TestFailureRecording:
    def test_failure_recorded_in_manifest(self, tmp_path: Path, cfg: PipelineConfig) -> None:
        ws = tmp_path / "job"
        job = Job(workspace=ws, cfg=cfg, source="test.mp4")

        stage = _FailingStage()

        with pytest.raises(StageFailed, match="intentional failure"):
            stage.execute(job, cfg)

        assert job.stage_status("s0_ingest") == "failed"
        manifest = job.manifest
        assert "intentional failure" in manifest["stages"]["s0_ingest"]["error"]
