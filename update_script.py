import re

with open('scripts/make_synthetic_scene.py', encoding='utf-8') as f:
    code = f.read()

# Add new variants
code = code.replace(
    'def render_equirect_panorama(',
    'def render_equirect_panorama(\n    uniform_sky: bool = False,\n    occluder: bool = False,'
)

code = code.replace(
    '    img = np.clip(best_color, 0, 255).astype(np.uint8)\n    return img',
    '''    img = np.clip(best_color, 0, 255).astype(np.uint8)
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
    return img'''
)

code = code.replace(
    'def render_pass_frame(t: float, width: int, height: int) -> np.ndarray:',
    '''def render_pass_frame(t: float, width: int, height: int, uniform_sky: bool = False, occluder: bool = False):
    """Lateral translation at 4 units/sec."""
    cam_pos = np.array([t * 4.0, 0.0, 0.0])
    cam_rot = np.eye(3)
    return render_equirect_panorama(uniform_sky=uniform_sky, occluder=occluder, cam_pos=cam_pos, cam_rot=cam_rot, width=width, height=height, room_radius=30.0)
'''
)

# Replace all other calls to render_equirect_panorama
code = re.sub(r'render_equirect_panorama\(cam_pos, cam_rot, width, height\)', r'render_equirect_panorama(False, False, cam_pos, cam_rot, width, height)', code)
code = re.sub(r'render_equirect_panorama\(np\.zeros\(3\), np\.eye\(3\), width, height\)', r'render_equirect_panorama(False, False, np.zeros(3), np.eye(3), width, height)', code)
code = re.sub(r'render_equirect_panorama\(cam_pos, np\.eye\(3\), width, height\)', r'render_equirect_panorama(False, False, cam_pos, np.eye(3), width, height)', code)


# variable speed
code = code.replace(
    'def main() -> None:',
    '''def render_variable_speed_frame(t: float, width: int, height: int):
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
    return render_equirect_panorama(False, False, cam_pos, np.eye(3), width, height)

def main() -> None:'''
)

# loop updates
loop_code = '''
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
'''
code = re.sub(r'    for i in range\(total_frames\):.*?(?=        elif args\.variant == "pure_yaw":)', loop_code, code, flags=re.DOTALL)

save_code = '''
    out.release()
    if gt_mask is not None:
        cv2.imwrite(str(Path(args.out).with_suffix('.mask.png')), gt_mask)
'''
code = code.replace('    out.release()', save_code)

with open('scripts/make_synthetic_scene.py', 'w', encoding='utf-8') as f:
    f.write(code)
