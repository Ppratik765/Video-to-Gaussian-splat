"""
Tests for config.py: loading, merging, overrides, schema generation.

Asserts real behaviour: precedence, deep merge, --set parsing, validation errors.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from splat360.config import (
    PipelineConfig,
    _apply_set_overrides,
    _deep_merge,
    config_to_dict,
    generate_schema,
    load_config,
)
from splat360.errors import ConfigError


# ---------------------------------------------------------------------------
# Deep-merge logic
# ---------------------------------------------------------------------------


class TestDeepMerge:
    def test_flat_override(self) -> None:
        base = {"a": 1, "b": 2}
        over = {"b": 99}
        assert _deep_merge(base, over) == {"a": 1, "b": 99}

    def test_nested_merge(self) -> None:
        base = {"x": {"a": 1, "b": 2}}
        over = {"x": {"b": 3, "c": 4}}
        result = _deep_merge(base, over)
        assert result == {"x": {"a": 1, "b": 3, "c": 4}}

    def test_does_not_mutate_base(self) -> None:
        base = {"x": {"a": 1}}
        over = {"x": {"b": 2}}
        _deep_merge(base, over)
        assert base == {"x": {"a": 1}}


# ---------------------------------------------------------------------------
# --set override parsing
# ---------------------------------------------------------------------------


class TestSetOverrides:
    def test_simple_string(self) -> None:
        data: dict = {}
        result = _apply_set_overrides(data, ["preset=ride_fast"])
        assert result["preset"] == "ride_fast"

    def test_dotted_path_numeric(self) -> None:
        data: dict = {}
        result = _apply_set_overrides(data, ["train.max_steps=50000"])
        assert result["train"]["max_steps"] == 50000

    def test_boolean_json(self) -> None:
        data: dict = {}
        result = _apply_set_overrides(data, ["ingest.i_have_permission=true"])
        assert result["ingest"]["i_have_permission"] is True

    def test_missing_equals_raises(self) -> None:
        with pytest.raises(ConfigError, match="key=value"):
            _apply_set_overrides({}, ["no_equals_here"])


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------


class TestLoadConfig:
    def test_defaults_produce_valid_config(self) -> None:
        cfg = load_config()
        assert isinstance(cfg, PipelineConfig)
        assert cfg.version == "0.1.0"

    def test_set_override_changes_value(self) -> None:
        cfg = load_config(set_overrides=["train.max_steps=100"])
        assert cfg.train.max_steps == 100

    def test_force_flag(self) -> None:
        cfg = load_config(force=True)
        assert cfg.force is True

    def test_unknown_preset_raises(self) -> None:
        with pytest.raises(ConfigError, match="Unknown preset"):
            load_config(preset="nonexistent_preset_xyz")

    def test_missing_config_file_raises(self) -> None:
        with pytest.raises(ConfigError, match="not found"):
            load_config(config_file=Path("/does/not/exist.yaml"))


# ---------------------------------------------------------------------------
# Config serialisation
# ---------------------------------------------------------------------------


class TestConfigSerialization:
    def test_round_trip(self) -> None:
        cfg = load_config()
        d = config_to_dict(cfg)
        assert isinstance(d, dict)
        assert d["version"] == cfg.version
        assert d["train"]["max_steps"] == cfg.train.max_steps

    def test_schema_generation(self) -> None:
        schema = generate_schema()
        assert "properties" in schema
        assert "train" in schema["properties"]
        # The schema should be valid JSON
        json.dumps(schema)


# ---------------------------------------------------------------------------
# Precedence: set overrides beat defaults
# ---------------------------------------------------------------------------


class TestPrecedence:
    def test_set_overrides_beat_defaults(self) -> None:
        default = load_config()
        overridden = load_config(set_overrides=["frames.max_keyframes=42"])
        assert default.frames.max_keyframes == 600
        assert overridden.frames.max_keyframes == 42