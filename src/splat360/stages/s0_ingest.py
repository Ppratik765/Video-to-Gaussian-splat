import json
import shutil
from pathlib import Path
from typing import ClassVar

from splat360.config import PipelineConfig
from splat360.errors import StageFailed
from splat360.ingest.downloader import download_video
from splat360.ingest.probe import probe_video
from splat360.job import Job
from splat360.stages.base import Stage, StageResult
from splat360.utils.logging import get_logger

logger = get_logger(__name__)

class IngestStage(Stage):
    name = "s0_ingest"
    requires: ClassVar[list[str]] = []

    def fingerprint(self, job: Job, cfg: PipelineConfig) -> str:
        return f"ingest_{getattr(job, 'source_url_or_path', '')}"

    def run(self, job: Job, cfg: PipelineConfig) -> StageResult:
        source_dir = job.workspace / "00_source"
        source_dir.mkdir(parents=True, exist_ok=True)

        url_or_path = getattr(job, "source", None)
        if not url_or_path:
            raise StageFailed(self.name, "No source URL or path provided.")

        permission_note = getattr(job, "permission_note", None)
        i_have_permission = getattr(job, "i_have_permission", False)

        if not permission_note and not i_have_permission:
            raise StageFailed(self.name, "Missing mandatory permission_note. Refusing to run unless --i-have-permission is passed.")

        cookies_file = getattr(job, "cookies", None)

        source_json_path = source_dir / "source.json"
        video_out_path = source_dir / "video.mp4"

        # Download or copy
        if url_or_path.startswith("http://") or url_or_path.startswith("https://"):
            logger.info(f"Downloading from URL: {url_or_path}")
            metadata = download_video(url_or_path, video_out_path, cookies_file)
        else:
            logger.info(f"Using local file: {url_or_path}")
            local_path = Path(url_or_path)
            if not local_path.exists():
                raise StageFailed(self.name, f"Local file not found: {local_path}")
            # Instead of copying, we can just symlink or copy to keep workspace self-contained
            shutil.copy2(local_path, video_out_path)
            metadata = {"title": local_path.name, "uploader": "local", "duration": 0}

        # Probe
        probe_meta = probe_video(video_out_path)
        metadata.update(probe_meta)

        # Save source.json
        source_data = {
            "url_or_path": url_or_path,
            "title": metadata.get("title", ""),
            "uploader": metadata.get("uploader", ""),
            "duration": metadata.get("duration", 0),
            "resolution": metadata.get("resolution", [0, 0]),
            "fps": metadata.get("fps", 0.0),
            "codec": metadata.get("codec", ""),
            "permission_note": permission_note or "User asserted --i-have-permission"
        }

        with open(source_json_path, "w", encoding="utf-8") as f:
            json.dump(source_data, f, indent=2)

        # Log to manifest
        job.update_manifest_stage(self.name, {"source": source_data})

        return StageResult(success=True, message="Ingest complete")
