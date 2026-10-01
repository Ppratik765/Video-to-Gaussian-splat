import json
from pathlib import Path
import numpy as np

from splat360.stages.base import Stage, StageResult
from splat360.job import Job
from splat360.config import PipelineConfig
from splat360.utils.logging import get_logger

# Optional dependencies for S1
try:
    import cv2
except ImportError:
    cv2 = None

try:
    from scenedetect import detect, ContentDetector, AdaptiveDetector
except ImportError:
    detect = None

logger = get_logger(__name__)

class PreflightStage(Stage):
    name = "s1_preflight"
    requires = ["s0_ingest"]
    
    def fingerprint(self, job: Job, cfg: PipelineConfig) -> str:
        return "preflight_v1"
        
    def run(self, job: Job, cfg: PipelineConfig) -> StageResult:
        source_dir = job.workspace / "00_source"
        preflight_dir = job.workspace / "01_preflight"
        preflight_dir.mkdir(parents=True, exist_ok=True)
        
        source_json_path = source_dir / "source.json"
        with open(source_json_path, "r", encoding="utf-8") as f:
            source_data = json.load(f)
            
        video_path = source_dir / "video.mp4"
        
        # 1. Format check
        w, h = source_data.get("resolution", [0, 0])
        aspect = w / h if h > 0 else 0
        
        reasons = []
        verdict = "PASS"
        
        if aspect < 1.9 or aspect > 2.1:
            if aspect > 0.9 and aspect < 1.1:
                # Top/Bottom stereo likely
                stereo_policy = cfg.preflight.stereo_policy
                if stereo_policy == "reject":
                    verdict = "REJECT"
                    reasons.append({
                        "code": "stereo_unsupported", 
                        "severity": "fatal", 
                        "message": "Video appears to be 1:1 Top/Bottom stereo. Configured to reject."
                    })
            else:
                verdict = "REJECT"
                reasons.append({
                    "code": "not_equirect",
                    "severity": "fatal",
                    "message": f"Aspect ratio {aspect:.2f} is not 2:1. Not an equirectangular video."
                })
        
        # S1 preflight metrics
        metrics = {
            "format_valid": verdict != "REJECT",
            "aspect_ratio": aspect,
            "scene_count": 1,
            "blur_fraction": 0.0,
            "exposure_flicker": 0.0,
            "median_flow": 0.0,
            "rotation_ratio": 0.0,
            "camera_attached_occlusion": "not_evaluated",
            "dynamic_content": "not_evaluated"
        }
        
        # S1 video processing (scene detect, flow, blur)
        if verdict != "REJECT" and cv2 is not None:
            video_path = source_dir / "video.mp4"
            
            # Scene detect
            from scenedetect import detect, AdaptiveDetector
            try:
                scene_list = detect(str(video_path), AdaptiveDetector())
                metrics["scene_count"] = max(1, len(scene_list))
            except Exception as e:
                logger.warning(f"Scene detection failed: {e}")
                
            cap = cv2.VideoCapture(str(video_path))
            if not cap.isOpened():
                raise StageFailed(self.name, "Could not open video file.")
            
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            duration = total_frames / fps if fps > 0 else 0
            
            if duration < cfg.preflight.min_segment_seconds:
                verdict = "REJECT"
                reasons.append({
                    "code": "too_short",
                    "severity": "fatal",
                    "message": f"Video duration {duration:.1f}s is below minimum {cfg.preflight.min_segment_seconds}s"
                })
            
            blurs = []
            exposures = []
            flows = []
            
            prev_gray = None
            
            frame_idx = 0
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                    
                # Downsample for speed
                h, w = frame.shape[:2]
                small = cv2.resize(frame, (640, 320))
                gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                
                # Blur
                laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
                blurs.append(laplacian_var)
                
                # Exposure
                exposures.append(gray.mean())
                
                # Flow
                if prev_gray is not None:
                    flow = cv2.calcOpticalFlowFarneback(prev_gray, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0)
                    mag, ang = cv2.cartToPolar(flow[..., 0], flow[..., 1])
                    flows.append(np.median(mag))
                
                prev_gray = gray
                frame_idx += 1
                
                # Limit to 300 frames for preflight speed
                if frame_idx > 300:
                    break
                    
            cap.release()
            
            if blurs:
                blur_fraction = sum(1 for b in blurs if b < cfg.preflight.blur_threshold) / len(blurs)
                metrics["blur_fraction"] = blur_fraction
                if blur_fraction > cfg.preflight.max_blur_fraction:
                    verdict = "REJECT"
                    reasons.append({"code": "excess_blur", "severity": "fatal", "message": f"Too many blurry frames ({blur_fraction*100:.0f}%)"})
            
            if exposures:
                exposure_flicker = np.std(exposures)
                metrics["exposure_flicker"] = exposure_flicker
                if exposure_flicker > 50.0:  # arbitrary threshold for unstable exposure
                    verdict = "REJECT"
                    reasons.append({"code": "exposure_unstable", "severity": "fatal", "message": "Exposure is highly unstable."})
                    
            if flows:
                median_flow = float(np.median(flows))
                metrics["median_flow"] = median_flow
                if median_flow < cfg.preflight.min_flow_magnitude:
                    verdict = "REJECT"
                    reasons.append({"code": "no_parallax", "severity": "fatal", "message": f"Insufficient camera motion (flow {median_flow:.2f} px < {cfg.preflight.min_flow_magnitude})"})
                elif median_flow > cfg.preflight.max_flow_magnitude:
                    if verdict != "REJECT":
                        verdict = "PASS_WITH_WARNINGS"
                    reasons.append({"code": "motion_too_fast", "severity": "warning", "message": f"Motion might be too fast (flow {median_flow:.2f} px)"})
            
        # Write metrics
        metrics_path = preflight_dir / "metrics.json"
        with open(metrics_path, "w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2)
            
        # Write report
        report_path = job.workspace / "report.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(f"# Preflight Report\n\nVerdict: {verdict}\n\n")
            for r in reasons:
                f.write(f"- {r['code']}: {r['message']}\n")
                
        job.update_manifest_stage(self.name, {"verdict": verdict, "metrics": metrics})
        
        if verdict == "REJECT":
            logger.error("Preflight REJECTED the video.")
            # Important: M1 requires "REJECT must exit cleanly (dedicated exit code), not crash."
            # Our cli.py will handle returning a specific exit code if verdict is REJECT.
            return StageResult(success=True, message="Rejected at preflight")
            
        return StageResult(success=True, message="Preflight PASS")
