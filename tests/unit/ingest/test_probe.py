import cv2
import pytest
from pathlib import Path
from splat360.ingest.probe import probe_video


def test_probe_video_on_real_clip(tmp_path: Path):
    # Generate a tiny 1-second video
    video_path = tmp_path / "tiny.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(video_path), fourcc, 10, (320, 160))
    import numpy as np
    for _ in range(10):
        out.write(np.zeros((160, 320, 3), dtype=np.uint8))
    out.release()

    res = probe_video(video_path)
    assert res["resolution"] == [320, 160]
    # The exact duration and FPS reported by ffprobe for a 10-frame clip can vary slightly
    assert abs(res["fps"] - 10.0) < 1.0
    assert "duration" in res
    assert res["codec"] in ("mpeg4", "h264")
