"""Unit tests: configuration validation, canonical identity, provenance."""

from __future__ import annotations

import json

import pytest

from visual_intensity_engine.config import (
    PipelineConfig,
    canonical_json,
    config_sha256,
    schemas_dir,
    validate_against_schema,
)
from visual_intensity_engine.errors import ConfigError
from visual_intensity_engine.provenance import (
    capture_provenance,
    environment_summary,
    sha256_bytes,
    sha256_file,
    utc_now_rfc3339,
)

from ..conftest import config_dict


def test_default_config_validates_and_matches_schema():
    d = PipelineConfig.default().to_dict()
    validate_against_schema(d, schemas_dir() / "pipeline_config.schema.json", what="config")


@pytest.mark.parametrize("lv", (8, 16, 32, 64, 128, 256))
def test_shipped_config_files_validate(lv):
    path = schemas_dir().parent / "configs" / f"quantization.uniform.l{lv:03d}.v1.json"
    cfg = PipelineConfig.load(path)
    assert cfg.quantization.levels == lv
    assert cfg.sha256() == config_sha256(cfg.to_dict())


def test_canonical_json_and_hash_stability():
    a = {"b": 1, "a": {"z": [1, 2], "y": 2}}
    b = {"a": {"y": 2, "z": [1, 2]}, "b": 1}
    assert canonical_json(a) == canonical_json(b)
    assert config_sha256(a) == config_sha256(b)
    assert len(config_sha256(a)) == 64


def test_config_round_trip_save_load(tmp_path):
    cfg = PipelineConfig.default(levels=64)
    cfg.save(tmp_path / "c.json")
    loaded = PipelineConfig.load(tmp_path / "c.json")
    assert loaded == cfg
    assert loaded.sha256() == cfg.sha256()


@pytest.mark.parametrize(
    "override, fragment",
    [
        ({"quantization.levels": 1}, "levels"),
        ({"quantization.levels": 300}, "levels"),
        ({"quantization.strategy": "histogram"}, "strategy"),
        ({"quantization.scope": "per_frame_adaptive"}, "scope"),
        ({"input_domain.luma_standard": "bt470"}, "luma_standard"),
        ({"input_domain.non_finite_policy": "ignore"}, "non_finite_policy"),
        ({"serialization.format": "hdf5"}, "format"),
        ({"seed": -1}, "seed"),
    ],
)
def test_schema_rejects_invalid_configs(override, fragment):
    bad = config_dict(**override)
    with pytest.raises(ConfigError, match=fragment):
        PipelineConfig.from_dict(bad)


def test_schema_rejects_unknown_property():
    bad = config_dict()
    bad["quantization"]["unknown_knob"] = 3  # additionalProperties:false
    with pytest.raises(ConfigError, match="unknown_knob"):
        PipelineConfig.from_dict(bad)


def test_missing_and_corrupt_config_files(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        PipelineConfig.load(tmp_path / "missing.json")
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{ not json ]")
    with pytest.raises(ConfigError, match="not valid JSON"):
        PipelineConfig.load(corrupt)


def test_max_frames_optional():
    cfg = PipelineConfig.default()
    assert "max_frames" not in cfg.to_dict()
    cfg2 = PipelineConfig(
        quantization=cfg.quantization, input_domain=cfg.input_domain,
        serialization=cfg.serialization, max_frames=5,
    )
    assert cfg2.to_dict()["max_frames"] == 5
    assert PipelineConfig.from_dict(cfg2.to_dict()).max_frames == 5


# ---------------------------------------------------------------------------
# provenance
# ---------------------------------------------------------------------------

def test_utc_rfc3339_format():
    ts = utc_now_rfc3339()
    assert ts.endswith("Z") and "T" in ts
    assert len(ts) == 24  # YYYY-MM-DDTHH:MM:SS.mmmZ


def test_capture_provenance_fields():
    p = capture_provenance(seed=7)
    for key in ("git_commit", "python_version", "numpy_version", "platform", "created_at_utc", "seed"):
        assert key in p
    assert p["seed"] == 7
    assert p["platform"] and p["numpy_version"]


def test_sha256_helpers(tmp_path):
    f = tmp_path / "x.bin"
    f.write_bytes(b"vie")
    assert sha256_file(f) == sha256_bytes(b"vie")
    import hashlib

    assert sha256_bytes(b"vie") == hashlib.sha256(b"vie").hexdigest()


def test_environment_summary_privacy():
    env = environment_summary()
    # plan §41: no hostnames/PII in recorded metadata
    blob = json.dumps(env).lower()
    for forbidden in ("hostname", "user", "/home/"):
        assert forbidden not in blob
    assert env["cpu_count"] >= 1
