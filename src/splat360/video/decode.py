"""
Responsibility: decode.py
Milestone: M0
"""

from collections.abc import Iterator

import cv2
import numpy as np


def stream_decode(video_path: str, start_sec: float, end_sec: float) -> Iterator[tuple[int, float, np.ndarray]]:
    """
    Stream-decode a segment of a video.
    Yields (frame_index, timestamp_sec, frame_bgr).
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 30.0

    cap.set(cv2.CAP_PROP_POS_MSEC, start_sec * 1000)
    start_frame = int(cap.get(cv2.CAP_PROP_POS_FRAMES))

    frame_idx = start_frame
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        t_sec = frame_idx / fps
        if t_sec > end_sec:
            break

        yield frame_idx, t_sec, frame
        frame_idx += 1

    cap.release()
