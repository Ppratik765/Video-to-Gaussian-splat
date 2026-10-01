# Splat360

A robust and scalable pipeline for converting 360-degree videos into high-fidelity 3D Gaussian Splats.

## Overview

Splat360 is an automated end-to-end processing framework designed to ingest equirectangular 360-degree video footage, extract high-quality keyframes, construct rigorous Structure-from-Motion (SfM) point clouds, and train performant 3D Gaussian Splatting (3DGS) models. It is built to address the unique complexities of 360-degree geometry, including spherical distortion handling, dynamic subject masking, and rigorous photometric preflight checks.

The framework emphasizes idempotency and reproducibility. Pipeline executions are managed as "Jobs", where each processing stage is individually fingerprinted based on its inputs, configuration, and code state. This caching layer allows for reliable resumption of failed jobs, rapid experimentation, and efficient use of compute resources without unnecessary recalculation.

## Key Features

* **End-to-End Pipeline**: A fully integrated system handling video ingestion, frame extraction, masking, SfM via COLMAP, and 3D Gaussian Splatting via `gsplat`.
* **Idempotent Execution Engine**: JSON-based manifest tracking and SHA-256 fingerprinting ensures that stages are only executed when their inputs or configuration change. 
* **Deep Configuration Management**: Powered by Pydantic v2, supporting deep hierarchical configuration merges, environment-specific overrides, and JSON schema generation.
* **Spherical Rig Geometry**: Specialized extraction techniques specifically tailored for 360-degree equirectangular projections rather than traditional pinhole camera models.
* **Extensive Diagnostics**: Automated environment checking (`doctor` command) and preflight gating to prevent pipeline execution on invalid or low-quality data.
* **Detailed Reporting**: Generates comprehensive post-training HTML/Markdown reports outlining reconstruction metrics, execution times, and visual coverage.

## Architecture

The system is composed of several discrete pipeline stages that transition a raw video into a queryable 3D representation:

1. **Ingest (`s0_ingest`)**: Acquisition and validation of source video files.
2. **Preflight (`s1_preflight`)**: Quality assurance, rotation detection, and metadata extraction.
3. **Frames (`s2_frames`)**: Keyframe decimation and equirectangular remapping into sub-views.
4. **Masks (`s3_masks`)**: Semantic masking of dynamic objects (e.g., tripods, operators).
5. **Rig (`s4_rig`)**: Synthetic multi-camera rig construction for robust SfM.
6. **SfM (`s5_sfm`)**: Feature matching and bundle adjustment via COLMAP.
7. **Post-SfM Gate (`s6_postsfm_gate`)**: Metric validation of the sparse point cloud.
8. **Train (`s7_train`)**: Optimization of the 3D Gaussian Splatting scene representation.
9. **Export & Eval (`s8_export_eval`)**: Generation of standardized `.ply` formats and rendering evaluation.
10. **Report (`s9_report`)**: Compilation of comprehensive execution and quality metrics.

## Installation

### Prerequisites

Splat360 requires a robust compute environment. The following dependencies must be installed on your system:

* **Python**: `^3.10` (CPython 3.10.11 recommended; PyPy is not supported due to native extension constraints).
* **CUDA Toolkit**: Required for `torch` and `gsplat` GPU acceleration.
* **FFmpeg**: Required for video decoding, frame extraction, and formatting. Must be available on your system `PATH`.
* **COLMAP**: Required for Structure-from-Motion.

### Environment Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/Ppratik765/Video-to-Gaussian-splat.git
   cd Video-to-Gaussian-splat
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   # On Windows:
   .\venv\Scripts\activate
   # On Linux/macOS:
   source venv/bin/activate
   ```

3. Install the Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Verify your environment setup:
   ```bash
   splat360 doctor
   ```

## Usage

Splat360 provides a feature-rich CLI powered by Typer.

### Global Commands

View the full command reference:
```bash
splat360 --help
```

### Running the Pipeline

To execute the entire pipeline end-to-end on a video file:
```bash
splat360 run path/to/video.mp4 --preset quality
```

To run a specific stage in isolation (useful for development and debugging):
```bash
splat360 stage s0_ingest path/to/video.mp4
```

### Analysis and Reporting

Inspect a job's manifest without running the pipeline:
```bash
splat360 inspect path/to/video.mp4
```

Regenerate the final quality report:
```bash
splat360 report path/to/video.mp4
```

Clean the workspace outputs for a given job:
```bash
splat360 clean path/to/video.mp4
```

## Development

The project utilizes `tasks.py` as a cross-platform command runner. 

* **Testing**: Run the unit test suite via `pytest`.
  ```bash
  python tasks.py test
  ```
* **Linting and Formatting**: The project uses `ruff` for fast linting and formatting.
  ```bash
  python tasks.py format
  python tasks.py lint
  ```
* **Type Checking**: Static analysis is enforced using `mypy`.
  ```bash
  python tasks.py typecheck
  ```

Configuration schemas can be generated dynamically:
```bash
python -m splat360.config --schema
```