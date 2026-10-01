"""S5: SfM with rig constraints (COLMAP). Milestone: M3"""
from __future__ import annotations
from splat360.config import PipelineConfig
from splat360.constants import STAGE_RIG, STAGE_SFM
from splat360.errors import StageNotImplemented
from splat360.job import Job
from splat360.stages.base import Stage, StageResult
from splat360.utils.hashing import hash_dict

class SfmStage(Stage):
    @property
    def name(self) -> str:
        return STAGE_SFM
    @property
    def requires(self) -> list[str]:
        return [STAGE_RIG]
    def run(self, job: Job, cfg: PipelineConfig) -> StageResult:
        raise StageNotImplemented(self.name, "M3")
    def fingerprint(self, job: Job, cfg: PipelineConfig) -> str:
        return hash_dict({"sfm": cfg.sfm.dict()})
