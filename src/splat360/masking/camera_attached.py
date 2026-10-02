"""
Responsibility: camera_attached.py
Milestone: M2
"""

import cv2
import numpy as np


def compute_camera_attached_mask(keyframes_gray: list[np.ndarray], variance_threshold: float) -> np.ndarray:
    """
    Compute a mask of camera-attached objects (tripod, etc.) using temporal variance.
    Returns a binary mask where 255 = camera-attached (exclude from SfM), 0 = static scene.
    """
    if not keyframes_gray:
        raise ValueError("No keyframes provided for camera_attached mask")

    stack = np.stack(keyframes_gray, axis=0) # (N, H, W)

    # Per-pixel variance
    variance = np.var(stack, axis=0) # (H, W)

    # Low variance = camera attached (it doesn't change over time as the scene moves)
    mask = (variance < variance_threshold).astype(np.uint8) * 255

    # Morphology to clean up noise
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
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
