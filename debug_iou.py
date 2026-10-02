from pathlib import Path

import cv2
import numpy as np
from tests.unit.integration.test_m2_behavior import make_test_video, run_stages

from splat360.config import PipelineConfig

tmp_job_dir = Path("debug_iou")
tmp_job_dir.mkdir(exist_ok=True)
video_path = tmp_job_dir / "occluder.mp4"
gt_mask = make_test_video(video_path, "occluder", duration=2)

cfg = PipelineConfig()
cfg.frames.min_parallax_px = 5.0
cfg.frames.max_gap_frames = 5
cfg.masks.camera_attached_threshold = 0.5

run_stages(video_path, tmp_job_dir, cfg, target_stage="s4_rig")

mask_dir = tmp_job_dir / "debug_iou_s00" / "03_masks"
masks = list(mask_dir.glob("*.png"))
pred_mask = cv2.imread(str(masks[0]), cv2.IMREAD_GRAYSCALE)

cv2.imwrite("debug_gt.png", gt_mask)
cv2.imwrite("debug_pred.png", pred_mask)

intersection = np.logical_and(pred_mask == 255, gt_mask == 255).sum()
union = np.logical_or(pred_mask == 255, gt_mask == 255).sum()
iou = intersection / union if union > 0 else 0
print("IoU:", iou)
print("GT area:", np.sum(gt_mask==255))
print("Pred area:", np.sum(pred_mask==255))
print("Intersection:", intersection)
