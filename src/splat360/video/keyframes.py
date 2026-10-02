"""
Responsibility: keyframes.py
Milestone: M2
"""

from typing import Any

import cv2

from splat360.gate.metrics import compute_flow_parallax
from splat360.geometry.pinhole import fov_to_focal_length
from splat360.geometry.remap import remap_image


def select_keyframes(
    frame_stream: Any,  # Iterator yielding (frame_idx, timestamp_sec, frame_bgr)
    min_parallax_px: float,
    min_gap_frames: int,
    max_gap_frames: int,
    max_keyframes: int,
    working_res: int,
    remaps: list[Any],
    blur_fn: Any,
) -> list[dict[str, Any]]:
    """
    Select keyframes by accumulated translation-induced parallax.

    Args:
        frame_stream: Iterator of (frame_idx, timestamp, image)
        working_res: Width for downscaling before flow calculation
        remaps: Precomputed remap coordinates [(RigView, map_x, map_y), ...]
        blur_fn: Function to compute blur score of a frame

    Returns:
        List of dicts with keys: frame_idx, timestamp, blur, parallax
    """
    selected: list[dict[str, Any]] = []

    prev_gray = None
    accumulated_parallax = 0.0
    frames_since_last_keyframe = 0

    # Track the sharpest frame within the window
    best_candidate = None
    best_candidate_blur = -1.0
    best_candidate_gray = None

    for frame_idx, t_sec, frame_bgr in frame_stream:
        # Resize to working resolution
        _h, _w = frame_bgr.shape[:2]
        small_h = working_res // 2
        small = cv2.resize(frame_bgr, (working_res, small_h))
        curr_gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

        # Calculate blur on the central view
        _v0, map_x0, map_y0 = remaps[0]
        view_front = remap_image(curr_gray, map_x0, map_y0)
        curr_blur = blur_fn(view_front)

        frames_since_last_keyframe += 1

        # Keep track of the sharpest frame in the current window
        if curr_blur > best_candidate_blur:
            best_candidate_blur = curr_blur
            best_candidate = (frame_idx, t_sec, curr_blur, accumulated_parallax, frame_bgr)
            best_candidate_gray = curr_gray

        if prev_gray is not None:
            # Compute flow across rig views
            flow_views = []
            view_w = working_res // 4
            view_h = working_res // 4
            for v, map_x, map_y in remaps:
                v1_r = remap_image(prev_gray, map_x, map_y)
                v2_r = remap_image(curr_gray, map_x, map_y)
                flow = cv2.calcOpticalFlowFarneback(
                    v1_r, v2_r, None, 0.5, 3, 15, 3, 5, 1.2, 0
                )  # type: ignore[call-overload]
                fl = fov_to_focal_length(v.fov_deg, view_w)
                flow_views.append((flow, fl, view_w / 2.0, view_h / 2.0, v.cam_from_rig))

            median_res, _rot, _ratio = compute_flow_parallax(flow_views)
            accumulated_parallax += median_res

        prev_gray = curr_gray

        # Decide whether to emit a keyframe
        keep = False

        if len(selected) == 0:
            # Always keep the first frame
            keep = True
        elif frames_since_last_keyframe >= max_gap_frames:
            # Continuity rule: forced to keep the best candidate we saw
            keep = True
        elif frames_since_last_keyframe >= min_gap_frames and accumulated_parallax >= min_parallax_px:
            keep = True

        if keep:
            # Emit the best candidate found in the window
            if best_candidate is not None:
                cand_idx, cand_t, cand_blur, cand_px, cand_bgr = best_candidate
                selected.append({
                    "frame_idx": cand_idx,
                    "timestamp": cand_t,
                    "blur": cand_blur,
                    "parallax": cand_px,
                    "image": cand_bgr
                })
                # Reset accumulators, starting from the chosen candidate
                accumulated_parallax = 0.0
                frames_since_last_keyframe = frame_idx - cand_idx
                best_candidate_blur = -1.0
                best_candidate = None
                prev_gray = best_candidate_gray

                # If we've hit max keyframes, we're done
                if len(selected) >= max_keyframes:
                    break
            else:
                # Fallback if no candidate was found (shouldn't happen)
                selected.append({
                    "frame_idx": frame_idx,
                    "timestamp": t_sec,
                    "blur": curr_blur,
                    "parallax": accumulated_parallax,
                    "image": frame_bgr
                })
                accumulated_parallax = 0.0
                frames_since_last_keyframe = 0
                best_candidate_blur = -1.0
                best_candidate = None

    return selected
