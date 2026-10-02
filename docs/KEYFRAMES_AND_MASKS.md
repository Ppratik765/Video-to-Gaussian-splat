# Keyframes and Masks (M2a)

All thresholds below are **provisional**: they were chosen on synthetic scenes only and have
not been validated on real 360 footage (that is M2b).

## S2 keyframe selection (`video/keyframes.py`)
- Streaming decode (`video/decode.py`); frames are consumed one at a time. `select_keyframes`
  is a generator: each keyframe is written to disk as soon as it is emitted, so memory does
  not grow with clip length. Only one candidate frame is held at a time.
- Per consecutive frame pair, dense Farneback flow is computed on the six rig views
  (cube6_fov100 at `preflight.working_resolution`). A global angular velocity is fitted by
  least squares and subtracted (`gate/metrics.py::compute_flow_parallax`); the median residual
  is the translation-induced parallax. Parallax is accumulated in `cumulative_parallax`.
- A keyframe is emitted when `frames_since_last >= min_gap_frames` and parallax since the last
  keyframe `>= min_parallax_px`, or when `max_gap_frames` is reached (continuity rule). The
  emitted frame is the sharpest in the window (Laplacian variance on the front view).
  After emitting candidate `c`, the accumulator becomes `cum[current] - cum[c]`, so no
  parallax between the candidate and the current frame is lost.
- Capped at `frames.max_keyframes`. Output: `02_frames/<id>.jpg` (quality `frames.jpeg_quality`)
  and `frame_index.csv` (`keyframe_id, source_frame, timestamp, blur, parallax`).

## S3 masks (`masking/`, `stages/s3_masks.py`)
Masks are produced in **equirect space** (255 = exclude) and reprojected by S4 with the same
geometry as the images.
1. **Camera-attached**: streaming per-pixel temporal luminance variance (Welford; one frame in
   RAM at a time). Per rig view, a pixel is attached if its variance is below
   `masks.camera_attached_threshold` x the view's median variance AND below
   `masks.camera_attached_max_variance`, and only if the view's median variance is at least
   `masks.camera_attached_min_scene_variance` (the scene must actually be changing). Then
   morphology (open + close) and removal of blobs smaller than
   `masks.camera_attached_min_blob_fraction` of the image.
2. **Dynamic objects**: `Segmenter` interface. `NullSegmenter` is the default;
   `HFSegmenter` (SegFormer-b0 or Mask2Former-tiny, ADE20K) is optional, lazily imported, and
   only used when `masks.segmenter` is set. See `docs/THIRD_PARTY.md` for the license status.
3. **Manual override**: `<job>/masks/manual_equirect.png` (white = exclude) is OR-merged and
   resized (nearest) if its size differs.
4. Optional zenith/nadir band exclusion (`masks.downweight_zenith_nadir`).
5. Debug overlays for about 8 keyframes in `03_masks/debug/`.

### Measured behavior and known limitations (synthetic only)
- On the synthetic nadir-occluder clip: IoU about **0.61** and false-positive fraction about
  **0.04** against the known occluder mask. The spec target of IoU >= 0.8 is **not met**.
- Cause: variance alone also flags low-variance scene regions. Directions along the translation
  axis (the epipoles) barely change, and flat-colored room surfaces have low variance. A dense
  per-pixel low-variance mask scores about the same (IoU about 0.58), so this is not a
  sampling or morphology problem.
- A uniform sky region is not masked in the sky test clip, but only because the synthetic
  room's global variance is high; it is not a general guarantee. Real clear-sky footage may be
  masked as "attached". Use the manual override or tune the thresholds on such footage.
- Real camera-attached hardware (ride cart, pole) has not been tested. M2b must review the
  debug overlays on real footage.

## S4 rig views (`stages/s4_rig.py`)
Keyframes and masks are rendered into the configured preset (default `cube6_fov100`, view size
`rig.view_size`, default 1600). Images use Lanczos; masks use nearest. Output:
`04_views/images/<kf>_<view>.jpg`, `04_views/masks/<kf>_<view>.png`, and a neutral `rig.json`
(view name, FOV, rotation). The COLMAP-specific rig config is deliberately deferred to M3.

## Caching
S2, S3 and S4 each fingerprint their config plus a code version. Unchanged inputs skip the
stage for a child segment; a changed threshold reruns it (tested). Fixed in this milestone: the
skip check compared against `"DONE"` while the manifest stores `"done"`, so these stages never
skipped before.
