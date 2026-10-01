REASON_CODES = {
    "not_equirect": "Input is not a 2:1 equirectangular video.",
    "stereo_unsupported": "Input appears to be stereo (1:1 aspect ratio), which is configured to be rejected.",
    "no_parallax": "Camera is completely static. No translation parallax is present to infer 3D structure.",
    "rotation_dominated": "Camera motion is purely rotational. No parallax to infer depth.",
    "motion_too_fast": "Camera motion is too fast, leading to excessive motion blur and poor overlap.",
    "excess_blur": "Too many frames are excessively blurry.",
    "exposure_unstable": "Exposure changes drastically between frames.",
    "camera_attached_occlusion": "A large portion of the scene is blocked by a camera-attached occluder (e.g., rider, helmet).",
    "high_dynamic_content": "A large portion of the scene contains dynamic objects (people, vehicles).",
    "low_texture": "Scene has very low texture (e.g., mostly sky, water, or night).",
    "too_short": "Video segment is too short.",
    "sfm_low_registration": "COLMAP failed to register enough keyframes.",
    "sfm_fragmented": "COLMAP model is fragmented into multiple disconnected components.",
    "sfm_high_reproj_error": "COLMAP reprojection error is too high.",
    "sfm_insufficient_baseline": "SfM baseline is insufficient for reliable 3D structure."
}

def get_reason_message(code: str) -> str:
    return REASON_CODES.get(code, f"Unknown reason code: {code}")
