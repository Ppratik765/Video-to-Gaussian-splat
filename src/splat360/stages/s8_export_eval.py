"""S8: Cleanup, export, evaluation. Milestone: M5"""
from __future__ import annotations

from splat360.config import PipelineConfig
from splat360.constants import STAGE_EXPORT_EVAL, STAGE_TRAIN
from splat360.errors import StageNotImplemented
from splat360.job import Job
from splat360.stages.base import Stage, StageResult
from splat360.utils.hashing import hash_dict


class ExportEvalStage(Stage):
    @property
    def name(self) -> str:
        return STAGE_EXPORT_EVAL
    @property
    def requires(self) -> list[str]:
        return [STAGE_TRAIN]
    def run(self, job: Job, cfg: PipelineConfig) -> StageResult:
        raise StageNotImplemented(self.name, "M5")
    def fingerprint(self, job: Job, cfg: PipelineConfig) -> str:
        return hash_dict({"export": cfg.export.model_dump()})
