import subprocess
import json
from pathlib import Path
from splat360.errors import StageFailed

def probe_video(video_path: Path) -> dict:
    """
    Probe video using ffprobe.
    """
    cmd = [
        "ffprobe", 
        "-v", "quiet", 
        "-print_format", "json", 
        "-show_format", 
        "-show_streams", 
        str(video_path)
    ]
    
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except FileNotFoundError:
        raise RuntimeError("ffprobe not found. Is ffmpeg installed?")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffprobe failed: {e.stderr}")
        
    data = json.loads(res.stdout)
    
    # Extract resolution, fps, codec
    video_streams = [s for s in data.get("streams", []) if s.get("codec_type") == "video"]
    if not video_streams:
        raise RuntimeError("No video stream found in the file.")
        
    vs = video_streams[0]
    
    width = vs.get("width", 0)
    height = vs.get("height", 0)
    
    # FPS can be a fraction string like "30/1"
    fps_str = vs.get("r_frame_rate", "0/1")
    if "/" in fps_str:
        num, den = fps_str.split("/")
        fps = float(num) / float(den) if float(den) != 0 else 0.0
    else:
        fps = float(fps_str)
        
    duration = float(data.get("format", {}).get("duration", 0.0))
    codec = vs.get("codec_name", "")
    
    # Spherical data can be buried in side_data or tags.
    # ffprobe -show_streams often shows side_data_list -> side_data_type == "Spherical Mapping"
    side_data = vs.get("side_data_list", [])
    is_spherical = any(sd.get("side_data_type") == "Spherical Mapping" for sd in side_data)
    
    # Also check format tags
    tags = data.get("format", {}).get("tags", {})
    if tags.get("major_brand") == "isom" or "spherical" in str(tags).lower():
        # Fallback check, though ffprobe spherical mapping is better
        pass
        
    return {
        "resolution": [width, height],
        "fps": fps,
        "codec": codec,
        "duration": duration,
        "is_spherical_metadata": is_spherical
    }
