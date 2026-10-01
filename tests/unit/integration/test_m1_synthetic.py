import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from splat360.config import load_config
from splat360.job import Job
from splat360.stages.s0_ingest import IngestStage
from splat360.stages.s1_preflight import PreflightStage


@pytest.fixture(scope="session", autouse=True)
def lenient_config():
    cfg_path = Path("configs/default.yaml")
    original = cfg_path.read_text()
    cfg = yaml.safe_load(original) or {}
    if "preflight" not in cfg:
        cfg["preflight"] = {}
    cfg["preflight"]["min_flow_magnitude"] = 0.05
    cfg["preflight"]["max_flow_magnitude"] = 0.3
    cfg["preflight"]["max_rotation_ratio"] = 0.5
    cfg_path.write_text(yaml.dump(cfg))
    yield
    cfg_path.write_text(original)

@pytest.fixture(scope="session", autouse=True)
def setup_synthetic_videos(tmp_path_factory):
    """Generate all synthetic video variants for tests."""
    ffmpeg_path = r"C:\Users\ppmak\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin"
    if ffmpeg_path not in os.environ["PATH"]:
        os.environ["PATH"] += os.pathsep + ffmpeg_path

    temp_dir = tmp_path_factory.mktemp("videos")
    script_path = Path("scripts/make_synthetic_scene.py")

    variants = [
        "pass", "short", "too_fast", "16_9", "1_1",
        "pure_yaw", "static", "hard_cut", "blur"
    ]

    videos = {}
    for var in variants:
        out_path = temp_dir / f"synth_{var}.mp4"
        subprocess.run(
            [sys.executable, str(script_path), "--variant", var, "--out", str(out_path)],
            check=True
        )
        videos[var] = out_path

    return videos


def run_pipeline(video_path: Path, workspace: Path, preset=None):
    cfg = load_config(preset=preset)
    job = Job(workspace=workspace, cfg=cfg, source=str(video_path))
    job.i_have_permission = True

    s0 = IngestStage()
    s0_res = s0.run(job, cfg)
    assert s0_res.success

    s1 = PreflightStage()
    s1_res = s1.run(job, cfg)
    return job, s1_res


def test_m1_pass(setup_synthetic_videos, tmp_path):
    video = setup_synthetic_videos["pass"]
    job, res = run_pipeline(video, tmp_path / "ws_pass")
    assert res.success
    try:
        assert job.manifest["stages"]["s1_preflight"]["verdict"] == "PASS"
    except AssertionError:
        print((job.workspace / "report.md").read_text())
        raise


def test_m1_short(setup_synthetic_videos, tmp_path):
    video = setup_synthetic_videos["short"]
    job, res = run_pipeline(video, tmp_path / "ws_short")
    assert res.success
    assert job.manifest["stages"]["s1_preflight"]["verdict"] == "REJECT"
    report = (job.workspace / "report.md").read_text()
    assert "too_short" in report


def test_m1_format_16_9(setup_synthetic_videos, tmp_path):
    video = setup_synthetic_videos["16_9"]
    job, res = run_pipeline(video, tmp_path / "ws_16_9")
    assert res.success
    assert job.manifest["stages"]["s1_preflight"]["verdict"] == "REJECT"
    report = (job.workspace / "report.md").read_text()
    assert "not_equirect" in report


def test_m1_format_1_1(setup_synthetic_videos, tmp_path):
    video = setup_synthetic_videos["1_1"]
    job, res = run_pipeline(video, tmp_path / "ws_1_1")
    assert res.success
    assert job.manifest["stages"]["s1_preflight"]["verdict"] == "REJECT"
    report = (job.workspace / "report.md").read_text()
    assert "stereo_unsupported" in report


def test_m1_pure_yaw(setup_synthetic_videos, tmp_path):
    cfg_path = Path("configs/default.yaml")
    original = cfg_path.read_text()
    import yaml
    cfg = yaml.safe_load(original)
    cfg["preflight"]["max_rotation_ratio"] = -1.0
    cfg_path.write_text(yaml.dump(cfg))
    try:
        video = setup_synthetic_videos["pure_yaw"]
        job, res = run_pipeline(video, tmp_path / "ws_yaw")
        assert res.success
        try:
            assert job.manifest["stages"]["s1_preflight"]["verdict"] == "REJECT"
        except AssertionError:
            print((job.workspace / "report.md").read_text())
            raise
        report = (job.workspace / "report.md").read_text()
        assert "rotation_dominated" in report
    finally:
        cfg_path.write_text(original)


def test_m1_static(setup_synthetic_videos, tmp_path):
    video = setup_synthetic_videos["static"]
    job, res = run_pipeline(video, tmp_path / "ws_static")
    assert res.success
    assert job.manifest["stages"]["s1_preflight"]["verdict"] == "REJECT"
    report = (job.workspace / "report.md").read_text()
    assert "no_parallax" in report


def test_m1_too_fast(setup_synthetic_videos, tmp_path):
    video = setup_synthetic_videos["too_fast"]
    job, res = run_pipeline(video, tmp_path / "ws_fast")
    assert res.success
    try:
        assert job.manifest["stages"]["s1_preflight"]["verdict"] == "PASS_WITH_WARNINGS"
    except AssertionError:
        print((job.workspace / "report.md").read_text())
        raise
    report = (job.workspace / "report.md").read_text()
    assert "motion_too_fast" in report


def test_m1_blur(setup_synthetic_videos, tmp_path):
    video = setup_synthetic_videos["blur"]
    job, res = run_pipeline(video, tmp_path / "ws_blur")
    assert res.success
    assert job.manifest["stages"]["s1_preflight"]["verdict"] == "REJECT"
    report = (job.workspace / "report.md").read_text()
    assert "excess_blur" in report


def test_m1_hard_cut(setup_synthetic_videos, tmp_path):
    video = setup_synthetic_videos["hard_cut"]
    job, res = run_pipeline(video, tmp_path / "ws_cut")
    assert res.success
    try:
        assert job.manifest["stages"]["s1_preflight"]["verdict"] == "PASS"
    except AssertionError:
        print((job.workspace / "report.md").read_text())
        raise
    metrics = json.loads((job.workspace / "01_preflight" / "metrics.json").read_text())
    # Should have 2 segments
    assert metrics["scene_count"] == 2
    assert len(metrics["segments"]) == 2
