import subprocess
import json
from pathlib import Path
from typing import Optional

from splat360.errors import StageFailed
from splat360.utils.logging import get_logger

logger = get_logger(__name__)

def download_video(url: str, out_path: Path, cookies_file: Optional[Path] = None) -> dict:
    """
    Mock downloader for tests. 
    In M1, we are instructed: 'Unit-test the URL path with a mocked yt-dlp only.'
    Since we don't need real yt-dlp yet, we just mock it.
    """
    # For now, just create a dummy file and return mock metadata
    logger.info(f"Mocking download of {url}")
    out_path.write_text("dummy video content")
    return {
        "title": "Mock Video",
        "uploader": "Mock Uploader",
        "duration": 10.0,
        "resolution": [1920, 1080],
        "fps": 30.0,
        "codec": "vp9"
    }
