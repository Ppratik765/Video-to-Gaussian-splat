"""
Stage abstract base class, StageResult dataclass, and caching/skip logic.

Every concrete stage inherits from ``Stage`` and implements ``name``,
``run()``, and ``fingerprint()``.  The base class handles:
- computing and comparing fingerprints (skip-if-unchanged)
- honouring ``--force``
- timing
- recording success/failure in the manifest

Responsibility: stages/base.py
Milestone: M0
"""

from __future__ import annotations

import time
import traceback
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from splat360.config import PipelineConfig
from splat360.constants import STATUS_DONE
from splat360.errors import GateRejected, StageFailed
from splat360.job import Job
from splat360.utils.logging import get_logger

log = get_logger("stages.base")


# ---------------------------------------------------------------------------
# StageResult
# ---------------------------------------------------------------------------


@dataclass
class StageResult:
    """Value returned by ``Stage.run()``."""

    success: bool = True
    message: str = ""
    verdict: str | None = None  # for gate stages
    reasons: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    skipped: bool = False


# ---------------------------------------------------------------------------
# Stage ABC
# ---------------------------------------------------------------------------


class Stage(ABC):
    """Abstract base for pipeline stages."""

    @property
    @abstractmethod
    def name(self) -> str:
        """The canonical stage name (e.g. ``s0_ingest``)."""

    @property
    def requires(self) -> list[str]:
        """Stage names that must complete before this one.

        Defaults to an empty list.  Override in subclasses.
        """
        return []

    @abstractmethod
    def run(self, job: Job, cfg: PipelineConfig) -> StageResult:
        """Execute the stage's work.

        Implementations should:
        - write outputs into ``job.stage_dir(self.name)``
        - return a ``StageResult``
        - raise ``GateRejected`` for a rejection verdict (this is *not* an error)
        """

    @abstractmethod
    def fingerprint(self, job: Job, cfg: PipelineConfig) -> str:
        """Compute a deterministic hash of the inputs and config relevant to
        this stage.

        If the returned fingerprint matches what's stored in the manifest
        *and* outputs exist, the stage is skipped.
        """

    # ------------------------------------------------------------------
    # Execution wrapper
    # ------------------------------------------------------------------

    def execute(self, job: Job, cfg: PipelineConfig) -> StageResult:
        """Run this stage with caching, timing, and error handling.

        Returns a ``StageResult``.  On failure the error is recorded in the
        manifest and a ``StageFailed`` is raised.  A ``GateRejected`` is
        caught, recorded as a *successful* result with ``verdict=REJECT``,
        and re-raised so the pipeline can stop cleanly.
        """
        stage_name = self.name

        # --- fingerprint / cache check ---
        fp = self.fingerprint(job, cfg)
        if not cfg.force:
            stored = job.stage_fingerprint(stage_name)
            if (
                stored is not None
                and stored == fp
                and job.stage_status(stage_name) == STATUS_DONE
            ):
                log.info("[%s] Skipped (fingerprint unchanged)", stage_name)
                job.mark_skipped(stage_name)
                return StageResult(skipped=True, message="unchanged")

        # --- run ---
        job.mark_running(stage_name)
        t0 = time.monotonic()

        try:
            result = self.run(job, cfg)
        except GateRejected as exc:
            duration = time.monotonic() - t0
            job.mark_done(stage_name, fp, duration)
            log.info("[%s] Gate rejected: %s", stage_name, exc)
            raise
        except Exception as exc:
            duration = time.monotonic() - t0
            tb = traceback.format_exc()
            job.mark_failed(stage_name, f"{exc}\n{tb}")
            log.error("[%s] Failed: %s", stage_name, exc)
            raise StageFailed(stage_name, str(exc)) from exc

        duration = time.monotonic() - t0
        job.mark_done(stage_name, fp, duration)
        log.info("[%s] Done in %.1fs", stage_name, duration)
        return result
