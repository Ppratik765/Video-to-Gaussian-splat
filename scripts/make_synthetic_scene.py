import argparse
import subprocess
from pathlib import Path

import cv2
import numpy as np

from splat360.geometry.equirect import pixels_to_rays


def make_textured_room() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Creates a simple 3D room (a cube from -1 to 1) with textured walls.
    Returns: points (N, 3), colors (N, 3) representing the room walls.
    """
    # Just draw a few points on the walls of a cube
    pts = []
    colors = []

    # 6 faces
    for face in range(6):
        for y in np.linspace(-100, 100, 100):
            for x in np.linspace(-100, 100, 100):
                if face == 0:
                    p = np.array([x, y, 100.0])
                elif face == 1:
                    p = np.array([x, y, -100.0])
                elif face == 2:
                    p = np.array([100.0, x, y])
                elif face == 3:
                    p = np.array([-100.0, x, y])
                elif face == 4:
                    p = np.array([x, 100.0, y])
                elif face == 5:
                    p = np.array([x, -100.0, y])

                pts.append(p)
                # color based on position
                c = (np.sin(x*10)*127 + 128, np.cos(y*10)*127 + 128, (face/6)*255)
                colors.append(c)

    return np.array(pts), np.array(colors)

def render_equirect(pts, colors, cam_pos, cam_rot, width=320, height=160):
    """
    Given 3D points and colors, render an equirectangular image from cam_pos and cam_rot.
    This is a VERY crude point splatting renderer.
    """
    img = np.zeros((height, width, 3), dtype=np.uint8)

    # Grid of rays
    u, v = np.meshgrid(np.arange(width), np.arange(height))
    # map to equirect
    pixels_to_rays(u.astype(np.float32), v.astype(np.float32), width, height)

    # transform points to camera space
    # p_cam = R^T * (p - cam_pos)
    pts_cam = (pts - cam_pos) @ cam_rot

    # For each point, find the nearest ray.
    # To speed up, we project pts_cam to equirect
    # x, y, z in cam
    x, y, z = pts_cam[:, 0], pts_cam[:, 1], pts_cam[:, 2]
    r = np.linalg.norm(pts_cam, axis=-1)

    valid = r > 0.1
    x, y, z, r = x[valid], y[valid], z[valid], r[valid]
    c_valid = colors[valid]

    lon = np.arctan2(x, z)
    lat = np.arcsin(np.clip(-y / r, -1.0, 1.0))

    u_proj = (lon / (2 * np.pi) + 0.5) * width
    v_proj = (0.5 - lat / np.pi) * height

    u_proj = np.clip(np.round(u_proj).astype(int), 0, width - 1)
    v_proj = np.clip(np.round(v_proj).astype(int), 0, height - 1)

    # splat (z-buffer would be better, but points are drawn over each other,
    # order by depth descending)
    order = np.argsort(-r)
    u_proj = u_proj[order]
    v_proj = v_proj[order]
    c_valid = c_valid[order]

    img[v_proj, u_proj] = c_valid

    # Dilate slightly to fill holes
    img = cv2.dilate(img, np.ones((3,3), np.uint8))

    return img

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="synth.mp4")
    parser.add_argument("--variant", default="pass")
    args = parser.parse_args()

    width, height = 320, 160
    fps = 10
    duration = 6.0

    pts, colors = make_textured_room()

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

    temp_mp4 = "temp_render.mp4"
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(temp_mp4, fourcc, fps, (width, height))

    for i in range(total_frames):
        t = i / fps

        cam_pos = np.zeros(3)
        cam_rot = np.eye(3)

        if args.variant == "pass":
            # sin(t * 0.5 * pi) is 0 at t=0, 1 at t=1, 0 at t=2, -1 at t=3.
            # Delta pos is 1.0 unit. Flow is ~ 4.0 px.
            cam_pos[0] = np.sin(t * 0.5 * np.pi) * 1.0
        elif args.variant == "pure_yaw":
            # 0.15 rad/sec -> 6.0 px flow, which is high enough to overpower ~1px rendering noise,
            # but small enough for optical flow to track!
            theta = t * 0.15
            cam_rot = np.array([
                [np.cos(theta), 0, np.sin(theta)],
                [0, 1, 0],
                [-np.sin(theta), 0, np.cos(theta)]
            ])
        elif args.variant == "static":
            pass # stay at 0
        elif args.variant == "too_fast":
            # Delta pos is 8.0 unit -> flow ~ 32.0 px -> motion_too_fast
            cam_pos[0] = np.sin(t * 0.5 * np.pi) * 8.0
        elif args.variant == "hard_cut":
            cam_pos[0] = np.sin(t * 0.5 * np.pi) * 1.0
            if t > 6.0:
                # hard cut: change to another random pattern to avoid blur
                np.random.seed(42) # different seed
                colors = np.random.randint(0, 255, (len(pts), 3), dtype=np.uint8)

        img = render_equirect(pts, colors, cam_pos, cam_rot, width, height)

        if args.variant == "blur":
            img = cv2.GaussianBlur(img, (21, 21), 0)

        out.write(img)

    out.release()

    # Convert to final with spherical metadata
    cmd = [
        r"C:\Users\ppmak\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin\ffmpeg.exe", "-y", "-i", temp_mp4,
        "-c:v", "libx264", "-pix_fmt", "yuv420p"
    ]
    if args.variant not in ["16_9", "1_1"]:
        cmd.extend([
            "-x264opts", "keyint=30",
            "-metadata:s:v:0", "spherical=true"
        ])
    cmd.append(args.out)

    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    Path(temp_mp4).unlink(missing_ok=True)

if __name__ == "__main__":
    main()
