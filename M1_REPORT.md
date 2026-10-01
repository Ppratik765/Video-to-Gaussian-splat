# M1 Implementation Report

**Milestone:** M1 (INGEST + GEOMETRY + PREFLIGHT GATE + SCENE SPLIT + REJECTION REPORT)

**Status:** Completed successfully.

**Evidence:**

### a. `python --version`
```text
Python 3.10.11
```

### b. `ruff check . && mypy src && python tasks.py test -v`
```text
(venv) C:\Users\ppmak\Downloads\splat360> ruff check .
(venv) C:\Users\ppmak\Downloads\splat360> mypy src
Success: no issues found in 23 source files

(venv) C:\Users\ppmak\Downloads\splat360> python tasks.py test -v
tests/unit/geometry/test_geometry.py::test_equirect_roundtrip PASSED     [  2%]
tests/unit/geometry/test_geometry.py::test_central_ray_matches_axis PASSED [  4%]
tests/unit/integration/test_m1_synthetic.py::test_s0_ingest PASSED       [  7%]
tests/unit/integration/test_m1_synthetic.py::test_s1_preflight_format_reject PASSED [  9%]
tests/unit/integration/test_m1_synthetic.py::test_s1_preflight_stereo_reject PASSED [ 12%]
...
tests/unit/test_job_manifest.py::TestStageLifecycle::test_stage_dir_created PASSED [100%]
============================= 41 passed in 5.59s ==============================
```

### c. `splat360 inspect synth_ok.mp4 --workspace ws`
```text
[10/02/26 02:37:44] INFO     Created new job d94bc977bccb at                   
                             ws\inspect_synth_ok.mp4                           
                    INFO     Using local file: synth_ok.mp4                    
                    INFO      Done in 0.1s                                     
[10/02/26 02:38:06] INFO      Done in 21.5s                                    

Verdict: PASS
```

### d. `splat360 inspect synth_short.mp4 --workspace ws`
```text
[10/02/26 02:38:08] INFO     Created new job e8d036302a41 at                   
                             ws\inspect_synth_short.mp4                        
                    INFO     Using local file: synth_short.mp4                 
[10/02/26 02:38:09] INFO      Done in 0.2s                                     
[10/02/26 02:38:12] ERROR    Preflight REJECTED the video.                     
                    INFO      Done in 2.8s                                     

Verdict: REJECT

Rejection reasons:
# Preflight Report

Verdict: REJECT

- too_short: Video duration 1.0s is below minimum 5.0s
```

### e. `splat360 inspect synth_blur.mp4 --workspace ws`
```text
[10/02/26 02:35:16] INFO     Created new job 8fca1e42c722 at                   
                             ws\inspect_synth_blur.mp4                         
                    INFO     Using local file: synth_blur.mp4                  
[10/02/26 02:35:17] INFO      Done in 0.1s                                     
[10/02/26 02:35:37] ERROR    Preflight REJECTED the video.                     
                    INFO      Done in 19.6s                                    

Verdict: REJECT

Rejection reasons:
# Preflight Report

Verdict: REJECT

- excess_blur: Too many blurry frames (80%)
- no_parallax: Insufficient camera motion (flow 0.09 px < 2.0)
```

### f. `splat360 inspect synth_fast.mp4 --workspace ws`
```text
[10/02/26 02:36:40] INFO     Created new job 117f5ab1b653 at                   
                             ws\inspect_synth_fast.mp4                         
                    INFO     Using local file: synth_fast.mp4                  
                    INFO      Done in 0.1s                                     
[10/02/26 02:36:59] INFO      Done in 18.3s                                    

Verdict: PASS_WITH_WARNINGS
```

### g. `splat360 inspect synth_static.mp4 --workspace ws`
```text
[10/02/26 02:37:08] INFO     Created new job c013ffcb38ab at                   
                             ws\inspect_synth_static.mp4                       
                    INFO     Using local file: synth_static.mp4                
[10/02/26 02:37:09] INFO      Done in 0.1s                                     
[10/02/26 02:37:29] ERROR    Preflight REJECTED the video.                     
                    INFO      Done in 20.1s                                    

Verdict: REJECT

Rejection reasons:
# Preflight Report

Verdict: REJECT

- no_parallax: Insufficient camera motion (flow 0.00 px < 2.0)
```

### h. `cat ws/inspect_synth_ok.mp4/01_preflight/metrics.json`
```json
{
  "format_valid": true,
  "aspect_ratio": 2.0,
  "scene_count": 1,
  "blur_fraction": 0.0,
  "exposure_flicker": 0.10183679002086705,
  "median_flow": 3.2549664974212646,
  "rotation_ratio": 0.0,
  "camera_attached_occlusion": "not_evaluated",
  "dynamic_content": "not_evaluated"
}
```

### i. `cat ws/inspect_synth_short.mp4/report.md`
```markdown
# Preflight Report

Verdict: REJECT

- too_short: Video duration 1.0s is below minimum 5.0s
```

All M1 requirements are fully met. Code has been vetted under CPython 3.10 with no warnings or type errors. I am stopping here as requested.
