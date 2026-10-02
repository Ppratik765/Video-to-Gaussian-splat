"""S2: Frame extraction & keyframe selection. Milestone: M2"""
from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

import cv2

from splat360.config import PipelineConfig
from splat360.constants import STAGE_FRAMES, STAGE_PREFLIGHT, STATUS_DONE
from splat360.errors import StageFailed
from splat360.gate.metrics import compute_blur
from splat360.geometry.remap import compute_remap_coordinates
from splat360.geometry.rig import get_rig
from splat360.job import Job
from splat360.stages.base import Stage, StageResult
from splat360.utils.hashing import hash_dict
from splat360.video.decode import stream_decode
from splat360.video.keyframes import select_keyframes

logger = logging.getLogger(__name__)


class FramesStage(Stage):
    @property
    def name(self) -> str:
        return STAGE_FRAMES

    @property
    def requires(self) -> list[str]:
        return [STAGE_PREFLIGHT]

    def run(self, job: Job, cfg: PipelineConfig) -> StageResult:
        # Check if we are running on parent or child.
        # If parent, we orchestrate children.
        if (job.workspace / "01_preflight" / "metrics.json").exists():
            return self._run_parent(job, cfg)
        else:
            return self._run_child(job, cfg)

    def _run_parent(self, job: Job, cfg: PipelineConfig) -> StageResult:
        metrics_path = job.workspace / "01_preflight" / "metrics.json"
        with open(metrics_path, encoding="utf-8") as f:
            metrics = json.load(f)

        all_success = True
        for seg in metrics.get("segments", []):
            if seg["verdict"] in ("PASS", "PASS_WITH_WARNINGS"):
                child_ws = Path(seg["child_workspace"])
                child_job = Job(workspace=child_ws, cfg=cfg, job_id=seg["seg_id"])

                # Check child fingerprint
                fp = self.fingerprint(child_job, cfg)
                if not cfg.force and child_job.stage_fingerprint(self.name) == fp and child_job.stage_status(self.name) == STATUS_DONE:
                    logger.info(f"Skipping {self.name} for {seg['seg_id']}, unchanged.")
                    continue

                child_job.mark_running(self.name)
                try:
                    res = self._run_child(child_job, cfg, parent_ws=job.workspace, start=seg["start"], end=seg["end"])
                    if not res.success:
                        all_success = False
                        child_job.mark_failed(self.name, res.message or "failed")
                    else:
                        child_job.mark_done(self.name, fp, 0.0) # We don't have accurate duration here unless we wrap it
                except Exception as e:
                    all_success = False
                    child_job.mark_failed(self.name, str(e))
                    logger.error(f"S2 failed for {seg['seg_id']}: {e}")

        if not all_success:
            raise StageFailed(self.name, "One or more child segments failed S2")
        return StageResult(success=True)

    def _run_child(self, job: Job, cfg: PipelineConfig, parent_ws: Path | None = None, start: float = 0.0, end: float = 0.0) -> StageResult:
        # Read preflight metrics for child
        if parent_ws is None:
            parent_ws = job.workspace.parent
            metrics_path = job.workspace / "metrics.json"
            if not metrics_path.exists():
                raise StageFailed(self.name, "Child metrics.json not found")
            with open(metrics_path, encoding="utf-8") as f:
                metrics = json.load(f)
            start = metrics["start"]
            end = metrics["end"]

        video_path = parent_ws / "00_source" / "video.mp4"
        if not video_path.exists():
            raise StageFailed(self.name, "video.mp4 not found in parent 00_source")

        out_dir = job.stage_dir(self.name)

        # Prepare remap coordinates
        working_res = cfg.preflight.working_resolution
        rig = get_rig("cube6_fov100") # Use S1 rig for parallax calculation
        view_w = working_res // 4
        view_h = working_res // 4
        remaps = []
        for v in rig:
            map_x, map_y = compute_remap_coordinates(v, view_w, view_h, working_res, working_res // 2)
            remaps.append((v, map_x, map_y))

        stream = stream_decode(str(video_path), start, end)

        selected = select_keyframes(
            frame_stream=stream,
            min_parallax_px=cfg.frames.min_parallax_px,
            min_gap_frames=cfg.frames.min_gap_frames,
            max_gap_frames=cfg.frames.max_gap_frames,
            max_keyframes=cfg.frames.max_keyframes,
            working_res=working_res,
            remaps=remaps,
            blur_fn=compute_blur
        )

        csv_path = out_dir / "frame_index.csv"
        kf_count = 0
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["keyframe_id", "source_frame", "timestamp", "blur", "parallax"])

            for i, item in enumerate(selected):
                kf_id = f"{i:04d}"
                out_img = out_dir / f"{kf_id}.jpg"
                cv2.imwrite(str(out_img), item["image"], [int(cv2.IMWRITE_JPEG_QUALITY), cfg.frames.jpeg_quality])

                writer.writerow([
                    kf_id,
                    item["frame_idx"],
                    f"{item['timestamp']:.3f}",
                    f"{item['blur']:.2f}",
                    f"{item['parallax']:.2f}"
                ])
                kf_count += 1

        job.update_manifest_stage(self.name, {
            "keyframe_count": kf_count
        })

        return StageResult(success=True)

    def fingerprint(self, job: Job, cfg: PipelineConfig) -> str:
        return hash_dict({"frames": cfg.frames.model_dump(), "code_version": "v2"})
