"""
Stage registry: ordering, dependency graph, and lazy imports.

All concrete stages are registered here.  Stages belonging to later
milestones raise ``StageNotImplemented`` when run.
"""

from __future__ import annotations

from splat360.constants import (
    STAGE_EXPORT_EVAL,
    STAGE_FRAMES,
    STAGE_INGEST,
    STAGE_MASKS,
    STAGE_ORDER,
    STAGE_POSTSFM_GATE,
    STAGE_PREFLIGHT,
    STAGE_REPORT,
    STAGE_RIG,
    STAGE_SFM,
    STAGE_TRAIN,
)
from splat360.stages.base import Stage


def _get_stage(name: str) -> Stage:
    """Return a concrete ``Stage`` instance for *name*.

    Stages that are not yet implemented raise ``StageNotImplemented``
    inside their ``run()`` method, but they are valid ``Stage`` objects
    so that the registry is always complete.
    """
    # Lazy imports to avoid pulling in heavy deps at import time.
    if name == STAGE_INGEST:
        from splat360.stages.s0_ingest import IngestStage
        return IngestStage()
    if name == STAGE_PREFLIGHT:
        from splat360.stages.s1_preflight import PreflightStage
        return PreflightStage()
    if name == STAGE_FRAMES:
        from splat360.stages.s2_frames import FramesStage
        return FramesStage()
    if name == STAGE_MASKS:
        from splat360.stages.s3_masks import MasksStage
        return MasksStage()
    if name == STAGE_RIG:
        from splat360.stages.s4_rig import RigStage
        return RigStage()
    if name == STAGE_SFM:
        from splat360.stages.s5_sfm import SfmStage
        return SfmStage()
    if name == STAGE_POSTSFM_GATE:
        from splat360.stages.s6_postsfm_gate import PostSfmGateStage
        return PostSfmGateStage()
    if name == STAGE_TRAIN:
        from splat360.stages.s7_train import TrainStage
        return TrainStage()
    if name == STAGE_EXPORT_EVAL:
        from splat360.stages.s8_export_eval import ExportEvalStage
        return ExportEvalStage()
    if name == STAGE_REPORT:
        from splat360.stages.s9_report import ReportStage
        return ReportStage()
    raise ValueError(f"Unknown stage: {name!r}")


STAGE_REGISTRY: dict[str, Stage] = {}


def get_stage(name: str) -> Stage:
    """Return a (cached) Stage instance for *name*."""
    if name not in STAGE_REGISTRY:
        STAGE_REGISTRY[name] = _get_stage(name)
    return STAGE_REGISTRY[name]
