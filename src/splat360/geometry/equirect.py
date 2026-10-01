import numpy as np

def pixels_to_rays(x: np.ndarray, y: np.ndarray, width: int, height: int) -> np.ndarray:
    """
    Convert equirectangular pixel coordinates to unit rays in the equirectangular frame.
    Convention: X right, Y down, Z forward.
    Center of image (x=width/2, y=height/2) points towards +Z.
    Top of image (y=0) points towards -Y (Up).
    """
    # Normalized coordinates
    u = (x + 0.5) / width
    v = (y + 0.5) / height
    
    # Angles
    lon = (u - 0.5) * 2 * np.pi
    lat = (0.5 - v) * np.pi
    
    # 3D vectors
    cos_lat = np.cos(lat)
    vec_x = cos_lat * np.sin(lon)
    vec_y = -np.sin(lat)
    vec_z = cos_lat * np.cos(lon)
    
    rays = np.stack([vec_x, vec_y, vec_z], axis=-1)
    return rays

def rays_to_pixels(rays: np.ndarray, width: int, height: int) -> tuple[np.ndarray, np.ndarray]:
    """
    Convert unit rays to equirectangular pixel coordinates.
    """
    # rays could be non-unit, normalize just in case
    norm = np.linalg.norm(rays, axis=-1, keepdims=True)
    rays_normalized = rays / (norm + 1e-8)
    
    vec_x, vec_y, vec_z = rays_normalized[..., 0], rays_normalized[..., 1], rays_normalized[..., 2]
    
    lon = np.arctan2(vec_x, vec_z)
    lat = np.arcsin(np.clip(-vec_y, -1.0, 1.0))
    
    u = lon / (2 * np.pi) + 0.5
    v = 0.5 - lat / np.pi
    
    x = u * width - 0.5
    y = v * height - 0.5
    
    return x, y
