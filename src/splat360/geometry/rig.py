from dataclasses import dataclass

import numpy as np

from splat360.geometry.rotations import R_x, R_y


@dataclass
class ViewDefinition:
    name: str
    fov_deg: float
    cam_from_rig: np.ndarray  # 3x3 rotation matrix

def _get_cube_views(fov_deg: float) -> list[ViewDefinition]:
    return [
        ViewDefinition("front", fov_deg, np.eye(3)),
        ViewDefinition("right", fov_deg, R_y(-np.pi / 2)),
        ViewDefinition("back", fov_deg, R_y(np.pi)),
        ViewDefinition("left", fov_deg, R_y(np.pi / 2)),
        ViewDefinition("top", fov_deg, R_x(-np.pi / 2)),
        ViewDefinition("bottom", fov_deg, R_x(np.pi / 2)),
    ]

def get_rig(preset_name: str) -> list[ViewDefinition]:
    if preset_name == "cube6":
        return _get_cube_views(90.0)
    elif preset_name == "cube6_fov100":
        return _get_cube_views(100.0)
    elif preset_name == "ring8_poles":
        views = []
        for i in range(8):
            yaw = i * (np.pi / 4)
            views.append(ViewDefinition(f"ring_{i}", 90.0, R_y(-yaw)))
        views.append(ViewDefinition("top", 90.0, R_x(-np.pi / 2)))
        views.append(ViewDefinition("bottom", 90.0, R_x(np.pi / 2)))
        return views
    else:
        raise ValueError(f"Unknown rig preset: {preset_name}")
