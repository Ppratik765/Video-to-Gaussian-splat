import csv
from pathlib import Path

import cv2
import numpy as np

from splat360.config import PipelineConfig
from splat360.job import Job
from splat360.stages.s3_masks import MasksStage


def test_s3_masks_child(tmp_path: Path):
    cfg = PipelineConfig()
    cfg.masks.segmenter = None # Use NullSegmenter for tests to avoid loading weights

    # Create child workspace
    parent_ws = tmp_path / "job_abc"
    child_ws = parent_ws / "job_abc_s00"
    child_ws.mkdir(parents=True)

    # Mock frames directory and csv from S2
    frames_dir = child_ws / "02_frames"
    frames_dir.mkdir()

    with open(frames_dir / "frame_index.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["keyframe_id", "source_frame", "timestamp", "blur", "parallax"])
        writer.writerow(["0000", "0", "0.0", "1.0", "0.0"])
        writer.writerow(["0001", "1", "0.1", "1.0", "5.0"])

    # Mock images
    img = np.ones((64, 128, 3), dtype=np.uint8) * 127
    cv2.imwrite(str(frames_dir / "0000.jpg"), img)
    cv2.imwrite(str(frames_dir / "0001.jpg"), img)

    job = Job(workspace=child_ws, cfg=cfg, job_id="job_abc_s00")

    stage = MasksStage()
    res = stage._run_child(job, cfg)

    assert res.success

    masks_dir = child_ws / "03_masks"
    assert masks_dir.is_dir()

    assert (masks_dir / "0000.png").exists()
    assert (masks_dir / "0001.png").exists()
    assert (masks_dir / "debug").is_dir()
