import json
import logging
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
        # 3f: Fingerprint hashing source file identity, config values, code version

        # We can hash the file mtime/size or use the metadata from s0.
        video_path = job.workspace / "00_source" / "video.mp4"
        file_identity = "unknown"
        if video_path.exists():
            st = video_path.stat()
            file_identity = f"{st.st_size}_{st.st_mtime}"

        config_hash_dict = {
            "min_seg": cfg.preflight.min_segment_seconds,
            "blur_th": cfg.preflight.blur_threshold,
            "max_blur": cfg.preflight.max_blur_fraction,
            "min_flow": cfg.preflight.min_flow_magnitude,
            "max_flow": cfg.preflight.max_flow_magnitude,
            "res": cfg.preflight.working_resolution,
            "fps": cfg.preflight.sampling_rate_fps,
            "max_rot": cfg.preflight.max_rotation_ratio,
        }

        return hash_string("preflight_v2" + file_identity + json.dumps(config_hash_dict, sort_keys=True))

    def run(self, job: Job, cfg: PipelineConfig) -> StageResult:
        if cv2 is None:
            raise StageFailed(self.name, "cv2 is required for S1 but not found.")

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

        # Aspect ratio check
        aspect = width / height if height > 0 else 0
        format_verdict = "PASS"
        format_reasons = []

        if aspect < 1.9 or aspect > 2.1:
            if aspect > 0.9 and aspect < 1.1:
                if cfg.preflight.stereo_policy == "reject":
                    format_verdict = "REJECT"
                    format_reasons.append({
                        "code": "stereo_unsupported",
                        "severity": "fatal",
                        "message": "Video appears to be 1:1 Top/Bottom stereo. Configured to reject."
                    })
            else:
                format_verdict = "REJECT"
                format_reasons.append({
                    "code": "not_equirect",
                    "severity": "fatal",
                    "message": f"Aspect ratio {aspect:.2f} is not 2:1. Not an equirectangular video."
                })

        # Pre-compute rig remaps for the working resolution
        working_res = cfg.preflight.working_resolution
        rig = get_rig("cube6_fov100")
        view_w = working_res // 4
        view_h = working_res // 4
        remaps = []
        for v in rig:
            map_x, map_y = compute_remap_coordinates(v, view_w, view_h, working_res, working_res // 2)
            remaps.append((v, map_x, map_y))

        # Scene detection
        scene_list = []
        if _detect is not None:
            try:
                # Returns list of (start_time, end_time) in FrameTimecode
                scenes = _detect(str(video_path), AdaptiveDetector())
                for s in scenes:
                    scene_list.append((s[0].seconds, s[1].seconds))
            except Exception as e:
                logger.warning(f"Scene detection failed: {e}")

        if not scene_list:
            scene_list = [(0.0, duration)]

        segments_data = []

        # Process each segment
        for seg_idx, (t_start, t_end) in enumerate(scene_list):
            seg_duration = t_end - t_start
            seg_verdict = "PASS"
            seg_reasons = list(format_reasons)
            if format_verdict == "REJECT":
                seg_verdict = "REJECT"

            if seg_duration < cfg.preflight.min_segment_seconds:
                seg_verdict = "REJECT"
                seg_reasons.append({
                    "code": "too_short",
                    "severity": "fatal",
                    "message": f"Video duration {seg_duration:.1f}s is below minimum {cfg.preflight.min_segment_seconds}s"
                })

            # Evaluate metrics if not already format-rejected
            metrics = {
                "format_valid": format_verdict != "REJECT",
                "aspect_ratio": aspect,
                "blur_fraction": 0.0,
                "exposure_flicker": 0.0,
                "median_flow": 0.0,
                "rotation_ratio": 0.0,
            }

            if seg_verdict != "REJECT":
                blurs = []
                exposures = []
                flows_list = []

                # We sample at sampling_rate_fps
                sample_interval = 1.0 / cfg.preflight.sampling_rate_fps
                t = t_start

                while t < t_end - (1.0 / video_fps):
                    # Read frame at t
                    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
                    ret, frame1 = cap.read()
                    if not ret:
                        break

                    # Read adjacent frame
                    ret, frame2 = cap.read()
                    if not ret:
                        break

                    f1_small = cv2.resize(frame1, (working_res, working_res // 2))
                    f2_small = cv2.resize(frame2, (working_res, working_res // 2))
                    f1_gray = cv2.cvtColor(f1_small, cv2.COLOR_BGR2GRAY)
                    f2_gray = cv2.cvtColor(f2_small, cv2.COLOR_BGR2GRAY)

                    exposures.append(f1_gray.mean())

                    # Evaluate on rig views
                    flow_views = []
                    for v, map_x, map_y in remaps:
                        view1 = remap_image(f1_gray, map_x, map_y)
                        view2 = remap_image(f2_gray, map_x, map_y)

                        blur = compute_blur(view1)
                        blurs.append(blur)

                        flow = cv2.calcOpticalFlowFarneback(view1, view2, None, 0.5, 3, 15, 3, 5, 1.2, 0)  # type: ignore[call-overload]

                        focal_length = fov_to_focal_length(v.fov_deg, view_w)
                        flow_views.append((flow, focal_length, view_w/2.0, view_h/2.0, v.cam_from_rig))

                    if flow_views:
                        median_res, _median_rot, rot_ratio = compute_flow_parallax(flow_views)
                        flows_list.append((median_res, rot_ratio))

                    t += sample_interval

                if blurs:
                    blur_fraction = sum(1 for b in blurs if b < cfg.preflight.blur_threshold) / len(blurs)
                    metrics["blur_fraction"] = blur_fraction
                    if blur_fraction > cfg.preflight.max_blur_fraction:
                        seg_verdict = "REJECT"
                        seg_reasons.append({"code": "excess_blur", "severity": "fatal", "message": f"Too many blurry frames ({blur_fraction*100:.0f}%)"})

                if exposures:
                    flicker = compute_exposure_flicker(exposures)
                    metrics["exposure_flicker"] = flicker
                    if flicker > cfg.preflight.exposure_flicker_threshold:
                        seg_verdict = "REJECT"
                        seg_reasons.append({"code": "exposure_unstable", "severity": "fatal", "message": f"Exposure is highly unstable ({flicker:.1f} > {cfg.preflight.exposure_flicker_threshold})."})

                if flows_list:
                    median_res_list = [f[0] for f in flows_list]
                    rot_ratio_list = [f[1] for f in flows_list]
                    median_res = float(np.median(median_res_list))
                    median_rot_ratio = float(np.median(rot_ratio_list))

                    metrics["median_flow"] = median_res
                    metrics["rotation_ratio"] = median_rot_ratio

                    if median_rot_ratio > cfg.preflight.max_rotation_ratio:
                        seg_verdict = "REJECT"
                        seg_reasons.append({"code": "rotation_dominated", "severity": "fatal", "message": f"Motion is rotation-dominated (ratio {median_rot_ratio:.2f} > {cfg.preflight.max_rotation_ratio})"})
                    elif median_res < cfg.preflight.min_flow_magnitude:
                        seg_verdict = "REJECT"
                        seg_reasons.append({"code": "no_parallax", "severity": "fatal", "message": f"Insufficient translational camera motion (residual flow {median_res:.2f} px < {cfg.preflight.min_flow_magnitude})"})
                    elif median_res > cfg.preflight.max_flow_magnitude:
                        if seg_verdict != "REJECT":
                            seg_verdict = "PASS_WITH_WARNINGS"
                        seg_reasons.append({"code": "motion_too_fast", "severity": "warning", "message": f"Motion might be too fast (residual flow {median_res:.2f} px > {cfg.preflight.max_flow_magnitude})"})

            segments_data.append({
                "segment_idx": seg_idx,
                "start": t_start,
                "end": t_end,
                "verdict": seg_verdict,
                "reasons": seg_reasons,
                "metrics": metrics
            })

        cap.release()

        # Combine verdicts
        # If any segment passes, the parent can be PASS or PASS_WITH_WARNINGS.
        # Else REJECT.
        parent_verdict = "REJECT"
        for s in segments_data:
            if s["verdict"] in ("PASS", "PASS_WITH_WARNINGS"):
                parent_verdict = s["verdict"]
                # We prioritize PASS_WITH_WARNINGS over PASS if any has warnings
                if any(x["verdict"] == "PASS_WITH_WARNINGS" for x in segments_data):
                    parent_verdict = "PASS_WITH_WARNINGS"
                break

        # Write metrics
        metrics_path = preflight_dir / "metrics.json"
        with open(metrics_path, "w", encoding="utf-8") as f:
            json.dump({
                "parent_verdict": parent_verdict,
                "scene_count": len(scene_list),
                "segments": segments_data
            }, f, indent=2)

        # Write report
        report_path = job.workspace / "report.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(f"# Preflight Report\n\nParent Verdict: {parent_verdict}\n\n")
            for seg in segments_data:
                f.write(f"## Segment {seg['segment_idx']} ({seg['start']:.2f}s - {seg['end']:.2f}s)\n")
                f.write(f"Verdict: {seg['verdict']}\n")
                for r in seg['reasons']:
                    f.write(f"- {r['code']}: {r['message']}\n")
                f.write("\n")

        job.update_manifest_stage(self.name, {
            "verdict": parent_verdict,
            "metrics": {"scene_count": len(scene_list)}
        })

        if parent_verdict == "REJECT":
            logger.error("Preflight REJECTED the video.")
            return StageResult(success=True, message="Rejected at preflight")

        return StageResult(success=True, message=f"Preflight {parent_verdict}")
