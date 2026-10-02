"""
Camera-attached region detection (tripod, ride cart, selfie pole, nadir hole).

Method: per-pixel temporal variance of luminance over many keyframes, evaluated per rig view
relative to the view's own median variance. A pixel is "camera-attached" only if the scene as a
whole is changing (median view variance >= ``min_scene_variance``) while that pixel stays
nearly constant. Known limitation: uniform regions (clear sky, blank wall) also have low
variance and cannot be told apart from attached hardware by variance alone; use
``masks/manual_equirect.png`` or tune the thresholds for such footage.
"""

from collections.abc import Iterable
from typing import Any

import cv2
import numpy as np


def compute_temporal_variance(frames_gray: Iterable[np.ndarray]) -> np.ndarray:
    """Streaming per-pixel variance (Welford). Holds one frame plus two float32 maps in RAM."""
    count = 0
    mean: np.ndarray | None = None
    m2: np.ndarray | None = None
    for gray in frames_gray:
        x = gray.astype(np.float32)
        if mean is None or m2 is None:
            mean = np.zeros_like(x)
            m2 = np.zeros_like(x)
        count += 1
        delta = x - mean
        mean += delta / count
        m2 += delta * (x - mean)
    if count == 0 or m2 is None:
        raise ValueError("No keyframes provided for camera_attached mask")
    return np.asarray(m2 / count, dtype=np.float32)


def camera_attached_mask_from_variance(
    variance: np.ndarray,
    variance_threshold: float,
    remaps: list[Any],
    equirect_shape: tuple[int, int],
    min_scene_variance: float = 5.0,
    max_attached_variance: float = 5.0,
    min_blob_fraction: float = 0.001,
) -> np.ndarray:
    """
    Returns a binary equirect mask: 255 = camera-attached (exclude), 0 = static scene.

    variance_threshold: pixel must be below this fraction of the view's median variance.
    min_scene_variance: median view variance required before anything may be declared attached.
    max_attached_variance: absolute variance ceiling for an attached pixel.
    min_blob_fraction: connected components smaller than this fraction of the image are dropped.
    """
    raw_mask = np.zeros(equirect_shape, dtype=np.uint8)

    for _v, map_x, map_y in remaps:
        map_x_int = np.clip(np.round(map_x).astype(np.int32), 0, equirect_shape[1] - 1).flatten()
        map_y_int = np.clip(np.round(map_y).astype(np.int32), 0, equirect_shape[0] - 1).flatten()

        view_var = variance[map_y_int, map_x_int]
        median_var = float(np.median(view_var))

        # Require global scene change before declaring anything attached
        if median_var >= min_scene_variance:
            low_var = (view_var < (variance_threshold * median_var)) & (
                view_var < max_attached_variance
            )
            raw_mask[map_y_int[low_var], map_x_int[low_var]] = 255

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.morphologyEx(raw_mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    num_labels, labels, stats, _centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)

    clean_mask = np.zeros_like(mask)
    h, w = mask.shape
    min_area = (h * w) * min_blob_fraction

    for i in range(1, num_labels):
        if stats[i, cv2.CC_STAT_AREA] >= min_area:
            clean_mask[labels == i] = 255

    return clean_mask


def compute_camera_attached_mask(
    keyframes_gray: list[np.ndarray],
    variance_threshold: float,
    remaps: list[Any],
    equirect_shape: tuple[int, int],
    **kwargs: float,
) -> np.ndarray:
    """In-memory convenience wrapper (tests, small inputs)."""
    variance = compute_temporal_variance(keyframes_gray)
    return camera_attached_mask_from_variance(
        variance, variance_threshold, remaps, equirect_shape, **kwargs
    )
