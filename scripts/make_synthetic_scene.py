"""
Generate synthetic 360 (equirectangular) video clips for testing.

Usage:
    python scripts/make_synthetic_scene.py --variant pass --out out.mp4

Variants:
    pass        Lateral camera translation — should PASS preflight.
    short       Only 1 second — should REJECT (too_short).
    too_fast    Very fast translation — adjacent flow exceeds threshold.
    16_9        16:9 flat frame — should REJECT (not_equirect).
    1_1         1:1 frame — should REJECT (stereo_unsupported).
    pure_yaw    Pure camera rotation, no translation — should REJECT (rotation_dominated).
    static      No camera motion — should REJECT (no_parallax).
    hard_cut    Two distinct scenes with a hard cut at 6 s — PASS with 2 segments.
    blur        Heavy Gaussian blur on every frame — REJECT (excess_blur).

Requires ffmpeg on PATH (use ``shutil.which("ffmpeg")``).  If absent the script
skips the re-encode step and leaves a raw mp4v container instead, with a warning.

Design notes for reliable optical flow
---------------------------------------
We use a **texture-mapped equirectangular panorama** rendered by projecting a
fully filled 3-D environment directly into longitude/latitude space.  The
environment consists of:
  - A dense procedural checkerboard covering all 6 faces of a close cube
    (radius 30 units) so there are NO zero-flow regions.
  - Camera positions / rotations that produce analytically predictable flow.

This avoids the sparse-splatting problem (gaps between dots → unstable
least-squares) and ensures optical flow is reliable across the whole image.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np


def render_equirect_panorama(
    cam_pos: np.ndarray,
    cam_rot: np.ndarray,
    width: int = 320,
    height: int = 160,
    room_radius: float = 30.0,
    uniform_sky: bool = False,
    occluder: bool = False,
) -> np.ndarray:
    """
    Render a dense equirectangular panorama by ray-casting into a procedurally
    textured cube room.  Every pixel gets a colour — no holes.

    cam_pos: (3,) camera position in world coords
    cam_rot: (3, 3) rotation matrix mapping rig-frame to world-frame
    """
    img = np.zeros((height, width, 3), dtype=np.uint8)

    # Pixel grid → longitude / latitude
    u = np.arange(width, dtype=np.float32)
    v = np.arange(height, dtype=np.float32)
    uu, vv = np.meshgrid(u, v)

    lon = (uu / width - 0.5) * (2 * np.pi)       # -π … π
    lat = (0.5 - vv / height) * np.pi             # π/2 … -π/2

    # Ray directions in world frame (applying cam_rot)
    # In rig frame: x=right, y=up, z=forward (looking at lon=0)
    cx = np.cos(lat) * np.sin(lon)
    cy = np.sin(lat)
    cz = np.cos(lat) * np.cos(lon)
    rig_ray = np.stack([cx, cy, cz], axis=-1)   # (H, W, 3)

    # Rotate to world frame
    world_ray = rig_ray @ cam_rot.T             # (H, W, 3)

    # Ray-box intersection: find t for each face of the axis-aligned cube
    r = room_radius
    t_candidates = []
    for axis in range(3):
        for sign in (+1, -1):
            plane = sign * r
            d = world_ray[..., axis]

            # Avoid division by zero explicitly
            valid_d = np.abs(d) > 1e-6
            t = np.full_like(d, np.inf)
            t[valid_d] = (plane - cam_pos[axis]) / d[valid_d]
            valid = (t > 0.01) & valid_d

            # Compute intersection point explicitly for valid pixels only
            hit = np.zeros_like(world_ray)
            hit[valid] = cam_pos + t[valid, None] * world_ray[valid]  # (H, W, 3)

            # Check if within the cube
            other_axes = [i for i in range(3) if i != axis]
            in_bounds = np.all(np.abs(hit[..., other_axes]) <= r + 0.01, axis=-1)
            mask = valid & in_bounds

            t_candidates.append((t, mask, hit, axis, sign))

    # For each pixel, take the closest valid hit
    best_t = np.full((height, width), np.inf)
    best_color = np.zeros((height, width, 3), dtype=np.float32)

    for t, mask, hit, axis, sign in t_candidates:
        closer = mask & (t < best_t)
        best_t = np.where(closer, t, best_t)

        # Checkerboard texture on this face
        other = [i for i in range(3) if i != axis]
        u_tex = hit[..., other[0]]
        v_tex = hit[..., other[1]]

        # Checkerboard: 8x8 tiles
        check = ((np.floor(u_tex / (r / 4)) + np.floor(v_tex / (r / 4))).astype(int) % 2)
        # Face colour bias so different faces are visually distinct
        face_id = axis * 2 + (0 if sign > 0 else 1)
        hue_offset = face_id * (255 // 6)

        r_ch = (check * 200 + hue_offset) % 256
        g_ch = ((check * 180 + hue_offset * 2) % 256).astype(np.float32)
        b_ch = ((check * 160 + hue_offset * 3) % 256).astype(np.float32)

        face_color = np.stack([r_ch.astype(np.float32), g_ch, b_ch], axis=-1)
        best_color = np.where(closer[..., None], face_color, best_color)

    img = np.clip(best_color, 0, 255).astype(np.uint8)
    mask = np.zeros((height, width), dtype=np.uint8)

    if uniform_sky:
        img[:height//2, :] = [255, 200, 100]

    if occluder:
        # Fixed blob at nadir in camera frame (bottom of equirect)
        # Let's make it a noticeable bar
        img[-40:, width//3:2*width//3] = 128
        mask[-40:, width//3:2*width//3] = 255

    if occluder:
        return img, mask
    return img


def render_pass_frame(t: float, width: int, height: int, uniform_sky: bool = False, occluder: bool = False):
    """Lateral translation at 4 units/sec."""
    cam_pos = np.array([t * 4.0, 0.0, 0.0])
    cam_rot = np.eye(3)
    return render_equirect_panorama(cam_pos=cam_pos, cam_rot=cam_rot, width=width, height=height, room_radius=30.0, uniform_sky=uniform_sky, occluder=occluder)

    """Lateral translation at 4 units/sec."""
    cam_pos = np.array([t * 4.0, 0.0, 0.0])
    cam_rot = np.eye(3)
    return render_equirect_panorama( cam_pos, cam_rot, width, height)


def render_pure_yaw_frame(t: float, width: int, height: int) -> np.ndarray:
    """Pure yaw rotation at 20 deg/s -- zero translation.

    At 20 deg/s x 0.5s baseline = 10 deg of rotation.  This produces ~9 px
    equatorial flow at 320px width, which is within Farneback's tracking range.
    The rotation fit should give rotation_ratio > 0.35 (rotation dominated).
    """
    theta = t * np.radians(20)  # 20 deg/s
    cam_rot = np.array([
        [np.cos(theta), 0, np.sin(theta)],
        [0, 1, 0],
        [-np.sin(theta), 0, np.cos(theta)],
    ])
    cam_pos = np.zeros(3)
    return render_equirect_panorama( cam_pos, cam_rot, width, height)


def render_static_frame(width: int, height: int) -> np.ndarray:
    """Static camera."""
    return render_equirect_panorama(np.zeros(3), np.eye(3), width, height, uniform_sky=False, occluder=False)


def render_too_fast_frame(t: float, width: int, height: int) -> np.ndarray:
    """Very fast translation: ~20 units/sec → large adjacent-pair flow.
    Moves in a circle of radius 10 so it stays within the room.
    """
    omega = 2 * np.pi / 3.0  # 1 rev per 3 secs
    cam_pos = np.array([np.cos(omega * t) * 10.0 - 10.0, 0.0, np.sin(omega * t) * 10.0])
    cam_rot = np.eye(3)
    return render_equirect_panorama( cam_pos, cam_rot, width, height)



def render_variable_speed_frame(t: float, width: int, height: int):
    # 0-2s: fast (8 units/sec)
    # 2-4s: slow (2 units/sec)
    # 4-6s: stopped (0 units/sec)
    if t < 2.0:
        pos = t * 8.0
    elif t < 4.0:
        pos = 16.0 + (t - 2.0) * 2.0
    else:
        pos = 20.0
    cam_pos = np.array([pos, 0.0, 0.0])
    return render_equirect_panorama(cam_pos, np.eye(3), width, height, uniform_sky=False, occluder=False)

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="synth.mp4")
    parser.add_argument("--variant", default="pass")
    args = parser.parse_args()

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        print(
            "WARNING: ffmpeg not found on PATH. The output will be a raw mp4v container "
            "without H.264 re-encode. Tests may still work but metadata injection is skipped.",
            file=sys.stderr,
        )

    width, height = 320, 160
    fps = 10
    duration = 6.0

    if args.variant == "short":
        duration = 1.0
    elif args.variant == "too_fast":
        fps = 10
        duration = 6.0
    elif args.variant == "16_9":
        width, height = 320, 180
    elif args.variant == "1_1":
        width, height = 320, 320
    elif args.variant == "hard_cut":
        duration = 12.0

    total_frames = int(duration * fps)

    temp_mp4 = Path(args.out).with_suffix(".tmp.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(temp_mp4), fourcc, fps, (width, height))


    gt_mask = None
    for i in range(total_frames):
        t = i / fps

        if args.variant == "pass":
            img = render_pass_frame(t, width, height)
        elif args.variant == "occluder":
            img, gt_mask = render_pass_frame(t, width, height, occluder=True)
        elif args.variant == "uniform_region":
            img = render_pass_frame(t, width, height, uniform_sky=True)
        elif args.variant == "variable_speed":
            img = render_variable_speed_frame(t, width, height)
        elif args.variant == "pure_yaw":
            img = render_pure_yaw_frame(t, width, height)

        elif args.variant == "static":
            img = render_static_frame(width, height)

        elif args.variant == "too_fast":
            img = render_too_fast_frame(t, width, height)

        elif args.variant == "short":
            img = render_pass_frame(t, width, height)

        elif args.variant == "16_9":
            # Flat 16:9 — just a coloured rectangle
            img = np.zeros((height, width, 3), dtype=np.uint8)
            img[:] = (80, 120, 180)

        elif args.variant == "1_1":
            # Square — just a coloured rectangle
            img = np.zeros((height, width, 3), dtype=np.uint8)
            img[:] = (180, 80, 120)

        elif args.variant == "hard_cut":
            if t < 6.0:
                img = render_pass_frame(t, width, height)
            else:
                # Hard cut: different camera height to change appearance drastically
                cam_pos = np.array([(t - 6.0) * 4.0, 5.0, 0.0])
                img = render_equirect_panorama(cam_pos, np.eye(3), width, height, uniform_sky=False, occluder=False)

        elif args.variant == "blur":
            img = render_pass_frame(t, width, height)
            img = cv2.GaussianBlur(img, (21, 21), 0)

        else:
            img = render_static_frame(width, height)

        out.write(img)


    out.release()
    if gt_mask is not None:
        cv2.imwrite(str(Path(args.out).with_suffix('.mask.png')), gt_mask)


    if ffmpeg is None:
        # No re-encode: just rename temp to final.
        temp_mp4.replace(args.out)
        return

    # Re-encode to H.264 + inject spherical metadata if applicable.
    cmd = [
        ffmpeg, "-y", "-i", str(temp_mp4),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
    ]
    if args.variant not in ("16_9", "1_1"):
        cmd.extend([
            "-x264opts", "keyint=30",
            "-metadata:s:v:0", "spherical=true",
        ])
    cmd.append(args.out)

    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    temp_mp4.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
