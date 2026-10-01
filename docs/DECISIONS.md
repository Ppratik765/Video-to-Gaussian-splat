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