# Splat360: 360° Video → 3D Gaussian Splat Pipeline

> **TO THE AGENT: this entire file is your specification.**
> **Your CURRENT ASSIGNMENT is milestone M0 ONLY (section 12).**
> 1. Save this file verbatim as `docs/SPEC.md` in the repository (first commit).
> 2. Build M0, verify it, write the status report defined in section 14, then **STOP**.
> 3. Do **not** begin M1 or any later milestone until the user assigns it explicitly in a later message.
> Later milestones are described here only so that M0's architecture does not block them.

---

## 0. Working rules for the agent (read first)

1. **Verify, don't recall.** The libraries here (COLMAP/pycolmap, gsplat, yt-dlp, transformers, SAM 2) change fast. Before using any API, check its *current* official docs or installed version (`pip show`, `--help`, source). Pin exact versions in `requirements*.txt`. If a recipe in this spec no longer works, find the current equivalent and record it in `docs/DECISIONS.md` (what changed, why).
2. **Never fabricate results.** No invented metrics, no mocked "success" output. If a stage cannot run in the current environment (e.g. no CUDA on the local machine), it must fail loudly with a clear message, not silently degrade.
3. **Small, reviewable commits** with conventional messages (`feat(ingest): ...`). Commit after each working sub-feature.
4. **Everything is resumable and idempotent.** Re-running a stage with unchanged inputs and config must skip work (hash-based cache, see section 4).
5. **Typed, tested, documented.** Python ≥3.10, full type hints, `ruff` + `mypy` clean, `pytest` for every module that can be tested without a GPU.
6. **Stop at milestone boundaries** and report: what was built, what was verified (with commands and output), what is uncertain, what you need from me.
7. **Ask before deviating** from this spec on anything architectural. Small implementation choices are yours; log them in `docs/DECISIONS.md`.
8. **Licensing hygiene.** Use permissively licensed components (Apache-2.0/BSD/MIT). Do NOT use the original Inria `diff-gaussian-rasterization` (non-commercial license). Ultralytics/YOLO is AGPL, so avoid it as a hard dependency. Record every third-party license in `docs/THIRD_PARTY.md`.

---

## 1. Project goal and scope

**Goal:** an automatic, resumable command-line pipeline that takes a 360° (equirectangular) video, decides whether it is reconstructable, and if so produces a high-quality 3D Gaussian splat (`.ply`, optional compressed formats) plus a quality report.

**Key facts that shape the design**
- 3DGS is *per-scene optimization*, not a trained model. **There is no neural network to train and no dataset to collect.** Do not add one.
- Quality is determined mostly by **frame selection, masking, and camera poses**, so those stages get the most engineering effort.
- Compute target: **Google Colab A100 GPU** (typically 40 GB VRAM; auto-detect and scale to whatever VRAM is actually present, including 80 GB variants, and degrade gracefully on smaller GPUs such as L4 24 GB). Not TPU. Colab VMs have limited CPU cores, so decode, optical flow, and image resampling must be efficient (streaming, multiprocessing, GPU where available). The local machine (Antigravity) may have no CUDA: all CPU-capable logic must be developed and unit-tested locally; GPU stages run in Colab.
- Inputs: YouTube 360 videos for which I have the uploader's **permission** (I will supply them as local files or URLs). Examples: an amusement-park ride (fast camera motion) and a multi-scene video (needs scene splitting).

**Non-goals (v1):** training any custom neural network, TPU support, dynamic/4D scenes, metric scale recovery, real-time web service, stereo/VR180 reconstruction (detect and reject or take one eye, see 5.2).

---

## 2. Architecture overview

```
 URL / local file
      │
 [S0 Ingest] ─► [S1 Preflight gate + scene split] ─► REJECT? ─► report
      │
 [S2 Frame extraction & keyframe selection]
      │
 [S3 Masking (camera-attached, dynamic, nadir)]
      │
 [S4 Equirect → perspective rig views]
      │
 [S5 SfM with rig constraints (COLMAP)] ─► [S6 Post-SfM gate] ─► REJECT? ─► report
      │
 [S7 Gaussian splat training (gsplat)]
      │
 [S8 Cleanup, export, evaluation, fly-through render]
      │
 [S9 Report (JSON + Markdown/HTML)]
```

Each stage is a class implementing a common interface (section 4). One **job** = one video segment (a video with N scenes becomes N jobs).

---

## 3. Repository layout

**Design principles**
- `stages/` files are **thin orchestrators** (read inputs, call library code, write outputs, update the manifest). All real logic lives in the subpackages so it can be unit-tested without running a stage.
- **Every module is importable on a CPU-only machine.** GPU/CUDA libraries (torch CUDA ops, gsplat, pycolmap-CUDA, SAM 2) are imported lazily inside the functions that need them, with a clear error if missing.
- One responsibility per module; no module above ~400 lines; no circular imports (`geometry`, `utils`, and `io` are leaf packages that import nothing from `stages`).
- `tests/` mirrors `src/splat360/` one-to-one.
- Names below are the **target layout**: create the full skeleton in M0 (empty modules with docstrings stating their responsibility and the milestone that fills them in), so the architecture is visible from day one.

```
splat360/
├─ .github/
│  ├─ workflows/
│  │  ├─ ci.yml                    # ruff + mypy + pytest (CPU only) on push/PR
│  │  └─ docs-check.yml            # fails if ARCHITECTURE.md references missing modules
│  ├─ ISSUE_TEMPLATE/
│  │  ├─ bug_report.md
│  │  └─ rejected_video.md         # template: attach report.json for gate false-positives
│  └─ pull_request_template.md
├─ .gitignore                      # workspace/, *.ply, *.mp4, checkpoints, caches, .ipynb_checkpoints
├─ .gitattributes                  # normalize line endings; mark notebooks as linguist-documentation
├─ .editorconfig
├─ .pre-commit-config.yaml         # ruff, ruff-format, mypy, nbstripout, end-of-file-fixer
├─ LICENSE                         # Apache-2.0 (confirm with the user before committing)
├─ CITATION.cff
├─ CHANGELOG.md                    # keep-a-changelog format, updated per milestone
├─ CONTRIBUTING.md                 # dev setup, commit style, how to add a stage/metric/preset
├─ README.md                       # what it does, quickstart, honest limitations, results gallery
├─ pyproject.toml                  # package metadata, entry point `splat360`, ruff/mypy/pytest config
├─ requirements.txt                # CPU-safe core deps, pinned
├─ requirements-gpu.txt            # CUDA stack: torch, gsplat, pycolmap/colmap, SAM 2, transformers, pinned
├─ requirements-dev.txt            # pytest, ruff, mypy, pre-commit, types-*
├─ Makefile                        # make setup | lint | fmt | typecheck | test | docs | clean
│
├─ docs/
│  ├─ SPEC.md                      # this file, verbatim
│  ├─ ARCHITECTURE.md              # data flow, stage contracts, coordinate conventions (kept in sync)
│  ├─ DECISIONS.md                 # dated ADR-style log of choices and deviations from SPEC
│  ├─ STATUS.md                    # per-milestone status reports (section 14), newest first
│  ├─ COLAB.md                     # exact working Colab setup recipe, with versions and known issues
│  ├─ GATE_METRICS.md              # definition, formula, rationale and calibrated threshold per gate metric
│  ├─ COORDINATE_CONVENTIONS.md    # equirect axes, rig rotations, COLMAP/gsplat convention conversions
│  ├─ DATA_FORMATS.md              # manifest.json, source.json, report.json, frame_index.csv, rig_config.json schemas
│  ├─ PRESETS.md                   # what each preset changes and when to use it
│  ├─ TROUBLESHOOTING.md           # symptom → cause → fix (SfM fails, OOM, 429 from YouTube, ...)
│  ├─ THIRD_PARTY.md               # every dependency, version, license, why it was chosen
│  ├─ ETHICS_AND_LICENSING.md      # permission-note policy, YouTube ToS notes, dataset/redistribution rules
│  └─ images/                      # diagrams and README figures (small, optimized)
│
├─ configs/
│  ├─ default.yaml                 # every tunable, documented inline
│  ├─ preset_walkthrough.yaml
│  ├─ preset_ride_fast.yaml
│  ├─ preset_drone.yaml
│  ├─ gate_thresholds.yaml         # all gate thresholds in one place, each marked provisional|calibrated
│  ├─ rigs/
│  │  ├─ cube6.yaml
│  │  ├─ cube6_fov100.yaml         # default
│  │  └─ ring8_poles.yaml
│  └─ schema/
│     └─ config.schema.json        # generated from the pydantic models (make docs)
│
├─ src/splat360/
│  ├─ __init__.py                  # version only
│  ├─ __main__.py                  # python -m splat360
│  ├─ cli.py                       # argparse/typer commands: run, stage, inspect, report, clean, doctor
│  ├─ config.py                    # pydantic models, YAML loading, preset merge, --set overrides
│  ├─ job.py                       # Job, workspace paths, manifest read/write, fingerprints
│  ├─ errors.py                    # typed exceptions (StageFailed, GateRejected, MissingDependency, ...)
│  ├─ constants.py                 # reason codes, stage names, file names (single source of truth)
│  │
│  ├─ stages/                      # thin orchestrators, one per pipeline stage
│  │  ├─ __init__.py               # STAGE_REGISTRY, ordering and dependency graph
│  │  ├─ base.py                   # Stage ABC, StageResult, caching/skip logic
│  │  ├─ s0_ingest.py
│  │  ├─ s1_preflight.py
│  │  ├─ s2_frames.py
│  │  ├─ s3_masks.py
│  │  ├─ s4_rig.py
│  │  ├─ s5_sfm.py
│  │  ├─ s6_postsfm_gate.py
│  │  ├─ s7_train.py
│  │  ├─ s8_export_eval.py
│  │  └─ s9_report.py
│  │
│  ├─ ingest/
│  │  ├─ downloader.py             # yt-dlp wrapper, format selection, cookies option, retry/backoff
│  │  ├─ local_source.py           # local file validation and copy/symlink
│  │  ├─ probe.py                  # ffprobe parsing, spherical side data, rotation flags
│  │  └─ permission.py             # permission-note enforcement and recording
│  │
│  ├─ geometry/                    # pure numpy, no I/O, most heavily tested package
│  │  ├─ equirect.py               # pixel <-> unit ray <-> (lon, lat), seam handling
│  │  ├─ rotations.py              # rotation matrices, quaternions, conversions, composition
│  │  ├─ pinhole.py                # intrinsics from FOV/size, projection and unprojection
│  │  ├─ rig.py                    # rig definitions, cam_from_rig extrinsics, presets
│  │  ├─ remap.py                  # equirect -> perspective sampling maps (CPU + optional GPU)
│  │  ├─ coverage.py               # angular coverage and overlap metrics between rig views
│  │  └─ transforms.py             # Sim3 normalization, applying/inverting scene transforms
│  │
│  ├─ video/
│  │  ├─ decode.py                 # streaming frame iterator (ffmpeg/PyAV), hw decode when available
│  │  ├─ scene_detect.py           # hard-cut detection, user timestamp parsing and override
│  │  ├─ keyframes.py              # parallax-driven keyframe selection with min/max gap logic
│  │  ├─ flow.py                   # optical flow (CPU fallback + GPU), rotation/translation separation
│  │  ├─ quality.py                # blur, exposure flicker, texture measures
│  │  └─ writer.py                 # lossless-ish image writing, video writing for renders
│  │
│  ├─ masking/
│  │  ├─ camera_attached.py        # temporal-variance detector for ride cart, pole, tripod, nadir
│  │  ├─ semantic.py               # SegFormer/Mask2Former dynamic-class masks
│  │  ├─ sam_refine.py             # optional SAM 2 refinement
│  │  ├─ manual.py                 # user-painted override masks
│  │  ├─ combine.py                # union/dilate/clean, per-view reprojection through geometry/
│  │  └─ debug.py                  # overlay images for visual review
│  │
│  ├─ gate/
│  │  ├─ metrics.py                # every preflight metric as a pure function
│  │  ├─ sfm_metrics.py            # post-SfM metrics from a COLMAP model
│  │  ├─ thresholds.py             # loading/validating gate_thresholds.yaml
│  │  ├─ verdict.py                # metrics + thresholds -> Verdict(PASS/WARN/REJECT, reasons)
│  │  └─ reasons.py                # reason-code catalogue with messages and fix suggestions
│  │
│  ├─ sfm/
│  │  ├─ colmap_env.py             # detect COLMAP/pycolmap version, CUDA support, rig API availability
│  │  ├─ rig_config.py             # write rig_config.json for the installed COLMAP version
│  │  ├─ extract_match.py          # feature extraction + matching (sequential/vocab-tree/exhaustive)
│  │  ├─ mapper.py                 # incremental / global mapper wrappers, rig-aware
│  │  ├─ recovery.py               # recovery ladder when registration is poor
│  │  ├─ model_io.py               # read/write COLMAP sparse models, connected-component selection
│  │  ├─ normalize.py              # recenter/rescale scene, store the Sim3 transform
│  │  └─ stats.py                  # registration ratio, reprojection error, track length, triangulation angle
│  │
│  ├─ train/
│  │  ├─ dataset.py                # COLMAP + images + masks -> training/eval samples, rig-frame holdout
│  │  ├─ model.py                  # Gaussian parameter container, init from SfM points, SH handling
│  │  ├─ strategies.py             # MCMC / default densification via gsplat strategies
│  │  ├─ losses.py                 # L1, SSIM, masked loss, regularizers, optional depth loss
│  │  ├─ appearance.py             # per-image appearance embedding / exposure compensation
│  │  ├─ depth_prior.py            # monocular depth + scale/shift alignment to sparse depth
│  │  ├─ pose_refine.py            # optional camera pose optimization
│  │  ├─ schedule.py               # LR schedules, SH degree ramp, densification schedule
│  │  ├─ trainer.py                # main training loop, AMP, grad accumulation, OOM guardrails
│  │  ├─ checkpoint.py             # save/resume (Drive-safe, atomic writes)
│  │  ├─ evaluate.py               # PSNR/SSIM/LPIPS on held-out rig frames
│  │  └─ vram.py                   # VRAM detection and budget -> max_gaussians/resolution defaults
│  │
│  ├─ export/
│  │  ├─ cleanup.py                # floater removal, outlier filtering, crop around camera path
│  │  ├─ ply_io.py                 # standard 3DGS .ply read/write
│  │  ├─ compress.py               # optional .spz/.sog (whichever is currently maintained)
│  │  └─ sidecar.py                # normalization transform and metadata JSON
│  │
│  ├─ viz/
│  │  ├─ flythrough.py             # render along recovered and perturbed camera paths
│  │  ├─ plots.py                  # gate plots, training curves, coverage maps
│  │  └─ sfm_preview.py            # sparse cloud + camera frusta screenshots
│  │
│  ├─ report/
│  │  ├─ builder.py                # assemble report.json and report.md
│  │  ├─ schema.py                 # pydantic report schema
│  │  └─ templates/
│  │     ├─ report.md.j2
│  │     └─ report.html.j2
│  │
│  └─ utils/
│     ├─ logging.py                # structured logging, per-stage log files, rich console
│     ├─ hashing.py                # stable fingerprints of files/configs/code version
│     ├─ gpu.py                    # GPU/CUDA/driver detection, `splat360 doctor` backend
│     ├─ seeds.py                  # global seeding
│     ├─ paths.py                  # workspace path helpers, Drive-safe atomic writes
│     ├─ timing.py                 # stage timers and peak-memory tracking
│     └─ progress.py               # progress bars that behave in Colab and terminals
│
├─ scripts/
│  ├─ download_video.sh            # local-machine helper: yt-dlp download then upload to Drive
│  ├─ make_synthetic_scene.py      # build the synthetic 360 test video with ground-truth poses
│  ├─ calibrate_gate.py            # run preflight over many videos, emit threshold suggestions
│  ├─ compare_runs.py              # side-by-side metrics for two jobs/configs
│  └─ export_report_bundle.py      # zip report, renders, and sidecar for sharing
│
├─ notebooks/
│  ├─ 01_setup_and_smoke_test.ipynb
│  ├─ 02_run_pipeline.ipynb
│  ├─ 03_inspect_gate_and_masks.ipynb      # visual review of preflight metrics and masks
│  └─ 04_compare_results.ipynb             # held-out renders vs ground truth, metrics tables
│
├─ viewer/                         # optional static web viewer (M6)
│  ├─ index.html
│  ├─ src/main.ts
│  ├─ package.json                 # pinned viewer library
│  └─ README.md
│
├─ examples/
│  ├─ manifests/                   # example source.json files (no media committed)
│  └─ reports/                     # one sample PASS and one sample REJECT report (small, text only)
│
├─ tests/
│  ├─ conftest.py                  # shared fixtures, GPU/COLMAP skip markers
│  ├─ fixtures/                    # tiny generated assets only, never real videos
│  ├─ unit/
│  │  ├─ test_config.py
│  │  ├─ test_job_manifest.py
│  │  ├─ test_caching.py           # skip-when-unchanged and rerun-on-config-change
│  │  ├─ test_cli.py
│  │  ├─ geometry/                 # test_equirect, test_rotations, test_rig, test_remap, test_transforms
│  │  ├─ video/                    # test_keyframes, test_scene_detect, test_quality
│  │  ├─ masking/                  # test_camera_attached, test_combine
│  │  ├─ gate/                     # test_verdict, test_thresholds, test_reasons
│  │  ├─ sfm/                      # test_rig_config, test_model_io, test_normalize, test_stats
│  │  ├─ train/                    # test_dataset_split, test_vram_budget, test_losses (CPU parts)
│  │  └─ export/                   # test_ply_io, test_cleanup
│  ├─ integration/                 # marked `gpu`/`colmap`, run in Colab only
│  │  ├─ test_synthetic_sfm.py     # pose error against ground truth
│  │  ├─ test_train_smoke.py
│  │  └─ test_end_to_end_short_clip.py
│  └─ regression/
│     └─ test_report_schema.py     # report.json schema stability
│
└─ workspace/                      # gitignored; created at runtime (see section 4)
```

**M0 deliverable for this section:** the full skeleton above exists, every module has a docstring (responsibility + milestone), `make lint test` passes, and `docs/ARCHITECTURE.md` explains the layout and the dependency rules.

---

## 4. Core framework (M0)

**Job workspace** (`workspace/<job_id>/`):
```
manifest.json     # source info, permission note, config snapshot, per-stage status + hashes + timings
00_source/        # video.mp4, source.json (URL, title, uploader, license/permission note)
01_preflight/     # metrics.json, thumbnails, scene_boundaries.json
02_frames/        # equirect keyframes (jpg/png), frame_index.csv
03_masks/         # equirect masks (png), debug overlays
04_views/         # perspective views + masks + rig_config.json
05_sfm/           # colmap database, sparse/0, sfm_stats.json
06_gate/          # post-SfM verdict
07_train/         # checkpoints, logs, tensorboard
08_output/        # scene.ply, optional .spz/.sog, renders, metrics.json, flythrough.mp4
report.json / report.md
```

**Stage interface:** `name`, `requires`, `run(job, cfg) -> StageResult`, `fingerprint(job, cfg)` (hash of inputs + relevant config + code version). Skip if fingerprint matches the stored one and outputs exist. A `--force` flag reruns. Failed stages record the error in the manifest and stop the pipeline with a non-zero exit code. A `REJECT` verdict is **not a crash**: exit code 0 or a dedicated code, with the report generated.

**Config:** pydantic models loaded from `configs/default.yaml`, overridden by a preset and then by `--set key=value`. Config snapshot is stored in the manifest. Every threshold in this spec lives in config, none hard-coded.

**CLI:**
```
splat360 run <url-or-path> [--preset ride_fast] [--scene-timestamps 00:12-01:40,02:05-03:30] [--workspace DIR]
splat360 stage <name> --job <job_id>
splat360 inspect <video>        # preflight only, prints verdict
splat360 report --job <job_id>
```

**M0 acceptance:** scaffold builds, `pip install -e .` works, `splat360 --help` works, config/job/manifest/caching have unit tests (including the "skip when unchanged" and "rerun when config changes" cases), CI-style `make lint test` passes locally.

---

## 5. Stage specifications

### S0: Ingest
- Accept a YouTube URL **or** a local file. Colab IPs are often blocked or rate-limited by YouTube (HTTP 429/bot checks), so the **recommended path is downloading locally and placing the file in Google Drive**. Support `--cookies cookies.txt` for yt-dlp as an option. Do not attempt to evade blocking beyond documented yt-dlp options.
- yt-dlp format selection: best available video, prefer the highest resolution equirectangular stream (up to 8K), VP9/AV1 acceptable; audio not needed. Keep the original container; do **not** re-encode (no extra compression generations).
- Write `source.json`: URL/path, title, uploader, duration, resolution, fps, codec, and a **mandatory `permission_note` field** (free text, e.g. "written permission from uploader, date"). Refuse to run on a URL with an empty permission note unless `--i-have-permission` is passed. Log it into the manifest and the final report.
- `ffprobe` metadata: resolution, fps, rotation flags, spherical/360 side data if present.

### S1: Preflight gate + scene splitting
Cheap checks that run before any heavy compute. Output `metrics.json` and a **verdict**: `PASS`, `PASS_WITH_WARNINGS`, or `REJECT`, each with human-readable reasons (the "rejection report", see section 7).

1. **Format check:** aspect ratio ≈ 2:1 → equirect mono. ≈ 1:1 or stacked → likely top/bottom stereo (VR180/3D 360): either take the top eye or REJECT per config (`stereo_policy`). Anything else (e.g. 16:9 flat video, cubemap strips, dual-fisheye) → REJECT with the explanation.
2. **Scene cut detection** (PySceneDetect or equivalent): split into segments at hard cuts. If the user supplies `--scene-timestamps`, those override auto-detection. Each segment becomes a child job.
3. **Per-segment sampling pass** (decode ~1 frame/sec, downscaled to e.g. 1024×512 equirect):
   - **Blur:** variance-of-Laplacian on rig views (not on the raw equirect, whose distortion biases it); report the fraction of frames below threshold.
   - **Exposure stability:** per-frame mean luminance flicker; auto-exposure jumps.
   - **Camera motion / parallax proxy:** dense optical flow on rig views between sampled frame pairs. Separate rotation-dominated flow (low translation → no depth information) from translation-induced flow. Report median flow magnitude and a **rotation-vs-translation ratio**.
   - **Static camera detection:** near-zero translation across the segment → REJECT (`no_parallax`).
   - **Too-fast motion:** flow magnitude per native-fps frame pair above threshold → WARN or REJECT (motion blur / insufficient overlap), and recommend `preset_ride_fast`.
   - **Camera-attached occluders:** regions that stay constant in camera space while the scene changes (see S3 detector). Report fraction of sphere covered. Above threshold → WARN, above a higher one → REJECT.
   - **Dynamic content:** fraction of pixels classified as people/vehicles/animals by the S3 segmenter (run on a small subset here). High → WARN.
   - **Scene type hints:** very low texture (sky/water/fog dominated), night/low light → WARN.
4. **Duration/size sanity:** min/max segment length (configurable defaults 5 s to 15 min).

Thresholds live in `configs/default.yaml` and are documented with rationale in `docs/GATE_METRICS.md`. Calibrate on real footage in M1 and record the calibration results (do not guess final values; start with conservative defaults and mark them `provisional`).

### S2: Frame extraction & keyframe selection
- Decode the full segment at native fps (ffmpeg, hardware decode if available) in streaming fashion, never loading all frames into RAM.
- **Select by baseline, not by time.** Compute a cheap per-frame signal (downscaled grayscale + optical flow or a sparse feature track) and accumulate translation-induced parallax. Keep a frame when accumulated parallax since the last keyframe exceeds `min_parallax_px` (target ~5–15% of image width of translation flow at the working resolution), subject to `min_gap_frames`/`max_gap_frames`. This yields dense sampling during motion and sparse sampling when slow or stopped.
- Drop frames with blur score below threshold *unless* dropping breaks continuity (max gap constraint), in which case keep the sharpest frame in the window.
- Cap total keyframes at `max_keyframes` (default 600; each becomes `n_views` images). Report the selected count and spatial coverage.
- Save as high-quality JPEG (q≥95) or PNG; record `frame_index.csv` (keyframe id, source frame number, timestamp, blur, parallax).
- **Preset `ride_fast`:** higher native-fps usage, stronger blur rejection, smaller `max_gap_frames`, and shorter keyframe spacing in time.

### S3: Masking
Goal: exclude from SfM *and* training anything that is not static scene geometry.
1. **Camera-attached regions** (ride cart, seat bar, selfie stick/pole, tripod, photographer's body, nadir/zenith holes, lens mount): per rig view, compute temporal statistics over many keyframes (median image + per-pixel temporal variance of luminance/gradients). Pixels with persistently low variance while the global scene changes are camera-attached. Produce a stable static mask via thresholding + morphology + connected components; allow a manual override (`masks/manual_equirect.png`, painted white = exclude).
2. **Dynamic objects:** semantic segmentation (SegFormer/Mask2Former from Hugging Face, ADE20K or Cityscapes classes: person, car, bus, truck, bicycle, motorcycle, animal, etc.), optional SAM 2 refinement. Dilate masks slightly. **Riders in the ride's own vehicle are camera-attached**, handled by (1).
3. **Stitching seams / poles:** optional down-weighting of the zenith/nadir bands (equirect distortion), configurable.
4. Masks are generated in **equirect space**, then reprojected with the same rig geometry as the images (S4), so they stay consistent.
5. Write debug overlays (image + mask tint) for a handful of keyframes into `03_masks/debug/` for visual review.

### S4: Equirect → perspective rig views
- Pure-geometry module in `geometry/` (numpy; unit-tested): equirect pixel ↔ unit ray, rotation conventions documented (right-handed, Y-up or whatever COLMAP expects: document the chosen convention in `docs/ARCHITECTURE.md` and test it).
- Rig presets (configurable): `cube6` (6 views, FOV 90°, no overlap, not recommended), **`cube6_fov100` (default)**, `ring8_poles` (8 horizontal views at 45° yaw spacing, FOV ~90° + top/bottom views). Output resolution per view default 1600×1600 (configurable).
- Render with high-quality resampling (bicubic or Lanczos via OpenCV `remap`; GPU `torch.grid_sample` allowed when CUDA is present). Same remap for masks (nearest/threshold).
- Write `rig_config.json` in the format required by the **current** COLMAP rig API (verify against the installed version: `rig_configurator` / `Rig`/`Sensor` objects): one reference sensor, the others with fixed `cam_from_rig` rotations (zero translation), shared intrinsics per view type (PINHOLE).
- Unit tests: round-trip a synthetic equirect with known patterns; verify ray directions of the central pixel of each view equal the intended view axis; verify mask/image alignment.

### S5: Structure-from-Motion
- **COLMAP with rig constraints** (current COLMAP/pycolmap with native rig support). Steps: feature extraction (SIFT default, GPU if available, with the masks applied; optional learned features if supported by the installed COLMAP version), matching (**sequential matching with loop detection via vocabulary tree**; exhaustive if keyframes < ~150), rig-aware incremental mapping. GLOMAP/global mapping is an optional alternative if available in the installed version; implement behind a config flag, default = whichever is proven more robust on my test videos (decide in M3 by experiment and log it).
- Recent COLMAP versions advertise native spherical/equirect camera models; evaluate whether this is production-ready in the installed version and whether it beats the rig approach on my footage. Keep the rig approach as default unless the experiment says otherwise (record results in `DECISIONS.md`).
- **CUDA COLMAP on Colab:** figure out the current working recipe (pip CUDA wheel vs. build from source vs. conda) and document it in `docs/COLAB.md`. If CUDA is unavailable, support CPU SIFT with reduced keyframes as a slow fallback.
- **Recovery ladder** if registration is poor: (a) increase matching window/overlap, (b) exhaustive matching on subsets, (c) re-select keyframes denser, (d) relax mapper thresholds. Record each attempt. If the ladder fails → the post-SfM gate REJECTs.
- Output: standard COLMAP sparse model (`cameras.bin`, `images.bin`, `points3D.bin`), `sfm_stats.json` (registered image ratio, rig-frame registration ratio, mean reprojection error, mean track length, 3D point count, scale/extent).
- **Normalization:** recenter and rescale the scene to a canonical frame for training; store the transform so the exported splat can be mapped back.

### S6: Post-SfM gate (the decisive check)
`PASS` if all hold (thresholds configurable, calibrated in M3):
- ≥ X% of rig frames registered (default target ≥ 85%, minimum 70% with a warning),
- mean reprojection error < ~1.0 px (rig-level),
- sufficient triangulation angle (median) and track length,
- a single connected model covers ≥ Y% of the keyframes (no fragmented models),
- point count above a minimum.
Otherwise `REJECT` with the specific failing metrics and *actionable suggestions* (e.g. "motion too fast: re-shoot slower", "too much camera-attached occlusion", "rotation-only motion").
A `PASS_WITH_WARNINGS` model can be partially used: train on the largest connected component and say so in the report.

### S7: Gaussian splat training
- Use **gsplat** (Apache-2.0, CUDA) via its Python API (verify current API: `rasterization`, strategies `DefaultStrategy` / `MCMCStrategy`, `absgrad`, antialiased mode, camera optimization). Write our own thin, readable trainer (not a fork of research code), using gsplat's official `examples/simple_trainer.py` as the reference. Training consumes the COLMAP model produced by S5 plus images and masks.
- Initialization from the SfM point cloud (+ optional extra random points far away for background); SH degree up to 3 with progressive increase.
- Densification: MCMC strategy by default (more robust to sparse init and gives a controllable Gaussian budget `max_gaussians`; **default 5M on an A100 40 GB**, auto-scaled from detected VRAM: roughly 3M at 24 GB, higher at 80 GB; always leave headroom for rasterization buffers and evaluation renders), default strategy selectable.
- **Loss:** L1 + (1 − SSIM) (λ=0.2), plus optional: scale/opacity regularizers, **per-image appearance embedding** (handles YouTube auto-exposure variation), **masked loss** (excluded pixels contribute zero), optional monocular-depth loss (Depth Anything V2 via Hugging Face; scale/shift aligned to SfM sparse depth per image), optional pose refinement.
- Held-out evaluation set: every Nth **rig frame** (all views of the frame together, to prevent leakage between neighboring views of the same instant). Default N=8.
- Mixed precision where safe; gradient accumulation if needed; target steps default 30k (configurable); checkpoint every 2k steps to Drive; **resume from the latest checkpoint**; TensorBoard logs; periodic eval renders with PSNR/SSIM/LPIPS.
- Memory guardrails: detect OOM risk from `max_gaussians` × SH degree × image size; auto-reduce resolution or Gaussian budget with a logged warning, never crash silently.
- Determinism: seed everything; document non-determinism sources.

### S8: Cleanup, export, evaluation
- **Cleanup:** remove floaters (low opacity, huge scale, far from camera trajectory envelope, statistical outlier filtering), optional crop to a bounding region around the camera path (configurable margin).
- **Export:** standard 3DGS `.ply` (required). Optional compact formats (`.spz` and/or `.sog`/compressed ply via their current open-source tools; verify what exists and is maintained). Include the normalization transform in a sidecar JSON.
- **Evaluation:** PSNR / SSIM / LPIPS on held-out frames (report mean, per-view-type, and worst 5 frames), number of Gaussians, file size, training time, peak VRAM.
- **Fly-through render:** render a video along the (smoothed) recovered camera path and one with a perturbed path (e.g. 0.3–0.5 m lateral offset, scaled by scene size) to expose view-extrapolation artifacts honestly.

### S9: Report
`report.json` + human-readable `report.md` (and HTML if cheap) containing: source and permission note, verdicts of both gates with reasons, all metrics, config snapshot, versions of every dependency, timings, sample images (keyframes, masks, SfM point cloud screenshot, renders vs ground truth), and an **"expected limitations"** section.

---

## 6. Presets (initial; calibrate in M1/M3)

| Preset | Intended for | Key differences |
|---|---|---|
| `walkthrough` | Walking/handheld/pole-mounted, moderate speed | Default thresholds |
| `ride_fast` | Rides/vehicles/fast motion | Native-fps decode, strict blur rejection, small max gap, stronger camera-attached masking, wider flow tolerance, loop-detection on |
| `drone` | Aerial footage | Larger baselines, mask drone body at nadir, scene-scale handling |

---

## 7. Rejection report format (user-facing)

On REJECT, produce `report.md` with: **Verdict**, **Why** (ordered by severity, each with the measured value vs. threshold), **What I saw** (thumbnails/plots), **How to fix / what footage works** (concrete, e.g. "needs translation of at least X; tripod/spinning-in-place footage contains no depth information"). Also write machine-readable `report.json` with `verdict`, `reasons[]` (code, severity, value, threshold, message).

Reason codes (extensible): `not_equirect`, `stereo_unsupported`, `no_parallax`, `rotation_dominated`, `motion_too_fast`, `excess_blur`, `exposure_unstable`, `camera_attached_occlusion`, `high_dynamic_content`, `low_texture`, `too_short`, `sfm_low_registration`, `sfm_fragmented`, `sfm_high_reproj_error`, `sfm_insufficient_baseline`.

---

## 8. Colab requirements

- Notebooks: `01_setup_and_smoke_test` (install, verify GPU/CUDA, COLMAP CUDA, gsplat import and a tiny render test) and `02_run_pipeline` (mount Drive, set workspace on Drive, run job, display report, download results).
- Workspace and checkpoints on Google Drive; caches survive session death; every stage resumable.
- Print GPU type, VRAM, CPU count, RAM, disk, and library versions at the top of each run.
- **A100 settings:** TF32 enabled for matmul/conv where safe, per-view resolution up to 2048×2048 (`rig.view_size`), larger keyframe cap (`max_keyframes` up to ~800), SegFormer/SAM 2/depth models run in fp16/bf16 with batching. All of these must be config values with VRAM-aware defaults, never hard-coded.
- Expect session limits: design for interruptions (checkpoints, idempotent stages).
- Preferred input path: video already in Drive (see S0 note about YouTube blocking).

---

## 9. Testing strategy

- **Unit (CPU, local):** geometry round-trips, rig config generation, config/caching logic, gate verdict logic with synthetic metric inputs, COLMAP model IO, keyframe selection on synthetic signals.
- **Synthetic end-to-end test:** generate a small synthetic 360 video programmatically (e.g. render a textured box room with a moving virtual equirect camera using numpy/OpenCV or a tiny software raycaster), so that SfM has known ground-truth poses. Used to verify S4→S5 (pose error vs. GT) in Colab.
- **Integration (Colab/GPU):** one short real clip end-to-end as a smoke test; asserts stages produce outputs and the report exists. Do not assert on image quality thresholds in CI-style tests, only sanity.
- **Real-data calibration (M1/M3):** run on my two sample videos and tune gate thresholds; record the results in `GATE_METRICS.md`.

---

## 10. Quality bar and honest expectations (put in README)

- Novel views are good **near the captured camera path** and degrade away from it; a ride/rail trajectory gives a thin "tube" of reliable viewpoints.
- Moving objects will be removed or smeared; this is by design.
- Compression artifacts and stitching errors in YouTube footage cap achievable sharpness.
- Scale is arbitrary (no metric units).
- Results from fast-motion footage will be poorer than slow walkthroughs; the gate and report must say so rather than hide it.

---

## 11. Sample inputs (for calibration and demos)

1. Amusement park ride, `https://youtu.be/tR8ZtyhSDYw`. Use preset `ride_fast`. Expect: fast motion, camera-attached ride vehicle and riders, motion blur, possible track loops.
2. Multi-scene video, `https://www.youtube.com/watch?v=kyN623RzFe0`. Use `--scene-timestamps` (to be supplied) so each scene becomes its own job; verify auto cut-detection agrees with the timestamps.

Both have **uploader permission**; record this in each job's `permission_note`. Do not run the pipeline on any other video without a permission note.

---

## 12. Milestones (stop and report after each)

| # | Milestone | Definition of done |
|---|---|---|
| **M0** | Scaffold, config, job/manifest/caching, CLI skeleton, tests | See section 4 acceptance |
| **M1** | S0 ingest + S1 preflight + scene split + rejection report | `splat360 inspect` works on both sample videos; report generated; thresholds calibrated and documented |
| **M2** | S2 keyframes + S3 masks + S4 rig views | Geometry tests pass; debug overlays look right on real footage (I will review images) |
| **M3** | S5 SfM + S6 post-SfM gate (Colab) | COLMAP CUDA recipe documented; synthetic GT test shows low pose error; real clip registers; recovery ladder implemented |
| **M4** | S7 training in Colab | Resumable training, eval metrics on held-out frames, first splat `.ply` viewable |
| **M5** | S8 cleanup/export/eval + fly-through + S9 report | Full automatic run: URL/file → splat + report |
| **M6** | Web viewer + compressed export (optional) | Static viewer loads the exported splat; pinned, maintained viewer library |
| **M7** | Docs, README gallery, reproducibility pass | Fresh-clone Colab run succeeds following only the docs |

At the end of **M0 to M2** (the base), I will share the GitHub link so the work can continue from the repository. Therefore keep `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, tests, and the Makefile always up to date so a new contributor can take over without asking you anything.

---

## 13. Open items the agent should flag, not guess

- Exact current COLMAP rig API and CUDA install route on Colab.
- Which compressed splat format/tooling is currently maintained.
- Calibrated gate thresholds (provisional until measured on real footage).
- Whether COLMAP's native spherical camera model is mature enough to replace the rig approach.

---

## 14. Status report protocol (end of EVERY milestone)

The user relays your status to a second assistant (Claude) that will later clone the repository and continue, so the report must be **self-contained, factual, and verifiable**. At the end of each milestone: (a) append the report to `docs/STATUS.md` (newest first), (b) commit it, and (c) paste the same text as your final message. Use exactly this template:

```
# STATUS: <milestone id and name>   (<date>)

## 1. Summary (max 5 lines)
## 2. What was built
- <module / file>: <what it does>  (one line each)
## 3. Verification evidence
- Commands run (exact) and their real output (trimmed, not invented)
- Test results: <n passed / n failed / n skipped (and why skipped)>
- Lint/type-check results
## 4. Repository state
- Branch, last commit hash, `tree -L 3` of src/ and tests/
- Pinned dependency versions that matter (python, torch, gsplat, colmap/pycolmap, etc.)
## 5. Deviations from SPEC.md
- <deviation>, <reason>, <DECISIONS.md entry>  (or "none")
## 6. Known issues, risks, and things you were unsure about
## 7. Open questions for the user (numbered, answerable in one line each)
## 8. What the next milestone needs from the user (files, timestamps, credentials, decisions)
```

Never claim something works unless you ran it. If something could not be run (e.g. no GPU locally), say exactly that and name where it must be verified.
