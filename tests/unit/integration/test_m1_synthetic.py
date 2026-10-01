import pytest
import numpy as np
from pathlib import Path
from splat360.stages.s1_preflight import PreflightStage
from splat360.stages.s0_ingest import IngestStage
from splat360.job import Job
from splat360.config import PipelineConfig

@pytest.fixture
def cfg():
    return PipelineConfig()

@pytest.fixture
def mock_job(tmp_path, cfg):
    job = Job(workspace=tmp_path / "workspace", cfg=cfg, source="https://mock.com/video")
    job.source_url_or_path = "https://mock.com/video"
    job.i_have_permission = True
    return job

def test_s0_ingest(mock_job, cfg, monkeypatch):
    import splat360.stages.s0_ingest
    monkeypatch.setattr(splat360.stages.s0_ingest, "probe_video", lambda p: {"resolution": [3840, 1920], "fps": 30.0, "codec": "vp9", "duration": 10.0, "is_spherical_metadata": True})
    
    s0 = IngestStage()
    res = s0.run(mock_job, cfg)
    assert res.success
    
    # source.json should exist
    source_json = mock_job.workspace / "00_source" / "source.json"
    assert source_json.exists()

def test_s1_preflight_format_reject(mock_job, cfg, monkeypatch):
    import splat360.stages.s0_ingest
    monkeypatch.setattr(splat360.stages.s0_ingest, "probe_video", lambda p: {"resolution": [3840, 1920], "fps": 30.0, "codec": "vp9", "duration": 10.0, "is_spherical_metadata": True})
    
    s0 = IngestStage()
    s0.run(mock_job, cfg)
    
    import json
    source_json = mock_job.workspace / "00_source" / "source.json"
    data = json.loads(source_json.read_text())
    # Override resolution to 16:9 flat video
    data["resolution"] = [1920, 1080]
    source_json.write_text(json.dumps(data))
    
    s1 = PreflightStage()
    res = s1.run(mock_job, cfg)
    # The stage returns success=True but verdict=REJECT, cleanly exiting
    assert res.success
    
    metrics_path = mock_job.workspace / "01_preflight" / "metrics.json"
    metrics = json.loads(metrics_path.read_text())
    assert metrics["format_valid"] is False
    
    # Check the report
    report_path = mock_job.workspace / "report.md"
    assert "not_equirect" in report_path.read_text()
    
def test_s1_preflight_stereo_reject(mock_job, cfg, monkeypatch):
    import splat360.stages.s0_ingest
    monkeypatch.setattr(splat360.stages.s0_ingest, "probe_video", lambda p: {"resolution": [3840, 1920], "fps": 30.0, "codec": "vp9", "duration": 10.0, "is_spherical_metadata": True})
    
    s0 = IngestStage()
    s0.run(mock_job, cfg)
    
    import json
    source_json = mock_job.workspace / "00_source" / "source.json"
    data = json.loads(source_json.read_text())
    # Override resolution to 1:1 stereo
    data["resolution"] = [2160, 2160]
    source_json.write_text(json.dumps(data))
    
    s1 = PreflightStage()
    res = s1.run(mock_job, cfg)
    
    report_path = mock_job.workspace / "report.md"
    assert "stereo_unsupported" in report_path.read_text()
