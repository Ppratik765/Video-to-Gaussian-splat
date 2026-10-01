import json
import subprocess
from pathlib import Path
from typing import Any

from splat360.utils.logging import get_logger

logger = get_logger(__name__)


def download_video(
    url: str, out_path: Path, cookies_file: Path | None = None
) -> dict[str, Any]:
    """
    Download video using yt-dlp.
    Optional dependency, no re-encode.
    """
    logger.info(f"Downloading {url} to {out_path}")
    cmd = [
        "yt-dlp",
        "--dump-json",
        "--no-playlist",
        "-f",
        "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "-o",
        str(out_path),
        url,
    ]
    if cookies_file:
        cmd.extend(["--cookies", str(cookies_file)])

    try:
        # First get the JSON metadata
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        meta = json.loads(res.stdout.strip().split("\n")[0])

        return {
            "title": meta.get("title", ""),
            "uploader": meta.get("uploader", ""),
            "duration": meta.get("duration", 0.0),
            "resolution": [meta.get("width", 0), meta.get("height", 0)],
            "fps": meta.get("fps", 0.0),
            "codec": meta.get("vcodec", ""),
            "is_spherical_metadata": True, # assume true for now or derive
        }
    except FileNotFoundError:
        raise RuntimeError("yt-dlp not found. Please install it.") from None
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"yt-dlp failed: {e.stderr}") from None
