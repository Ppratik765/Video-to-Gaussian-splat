"""
S1: Preflight gate + scene splitting.

Responsibility:
  - Format / aspect-ratio check (equirect 2:1, stereo detection).
  - Scene-cut detection via PySceneDetect (or user-supplied --scene-timestamps).
  - Per-segment sampling pass (~1 frame/sec):
      * Blur: variance-of-Laplacian on rig views.
      * Exposure stability: per-frame mean-luminance flicker.
      * Camera motion / parallax: dense optical flow between frame pairs separated by
        ``cfg.preflight.flow_baseline_seconds`` (default 0.5 s).  A longer baseline
        produces much higher translational residual vs. rotational noise (SNR) than
        adjacent-pair measurement.  The rotation fit uses least-squares across all rig
        views; the residual is the translational component.
      * Adjacent-pair flow (1/fps) is used only for the ``motion_too_fast`` check.
  - Each segment produces an independent child job (own workspace + manifest + verdict).
  - The parent job manifest summarises children.

Milestone: M1
"""

import json
import logging
import shutil
from pathlib import Path
from typing import Any, ClassVar

import numpy as np

from splat360.config import PipelineConfig
from splat360.errors import StageFailed
from splat360.gate.metrics import compute_blur, compute_exposure_flicker, compute_flow_parallax
from splat360.geometry.pinhole import fov_to_focal_length
from splat360.geometry.remap import compute_remap_coordinates, remap_image
from splat360.geometry.rig import get_rig
from splat360.job import Job
from splat360.stages.base import Stage, StageResult
from splat360.utils.hashing import hash_string

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]

try:
    from scenedetect import AdaptiveDetector, detect
except ImportError:
    _detect: Any = None
else:
    _detect = detect

logger = logging.getLogger(__name__)


class PreflightStage(Stage):
    name = "s1_preflight"
    requires: ClassVar[list[str]] = ["s0_ingest"]

    def fingerprint(self, job: Job, cfg: PipelineConfig) -> str:
        """Hash of file identity + relevant config keys."""
        video_path = job.workspace / "00_source" / "video.mp4"
        file_identity = "unknown"
        if video_path.exists():
            st = video_path.stat()
            file_identity = f"{st.st_size}_{st.st_mtime}"

        config_hash_dict = {
            "min_seg": cfg.preflight.min_segment_seconds,
            "blur_th": cfg.preflight.blur_threshold,
            "max_blur": cfg.preflight.max_blur_fraction,
            "baseline": cfg.preflight.flow_baseline_seconds,
            "min_flow": cfg.preflight.min_flow_magnitude,
            "max_flow": cfg.preflight.max_flow_magnitude,
            "res": cfg.preflight.working_resolution,
            "fps": cfg.preflight.sampling_rate_fps,
            "max_rot": cfg.preflight.max_rotation_ratio,
            "ts": json.dumps(job.scene_timestamps),
        }

        return hash_string("preflight_v3" + file_identity + json.dumps(config_hash_dict, sort_keys=True))

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self, job: Job, cfg: PipelineConfig) -> StageResult:
        if cv2 is None:
            raise StageFailed(self.name, "cv2 is required for S1 but not found.")

        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            logger.warning("ffmpeg not found on PATH; some S1 checks may degrade.")

        source_dir = job.workspace / "00_source"
        preflight_dir = job.workspace / "01_preflight"
        preflight_dir.mkdir(parents=True, exist_ok=True)

        video_path = source_dir / "video.mp4"
        if not video_path.exists():
            raise StageFailed(self.name, "video.mp4 not found in 00_source.")

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise StageFailed(self.name, "Could not open video file.")

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        video_fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        duration = total_frames / video_fps if video_fps > 0 else 0

        # ------------------------------------------------------------------
        # 1. Aspect-ratio / format check
        # ------------------------------------------------------------------
        aspect = width / height if height > 0 else 0
        format_verdict = "PASS"
        format_reasons: list[dict[str, Any]] = []

        if aspect < 1.9 or aspect > 2.1:
            if 0.9 < aspect < 1.1:
                if cfg.preflight.stereo_policy == "reject":
                    format_verdict = "REJECT"
                    format_reasons.append({
                        "code": "stereo_unsupported",
                        "severity": "fatal",
                        "message": "Video appears to be 1:1 Top/Bottom stereo. Configured to reject.",
                    })
            else:
                format_verdict = "REJECT"
                format_reasons.append({
                    "code": "not_equirect",
                    "severity": "fatal",
                    "message": (
                        f"Aspect ratio {aspect:.2f} is not 2:1. Not an equirectangular video."
                    ),
                })

        # ------------------------------------------------------------------
        # 2. Pre-compute rig remaps
        # ------------------------------------------------------------------
        working_res = cfg.preflight.working_resolution
        rig = get_rig("cube6_fov100")
        view_w = working_res // 4
        view_h = working_res // 4
        remaps = []
        for v in rig:
            map_x, map_y = compute_remap_coordinates(v, view_w, view_h, working_res, working_res // 2)
            remaps.append((v, map_x, map_y))

        # ------------------------------------------------------------------
        # 3. Scene / segment list
        #    Precedence: user-supplied job.scene_timestamps > PySceneDetect > whole video
        # ------------------------------------------------------------------
        if job.scene_timestamps is not None:
            scene_list = list(job.scene_timestamps)
        else:
            scene_list = _auto_detect_scenes(str(video_path), duration)

        # ------------------------------------------------------------------
        # 4. Per-segment evaluation → child jobs
        # ------------------------------------------------------------------
        child_summaries: list[dict[str, Any]] = []
        parent_verdict = "REJECT"

        for seg_idx, (t_start, t_end) in enumerate(scene_list):
            seg_id = f"{job.job_id}_s{seg_idx:02d}"
            child_ws = job.workspace.parent / seg_id

            seg_summary = _evaluate_segment(
                cap=cap,
                video_fps=video_fps,
                t_start=t_start,
                t_end=t_end,
                seg_idx=seg_idx,
                seg_id=seg_id,
                child_ws=child_ws,
                cfg=cfg,
                remaps=remaps,
                view_w=view_w,
                view_h=view_h,
                format_verdict=format_verdict,
                format_reasons=format_reasons,
                parent_job=job,
            )
            child_summaries.append(seg_summary)

            if seg_summary["verdict"] in ("PASS", "PASS_WITH_WARNINGS"):
                if parent_verdict == "REJECT":
                    parent_verdict = seg_summary["verdict"]
                elif seg_summary["verdict"] == "PASS_WITH_WARNINGS":
                    parent_verdict = "PASS_WITH_WARNINGS"

        cap.release()

        # ------------------------------------------------------------------
        # 5. Write parent metrics + report
        # ------------------------------------------------------------------
        metrics_data = {
            "parent_verdict": parent_verdict,
            "scene_count": len(scene_list),
            "segments": child_summaries,
        }
        metrics_path = preflight_dir / "metrics.json"
        with open(metrics_path, "w", encoding="utf-8") as f:
            json.dump(metrics_data, f, indent=2)

        report_path = job.workspace / "report.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(f"# Preflight Report\n\nParent Verdict: {parent_verdict}\n\n")
            for seg in child_summaries:
                f.write(
                    f"## Segment {seg['segment_idx']} "
                    f"({seg['start']:.2f}s - {seg['end']:.2f}s)\n"
                )
                f.write(f"Verdict: {seg['verdict']}\n")
                for r in seg["reasons"]:
                    f.write(f"- {r['code']}: {r['message']}\n")
                f.write("\n")

        job.update_manifest_stage(self.name, {
            "verdict": parent_verdict,
            "metrics": {"scene_count": len(scene_list)},
        })

        if parent_verdict == "REJECT":
            logger.error("Preflight REJECTED the video.")

        return StageResult(success=True, message=f"Preflight {parent_verdict}")


# ---------------------------------------------------------------------------
# Scene detection helper
# ---------------------------------------------------------------------------

def _auto_detect_scenes(video_path: str, duration: float) -> list[tuple[float, float]]:
    """Use PySceneDetect when available; fall back to single-segment."""
    if _detect is not None:
        try:
            scenes = _detect(video_path, AdaptiveDetector())
            result = []
            for s in scenes:
                start = s[0].get_seconds() if hasattr(s[0], "get_seconds") else s[0].seconds
                end = s[1].get_seconds() if hasattr(s[1], "get_seconds") else s[1].seconds
                result.append((start, end))
            if result:
                return result
        except Exception as e:
            logger.warning("Scene detection failed: %s", e)
    return [(0.0, duration)]


# ---------------------------------------------------------------------------
# Per-segment evaluation
# ---------------------------------------------------------------------------

def _read_gray_frame(
    cap: Any, t_sec: float, working_res: int
) -> np.ndarray | None:
    """Seek to *t_sec* and return a resized grayscale frame, or None on failure."""
    cap.set(2, t_sec * 1000)  # CAP_PROP_POS_MSEC = 0, but we use index 0 = ms
    cap.set(0, t_sec * 1000)  # CAP_PROP_POS_MSEC
    ret, frame = cap.read()
    if not ret:
        return None
    small = cv2.resize(frame, (working_res, working_res // 2))
    return cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)  # type: ignore[no-any-return]


def _compute_flow_pair(
    f1_gray: np.ndarray,
    f2_gray: np.ndarray,
    remaps: list[Any],
    view_w: int,
    view_h: int,
    focal_fn: Any,
) -> tuple[float, float, float]:
    """Return (median_residual, median_rot, rot_ratio) for a frame pair across all rig views."""
    flow_views = []
    for v, map_x, map_y in remaps:
        view1 = remap_image(f1_gray, map_x, map_y)
        view2 = remap_image(f2_gray, map_x, map_y)
        flow = cv2.calcOpticalFlowFarneback(  # type: ignore[call-overload]
            view1, view2, None, 0.5, 3, 15, 3, 5, 1.2, 0
        )
        fl = focal_fn(v.fov_deg, view_w)
        flow_views.append((flow, fl, view_w / 2.0, view_h / 2.0, v.cam_from_rig))
    if not flow_views:
        return 0.0, 0.0, 0.0
    return compute_flow_parallax(flow_views)


def _evaluate_segment(
    *,
    cap: Any,
    video_fps: float,
    t_start: float,
    t_end: float,
    seg_idx: int,
    seg_id: str,
    child_ws: Path,
    cfg: PipelineConfig,
    remaps: list[Any],
    view_w: int,
    view_h: int,
    format_verdict: str,
    format_reasons: list[dict[str, Any]],
    parent_job: Job,
) -> dict[str, Any]:
    """Evaluate one segment and return a summary dict (also writes child job files)."""

    seg_duration = t_end - t_start
    seg_verdict = format_verdict  # inherit format failure
    seg_reasons: list[dict[str, Any]] = list(format_reasons)

    if seg_duration < cfg.preflight.min_segment_seconds and seg_verdict != "REJECT":
        seg_verdict = "REJECT"
        seg_reasons.append({
            "code": "too_short",
            "severity": "fatal",
            "message": (
                f"Video duration {seg_duration:.1f}s is below minimum "
                f"{cfg.preflight.min_segment_seconds}s"
            ),
        })

    metrics: dict[str, Any] = {
        "format_valid": format_verdict != "REJECT",
        "aspect_ratio": 0.0,
        "blur_fraction": 0.0,
        "exposure_flicker": 0.0,
        "median_flow": 0.0,
        "rotation_ratio": 0.0,
        "adjacent_flow": 0.0,
    }

    if seg_verdict != "REJECT":
        seg_verdict_ref = [seg_verdict]
        _measure_segment(
            cap=cap,
            video_fps=video_fps,
            t_start=t_start,
            t_end=t_end,
            cfg=cfg,
            remaps=remaps,
            view_w=view_w,
            view_h=view_h,
            seg_verdict_ref=seg_verdict_ref,
            seg_reasons=seg_reasons,
            metrics=metrics,
        )
        seg_verdict = seg_verdict_ref[0]


    # Build child job workspace (lightweight: just write verdict + metrics)
    child_ws.mkdir(parents=True, exist_ok=True)
    child_metrics_path = child_ws / "metrics.json"
    child_verdict_data = {
        "segment_idx": seg_idx,
        "start": t_start,
        "end": t_end,
        "verdict": seg_verdict,
        "reasons": seg_reasons,
        "metrics": metrics,
    }
    with open(child_metrics_path, "w", encoding="utf-8") as f:
        json.dump(child_verdict_data, f, indent=2)

    child_report_path = child_ws / "report.md"
    with open(child_report_path, "w", encoding="utf-8") as f:
        f.write(f"# Preflight Report — Segment {seg_idx} ({t_start:.2f}s - {t_end:.2f}s)\n\n")
        f.write(f"Verdict: {seg_verdict}\n\n")
        for r in seg_reasons:
            f.write(f"- {r['code']}: {r['message']}\n")

    return {
        "segment_idx": seg_idx,
        "seg_id": seg_id,
        "start": t_start,
        "end": t_end,
        "verdict": seg_verdict,
        "reasons": seg_reasons,
        "metrics": metrics,
        "child_workspace": str(child_ws),
    }


def _measure_segment(
    *,
    cap: Any,
    video_fps: float,
    t_start: float,
    t_end: float,
    cfg: PipelineConfig,
    remaps: list[Any],
    view_w: int,
    view_h: int,
    seg_verdict_ref: list[str],
    seg_reasons: list[dict[str, Any]],
    metrics: dict[str, Any],
) -> str:
    """Run the metric sweep and update seg_verdict_ref[0], seg_reasons, and metrics in-place.

    Returns the final verdict string.
    """
    working_res = cfg.preflight.working_resolution
    sample_interval = 1.0 / cfg.preflight.sampling_rate_fps
    baseline = max(cfg.preflight.flow_baseline_seconds, 1.0 / max(video_fps, 1.0))

    blurs: list[float] = []
    exposures: list[float] = []
    baseline_flows: list[tuple[float, float]] = []  # (median_res, rot_ratio)
    adjacent_flows: list[float] = []  # total flow magnitude per adjacent pair

    t = t_start
    while t < t_end - baseline:
        # ---------- baseline-pair for parallax / rotation ----------
        f1 = _read_frame_at(cap, t, working_res)
        f2 = _read_frame_at(cap, t + baseline, working_res)
        if f1 is None or f2 is None:
            t += sample_interval
            continue

        # Blur on first frame (one view is enough; use front view remap)
        _v0, map_x0, map_y0 = remaps[0]
        view1_front = remap_image(f1, map_x0, map_y0)
        blurs.append(compute_blur(view1_front))
        exposures.append(float(f1.mean()))

        # Full baseline-pair flow across all rig views
        flow_views = []
        for v, map_x, map_y in remaps:
            v1_r = remap_image(f1, map_x, map_y)
            v2_r = remap_image(f2, map_x, map_y)
            flow = cv2.calcOpticalFlowFarneback(  # type: ignore[call-overload]
                v1_r, v2_r, None, 0.5, 3, 15, 3, 5, 1.2, 0
            )
            fl = fov_to_focal_length(v.fov_deg, view_w)
            flow_views.append((flow, fl, view_w / 2.0, view_h / 2.0, v.cam_from_rig))
        median_res, _median_rot, rot_ratio = compute_flow_parallax(flow_views)
        baseline_flows.append((median_res, rot_ratio))

        # ---------- adjacent-pair for too-fast check ----------
        f_next = _read_frame_at(cap, t + 1.0 / max(video_fps, 1.0), working_res)
        if f_next is not None:
            _v0a, mx, my = remaps[0]
            vf = remap_image(f1, mx, my)
            vn = remap_image(f_next, mx, my)
            adj_flow = cv2.calcOpticalFlowFarneback(  # type: ignore[call-overload]
                vf, vn, None, 0.5, 3, 15, 3, 5, 1.2, 0
            )
            mag = float(np.median(np.linalg.norm(adj_flow, axis=-1)))
            adjacent_flows.append(mag)

        t += sample_interval

    seg_verdict = seg_verdict_ref[0]

    # ---- Blur ----
    if blurs:
        blur_fraction = sum(1 for b in blurs if b < cfg.preflight.blur_threshold) / len(blurs)
        metrics["blur_fraction"] = blur_fraction
        if blur_fraction > cfg.preflight.max_blur_fraction:
            seg_verdict = "REJECT"
            seg_reasons.append({
                "code": "excess_blur",
                "severity": "fatal",
                "message": f"Too many blurry frames ({blur_fraction * 100:.0f}%)",
            })

    # ---- Exposure ----
    if exposures:
        flicker = compute_exposure_flicker(exposures)
        metrics["exposure_flicker"] = flicker
        if flicker > cfg.preflight.exposure_flicker_threshold:
            seg_verdict = "REJECT"
            seg_reasons.append({
                "code": "exposure_unstable",
                "severity": "fatal",
                "message": (
                    f"Exposure is highly unstable "
                    f"({flicker:.1f} > {cfg.preflight.exposure_flicker_threshold})."
                ),
            })

    # ---- Parallax / rotation (baseline pairs) ----
    if baseline_flows:
        res_vals = [f[0] for f in baseline_flows]
        rot_vals = [f[1] for f in baseline_flows]
        median_res = float(np.median(res_vals))
        median_rot_ratio = float(np.median(rot_vals))

        metrics["median_flow"] = median_res
        metrics["rotation_ratio"] = median_rot_ratio

        if median_res < cfg.preflight.min_flow_magnitude:
            seg_verdict = "REJECT"
            seg_reasons.append({
                "code": "no_parallax",
                "severity": "fatal",
                "message": (
                    f"Insufficient translational camera motion "
                    f"(residual flow {median_res:.3f} px < {cfg.preflight.min_flow_magnitude})"
                ),
            })
        elif median_rot_ratio > cfg.preflight.max_rotation_ratio:
            seg_verdict = "REJECT"
            seg_reasons.append({
                "code": "rotation_dominated",
                "severity": "fatal",
                "message": (
                    f"Motion is rotation-dominated "
                    f"(ratio {median_rot_ratio:.3f} > {cfg.preflight.max_rotation_ratio})"
                ),
            })

    # ---- Too-fast check (adjacent pairs) ----
    if adjacent_flows:
        adj_median = float(np.median(adjacent_flows))
        metrics["adjacent_flow"] = adj_median
        if adj_median > cfg.preflight.max_flow_magnitude:
            if seg_verdict not in ("REJECT",):
                seg_verdict = "PASS_WITH_WARNINGS"
            seg_reasons.append({
                "code": "motion_too_fast",
                "severity": "warning",
                "message": (
                    f"Motion might be too fast for reliable SfM "
                    f"(adjacent flow {adj_median:.2f} px > {cfg.preflight.max_flow_magnitude})"
                ),
            })

    seg_verdict_ref[0] = seg_verdict
    return seg_verdict


def _read_frame_at(cap: Any, t_sec: float, working_res: int) -> np.ndarray | None:
    """Seek video capture to *t_sec* and return a small grayscale frame or None."""
    cap.set(0, t_sec * 1000)  # CAP_PROP_POS_MSEC = 0
    ret, frame = cap.read()
    if not ret:
        return None
    small = cv2.resize(frame, (working_res, working_res // 2))
    return cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)  # type: ignore[no-any-return]
