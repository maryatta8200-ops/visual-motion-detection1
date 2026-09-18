"""Unit tests for `vie.objects-config/1` (VIE-SPEC-REP 1.1.0 §R5)."""

from __future__ import annotations

import json

import pytest

from visual_intensity_engine.config import canonical_json, schemas_dir
from visual_intensity_engine.errors import ConfigError
from visual_intensity_engine.objects.objects_config import (
    OBJECTS_CONFIG_SCHEMA,
    ObjectsConfig,
)


def test_defaults_match_the_spec_fragment():
    assert ObjectsConfig().to_dict() == {
        "schema": "vie.objects-config/1",
        "objects_config_version": "1.0.0",
        "connectivity": 4,
        "min_area": 1,
        "max_regions": None,
        "implementation": "reference",
    }


def test_serialized_form_validates_against_the_packaged_schema():
    for config in (ObjectsConfig(), ObjectsConfig(min_area=4), ObjectsConfig(min_area=2, max_regions=500)):
        config.validate()
        assert (schemas_dir() / "objects_config.schema.json").is_file()


@pytest.mark.parametrize(
    "kwargs,message",
    [
        ({"connectivity": 8}, "connectivity=8"),
        ({"connectivity": 6}, "connectivity=6"),
        ({"min_area": 0}, "min_area must be"),
        ({"max_regions": 0}, "max_regions must be"),
        ({"implementation": "optimized"}, "implementation="),
        ({"objects_config_version": "2.0.0"}, "objects_config_version"),
    ],
)
def test_invalid_configurations_fail_with_actionable_messages(kwargs, message):
    with pytest.raises(ConfigError, match=message):
        ObjectsConfig(**kwargs)


def test_schema_rejects_connectivity_8_even_when_constructed_from_json():
    data = ObjectsConfig().to_dict()
    data["connectivity"] = 8
    with pytest.raises(ConfigError, match="schema validation"):
        ObjectsConfig.from_dict(data)


def test_from_dict_rejects_unknown_keys_and_wrong_schema():
    data = ObjectsConfig().to_dict()
    with pytest.raises(ConfigError, match="schema validation"):
        ObjectsConfig.from_dict({**data, "extra": 1})
    with pytest.raises(ConfigError, match="schema validation"):
        ObjectsConfig.from_dict({**data, "schema": "vie.objects-config/2"})
    with pytest.raises(ConfigError, match="schema validation"):
        ObjectsConfig.from_dict(["not", "a", "dict"])  # type: ignore[arg-type]


def test_sha256_is_canonical_json_and_detects_changes():
    base = ObjectsConfig()
    assert base.sha256() == __import__("hashlib").sha256(
        canonical_json(base.to_dict()).encode("utf-8")
    ).hexdigest()
    assert base.sha256() != ObjectsConfig(min_area=2).sha256()
    assert base.sha256() == ObjectsConfig().sha256()  # stable across instances
    assert len(base.sha256()) == 64


def test_round_trip_through_json_bytes_is_stable():
    config = ObjectsConfig(min_area=3, max_regions=7)
    payload = json.dumps(config.to_dict())
    assert ObjectsConfig.from_dict(json.loads(payload)) == config
    assert ObjectsConfig.from_dict(json.loads(payload)).sha256() == config.sha256()


def test_schema_id_constant_matches_the_schema_document():
    doc = json.loads((schemas_dir() / "objects_config.schema.json").read_text())
    assert doc["properties"]["schema"]["const"] == OBJECTS_CONFIG_SCHEMA
    assert doc["additionalProperties"] is False


def test_module_info_contract():
    from visual_intensity_engine.objects import objects_config

    info = objects_config.module_info()
    assert info["module"] == "visual_intensity_engine.objects.objects_config"
    assert info["config_schema"] == OBJECTS_CONFIG_SCHEMA
