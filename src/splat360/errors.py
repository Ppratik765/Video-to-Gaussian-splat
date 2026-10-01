"""
Typed exception hierarchy for the pipeline.

All exceptions are subclasses of Splat360Error so callers can catch broadly.
Stage orchestrators translate Python-level errors into manifest status entries;
a GateRejected is *not* a crash — it means the pipeline made a decision.

Responsibility: errors.py
Milestone: M0
"""

from __future__ import annotations


class Splat360Error(Exception):
    """Base class for all splat360 errors."""


class ConfigError(Splat360Error):
    """Invalid configuration (missing key, bad type, unknown preset, etc.)."""


class StageFailed(Splat360Error):
    """A pipeline stage crashed or could not produce its outputs."""

    def __init__(self, stage_name: str, message: str) -> None:
        self.stage_name = stage_name
        super().__init__(f"Stage {stage_name} failed: {message}")


class GateRejected(Splat360Error):
    """A gate stage decided the input is not reconstructable.

    This is a *normal* outcome, not a bug.  The pipeline exits cleanly and
    produces a rejection report.
    """

    def __init__(self, stage_name: str, reasons: list[dict[str, object]]) -> None:
        self.stage_name = stage_name
        self.reasons = reasons
        codes = [str(r.get("code", "?")) for r in reasons]
        super().__init__(
            f"Gate {stage_name} rejected: {', '.join(codes)}"
        )


class MissingDependency(Splat360Error):
    """A required external tool (ffmpeg, COLMAP, …) is not installed."""

    def __init__(self, tool: str, hint: str = "") -> None:
        self.tool = tool
        msg = f"Missing dependency: {tool}"
        if hint:
            msg += f" — {hint}"
        super().__init__(msg)


class StageNotImplemented(Splat360Error):
    """Raised by stages that belong to a later milestone."""

    def __init__(self, stage_name: str, milestone: str) -> None:
        self.stage_name = stage_name
        self.milestone = milestone
        super().__init__(
            f"Stage {stage_name} is not yet implemented (planned for {milestone})"
        )
