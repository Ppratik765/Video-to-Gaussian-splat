"""
S0: Ingest stage — download or validate a local video file.

Responsibility: s0_ingest.py
Milestone: M1
"""

from __future__ import annotations

from splat360.config import PipelineConfig
from splat360.constants import STAGE_INGEST
from splat360.errors import StageNotImplemented
from splat360.job import Job
from splat360.stages.base import Stage, StageResult
from splat360.utils.hashing import hash_dict


class IngestStage(Stage):
    @property
    def name(self) -> str:
        return STAGE_INGEST

    def run(self, job: Job, cfg: PipelineConfig) -> StageResult:
        raise StageNotImplemented(self.name, "M1")

    def fingerprint(self, job: Job, cfg: PipelineConfig) -> str:
        return hash_dict({"source": job.source, "ingest": cfg.ingest.model_dump()})
