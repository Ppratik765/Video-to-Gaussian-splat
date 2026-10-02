"""
Responsibility: camera_attached.py
Milestone: M2
"""

from typing import Any

import cv2
import numpy as np


def compute_camera_attached_mask(
    keyframes_gray: list[np.ndarray],
    variance_threshold: float,
    remaps: list[Any],
    equirect_shape: tuple[int, int]
) -> np.ndarray:
    """
    Compute a mask of camera-attached objects (tripod, etc.) using temporal variance.
    Returns a binary mask where 255 = camera-attached (exclude from SfM), 0 = static scene.
    """
    if not keyframes_gray:
        raise ValueError("No keyframes provided for camera_attached mask")

    stack = np.stack(keyframes_gray, axis=0) # (N, H, W)

    # Per-pixel variance
    variance = np.var(stack, axis=0) # (H, W)

    raw_mask = np.zeros(equirect_shape, dtype=np.uint8)

    for _v, map_x, map_y in remaps:
        map_x_int = np.clip(np.round(map_x).astype(np.int32), 0, equirect_shape[1] - 1).flatten()
        map_y_int = np.clip(np.round(map_y).astype(np.int32), 0, equirect_shape[0] - 1).flatten()

        view_var = variance[map_y_int, map_x_int]
        median_var = float(np.median(view_var))

        # Require global scene change to be present before declaring anything attached
        if median_var >= 5.0:
            low_var_mask = (view_var < (variance_threshold * median_var)) & (view_var < 5.0)
            raw_mask[map_y_int[low_var_mask], map_x_int[low_var_mask]] = 255

    # Morphology to clean up noise
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.morphologyEx(raw_mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    # Connected components: only keep large blobs
    num_labels, labels, stats, _centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)

    clean_mask = np.zeros_like(mask)
    h, w = mask.shape
    min_area = (h * w) * 0.001 # 0.1% of image area

    for i in range(1, num_labels):
        if stats[i, cv2.CC_STAT_AREA] >= min_area:
            clean_mask[labels == i] = 255

    return clean_mask
