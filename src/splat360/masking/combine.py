"""
Responsibility: combine.py
Milestone: M2
"""

import cv2
import numpy as np


def combine_masks(
    equirect_shape: tuple[int, int],
    camera_attached_mask: np.ndarray | None = None,
    dynamic_mask: np.ndarray | None = None,
    manual_mask: np.ndarray | None = None,
    downweight_zenith_nadir: bool = False,
) -> np.ndarray:
    """
    Combine all masks into a single binary mask for the equirectangular image.
    255 = exclude (masked out), 0 = keep.
    """
    h, w = equirect_shape
    final_mask = np.zeros((h, w), dtype=np.uint8)

    if camera_attached_mask is not None:
        final_mask = cv2.bitwise_or(final_mask, camera_attached_mask)  # type: ignore

    if dynamic_mask is not None:
        # Dilate dynamic mask slightly
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
        dynamic_dilated = cv2.dilate(dynamic_mask, kernel)
        final_mask = cv2.bitwise_or(final_mask, dynamic_dilated)  # type: ignore

    if manual_mask is not None:
        # Assuming manual_mask is grayscale where >127 means exclude
        _, manual_bin = cv2.threshold(manual_mask, 127, 255, cv2.THRESH_BINARY)
        final_mask = cv2.bitwise_or(final_mask, manual_bin)  # type: ignore

    if downweight_zenith_nadir:
        # Optional: heavily mask out the top and bottom 5%
        band = int(h * 0.05)
        final_mask[:band, :] = 255
        final_mask[-band:, :] = 255

    return final_mask
