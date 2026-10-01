#!/usr/bin/env python3
import os
import cv2
import numpy as np
import argparse
import subprocess

def make_frame(t, duration, variant, width=960, height=480):
    img = np.zeros((height, width, 3), dtype=np.uint8)
    
    fps = 30
    total_frames = int(duration * fps)
    frame_idx = int(t * fps)
    
    if variant == "static":
        offset_x = 0
    elif variant == "fast":
        offset_x = int((t * 2.0) * width) % width # very fast pan
    else:
        offset_x = int((t / duration) * width) % width # normal pan, 100% width
        
    # Draw background grid shifted by offset_x
    for y in range(0, height, 40):
        cv2.line(img, (0, y), (width, y), (50, 50, 50), 2)
    for x in range(0, width, 40):
        shifted_x = (x + offset_x) % width
        cv2.line(img, (shifted_x, 0), (shifted_x, height), (50, 50, 50), 2)
        
    cv2.circle(img, ((width//2 + offset_x) % width, height // 2), 50, (0, 0, 255), -1)
    
    if variant == "blur":
        if frame_idx % 10 < 8:
            img = cv2.GaussianBlur(img, (51, 51), 0)
            
    return img

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", choices=["ok", "short", "blur", "fast", "static"], default="ok")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    
    duration = 6.0
    if args.variant == "short":
        duration = 1.0 # too short
        
    fps = 30
    width = 960
    height = 480
    
    out_file = args.output
    temp_file = out_file + ".avi"
    
    fourcc = cv2.VideoWriter_fourcc(*'XVID')
    out = cv2.VideoWriter(temp_file, fourcc, fps, (width, height))
    
    for i in range(int(duration * fps)):
        t = i / fps
        frame = make_frame(t, duration, args.variant, width, height)
        out.write(frame)
        
    out.release()
    
    # Convert to mp4 with ffmpeg and inject spherical metadata using a simple trick
    subprocess.run([
        "ffmpeg", "-y", "-i", temp_file,
        "-metadata:s:v:0", "spherical=true",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", out_file
    ], check=True)
    
    os.remove(temp_file)

if __name__ == "__main__":
    main()
