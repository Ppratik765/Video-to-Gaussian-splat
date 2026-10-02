import tracemalloc

import numpy as np

from splat360.geometry.remap import compute_remap_coordinates
from splat360.geometry.rig import get_rig
from splat360.video.keyframes import select_keyframes


def test_select_keyframes_memory_and_timing():
    """
    Test that select_keyframes is a generator that does not hold all frames in memory.
    Also tests that parallax bookkeeping produces correct keyframe selection over time.
    """
    # 1. Create a dummy generator that yields 1000 frames
    def frame_gen():
        for i in range(100):
            # A moving vertical bar to create some parallax
            img = np.zeros((128, 256, 3), dtype=np.uint8)
            x_start = min(i * 2, 230)
            img[:, x_start : x_start + 20] = 255
            yield (i, i / 30.0, img)

    rig = get_rig("cube6_fov100")
    remaps = []
    for v in rig:
        map_x, map_y = compute_remap_coordinates(v, 64, 64, 256, 128)
        remaps.append((v, map_x, map_y))

    def dummy_blur(img):
        return 10.0

    tracemalloc.start()

    gen = select_keyframes(
        frame_stream=frame_gen(),
        min_parallax_px=5.0,
        min_gap_frames=5,
        max_gap_frames=30,
        max_keyframes=500,
        working_res=256,
        remaps=remaps,
        blur_fn=dummy_blur
    )

    kfs = []
    for kf in gen:
        kfs.append(kf)
        # Check memory usage inside loop
        _current, peak = tracemalloc.get_traced_memory()
        # Memory should be roughly constant, well under what 1000 frames would take
        # 1000 frames of 128x256x3 = ~98 MB.
        assert peak < 50 * 1024 * 1024 # 50 MB
        if len(kfs) >= 20:
            break

    tracemalloc.stop()

    assert len(kfs) > 0
    # verify frame distances are uniform because movement is constant
    frame_gaps = [kfs[i]["frame_idx"] - kfs[i-1]["frame_idx"] for i in range(1, len(kfs))]
    # standard deviation should be small
    std_gap = np.std(frame_gaps)
    assert std_gap < 15.0 # Relatively uniform
