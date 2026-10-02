# Decisions

Architecture Decision Record (ADR) log for Splat360.

## 2026-10-02: Use `tasks.py` instead of `make`
**Context**: Windows environments lack `make` out of the box, leading to failures during development and CI setup.
**Decision**: Adopt a pure Python `tasks.py` script as a cross-platform command runner.
**Consequences**: The `Makefile` is deprecated/reduced to a redirect. Developers can run `python tasks.py test` seamlessly on Windows, macOS, and Linux without installing GNU Make.

## 2026-10-02: Enforce CPython 3.10 and Pydantic v2
**Context**: We initially explored PyPy for performance and had to downgrade to Pydantic v1 because `pydantic-core` (v2) requires a Rust toolchain which fails on PyPy in many environments.
**Decision**: Revert to standard CPython 3.10 (which exactly matches Google Colab's default environment). Migrate fully to pure Pydantic v2 (`BaseModel`, `model_dump()`, etc) without any v1 compatibility wrappers.
**Consequences**: Eliminates complex build failures for native dependencies (like `gsplat`). Aligns our development environment strictly with the target deployment environment (Google Colab).

## 2026-10-02: ASCII-only CLI Output
**Context**: Typer's CLI help generation crashed with `UnicodeEncodeError` when encountering characters like `→` and `°` on Windows terminals using the default `cp1252` encoding.
**Decision**: Remove non-ASCII characters from `__init__.py` descriptions and `cli.py` docstrings.
**Consequences**: Ensures the CLI can be invoked natively on all Windows systems without requiring users to actively switch their terminal codepages to UTF-8 (`chcp 65001`).

## 2026-10-02: 3DGS is Per-Scene Optimization, Not General Training
**Context**: Clarity is needed on hardware constraints and training topology for the 3D Gaussian Splatting stage.
**Decision**: 3DGS involves optimizing parameters for a *single specific scene* based on its SfM points and images. There is no generalized "model training" across datasets, and thus no TPU requirement or distributed data parallel setup is needed.
**Consequences**: The pipeline runs locally or on a single GPU node (like a Colab T4). The word "Train" refers strictly to scene optimization.

## 2026-10-02: Keyframes selected by accumulated translation parallax (M2a)
**Decision**: S2 reuses the S1 rotation-fit residual and accumulates it per frame pair; keyframes are written to disk immediately (generator), not collected in memory.
**Consequences**: Dense sampling during motion, sparse when stopped; bounded memory on large 360 frames.

## 2026-10-02: Camera-attached mask by temporal variance, with known limits (M2a)
**Decision**: Streaming per-pixel variance per rig view relative to the view's median variance, with a scene-change precondition and a manual override.
**Consequences**: Measured IoU about 0.61 on the synthetic occluder (target 0.8 not met); low-variance scene regions are also flagged. Real-footage review (M2b) decides whether an extra cue is needed.

## 2026-10-02: Semantic segmenter optional and license-unconfirmed (M2a)
**Decision**: `Segmenter` interface with `NullSegmenter` default; HF SegFormer/Mask2Former are lazy, optional and off by default because the HF license tag is "other".
**Consequences**: CI and default runs need no model weights. Confirm terms before enabling or redistributing.

## 2026-10-02: Stage skip check uses STATUS_DONE (M2a fix)
**Context**: S2/S3/S4 compared the stored status to `"DONE"`, but the manifest stores `"done"`, so child stages were never skipped.
**Decision**: Compare against the `STATUS_DONE` constant; covered by a rerun/skip test.
