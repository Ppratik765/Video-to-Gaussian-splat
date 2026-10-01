"""
Single source of truth for stage names, reason codes, file names, and other constants.

Responsibility: constants.py
Milestone: M0
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Stage names (ordered)
# ---------------------------------------------------------------------------
STAGE_INGEST = "s0_ingest"
STAGE_PREFLIGHT = "s1_preflight"
STAGE_FRAMES = "s2_frames"
STAGE_MASKS = "s3_masks"
STAGE_RIG = "s4_rig"
STAGE_SFM = "s5_sfm"
STAGE_POSTSFM_GATE = "s6_postsfm_gate"
STAGE_TRAIN = "s7_train"
STAGE_EXPORT_EVAL = "s8_export_eval"
STAGE_REPORT = "s9_report"

STAGE_ORDER: list[str] = [
    STAGE_INGEST,
    STAGE_PREFLIGHT,
    STAGE_FRAMES,
    STAGE_MASKS,
    STAGE_RIG,
    STAGE_SFM,
    STAGE_POSTSFM_GATE,
    STAGE_TRAIN,
    STAGE_EXPORT_EVAL,
    STAGE_REPORT,
]

# ---------------------------------------------------------------------------
# Workspace directory names (per-stage)
# ---------------------------------------------------------------------------
WORKSPACE_DIRS: dict[str, str] = {
    STAGE_INGEST: "00_source",
    STAGE_PREFLIGHT: "01_preflight",
    STAGE_FRAMES: "02_frames",
    STAGE_MASKS: "03_masks",
    STAGE_RIG: "04_views",
    STAGE_SFM: "05_sfm",
    STAGE_POSTSFM_GATE: "06_gate",
    STAGE_TRAIN: "07_train",
    STAGE_EXPORT_EVAL: "08_output",
    STAGE_REPORT: "",  # report lives at workspace root
}

# ---------------------------------------------------------------------------
# Well-known file names
# ---------------------------------------------------------------------------
MANIFEST_FILENAME = "manifest.json"
SOURCE_JSON = "source.json"
REPORT_JSON = "report.json"
REPORT_MD = "report.md"
FRAME_INDEX_CSV = "frame_index.csv"
RIG_CONFIG_JSON = "rig_config.json"
SFM_STATS_JSON = "sfm_stats.json"

# ---------------------------------------------------------------------------
# Verdict values
# ---------------------------------------------------------------------------
VERDICT_PASS = "PASS"
VERDICT_WARN = "PASS_WITH_WARNINGS"
VERDICT_REJECT = "REJECT"

# ---------------------------------------------------------------------------
# Rejection reason codes
# ---------------------------------------------------------------------------
REASON_NOT_EQUIRECT = "not_equirect"
REASON_STEREO_UNSUPPORTED = "stereo_unsupported"
REASON_NO_PARALLAX = "no_parallax"
REASON_ROTATION_DOMINATED = "rotation_dominated"
REASON_MOTION_TOO_FAST = "motion_too_fast"
REASON_EXCESS_BLUR = "excess_blur"
REASON_EXPOSURE_UNSTABLE = "exposure_unstable"
REASON_CAMERA_ATTACHED = "camera_attached_occlusion"
REASON_DYNAMIC_CONTENT = "high_dynamic_content"
REASON_LOW_TEXTURE = "low_texture"
REASON_TOO_SHORT = "too_short"
REASON_SFM_LOW_REG = "sfm_low_registration"
REASON_SFM_FRAGMENTED = "sfm_fragmented"
REASON_SFM_HIGH_REPROJ = "sfm_high_reproj_error"
REASON_SFM_INSUFFICIENT_BASELINE = "sfm_insufficient_baseline"

# ---------------------------------------------------------------------------
# Stage status values recorded in manifest
# ---------------------------------------------------------------------------
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"

# ---------------------------------------------------------------------------
# Package version — single source
# ---------------------------------------------------------------------------
VERSION = "0.1.0"
