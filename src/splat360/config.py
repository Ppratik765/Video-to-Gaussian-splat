"""
Pydantic configuration models, YAML loading, preset merging, and CLI overrides.

Hierarchy:  defaults → preset YAML → user YAML → ``--set key=value`` overrides.

Uses pydantic v2 only.

Responsibility: config.py
Milestone: M0
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from splat360.constants import VERSION
from splat360.errors import ConfigError

# ---------------------------------------------------------------------------
# Sub-models — one per conceptual area
# ---------------------------------------------------------------------------


class IngestConfig(BaseModel):
    """Settings for S0 (ingest)."""

    cookies_file: str | None = Field(
        None, description="Path to a cookies.txt for yt-dlp"
    )
    i_have_permission: bool = Field(
        False,
        description="Skip the mandatory permission-note check",
    )
    max_resolution: int = Field(
        7680, description="Maximum video resolution to request (width in px)"
    )


class PreflightConfig(BaseModel):
    """Settings for S1 (preflight gate)."""

    stereo_policy: str = Field(
        "reject",
        description="'reject' | 'top_eye' — what to do with stereo/VR180 input",
    )
    min_segment_seconds: float = Field(5.0, description="Minimum segment duration")
    max_segment_seconds: float = Field(900.0, description="Maximum segment duration")
    blur_threshold: float = Field(
        50.0, description="Variance-of-Laplacian below which a frame is blurry (provisional)"
    )
    max_blur_fraction: float = Field(
        0.6, description="Fraction of frames allowed to be blurry before REJECT"
    )
    min_flow_magnitude: float = Field(
        2.0, description="Minimum median flow (px) to avoid no_parallax"
    )
    max_flow_magnitude: float = Field(
        80.0, description="Maximum per-frame flow (px) before motion_too_fast warning"
    )
    camera_attached_warn: float = Field(
        0.15, description="Sphere fraction covered by camera-attached regions before WARN"
    )
    camera_attached_reject: float = Field(
        0.40, description="Sphere fraction covered by camera-attached regions before REJECT"
    )
    dynamic_content_warn: float = Field(
        0.30, description="Fraction of pixels classified dynamic before WARN"
    )


class FramesConfig(BaseModel):
    """Settings for S2 (frame extraction)."""

    min_parallax_px: float = Field(
        80.0, description="Accumulated translation flow before keeping a new keyframe"
    )
    min_gap_frames: int = Field(5, description="Minimum frames between keyframes")
    max_gap_frames: int = Field(60, description="Maximum frames between keyframes")
    max_keyframes: int = Field(600, description="Hard cap on total keyframes")
    jpeg_quality: int = Field(95, description="JPEG quality for saved keyframes")


class RigConfig(BaseModel):
    """Settings for S4 (equirect → perspective views)."""

    preset: str = Field("cube6_fov100", description="Rig preset name")
    view_size: int = Field(1600, description="Output view width and height in px")
    fov_deg: float = Field(100.0, description="Field of view in degrees for the default rig")


class SfmConfig(BaseModel):
    """Settings for S5 (Structure-from-Motion)."""

    matching_strategy: str = Field(
        "sequential", description="'sequential' | 'exhaustive' | 'vocab_tree'"
    )
    use_gpu: bool = Field(True, description="Use GPU-accelerated SIFT if available")
    mapper: str = Field("incremental", description="'incremental' | 'global'")


class PostSfmGateConfig(BaseModel):
    """Settings for S6 (post-SfM gate)."""

    min_registered_ratio: float = Field(
        0.70, description="Minimum fraction of rig frames registered"
    )
    target_registered_ratio: float = Field(
        0.85, description="Target fraction (below → WARN)"
    )
    max_reproj_error_px: float = Field(
        1.0, description="Maximum mean reprojection error (px)"
    )
    min_point_count: int = Field(
        1000, description="Minimum 3D points in the sparse model"
    )


class TrainConfig(BaseModel):
    """Settings for S7 (Gaussian-splat training)."""

    max_steps: int = Field(30_000, description="Training iterations")
    max_gaussians: int = Field(
        5_000_000, description="Gaussian budget (auto-scaled by VRAM)"
    )
    ssim_lambda: float = Field(0.2, description="Weight of SSIM loss term")
    eval_every_n_rig_frames: int = Field(8, description="Hold-out every Nth rig frame")
    checkpoint_every: int = Field(2000, description="Save checkpoint every N steps")
    use_appearance_embedding: bool = Field(True, description="Per-image appearance embedding")
    use_depth_loss: bool = Field(False, description="Monocular depth supervision")
    strategy: str = Field("mcmc", description="'mcmc' | 'default' densification strategy")


class ExportConfig(BaseModel):
    """Settings for S8 (cleanup, export, evaluation)."""

    min_opacity: float = Field(0.005, description="Remove Gaussians below this opacity")
    outlier_std: float = Field(3.0, description="Standard deviations for outlier removal")
    camera_margin: float = Field(1.5, description="Crop margin multiplier around camera path")
    compress_format: str | None = Field(
        None, description="Optional compressed format: 'spz' | 'sog' | null"
    )


class PipelineConfig(BaseModel):
    """Top-level pipeline configuration.

    Every tunable lives here.  ``configs/default.yaml`` is auto-generated from
    this model's defaults.
    """

    model_config = {"extra": "forbid"}

    version: str = Field(default=VERSION, description="Config schema version")
    workspace: str = Field(default="workspace", description="Root workspace directory")
    preset: str | None = Field(default=None, description="Named preset to merge on top of defaults")

    ingest: IngestConfig = Field(default_factory=lambda: IngestConfig())
    preflight: PreflightConfig = Field(default_factory=lambda: PreflightConfig())
    frames: FramesConfig = Field(default_factory=lambda: FramesConfig())
    rig: RigConfig = Field(default_factory=lambda: RigConfig())
    sfm: SfmConfig = Field(default_factory=lambda: SfmConfig())
    post_sfm_gate: PostSfmGateConfig = Field(default_factory=lambda: PostSfmGateConfig())
    train: TrainConfig = Field(default_factory=lambda: TrainConfig())
    export: ExportConfig = Field(default_factory=lambda: ExportConfig())

    # ------------------------------------------------------------------
    # force flag (not persisted in YAML, set via CLI)
    # ------------------------------------------------------------------
    force: bool = Field(False, description="Force re-run of all stages")


# ---------------------------------------------------------------------------
# YAML loading helpers
# ---------------------------------------------------------------------------


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file and return its contents as a dict."""
    try:
        import yaml
    except ImportError as exc:
        raise ConfigError("PyYAML is required: pip install pyyaml") from exc

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a YAML mapping, got {type(data).__name__}")
    return data


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge *override* into *base* (returns a new dict)."""
    result = dict(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def _apply_set_overrides(data: dict[str, Any], overrides: list[str]) -> dict[str, Any]:
    """Apply ``--set key=value`` CLI overrides.

    Keys use dotted notation: ``train.max_steps=50000``.
    Values are parsed as JSON first, then fall back to strings.
    """
    for item in overrides:
        if "=" not in item:
            raise ConfigError(f"--set value must be key=value, got: {item!r}")
        key, raw_value = item.split("=", 1)
        # Parse value
        try:
            value: Any = json.loads(raw_value)
        except (json.JSONDecodeError, ValueError):
            value = raw_value

        # Walk the dotted path and set
        parts = key.strip().split(".")
        target = data
        for part in parts[:-1]:
            if part not in target or not isinstance(target[part], dict):
                target[part] = {}
            target = target[part]
        target[parts[-1]] = value

    return data


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_CONFIGS_DIR = Path(__file__).resolve().parent.parent.parent / "configs"


def load_config(
    *,
    config_file: Path | None = None,
    preset: str | None = None,
    set_overrides: list[str] | None = None,
    force: bool = False,
) -> PipelineConfig:
    """Build a ``PipelineConfig`` by merging layers.

    Order (last wins):
    1. Pydantic defaults
    2. ``configs/default.yaml``
    3. Preset YAML (``configs/preset_<name>.yaml``)
    4. User-supplied YAML file
    5. ``--set key=value`` overrides

    Raises ``ConfigError`` on unknown presets or invalid values.
    """
    data: dict[str, Any] = {}

    # 1. default.yaml (if it exists and has real content)
    default_yaml = _CONFIGS_DIR / "default.yaml"
    if default_yaml.is_file():
        loaded = _load_yaml(default_yaml)
        if loaded:
            data = _deep_merge(data, loaded)

    # 2. preset
    effective_preset = preset
    if effective_preset is None and "preset" in data:
        effective_preset = data["preset"]

    if effective_preset is not None:
        preset_path = _CONFIGS_DIR / f"preset_{effective_preset}.yaml"
        if not preset_path.is_file():
            raise ConfigError(
                f"Unknown preset {effective_preset!r}: "
                f"expected {preset_path} to exist"
            )
        data = _deep_merge(data, _load_yaml(preset_path))
        data["preset"] = effective_preset

    # 3. user-supplied config file
    if config_file is not None:
        if not config_file.is_file():
            raise ConfigError(f"Config file not found: {config_file}")
        data = _deep_merge(data, _load_yaml(config_file))

    # 4. --set overrides
    if set_overrides:
        data = _apply_set_overrides(data, set_overrides)

    # Remove 'force' from data if present (set separately)
    data_force = data.pop("force", False)

    # Build pydantic model (validates everything)
    try:
        cfg = PipelineConfig(**data)
    except Exception as exc:
        raise ConfigError(f"Invalid configuration: {exc}") from exc

    cfg.force = force or data_force
    return cfg


def config_to_dict(cfg: PipelineConfig) -> dict[str, Any]:
    """Serialise config to a plain dict (for manifest snapshot)."""
    return json.loads(cfg.model_dump_json())  # type: ignore[no-any-return]


def generate_schema() -> dict[str, Any]:
    """Return the JSON Schema for ``PipelineConfig``."""
    return PipelineConfig.model_json_schema()


def generate_default_yaml() -> str:
    """Return a YAML string with all defaults and inline documentation."""
    try:
        import yaml
    except ImportError as exc:
        raise ConfigError("PyYAML is required: pip install pyyaml") from exc

    cfg = PipelineConfig()
    data = config_to_dict(cfg)
    return yaml.dump(data, default_flow_style=False, sort_keys=False)  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# CLI entry point:  python -m splat360.config --schema
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if "--schema" in sys.argv:
        schema = generate_schema()
        out = _CONFIGS_DIR / "schema" / "config.schema.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(schema, f, indent=2)
            f.write("\n")
        print(f"Schema written to {out}")
    elif "--defaults" in sys.argv:
        print(generate_default_yaml())
    else:
        print("Usage: python -m splat360.config [--schema | --defaults]")
