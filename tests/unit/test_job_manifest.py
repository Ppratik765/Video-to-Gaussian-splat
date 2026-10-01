"""
Tests for job.py: manifest creation, round-trip, stage lifecycle.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from splat360.config import PipelineConfig, load_config
from splat360.constants import STATUS_DONE, STATUS_FAILED, STATUS_PENDING, STATUS_RUNNING, STATUS_SKIPPED
from splat360.job import Job


@pytest.fixture
def cfg() -> PipelineConfig:
    return load_config()


class TestJobCreation:
    def test_new_job_creates_manifest(self, tmp_path: Path, cfg: PipelineConfig) -> None:
        ws = tmp_path / "test_job"
        job = Job(workspace=ws, cfg=cfg, source="test_video.mp4", job_id="test123")

        assert job.job_id == "test123"
        assert (ws / "manifest.json").is_file()

    def test_new_job_manifest_has_all_stages(self, tmp_path: Path, cfg: PipelineConfig) -> None:
        ws = tmp_path / "test_job"
        job = Job(workspace=ws, cfg=cfg, source="test.mp4")
        manifest = job.manifest

        assert "stages" in manifest
        for stage_name in manifest["stages"]:
            assert manifest["stages"][stage_name]["status"] == STATUS_PENDING

    def test_new_job_stores_config_snapshot(self, tmp_path: Path, cfg: PipelineConfig) -> None:
        ws = tmp_path / "test_job"
        job = Job(workspace=ws, cfg=cfg, source="test.mp4")
        manifest = job.manifest

        assert "config_snapshot" in manifest
        assert manifest["config_snapshot"]["version"] == cfg.version


class TestManifestRoundTrip:
    def test_manifest_survives_reload(self, tmp_path: Path, cfg: PipelineConfig) -> None:
        ws = tmp_path / "test_job"
        job1 = Job(workspace=ws, cfg=cfg, source="test.mp4", job_id="rt1")
        job1.mark_running("s0_ingest")
        job1.mark_done("s0_ingest", "fp_abc", 1.234)

        # Reload from disk
        job2 = Job(workspace=ws, cfg=cfg, source="test.mp4", job_id="rt1")
        assert job2.stage_status("s0_ingest") == STATUS_DONE
        assert job2.stage_fingerprint("s0_ingest") == "fp_abc"

    def test_manifest_json_is_valid(self, tmp_path: Path, cfg: PipelineConfig) -> None:
        ws = tmp_path / "test_job"
        Job(workspace=ws, cfg=cfg, source="test.mp4", job_id="json_test")

        raw = (ws / "manifest.json").read_text(encoding="utf-8")
        data = json.loads(raw)
        assert data["job_id"] == "json_test"


class TestStageLifecycle:
    def test_mark_running(self, tmp_path: Path, cfg: PipelineConfig) -> None:
        ws = tmp_path / "test_job"
        job = Job(workspace=ws, cfg=cfg, source="test.mp4")
        job.mark_running("s0_ingest")
        assert job.stage_status("s0_ingest") == STATUS_RUNNING

    def test_mark_done(self, tmp_path: Path, cfg: PipelineConfig) -> None:
        ws = tmp_path / "test_job"
        job = Job(workspace=ws, cfg=cfg, source="test.mp4")
        job.mark_done("s0_ingest", "fp_123", 2.5)
        assert job.stage_status("s0_ingest") == STATUS_DONE
        assert job.stage_fingerprint("s0_ingest") == "fp_123"

    def test_mark_failed(self, tmp_path: Path, cfg: PipelineConfig) -> None:
        ws = tmp_path / "test_job"
        job = Job(workspace=ws, cfg=cfg, source="test.mp4")
        job.mark_failed("s0_ingest", "something broke")
        assert job.stage_status("s0_ingest") == STATUS_FAILED
        manifest = job.manifest
        assert manifest["stages"]["s0_ingest"]["error"] == "something broke"

    def test_mark_skipped(self, tmp_path: Path, cfg: PipelineConfig) -> None:
        ws = tmp_path / "test_job"
        job = Job(workspace=ws, cfg=cfg, source="test.mp4")
        job.mark_skipped("s0_ingest", "unchanged")
        assert job.stage_status("s0_ingest") == STATUS_SKIPPED

    def test_stage_dir_created(self, tmp_path: Path, cfg: PipelineConfig) -> None:
        ws = tmp_path / "test_job"
        job = Job(workspace=ws, cfg=cfg, source="test.mp4")
        d = job.stage_dir("s0_ingest")
        assert d.is_dir()
        assert d.name == "00_source"