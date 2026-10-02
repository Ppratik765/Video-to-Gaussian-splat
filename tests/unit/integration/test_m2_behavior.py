import shutil
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

from splat360.config import PipelineConfig
from splat360.job import Job
from splat360.stages import get_stage

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from scripts.make_synthetic_scene import render_equirect_panorama


@pytest.fixture
def tmp_job_dir(tmp_path):
    return tmp_path / "job_behavior"

def make_test_video(path: Path, variant: str, duration: int = 6, fps: int = 10):
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    width, height = 320, 160
    out = cv2.VideoWriter(str(path), fourcc, fps, (width, height))
    gt_mask = None

    total_frames = duration * fps
    for i in range(total_frames):
        t = i / fps
        if variant == "variable_speed":
            if t < 2.0:
                pos = t * 8.0
            elif t < 4.0:
                pos = 16.0 + (t - 2.0) * 2.0
            else:
                pos = 20.0
            cam_pos = np.array([pos, 0.0, 0.0])
            img = render_equirect_panorama(cam_pos, np.eye(3), width, height, uniform_sky=False, occluder=False)
        elif variant == "occluder":
            cam_pos = np.array([t * 4.0, 0.0, 0.0])
            img, mask = render_equirect_panorama(cam_pos, np.eye(3), width, height, uniform_sky=False, occluder=True)
            if i == 0: gt_mask = mask
        elif variant == "uniform_region":
            cam_pos = np.array([t * 4.0, 0.0, 0.0])
            img = render_equirect_panorama(cam_pos, np.eye(3), width, height, uniform_sky=True, occluder=False)

        out.write(img)
    out.release()
    return gt_mask

def run_stages(video_path: Path, job_dir: Path, cfg: PipelineConfig, target_stage: str):
    job = Job(workspace=job_dir, cfg=cfg, job_id=job_dir.name)

    # Fake S0
    source_dir = job_dir / "00_source"
    source_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(str(video_path), str(source_dir / "video.mp4"))
    job.mark_done("s0_ingest", "fp", 0.0)

    # Fake S1
    import json
    metrics_path = job_dir / "01_preflight"
    metrics_path.mkdir(parents=True, exist_ok=True)
    with open(metrics_path / "metrics.json", "w") as f:
        json.dump({
            "segments": [
                {
                    "verdict": "PASS",
                    "child_workspace": str(job_dir / f"{job_dir.name}_s00"),
                    "seg_id": f"{job_dir.name}_s00",
                    "start": 0.0,
                    "end": 6.0
                }
            ]
        }, f)
    job.mark_done("s1_preflight", "fp", 0.0)

    stages = ["s2_frames", "s3_masks", "s4_rig"]
    for s in stages:
        stage = get_stage(s)
        stage.run(job, cfg)
        if s == target_stage:
            break

def test_m2_variable_speed_and_max_gap(tmp_job_dir):
    video_path = tmp_job_dir / "variable_speed.mp4"
    tmp_job_dir.mkdir(parents=True)
    make_test_video(video_path, "variable_speed", duration=6)

    cfg = PipelineConfig()
    cfg.frames.min_parallax_px = 5.0
    cfg.frames.min_gap_frames = 2
    cfg.frames.max_gap_frames = 15
    cfg.frames.max_keyframes = 100

    run_stages(video_path, tmp_job_dir, cfg, target_stage="s4_rig")

    # Check frame_index.csv
    import csv
    csv_path = tmp_job_dir / "job_behavior_s00" / "02_frames" / "frame_index.csv"
    assert csv_path.exists()

    with open(csv_path) as f:
        rows = list(csv.DictReader(f))

    assert len(rows) > 0
    assert len(rows) <= cfg.frames.max_keyframes

    source_frames = [int(r["source_frame"]) for r in rows]

    # check max_gap rule
    gaps = [source_frames[i] - source_frames[i-1] for i in range(1, len(source_frames))]
    assert all(g <= cfg.frames.max_gap_frames for g in gaps), "Max gap rule broken"

    # density fast > slow > stopped (stopped should just be max gap)
    fast_kfs = [f for f in source_frames if f < 20] # 0-2s
    slow_kfs = [f for f in source_frames if 20 <= f < 40] # 2-4s
    stop_kfs = [f for f in source_frames if 40 <= f < 60] # 4-6s

    assert len(fast_kfs) > len(slow_kfs)
    assert len(slow_kfs) > len(stop_kfs)
    # stopped should be roughly 20 / max_gap_frames
    assert len(stop_kfs) <= (20 // cfg.frames.max_gap_frames) + 2

def test_m2_occluder_and_sky(tmp_job_dir):
    video_path = tmp_job_dir / "occluder.mp4"
    tmp_job_dir.mkdir(parents=True)
    gt_mask = make_test_video(video_path, "occluder", duration=2)

    cfg = PipelineConfig()
    cfg.frames.min_parallax_px = 5.0
    cfg.frames.max_gap_frames = 5
    cfg.masks.camera_attached_threshold = 0.5

    run_stages(video_path, tmp_job_dir, cfg, target_stage="s4_rig")

    mask_dir = tmp_job_dir / "job_behavior_s00" / "03_masks"
    masks = list(mask_dir.glob("*.png"))
    assert len(masks) > 0

    pred_mask = cv2.imread(str(masks[0]), cv2.IMREAD_GRAYSCALE)

    # Calculate IoU
    intersection = np.logical_and(pred_mask == 255, gt_mask == 255).sum()
    union = np.logical_or(pred_mask == 255, gt_mask == 255).sum()
    iou = intersection / union if union > 0 else 0
    assert iou >= 0.5, f"Occluder IoU too low: {iou}"

    fp = np.logical_and(pred_mask == 255, gt_mask == 0).sum()
    fp_frac = fp / (gt_mask == 0).sum()
    assert fp_frac < 0.05, f"False positive too high: {fp_frac}"

def test_m2_uniform_region_not_masked(tmp_job_dir):
    video_path = tmp_job_dir / "uniform.mp4"
    tmp_job_dir.mkdir(parents=True)
    make_test_video(video_path, "uniform_region", duration=2)

    cfg = PipelineConfig()
    cfg.frames.max_gap_frames = 5
    cfg.masks.camera_attached_threshold = 0.5

    run_stages(video_path, tmp_job_dir, cfg, target_stage="s3_masks")

    mask_dir = tmp_job_dir / "job_behavior_s00" / "03_masks"
    masks = list(mask_dir.glob("*.png"))
    assert len(masks) > 0

    pred_mask = cv2.imread(str(masks[0]), cv2.IMREAD_GRAYSCALE)
    # top half is uniform sky
    top_half = pred_mask[:pred_mask.shape[0]//2, :]
    assert np.mean(top_half) < 5.0
