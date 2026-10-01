import numpy as np
import cv2

def compute_blur(image: np.ndarray) -> float:
    """
    Variance of Laplacian.
    Expects grayscale image.
    """
    return cv2.Laplacian(image, cv2.CV_64F).var()

def compute_exposure_flicker(luminance_sequence: list[float]) -> float:
    """
    Measure of exposure stability across frames.
    """
    if len(luminance_sequence) < 2:
        return 0.0
    arr = np.array(luminance_sequence)
    diffs = np.abs(np.diff(arr))
    return float(np.mean(diffs))

def compute_flow_parallax(flow: np.ndarray) -> tuple[float, float]:
    """
    Dense optical flow between two frames (e.g. from Farneback).
    Returns median flow magnitude and a rotation-vs-translation ratio proxy.
    """
    mag, ang = cv2.cartToPolar(flow[..., 0], flow[..., 1])
    median_mag = float(np.median(mag))
    
    # Very crude rotation vs translation separation proxy for M1:
    # If the camera purely rotates (yaws), flow magnitude is uniform across the horizontal band.
    # If the camera translates, flow is zero at the epipole (heading direction) and max at the sides.
    # We can measure the variance of the flow magnitude divided by the mean.
    # High variance = translation (or complex scene). Low variance = pure rotation.
    mean_mag = float(np.mean(mag))
    std_mag = float(np.std(mag))
    
    rot_ratio = 1.0
    if mean_mag > 0.5:
        rot_ratio = 1.0 - min(1.0, std_mag / mean_mag)
        
    return median_mag, rot_ratio
