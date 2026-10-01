"""S1: Preflight gate + scene splitting. Milestone: M1"""
from __future__ import annotations

from splat360.config import PipelineConfig
from splat360.constants import STAGE_INGEST, STAGE_PREFLIGHT
from splat360.errors import StageNotImplemented
from splat360.job import Job
from splat360.stages.base import Stage, StageResult
from splat360.utils.hashing import hash_dict


class PreflightStage(Stage):
    @property
    def name(self) -> str:
        return STAGE_PREFLIGHT
    @property
    def requires(self) -> list[str]:
        return [STAGE_INGEST]
    def run(self, job: Job, cfg: PipelineConfig) -> StageResult:
        raise StageNotImplemented(self.name, "M1")
    def fingerprint(self, job: Job, cfg: PipelineConfig) -> str:
        return hash_dict({"preflight": cfg.preflight.model_dump()})
