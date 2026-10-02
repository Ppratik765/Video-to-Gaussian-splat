"""
CLI entry point for splat360.

Commands: run, stage, inspect, report, clean, doctor.

Responsibility: cli.py
Milestone: M0
"""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from splat360.constants import STAGE_ORDER, VERSION

app = typer.Typer(
    name="splat360",
    help="360 Video -> 3D Gaussian Splat Pipeline.",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()


def _parse_scene_timestamps(raw: str | None) -> list[tuple[float, float]] | None:
    """Parse ``--scene-timestamps`` string into a list of (start, end) pairs.

    Format: ``00:12-01:40,02:05-03:30`` or ``12.5-100.0,105-200``
    """
    if not raw:
        return None
    result: list[tuple[float, float]] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.split("-")
        if len(parts) != 2:
            raise typer.BadParameter(f"Invalid timestamp range: {chunk!r}")
        start_s, end_s = parts[0].strip(), parts[1].strip()
        result.append((_ts_to_seconds(start_s), _ts_to_seconds(end_s)))
    return result if result else None


def _ts_to_seconds(ts: str) -> float:
    """Convert 'HH:MM:SS', 'MM:SS', or plain float seconds to float."""
    if ":" in ts:
        segs = ts.split(":")
        total = 0.0
        for s in segs:
            total = total * 60 + float(s)
        return total
    return float(ts)


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"splat360 {VERSION}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", "-V", callback=_version_callback, is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """splat360 - 360 Video -> 3D Gaussian Splat Pipeline."""


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


@app.command()
def run(
    source: str = typer.Argument(..., help="YouTube URL or local video file path."),
    preset: str | None = typer.Option(None, "--preset", "-p", help="Config preset."),
    scene_timestamps: str | None = typer.Option(
        None, "--scene-timestamps", help="Comma-separated time ranges."
    ),
    workspace: str = typer.Option("workspace", "--workspace", "-w", help="Workspace root."),
    config_file: Path | None = typer.Option(None, "--config", "-c", help="Config YAML."),
    set_overrides: list[str] | None = typer.Option(None, "--set", help="key=value overrides."),
    force: bool = typer.Option(False, "--force", help="Force re-run all stages."),
    i_have_permission: bool = typer.Option(
        False, "--i-have-permission", help="Acknowledge video permission."
    ),
) -> None:
    """Run the full pipeline on a video."""
    from splat360.config import load_config
    from splat360.errors import GateRejected, StageFailed, StageNotImplemented
    from splat360.job import Job
    from splat360.stages import get_stage
    from splat360.utils.logging import setup_logging

    setup_logging()

    overrides = list(set_overrides) if set_overrides else []
    if i_have_permission:
        overrides.append("ingest.i_have_permission=true")

    cfg = load_config(
        config_file=config_file,
        preset=preset,
        set_overrides=overrides,
        force=force,
    )

    job_ws = Path(workspace) / source.replace("/", "_").replace(":", "_")[:60]
    job = Job(
        workspace=job_ws,
        cfg=cfg,
        source=source,
        scene_timestamps=_parse_scene_timestamps(scene_timestamps),
    )

    console.print(f"[bold green]Job {job.job_id}[/] → {job.workspace}")

    for stage_name in STAGE_ORDER:
        stage = get_stage(stage_name)
        try:
            result = stage.execute(job, cfg)
            if result.skipped:
                console.print(f"  [dim]{stage_name}: skipped (unchanged)[/]")
            else:
                console.print(f"  [green]✓ {stage_name}[/]")
        except StageNotImplemented as exc:
            console.print(f"  [yellow]⏭ {stage_name}: {exc}[/]")
            break
        except GateRejected as exc:
            console.print(f"  [red]✗ {stage_name}: REJECTED — {exc}[/]")
            raise typer.Exit(code=0) from exc
        except StageFailed as exc:
            console.print(f"  [red]✗ {stage_name}: FAILED — {exc}[/]")
            raise typer.Exit(code=1) from exc

    console.print("[bold green]Pipeline finished.[/]")


# ---------------------------------------------------------------------------
# stage
# ---------------------------------------------------------------------------


@app.command()
def stage(
    name: str = typer.Argument(..., help="Stage name to run."),
    job_id: str = typer.Option(..., "--job", help="Job ID."),
    workspace: str = typer.Option("workspace", "--workspace", "-w"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    """Run a single pipeline stage."""
    from splat360.config import load_config
    from splat360.errors import StageNotImplemented
    from splat360.job import Job
    from splat360.stages import get_stage
    from splat360.utils.logging import setup_logging

    setup_logging()
    cfg = load_config(force=force)
    ws = Path(workspace) / job_id
    if not ws.exists():
        console.print(f"[red]Workspace not found: {ws}[/]")
        raise typer.Exit(code=1)

    job = Job(workspace=ws, cfg=cfg, job_id=job_id)
    s = get_stage(name)
    try:
        s.execute(job, cfg)
        console.print(f"[green]✓ {name}[/]")
    except StageNotImplemented as exc:
        console.print(f"[yellow]{exc}[/]")
        raise typer.Exit(code=0) from exc


# ---------------------------------------------------------------------------
# inspect
# ---------------------------------------------------------------------------


@app.command()
def inspect(
    video: str = typer.Argument(..., help="Video URL or path to inspect."),
    preset: str | None = typer.Option(None, "--preset", "-p"),
    workspace: str = typer.Option("workspace", "--workspace", "-w"),
    scene_timestamps: str | None = typer.Option(
        None, "--scene-timestamps",
        help="Comma-separated time ranges e.g. '00:12-01:40,02:05-03:30'. Overrides auto-detect."
    ),
) -> None:
    """Run preflight only and print the verdict."""
    from splat360.config import load_config
    from splat360.errors import GateRejected, StageFailed
    from splat360.job import Job
    from splat360.stages import get_stage
    from splat360.utils.logging import setup_logging

    setup_logging()
    cfg = load_config(preset=preset)

    # Generate unique workspace for inspect
    job_ws = Path(workspace) / ("inspect_" + video.replace("/", "_").replace(":", "_")[:40])
    job = Job(
        workspace=job_ws,
        cfg=cfg,
        source=video,
        scene_timestamps=_parse_scene_timestamps(scene_timestamps),
    )

    # We must set i_have_permission for inspect so S0 doesn't fail
    job.i_have_permission = True

    # Run S0
    s0 = get_stage("s0_ingest")
    try:
        s0.execute(job, cfg)
    except StageFailed as exc:
        console.print(f"[red]Ingest failed: {exc}[/]")
        raise typer.Exit(code=1) from exc

    # Run S1
    s1 = get_stage("s1_preflight")
    try:
        s1.execute(job, cfg)
    except GateRejected:
        pass  # Expected for REJECT
    except StageFailed as exc:
        console.print(f"[red]Preflight failed: {exc}[/]")
        raise typer.Exit(code=1) from exc

    preflight_data = job.manifest.get("stages", {}).get("s1_preflight", {})
    verdict = preflight_data.get("verdict", "UNKNOWN")

    console.print(f"\n[bold]Verdict:[/] {verdict}")
    # Always show report for all verdicts
    report_path = job_ws / "report.md"
    if report_path.exists():
        console.print("\n[bold]Report:[/]")
        console.print(report_path.read_text())

# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------


@app.command()
def report(
    job_id: str = typer.Option(..., "--job", help="Job ID."),
    workspace: str = typer.Option("workspace", "--workspace", "-w"),
) -> None:
    """Display or regenerate the report for a job."""
    ws = Path(workspace) / job_id
    report_json = ws / "report.json"
    if report_json.is_file():
        data = json.loads(report_json.read_text(encoding="utf-8"))
        console.print_json(json.dumps(data, indent=2))
    else:
        console.print(f"[yellow]No report found at {report_json}[/]")


# ---------------------------------------------------------------------------
# clean
# ---------------------------------------------------------------------------


@app.command()
def clean(
    workspace: str = typer.Option("workspace", "--workspace", "-w"),
    job_id: str | None = typer.Option(None, "--job", help="Job ID to clean (all if omitted)."),
) -> None:
    """Remove workspace outputs."""
    ws = Path(workspace)
    if job_id:
        target = ws / job_id
        if target.exists():
            shutil.rmtree(target)
            console.print(f"Cleaned {target}")
        else:
            console.print(f"[yellow]Not found: {target}[/]")
    else:
        if ws.exists():
            shutil.rmtree(ws)
            console.print(f"Cleaned {ws}")
        else:
            console.print("[yellow]Nothing to clean.[/]")


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------


def _run_quiet(cmd: list[str]) -> tuple[int, str]:
    """Run a command and return (returncode, stdout+stderr)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.returncode, (result.stdout + result.stderr).strip()
    except FileNotFoundError:
        return -1, "not found"
    except subprocess.TimeoutExpired:
        return -1, "timed out"
    except Exception as exc:
        return -1, str(exc)


@app.command()
def doctor() -> None:
    """Check the environment: Python, OS, GPU, ffmpeg, COLMAP."""
    table = Table(title="splat360 doctor", show_header=True)
    table.add_column("Check", style="bold")
    table.add_column("Status")
    table.add_column("Details")

    # Python
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_impl = platform.python_implementation()
    table.add_row("Python", f"[green]{py_version}[/]", py_impl)

    # OS
    table.add_row("OS", f"[green]{platform.system()}[/]", platform.platform())

    # GPU / CUDA
    try:
        import torch

        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            vram = torch.cuda.get_device_properties(0).total_mem / (1024**3)
            table.add_row("CUDA", f"[green]{torch.version.cuda}[/]", f"{gpu_name} ({vram:.1f} GB)")
        else:
            table.add_row("CUDA", "[yellow]no GPU[/]", "torch installed but no CUDA device")
    except ImportError:
        table.add_row("CUDA", "[yellow]N/A[/]", "torch not installed")

    # ffmpeg
    rc, out = _run_quiet(["ffmpeg", "-version"])
    if rc == 0:
        first_line = out.split("\n")[0] if out else "?"
        table.add_row("ffmpeg", "[green]found[/]", first_line)
    else:
        table.add_row("ffmpeg", "[red]missing[/]", out)

    # ffprobe
    rc, out = _run_quiet(["ffprobe", "-version"])
    if rc == 0:
        first_line = out.split("\n")[0] if out else "?"
        table.add_row("ffprobe", "[green]found[/]", first_line)
    else:
        table.add_row("ffprobe", "[red]missing[/]", out)

    # COLMAP
    rc, out = _run_quiet(["colmap", "help"])
    if rc == 0 or (rc != -1):
        table.add_row("COLMAP", "[green]found[/]", out[:80] if out else "")
    else:
        table.add_row("COLMAP", "[yellow]missing[/]", "install for SfM (M3)")

    # pycolmap
    try:
        import pycolmap
        table.add_row("pycolmap", "[green]found[/]", str(getattr(pycolmap, "__version__", "?")))
    except ImportError:
        table.add_row("pycolmap", "[yellow]missing[/]", "install for SfM (M3)")

    # gsplat
    try:
        import gsplat
        table.add_row("gsplat", "[green]found[/]", str(getattr(gsplat, "__version__", "?")))
    except ImportError:
        table.add_row("gsplat", "[yellow]missing[/]", "install for training (M4)")

    # ruff
    rc, out = _run_quiet(["ruff", "--version"])
    if rc == 0:
        table.add_row("ruff", "[green]found[/]", out)
    else:
        rc2, out2 = _run_quiet([sys.executable, "-m", "ruff", "--version"])
        if rc2 == 0:
            table.add_row("ruff", "[green]found[/]", out2)
        else:
            table.add_row("ruff", "[yellow]missing[/]", "pip install ruff")

    console.print(table)
