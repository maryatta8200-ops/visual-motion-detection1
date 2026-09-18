"""Objects configuration (vie.objects-config/1) — Phase 2.

Same strictness pattern as the Phase 1 pipeline config: every field is validated
against the packaged JSON Schema, `additionalProperties` is false, and extension
points fail until they are specified and tested (§R5). In particular
`connectivity: 8` is *rejected* rather than silently treated as 4.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import canonical_json, schemas_dir, validate_against_schema
from ..errors import ConfigError

OBJECTS_CONFIG_VERSION = "1.0.0"
OBJECTS_CONFIG_SCHEMA = "vie.objects-config/1"
OBJECTS_CONFIG_SCHEMA_FILE = "objects_config.schema.json"
SUPPORTED_CONNECTIVITY = (4,)
SUPPORTED_IMPLEMENTATIONS = ("reference",)


@dataclass(frozen=True)
class ObjectsConfig:
    connectivity: int = 4
    min_area: int = 1
    max_regions: int | None = None
    implementation: str = "reference"
    objects_config_version: str = OBJECTS_CONFIG_VERSION

    def __post_init__(self) -> None:
        if self.connectivity not in SUPPORTED_CONNECTIVITY:
            raise ConfigError(
                f"connectivity={self.connectivity} is not supported; "
                f"VIE-SPEC-REP 1.1.0 §R2 defines level-uniform 4-connected regions "
                f"and extension points must fail until specified and tested"
            )
        if self.implementation not in SUPPORTED_IMPLEMENTATIONS:
            raise ConfigError(
                f"implementation={self.implementation!r} is not supported "
                f"(known: {SUPPORTED_IMPLEMENTATIONS}; extension points fail until specified)"
            )
        if self.objects_config_version != OBJECTS_CONFIG_VERSION:
            raise ConfigError(
                f"objects_config_version={self.objects_config_version!r} is not supported "
                f"(this build implements {OBJECTS_CONFIG_VERSION})"
            )
        if self.min_area < 1:
            raise ConfigError(f"min_area must be >= 1, got {self.min_area}")
        if self.max_regions is not None and self.max_regions < 1:
            raise ConfigError(f"max_regions must be null or >= 1, got {self.max_regions}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": OBJECTS_CONFIG_SCHEMA,
            "objects_config_version": self.objects_config_version,
            "connectivity": self.connectivity,
            "min_area": self.min_area,
            "max_regions": self.max_regions,
            "implementation": self.implementation,
        }

    def sha256(self) -> str:
        return hashlib.sha256(canonical_json(self.to_dict()).encode("utf-8")).hexdigest()

    def validate(self, *, schemas_path: Path | None = None) -> None:
        """Validate the *serialized* form against the packaged JSON Schema."""
        base = Path(schemas_path) if schemas_path is not None else schemas_dir()
        validate_against_schema(
            self.to_dict(), base / OBJECTS_CONFIG_SCHEMA_FILE, what="objects config"
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, schemas_path: Path | None = None) -> ObjectsConfig:
        base = Path(schemas_path) if schemas_path is not None else schemas_dir()
        validate_against_schema(data, base / OBJECTS_CONFIG_SCHEMA_FILE, what="objects config")
        unknown = sorted(set(data) - set(cls().to_dict()))
        if unknown:
            raise ConfigError(f"unknown objects-config keys: {unknown}")
        if data.get("schema") != OBJECTS_CONFIG_SCHEMA:
            raise ConfigError(
                f"objects config schema must be {OBJECTS_CONFIG_SCHEMA!r}, got {data.get('schema')!r}"
            )
        return cls(
            connectivity=int(data.get("connectivity", 4)),
            min_area=int(data.get("min_area", 1)),
            max_regions=None if data.get("max_regions") is None else int(data["max_regions"]),
            implementation=str(data.get("implementation", "reference")),
            objects_config_version=str(data.get("objects_config_version", OBJECTS_CONFIG_VERSION)),
        )


def module_info() -> dict:
    return {
        "module": "visual_intensity_engine.objects.objects_config",
        "version": "1.0.0",
        "input_schema": OBJECTS_CONFIG_SCHEMA,
        "output_schema": "ObjectsConfig",
        "config_schema": OBJECTS_CONFIG_SCHEMA,
        "error_behavior": "ConfigError for unsupported connectivity/implementation/version and malformed fields",
        "logging_behavior": "silent",
        "performance_expectations": "constant-time validation, negligible cost",
        "test_coverage": "tests/unit/test_objects_config.py",
    }
