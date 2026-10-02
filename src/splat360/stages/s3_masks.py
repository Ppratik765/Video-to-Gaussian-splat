"""S3: Masking (camera-attached, dynamic, nadir). Milestone: M2"""
from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

import cv2

from splat360.config import PipelineConfig
from splat360.constants import STAGE_FRAMES, STAGE_MASKS
from splat360.errors import StageFailed
from splat360.geometry.remap import compute_remap_coordinates
from splat360.geometry.rig import get_rig
from splat360.job import Job
from splat360.masking.camera_attached import compute_camera_attached_mask
from splat360.masking.combine import combine_masks
from splat360.masking.debug import create_debug_overlay
from splat360.masking.semantic import HFSegmenter, NullSegmenter, Segmenter
from splat360.stages.base import Stage, StageResult
from splat360.utils.hashing import hash_dict

logger = logging.getLogger(__name__)


class MasksStage(Stage):
    @property
    def name(self) -> str:
        return STAGE_MASKS

    @property
    def requires(self) -> list[str]:
        return [STAGE_FRAMES]

    def run(self, job: Job, cfg: PipelineConfig) -> StageResult:
        if (job.workspace / "01_preflight" / "metrics.json").exists():
            return self._run_parent(job, cfg)
        else:
            return self._run_child(job, cfg)

    def _run_parent(self, job: Job, cfg: PipelineConfig) -> StageResult:
        metrics_path = job.workspace / "01_preflight" / "metrics.json"
        with open(metrics_path, encoding="utf-8") as f:
            metrics = json.load(f)

        all_success = True

        segmenter = None
        if cfg.masks.segmenter is not None:
            segmenter = HFSegmenter(model_type=cfg.masks.segmenter)

        for seg in metrics.get("segments", []):
            if seg["verdict"] in ("PASS", "PASS_WITH_WARNINGS"):
                child_ws = Path(seg["child_workspace"])
                child_job = Job(workspace=child_ws, cfg=cfg, job_id=seg["seg_id"])

                fp = self.fingerprint(child_job, cfg)
                if not cfg.force and child_job.stage_fingerprint(self.name) == fp and child_job.stage_status(self.name) == "DONE":
                    logger.info(f"Skipping {self.name} for {seg['seg_id']}, unchanged.")
                    continue

                child_job.mark_running(self.name)
                try:
                    res = self._run_child(child_job, cfg, segmenter=segmenter)
                    if not res.success:
                        all_success = False
                        child_job.mark_failed(self.name, res.message or "failed")
                    else:
                        child_job.mark_done(self.name, fp, 0.0)
                except Exception as e:
                    all_success = False
                    child_job.mark_failed(self.name, str(e))
                    logger.error(f"S3 failed for {seg['seg_id']}: {e}")

        if not all_success:
            raise StageFailed(self.name, "One or more child segments failed S3")
        return StageResult(success=True)

    def _run_child(self, job: Job, cfg: PipelineConfig, segmenter: Segmenter | None = None) -> StageResult:
        frames_dir = job.stage_dir(STAGE_FRAMES)
        csv_path = frames_dir / "frame_index.csv"

        if not csv_path.exists():
            raise StageFailed(self.name, "frame_index.csv not found from S2")

        keyframes_gray = []
        keyframes_bgr = []
        kf_ids = []

        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                kf_id = row["keyframe_id"]
                img_path = frames_dir / f"{kf_id}.jpg"
                if not img_path.exists():
                    img_path = frames_dir / f"{kf_id}.png"
                img = cv2.imread(str(img_path))
                if img is None:
                    continue

                keyframes_bgr.append(img)
                keyframes_gray.append(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
                kf_ids.append(kf_id)

        if not keyframes_gray:
            raise StageFailed(self.name, "No keyframes loaded")

        equirect_shape = keyframes_gray[0].shape[:2]

        # Prepare remap coordinates for camera-attached mask
        working_res = cfg.preflight.working_resolution
        rig = get_rig("cube6_fov100")
        view_w = working_res
        view_h = working_res
        remaps = []
        for v in rig:
            map_x, map_y = compute_remap_coordinates(v, view_w, view_h, equirect_shape[1], equirect_shape[0])
            remaps.append((v, map_x, map_y))

        # 1. Camera-attached mask
        camera_attached_mask = compute_camera_attached_mask(keyframes_gray, cfg.masks.camera_attached_threshold, remaps, equirect_shape)

        # 2. Dynamic object mask
        if segmenter is None:
            if cfg.masks.segmenter is not None:
                segmenter = HFSegmenter(model_type=cfg.masks.segmenter)
            else:
                segmenter = NullSegmenter()

        # 3. Manual override
        manual_mask = None
        manual_path = job.workspace.parent / "masks" / "manual_equirect.png"
        if manual_path.exists():
            manual_mask = cv2.imread(str(manual_path), cv2.IMREAD_GRAYSCALE)

        out_dir = job.stage_dir(self.name)
        debug_dir = out_dir / "debug"
        debug_dir.mkdir(parents=True, exist_ok=True)

        step_debug = max(1, len(kf_ids) // 8)

        for i, (kf_id, img_bgr) in enumerate(zip(kf_ids, keyframes_bgr, strict=True)):
            dynamic_mask = segmenter.predict_dynamic_mask(img_bgr)

            final_mask = combine_masks(
                equirect_shape=equirect_shape,
                camera_attached_mask=camera_attached_mask,
                dynamic_mask=dynamic_mask,
                manual_mask=manual_mask,
                downweight_zenith_nadir=cfg.masks.downweight_zenith_nadir
            )

            mask_out_path = out_dir / f"{kf_id}.png"
            cv2.imwrite(str(mask_out_path), final_mask)

            # Save debug overlays for roughly 8 frames
            if i % step_debug == 0 or i == len(kf_ids) - 1:
                debug_overlay = create_debug_overlay(img_bgr, final_mask)
                cv2.imwrite(str(debug_dir / f"{kf_id}.jpg"), debug_overlay, [int(cv2.IMWRITE_JPEG_QUALITY), 80])

        job.update_manifest_stage(self.name, {
            "mask_count": len(kf_ids)
        })

        return StageResult(success=True)

    def fingerprint(self, job: Job, cfg: PipelineConfig) -> str:
        return hash_dict({"masks": cfg.masks.model_dump(), "code_version": "v3"})
