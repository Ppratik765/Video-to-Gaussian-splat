"""S7: Gaussian splat training (gsplat). Milestone: M4"""
from __future__ import annotations
from splat360.config import PipelineConfig
from splat360.constants import STAGE_POSTSFM_GATE, STAGE_TRAIN
from splat360.errors import StageNotImplemented
from splat360.job import Job
from splat360.stages.base import Stage, StageResult
from splat360.utils.hashing import hash_dict

class TrainStage(Stage):
    @property
    def name(self) -> str:
        return STAGE_TRAIN
    @property
    def requires(self) -> list[str]:
        return [STAGE_POSTSFM_GATE]
    def run(self, job: Job, cfg: PipelineConfig) -> StageResult:
        raise StageNotImplemented(self.name, "M4")
    def fingerprint(self, job: Job, cfg: PipelineConfig) -> str:
        return hash_dict({"train": cfg.train.dict()})
