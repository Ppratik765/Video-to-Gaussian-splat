import json
from pathlib import Path

import cv2
import numpy as np

from splat360.config import PipelineConfig
from splat360.job import Job
from splat360.stages.s2_frames import FramesStage


def test_s2_frames_child(tmp_path: Path):
    cfg = PipelineConfig()
    cfg.frames.min_gap_frames = 1
    cfg.frames.max_gap_frames = 10

    # Create parent and child workspaces
    parent_ws = tmp_path / "job_abc"
    child_ws = parent_ws / "job_abc_s00"
    child_ws.mkdir(parents=True)

    # Mock preflight metrics for child
    metrics_path = child_ws / "metrics.json"
    with open(metrics_path, "w") as f:
        json.dump({"start": 0.0, "end": 1.0}, f)

    # Mock video file
    source_dir = parent_ws / "00_source"
    source_dir.mkdir()
    video_path = source_dir / "video.mp4"

    # Generate a tiny dummy video
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(video_path), fourcc, 10.0, (128, 64))
    for i in range(10):
        frame = np.zeros((64, 128, 3), dtype=np.uint8)
        frame[:, i*10:i*10+10] = 255  # moving block
        out.write(frame)
    out.release()

    job = Job(workspace=child_ws, cfg=cfg, job_id="job_abc_s00")

    stage = FramesStage()
    res = stage._run_child(job, cfg, parent_ws=parent_ws)

    assert res.success

    frames_dir = child_ws / "02_frames"
    assert frames_dir.is_dir()

    csv_path = frames_dir / "frame_index.csv"
    assert csv_path.exists()

    # Check that at least some keyframes were extracted
    with open(csv_path) as f:
        lines = f.readlines()
        assert len(lines) > 1 # Header + at least one frame
