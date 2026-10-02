"""
Integration tests for M1: S0 ingest + S1 preflight.

Design rules:
- Tests use DEFAULT PipelineConfig thresholds — NO lenient_config fixtures,
  NO threshold overrides per test (except the fingerprint-change test, which
  explicitly tests that a threshold change is detected).
- Configs are built fully in-memory (PipelineConfig(**overrides)); tracked
  files (configs/default.yaml) are NEVER read or written by tests.
- ffmpeg is required for synthetic video generation.  If absent, all
  synthetic-video tests are skipped with a clear message.
- Tests assert on actual metric values (not just verdict strings) where
  the spec calls for it.

Test matrix
-----------
a. test_m1_pass         — translation clip → PASS; rotation_ratio < threshold
b. test_m1_short        — 1-s clip → REJECT (too_short)
c. test_m1_format_16_9  — 16:9 frame → REJECT (not_equirect)
d. test_m1_format_1_1   — 1:1 frame → REJECT (stereo_unsupported)
e. test_m1_pure_yaw     — pure rotation → REJECT (rotation_dominated);
                          rotation_ratio of yaw clip > threshold
f. test_m1_static       — static camera → REJECT (no_parallax)
g. test_m1_too_fast     — very fast motion → PASS_WITH_WARNINGS (motion_too_fast)
h. test_m1_blur         — blurred frames → REJECT (excess_blur)
i. test_m1_hard_cut     — 12-s clip with hard cut at 6 s → PASS + 2 segments
j. test_m1_scene_timestamps — user timestamps override auto-detect; boundaries asserted
k. test_m1_fingerprint  — fingerprint changes when a threshold changes; stable otherwise
l. test_metric_assertions — pass clip rotation_ratio < threshold < yaw clip rotation_ratio;
                            static residual ~ 0
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from splat360.config import PipelineConfig, PreflightConfig
from splat360.job import Job
from splat360.stages.s0_ingest import IngestStage
from splat360.stages.s1_preflight import PreflightStage

# ---------------------------------------------------------------------------
# Skip marker — all synthetic-video tests need ffmpeg
# ---------------------------------------------------------------------------

_FFMPEG = shutil.which("ffmpeg")
_needs_ffmpeg = pytest.mark.skipif(
    _FFMPEG is None,
    reason="ffmpeg not found on PATH — install ffmpeg to run integration tests",
)

_SCRIPT = Path(__file__).parent.parent.parent.parent / "scripts" / "make_synthetic_scene.py"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_default_cfg(**preflight_overrides: object) -> PipelineConfig:
    """Return a PipelineConfig built fully in-memory with default values.

    No files are read.  Optional preflight_overrides let individual tests
    override specific thresholds for the fingerprint test only.
    """
    pf = PreflightConfig(**preflight_overrides)  # type: ignore[arg-type]
    return PipelineConfig(preflight=pf)


def _generate_video(variant: str, out: Path) -> None:
    """Run make_synthetic_scene.py to produce *out*."""
    subprocess.run(
        [sys.executable, str(_SCRIPT), "--variant", variant, "--out", str(out)],
        check=True,
    )


def _run_pipeline(
    video: Path,
    workspace: Path,
    cfg: PipelineConfig | None = None,
    scene_timestamps: list[tuple[float, float]] | None = None,
) -> tuple[Job, object]:
    """Run S0 + S1 and return (job, s1_result)."""
    if cfg is None:
        cfg = _make_default_cfg()
    job = Job(
        workspace=workspace,
        cfg=cfg,
        source=str(video),
        i_have_permission=True,
        scene_timestamps=scene_timestamps,
    )
    s0 = IngestStage()
    s0_res = s0.run(job, cfg)
    assert s0_res.success, f"S0 failed: {s0_res.message}"

    s1 = PreflightStage()
    s1_res = s1.run(job, cfg)
    return job, s1_res


def _metrics(job: Job) -> dict:  # type: ignore[type-arg]
    """Return the first segment's metrics from metrics.json."""
    mp = job.workspace / "01_preflight" / "metrics.json"
    data = json.loads(mp.read_text())
    return data["segments"][0]["metrics"]  # type: ignore[return-value]


def _all_segments(job: Job) -> list:  # type: ignore[type-arg]
    mp = job.workspace / "01_preflight" / "metrics.json"
    data = json.loads(mp.read_text())
    return data["segments"]  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# (a) PASS — lateral translation
# ---------------------------------------------------------------------------

@_needs_ffmpeg
def test_m1_pass(tmp_path: Path) -> None:
    video = tmp_path / "synth_pass.mp4"
    _generate_video("pass", video)
    job, res = _run_pipeline(video, tmp_path / "ws_pass")
    assert res.success
    verdict = job.manifest["stages"]["s1_preflight"]["verdict"]
    report = (job.workspace / "report.md").read_text()
    assert verdict == "PASS", f"Expected PASS, got {verdict}.\nReport:\n{report}"

    m = _metrics(job)
    cfg = _make_default_cfg()
    # rotation_ratio must be well below the threshold
    assert m["rotation_ratio"] < cfg.preflight.max_rotation_ratio, (
        f"rotation_ratio={m['rotation_ratio']:.3f} should be < {cfg.preflight.max_rotation_ratio}"
    )
    # residual flow must be above the min threshold
    assert m["median_flow"] >= cfg.preflight.min_flow_magnitude, (
        f"median_flow={m['median_flow']:.3f} should be >= {cfg.preflight.min_flow_magnitude}"
    )


# ---------------------------------------------------------------------------
# (b) too_short
# ---------------------------------------------------------------------------

@_needs_ffmpeg
def test_m1_short(tmp_path: Path) -> None:
    video = tmp_path / "synth_short.mp4"
    _generate_video("short", video)
    job, res = _run_pipeline(video, tmp_path / "ws_short")
    assert res.success
    assert job.manifest["stages"]["s1_preflight"]["verdict"] == "REJECT"
    report = (job.workspace / "report.md").read_text()
    assert "too_short" in report


# ---------------------------------------------------------------------------
# (c) not_equirect
# ---------------------------------------------------------------------------

@_needs_ffmpeg
def test_m1_format_16_9(tmp_path: Path) -> None:
    video = tmp_path / "synth_16_9.mp4"
    _generate_video("16_9", video)
    job, res = _run_pipeline(video, tmp_path / "ws_16_9")
    assert res.success
    assert job.manifest["stages"]["s1_preflight"]["verdict"] == "REJECT"
    report = (job.workspace / "report.md").read_text()
    assert "not_equirect" in report


# ---------------------------------------------------------------------------
# (d) stereo_unsupported
# ---------------------------------------------------------------------------

@_needs_ffmpeg
def test_m1_format_1_1(tmp_path: Path) -> None:
    video = tmp_path / "synth_1_1.mp4"
    _generate_video("1_1", video)
    job, res = _run_pipeline(video, tmp_path / "ws_1_1")
    assert res.success
    assert job.manifest["stages"]["s1_preflight"]["verdict"] == "REJECT"
    report = (job.workspace / "report.md").read_text()
    assert "stereo_unsupported" in report


# ---------------------------------------------------------------------------
# (e) rotation_dominated — pure yaw
# ---------------------------------------------------------------------------

@_needs_ffmpeg
def test_m1_pure_yaw(tmp_path: Path) -> None:
    video = tmp_path / "synth_pure_yaw.mp4"
    _generate_video("pure_yaw", video)
    job, res = _run_pipeline(video, tmp_path / "ws_yaw")
    assert res.success

    verdict = job.manifest["stages"]["s1_preflight"]["verdict"]
    report = (job.workspace / "report.md").read_text()
    assert verdict == "REJECT", f"Expected REJECT, got {verdict}.\nReport:\n{report}"
    assert "rotation_dominated" in report, f"Expected rotation_dominated in report:\n{report}"

    m = _metrics(job)
    cfg = _make_default_cfg()
    assert m["rotation_ratio"] > cfg.preflight.max_rotation_ratio, (
        f"yaw rotation_ratio={m['rotation_ratio']:.3f} should be > {cfg.preflight.max_rotation_ratio}"
    )


# ---------------------------------------------------------------------------
# (f) no_parallax — static camera
# ---------------------------------------------------------------------------

@_needs_ffmpeg
def test_m1_static(tmp_path: Path) -> None:
    video = tmp_path / "synth_static.mp4"
    _generate_video("static", video)
    job, res = _run_pipeline(video, tmp_path / "ws_static")
    assert res.success
    assert job.manifest["stages"]["s1_preflight"]["verdict"] == "REJECT"
    report = (job.workspace / "report.md").read_text()
    assert "no_parallax" in report

    m = _metrics(job)
    # Static camera must have residual flow near 0
    assert m["median_flow"] < 0.5, (
        f"static median_flow={m['median_flow']:.4f} should be near 0"
    )


# ---------------------------------------------------------------------------
# (g) motion_too_fast
# ---------------------------------------------------------------------------

@_needs_ffmpeg
def test_m1_too_fast(tmp_path: Path) -> None:
    video = tmp_path / "synth_too_fast.mp4"
    _generate_video("too_fast", video)
    job, res = _run_pipeline(video, tmp_path / "ws_fast")
    assert res.success

    verdict = job.manifest["stages"]["s1_preflight"]["verdict"]
    report = (job.workspace / "report.md").read_text()
    assert verdict == "PASS_WITH_WARNINGS", (
        f"Expected PASS_WITH_WARNINGS, got {verdict}.\nReport:\n{report}"
    )
    assert "motion_too_fast" in report


# ---------------------------------------------------------------------------
# (h) excess_blur
# ---------------------------------------------------------------------------

@_needs_ffmpeg
def test_m1_blur(tmp_path: Path) -> None:
    video = tmp_path / "synth_blur.mp4"
    _generate_video("blur", video)
    job, res = _run_pipeline(video, tmp_path / "ws_blur")
    assert res.success
    assert job.manifest["stages"]["s1_preflight"]["verdict"] == "REJECT"
    report = (job.workspace / "report.md").read_text()
    assert "excess_blur" in report


# ---------------------------------------------------------------------------
# (i) hard_cut — 2 scenes, both PASS
# ---------------------------------------------------------------------------

@_needs_ffmpeg
def test_m1_hard_cut(tmp_path: Path) -> None:
    video = tmp_path / "synth_hard_cut.mp4"
    _generate_video("hard_cut", video)
    job, res = _run_pipeline(video, tmp_path / "ws_cut")
    assert res.success

    verdict = job.manifest["stages"]["s1_preflight"]["verdict"]
    report = (job.workspace / "report.md").read_text()
    assert verdict == "PASS", f"Expected PASS, got {verdict}.\nReport:\n{report}"

    segs = _all_segments(job)
    assert len(segs) == 2, f"Expected 2 segments, got {len(segs)}"


# ---------------------------------------------------------------------------
# (j) scene_timestamps override auto-detect
# ---------------------------------------------------------------------------

@_needs_ffmpeg
def test_m1_scene_timestamps(tmp_path: Path) -> None:
    """User-supplied --scene-timestamps must override auto-detection."""
    video = tmp_path / "synth_ts.mp4"
    _generate_video("hard_cut", video)  # 12-s clip

    # Force a split at exactly 4 s instead of the ~6 s hard cut
    timestamps = [(0.0, 4.0), (4.0, 12.0)]

    job, res = _run_pipeline(
        video,
        tmp_path / "ws_ts",
        scene_timestamps=timestamps,
    )
    assert res.success

    segs = _all_segments(job)
    assert len(segs) == 2, f"Expected 2 segments from timestamps, got {len(segs)}"
    # Assert segment boundaries from our timestamps (not auto-detect)
    assert abs(segs[0]["start"] - 0.0) < 0.1
    assert abs(segs[0]["end"] - 4.0) < 0.1
    assert abs(segs[1]["start"] - 4.0) < 0.1
    assert abs(segs[1]["end"] - 12.0) < 0.1


# ---------------------------------------------------------------------------
# (k) fingerprint stability
# ---------------------------------------------------------------------------

@_needs_ffmpeg
def test_m1_fingerprint(tmp_path: Path) -> None:
    """Fingerprint changes when a threshold changes; stays equal otherwise."""
    video = tmp_path / "synth_fp.mp4"
    _generate_video("pass", video)

    # Run once to get initial fingerprint
    job1, _ = _run_pipeline(video, tmp_path / "ws_fp1")
    s1 = PreflightStage()
    fp1 = s1.fingerprint(job1, job1.cfg)

    # Same config → same fingerprint
    job1b, _ = _run_pipeline(video, tmp_path / "ws_fp1b")
    fp1b = s1.fingerprint(job1b, job1b.cfg)
    assert fp1 == fp1b, "Fingerprint should be stable for identical config"

    # Changed threshold → different fingerprint
    cfg2 = _make_default_cfg(min_flow_magnitude=99.0)
    job2, _ = _run_pipeline(video, tmp_path / "ws_fp2", cfg=cfg2)
    fp2 = s1.fingerprint(job2, cfg2)
    assert fp1 != fp2, "Fingerprint should change when a threshold changes"


# ---------------------------------------------------------------------------
# (l) metric value assertions
# ---------------------------------------------------------------------------

@_needs_ffmpeg
def test_metric_assertions(tmp_path: Path) -> None:
    """rotation_ratio: pass < threshold < yaw; static residual ~ 0."""
    cfg = _make_default_cfg()
    threshold = cfg.preflight.max_rotation_ratio

    # Pass clip
    pass_vid = tmp_path / "assert_pass.mp4"
    _generate_video("pass", pass_vid)
    job_pass, _ = _run_pipeline(pass_vid, tmp_path / "ws_assert_pass")
    m_pass = _metrics(job_pass)

    # Pure-yaw clip
    yaw_vid = tmp_path / "assert_yaw.mp4"
    _generate_video("pure_yaw", yaw_vid)
    job_yaw, _ = _run_pipeline(yaw_vid, tmp_path / "ws_assert_yaw")
    m_yaw = _metrics(job_yaw)

    # Static clip
    static_vid = tmp_path / "assert_static.mp4"
    _generate_video("static", static_vid)
    job_static, _ = _run_pipeline(static_vid, tmp_path / "ws_assert_static")
    m_static = _metrics(job_static)

    assert m_pass["rotation_ratio"] < threshold < m_yaw["rotation_ratio"], (
        f"Expected pass_rot({m_pass['rotation_ratio']:.3f}) < "
        f"{threshold} < yaw_rot({m_yaw['rotation_ratio']:.3f})"
    )
    assert m_static["median_flow"] < 0.5, (
        f"static median_flow={m_static['median_flow']:.4f} should be ~0"
    )
