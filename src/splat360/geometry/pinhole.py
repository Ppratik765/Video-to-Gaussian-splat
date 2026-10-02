import numpy as np


def fov_to_focal_length(fov_deg: float, size: int) -> float:
    """Convert field of view in degrees to focal length in pixels."""
    fov_rad = np.radians(fov_deg)
    return float((size / 2.0) / np.tan(fov_rad / 2.0))

def get_pixel_grid(width: int, height: int) -> tuple[np.ndarray, np.ndarray]:
    """Return meshgrid of pixel coordinates (x, y)."""
    x = np.arange(width)
    y = np.arange(height)
    xs, ys = np.meshgrid(x, y)
    return xs, ys

def unproject(x: np.ndarray, y: np.ndarray, focal_length: float, cx: float, cy: float) -> np.ndarray:
    """
    Unproject pixel coordinates to rays in the local pinhole camera frame.
    Camera looks down +Z, X is right, Y is down.
    """
    z = np.ones_like(x, dtype=np.float32)
    dir_x = (x - cx) / focal_length
    dir_y = (y - cy) / focal_length

    rays = np.stack([dir_x, dir_y, z], axis=-1)

    # Normalize rays
    norm = np.linalg.norm(rays, axis=-1, keepdims=True)
    return rays / norm  # type: ignore[no-any-return]
