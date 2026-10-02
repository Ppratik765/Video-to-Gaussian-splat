# Architecture

## Stage layout per job
```
<job>/                      parent job (one per source video)
  00_source/                S0: video.mp4, source.json
  01_preflight/             S1: metrics.json (segments + verdicts), report at <job>/report.md
<job>_sNN/                  child job per scene segment (created by S1)
  02_frames/                S2: keyframes (<id>.jpg), frame_index.csv
  03_masks/                 S3: equirect masks (<id>.png), debug/ overlays
  04_views/                 S4: images/, masks/, rig.json
```
Stages S2 to S4 run per child segment with a PASS or PASS_WITH_WARNINGS verdict. Each child has
its own manifest; the parent manifest summarizes children.

## Conventions
Geometry conventions (equirect <-> ray, rig rotations) are documented and tested; see
`docs/COORDINATE_CONVENTIONS.md` and `tests/unit/geometry`.
