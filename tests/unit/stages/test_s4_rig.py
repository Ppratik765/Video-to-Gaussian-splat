import csv
import json
from pathlib import Path

import cv2
import numpy as np

from splat360.config import PipelineConfig
from splat360.job import Job
from splat360.stages.s4_rig import RigStage


def test_s4_rig_child(tmp_path: Path):
    cfg = PipelineConfig()
    cfg.rig.preset = "cube6"
    cfg.rig.view_size = 64

    # Create child workspace
    parent_ws = tmp_path / "job_abc"
    child_ws = parent_ws / "job_abc_s00"
    child_ws.mkdir(parents=True)

    # Mock frames and masks directories
    frames_dir = child_ws / "02_frames"
    masks_dir = child_ws / "03_masks"
    frames_dir.mkdir()
    masks_dir.mkdir()

    with open(frames_dir / "frame_index.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["keyframe_id", "source_frame", "timestamp", "blur", "parallax"])
        writer.writerow(["0000", "0", "0.0", "1.0", "0.0"])

    img = np.ones((64, 128, 3), dtype=np.uint8) * 127
    mask = np.zeros((64, 128), dtype=np.uint8)
    cv2.imwrite(str(frames_dir / "0000.jpg"), img)
    cv2.imwrite(str(masks_dir / "0000.png"), mask)

    job = Job(workspace=child_ws, cfg=cfg, job_id="job_abc_s00")

    stage = RigStage()
    res = stage._run_child(job, cfg)

    assert res.success

    rig_dir = child_ws / "04_views"
    assert rig_dir.is_dir()
    assert (rig_dir / "images").is_dir()
    assert (rig_dir / "masks").is_dir()

    assert (rig_dir / "rig.json").exists()
    with open(rig_dir / "rig.json") as f:
        rig_info = json.load(f)
        assert len(rig_info) == 6 # cube6 has 6 views

    # Check that images and masks are created for each view
    for v in rig_info:
        name = v["camera_id"]
        assert (rig_dir / "images" / f"0000_{name}.jpg").exists()
        assert (rig_dir / "masks" / f"0000_{name}.png").exists()
