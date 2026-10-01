import cv2
import numpy as np

from splat360.geometry.equirect import rays_to_pixels
from splat360.geometry.pinhole import fov_to_focal_length, get_pixel_grid, unproject
from splat360.geometry.rig import ViewDefinition


def compute_remap_coordinates(
    view: ViewDefinition,
    view_width: int,
    view_height: int,
    equi_width: int,
    equi_height: int
) -> tuple[np.ndarray, np.ndarray]:
    """
    Compute mapping maps (map_x, map_y) for cv2.remap.
    """
    focal_length = fov_to_focal_length(view.fov_deg, view_width)
    cx = view_width / 2.0
    cy = view_height / 2.0

    xx, yy = get_pixel_grid(view_width, view_height)

    # Rays in pinhole local frame
    local_rays = unproject(xx, yy, focal_length, cx, cy)

    # Rig rotation (cam_from_rig) takes rig points to camera.
    # So to go from camera to rig (world), we multiply by transpose(cam_from_rig).
    rig_from_cam = view.cam_from_rig.T
    world_rays = np.einsum('ij,...j->...i', rig_from_cam, local_rays)

    # World rays to equirectangular pixels
    map_x, map_y = rays_to_pixels(world_rays, equi_width, equi_height)

    return map_x.astype(np.float32), map_y.astype(np.float32)

def remap_image(equi_img: np.ndarray, map_x: np.ndarray, map_y: np.ndarray, is_mask: bool = False) -> np.ndarray:
    """
    Apply cv2.remap. Uses Lanczos4 for images and Nearest for masks.
    Handles wraparound for equirectangular X coordinate seamlessly by wrapping map_x.
    """
    # map_x might be out of bounds, but cv2.remap with BORDER_WRAP can handle it
    # We explicitly wrap map_x for safety
    h, w = equi_img.shape[:2]

    # map_x is wrapped around W
    map_x_wrapped = np.mod(map_x, w).astype(np.float32)
    # map_y is clamped
    map_y_clamped = np.clip(map_y, 0, h - 1).astype(np.float32)

    interpolation = cv2.INTER_NEAREST if is_mask else cv2.INTER_LANCZOS4

    # remap
    result = cv2.remap(
        equi_img,
        map_x_wrapped,
        map_y_clamped,
        interpolation=interpolation,
        borderMode=cv2.BORDER_WRAP
    )
    return result
