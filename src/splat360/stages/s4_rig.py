"""S4: Equirect → perspective rig views. Milestone: M2"""
from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

import cv2
import numpy as np

from splat360.config import PipelineConfig
from splat360.constants import STAGE_FRAMES, STAGE_MASKS, STAGE_RIG, STATUS_DONE
from splat360.errors import StageFailed
from splat360.geometry.pinhole import fov_to_focal_length
from splat360.geometry.remap import compute_remap_coordinates, remap_image
from splat360.geometry.rig import get_rig
from splat360.job import Job
from splat360.stages.base import Stage, StageResult
from splat360.utils.hashing import hash_dict

logger = logging.getLogger(__name__)


class RigStage(Stage):
    @property
    def name(self) -> str:
        return STAGE_RIG

    @property
    def requires(self) -> list[str]:
        return [STAGE_MASKS]

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

        for seg in metrics.get("segments", []):
            if seg["verdict"] in ("PASS", "PASS_WITH_WARNINGS"):
                child_ws = Path(seg["child_workspace"])
                child_job = Job(workspace=child_ws, cfg=cfg, job_id=seg["seg_id"])

                fp = self.fingerprint(child_job, cfg)
                if not cfg.force and child_job.stage_fingerprint(self.name) == fp and child_job.stage_status(self.name) == STATUS_DONE:
                    logger.info(f"Skipping {self.name} for {seg['seg_id']}, unchanged.")
                    continue

                child_job.mark_running(self.name)
                try:
                    res = self._run_child(child_job, cfg)
                    if not res.success:
                        all_success = False
                        child_job.mark_failed(self.name, res.message or "failed")
                    else:
                        child_job.mark_done(self.name, fp, 0.0)
                except Exception as e:
                    all_success = False
                    child_job.mark_failed(self.name, str(e))
                    logger.error(f"S4 failed for {seg['seg_id']}: {e}")

        if not all_success:
            raise StageFailed(self.name, "One or more child segments failed S4")
        return StageResult(success=True)

    def _run_child(self, job: Job, cfg: PipelineConfig) -> StageResult:
        frames_dir = job.stage_dir(STAGE_FRAMES)
        masks_dir = job.stage_dir(STAGE_MASKS)
        csv_path = frames_dir / "frame_index.csv"

        if not csv_path.exists():
            raise StageFailed(self.name, "frame_index.csv not found from S2")

        kf_ids = []
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                kf_ids.append(row["keyframe_id"])

        if not kf_ids:
            raise StageFailed(self.name, "No keyframes to process")

        # Determine equirect shape from first frame
        test_img_path = frames_dir / f"{kf_ids[0]}.jpg"
        if not test_img_path.exists():
            test_img_path = frames_dir / f"{kf_ids[0]}.png"
        test_img = cv2.imread(str(test_img_path))
        if test_img is None:
            raise StageFailed(self.name, f"Could not read keyframe {kf_ids[0]}")
        equi_h, equi_w = test_img.shape[:2]

        out_dir = job.stage_dir(self.name)
        images_out = out_dir / "images"
        masks_out = out_dir / "masks"
        images_out.mkdir(parents=True, exist_ok=True)
        masks_out.mkdir(parents=True, exist_ok=True)

        rig = get_rig(cfg.rig.preset)
        remaps = []
        view_w = cfg.rig.view_size
        # Assuming square aspect ratio based on FOV specs, but let's just make it square
        view_h = view_w

        for v in rig:
            map_x, map_y = compute_remap_coordinates(v, view_w, view_h, equi_w, equi_h)
            remaps.append((v, map_x, map_y))

        for kf_id in kf_ids:
            img_path = frames_dir / f"{kf_id}.jpg"
            if not img_path.exists():
                img_path = frames_dir / f"{kf_id}.png"
            mask_path = masks_dir / f"{kf_id}.png"

            img_bgr = cv2.imread(str(img_path))
            if img_bgr is None:
                raise StageFailed(self.name, f"Failed to read image {img_path}")

            mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
            if mask is None:
                mask = np.zeros(img_bgr.shape[:2], dtype=np.uint8)

            for v, map_x, map_y in remaps:
                view_img = remap_image(img_bgr, map_x, map_y, is_mask=False)
                view_mask = remap_image(mask, map_x, map_y, is_mask=True)

                view_name = v.name

                cv2.imwrite(str(images_out / f"{kf_id}_{view_name}.jpg"), view_img, [int(cv2.IMWRITE_JPEG_QUALITY), cfg.frames.jpeg_quality])
                cv2.imwrite(str(masks_out / f"{kf_id}_{view_name}.png"), view_mask)

        # Write neutral rig.json
        rig_info = []
        for v in rig:
            fl = fov_to_focal_length(v.fov_deg, view_w)
            rig_info.append({
                "camera_id": v.name,
                "model": "PINHOLE",
                "width": view_w,
                "height": view_h,
                "params": [fl, fl, view_w / 2.0, view_h / 2.0],
                "cam_from_rig": v.cam_from_rig.tolist(),
            })

        with open(out_dir / "rig.json", "w", encoding="utf-8") as f:
            json.dump(rig_info, f, indent=2)

        return StageResult(success=True)

    def fingerprint(self, job: Job, cfg: PipelineConfig) -> str:
        return hash_dict({"rig": cfg.rig.model_dump(), "code_version": "v2"})
