"""
Responsibility: debug.py
Milestone: M2
"""

import cv2
import numpy as np


def create_debug_overlay(image_bgr: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """
    Create a debug overlay where the masked out regions are tinted red.
    """
    overlay = image_bgr.copy()
    red_tint = np.zeros_like(image_bgr)
    red_tint[:, :, 2] = 255  # Red channel

    # Blend red tint into masked areas
    overlay_tinted = cv2.addWeighted(overlay, 0.5, red_tint, 0.5, 0)

    # Apply tinted where mask == 255
    mask_bool = mask == 255
    overlay[mask_bool] = overlay_tinted[mask_bool]

    return overlay
