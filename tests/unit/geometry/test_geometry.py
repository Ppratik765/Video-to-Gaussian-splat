import numpy as np
import pytest

from splat360.geometry.equirect import pixels_to_rays, rays_to_pixels
from splat360.geometry.pinhole import unproject, fov_to_focal_length, get_pixel_grid
from splat360.geometry.rotations import R_y, R_x
from splat360.geometry.rig import get_rig
from splat360.geometry.remap import compute_remap_coordinates

def test_equirect_roundtrip():
    width, height = 512, 256
    xx, yy = np.meshgrid(np.arange(width), np.arange(height))
    
    rays = pixels_to_rays(xx, yy, width, height)
    xx_recon, yy_recon = rays_to_pixels(rays, width, height)
    
    # Precision issues near poles and seam might happen, but general pixels should match
    np.testing.assert_allclose(xx, xx_recon, atol=1.0)
    np.testing.assert_allclose(yy, yy_recon, atol=1.0)

def test_central_ray_matches_axis():
    rig = get_rig("cube6")
    width, height = 512, 256
    view_width, view_height = 256, 256
    
    expected_axes = {
        "front": np.array([0, 0, 1]),
        "right": np.array([1, 0, 0]),
        "back": np.array([0, 0, -1]),
        "left": np.array([-1, 0, 0]),
        "top": np.array([0, -1, 0]),
        "bottom": np.array([0, 1, 0]),
    }
    
    for view in rig:
        map_x, map_y = compute_remap_coordinates(view, view_width, view_height, width, height)
        # Center pixel of view
        cx = view_width // 2
        cy = view_height // 2
        px = map_x[cy, cx]
        py = map_y[cy, cx]
        
        ray = pixels_to_rays(np.array(px), np.array(py), width, height)
        ray_normalized = ray / np.linalg.norm(ray)
        
        np.testing.assert_allclose(ray_normalized, expected_axes[view.name], atol=1e-3)
