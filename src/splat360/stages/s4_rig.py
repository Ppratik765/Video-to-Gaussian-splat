"""S4: Equirect → perspective rig views. Milestone: M2"""
from __future__ import annotations

from splat360.config import PipelineConfig
from splat360.constants import STAGE_MASKS, STAGE_RIG
from splat360.errors import StageNotImplemented
from splat360.job import Job
from splat360.stages.base import Stage, StageResult
from splat360.utils.hashing import hash_dict


class RigStage(Stage):
    @property
    def name(self) -> str:
        return STAGE_RIG
    @property
    def requires(self) -> list[str]:
        return [STAGE_MASKS]
    def run(self, job: Job, cfg: PipelineConfig) -> StageResult:
        raise StageNotImplemented(self.name, "M2")
    def fingerprint(self, job: Job, cfg: PipelineConfig) -> str:
        return hash_dict({"rig": cfg.rig.model_dump()})
