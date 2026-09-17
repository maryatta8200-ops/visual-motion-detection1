"""Versioned configuration (plan §3.8, VIE-SPEC-REP §10).

Configuration is always a JSON file validated against
`schemas/pipeline_config.schema.json` (draft 2020-12). Identity of a config is
the SHA-256 of its canonical JSON (sorted keys, UTF-8, no extra whitespace).
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

import jsonschema

from .errors import ConfigError

SCHEMA_NAME = "pipeline_config.schema.json"
CONFIG_SCHEMA_ID = "vie.pipeline-config/1"


def schemas_dir() -> Path:
    """Locate the repo `schemas/` directory.

    Works from a source checkout and from `pip install -e .` (package dir sits
    directly inside the repo root). Override with env VIE_SCHEMA_DIR if the
    package is copied elsewhere.
    """
    import os

    env = os.environ.get("VIE_SCHEMA_DIR")
    if env:
        p = Path(env)
        if p.is_dir():
            return p
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "schemas"
        if (candidate / SCHEMA_NAME).is_file():
            return candidate
    raise ConfigError(
        f"cannot locate schemas/{SCHEMA_NAME}; set VIE_SCHEMA_DIR to the repo 'schemas' directory"
    )


def _load_json(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"config file {path} is not valid JSON: {exc}") from exc


_schema_registry_cache: dict[str, object] = {}


def _schema_registry(schema_dir: Path):
    """Build a `referencing` Registry mapping each schema's $id to the local
    document, so relative $refs between schemas resolve offline (no network).
    """
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT202012

    key = str(schema_dir.resolve())
    if key in _schema_registry_cache:
        return _schema_registry_cache[key]
    registry = Registry()
    for path in sorted(schema_dir.glob("*.schema.json")):
        doc = _load_json(path)
        resource = Resource.from_contents(doc, default_specification=DRAFT202012)
        registry = registry.with_resource(doc["$id"], resource)
    _schema_registry_cache[key] = registry
    return registry


def validate_against_schema(instance: dict, schema_path: Path, *, what: str) -> None:
    try:
        schema = _load_json(schema_path)
    except ConfigError as exc:
        raise ConfigError(f"schema for {what} unavailable: {exc}") from exc
    validator = jsonschema.Draft202012Validator(
        schema, registry=_schema_registry(schema_path.parent)
    )
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
    if errors:
        first = errors[0]
        loc = "/".join(str(p) for p in first.path) or "<root>"
        raise ConfigError(
            f"{what} failed schema validation at '{loc}': {first.message}"
            + (f" (+{len(errors) - 1} more errors)" if len(errors) > 1 else "")
        )


def canonical_json(obj: dict) -> str:
    """Canonical form: sorted keys, compact separators, UTF-8 (VIE-SPEC-REP §10.2)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def config_sha256(config_dict: dict) -> str:
    return sha256_text(canonical_json(config_dict))


@dataclass(frozen=True)
class QuantizationSettings:
    strategy: str = "uniform"
    levels: int = 16
    scope: str = "global_fixed"
    boundary_rule: str = "floor_right_open"
    implementation: str = "reference"


@dataclass(frozen=True)
class InputDomainSettings:
    channel_order: str = "RGB"
    luma_standard: str = "bt601"
    normalization: str = "dtype_max"
    alpha_policy: str = "drop"
    non_finite_policy: str = "strict"
    float_range_policy: str = "strict"


@dataclass(frozen=True)
class SerializationSettings:
    format: str = "vie-framestore/1"
    deterministic: bool = True


@dataclass(frozen=True)
class PipelineConfig:
    quantization: QuantizationSettings
    input_domain: InputDomainSettings
    serialization: SerializationSettings
    seed: int = 0
    max_frames: int | None = None
    strict: bool = True
    config_version: str = "1.0.0"

    # ---- serialization -------------------------------------------------
    def to_dict(self) -> dict:
        d = {
            "schema": CONFIG_SCHEMA_ID,
            "config_version": self.config_version,
            "seed": self.seed,
            "quantization": asdict(self.quantization),
            "input_domain": asdict(self.input_domain),
            "serialization": asdict(self.serialization),
        }
        if self.max_frames is not None:
            d["max_frames"] = self.max_frames
        if not self.strict:
            d["strict"] = False
        return d

    def canonical(self) -> str:
        return canonical_json(self.to_dict())

    def sha256(self) -> str:
        return sha256_text(self.canonical())

    def save(self, path: Path) -> None:
        """Configuration export (pretty, stable order) — plan §20 'configuration export'."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # ---- construction --------------------------------------------------
    @classmethod
    def from_dict(cls, d: dict) -> "PipelineConfig":
        schema_path = schemas_dir() / SCHEMA_NAME
        validate_against_schema(d, schema_path, what="pipeline config")
        max_frames = d.get("max_frames")
        return cls(
            quantization=QuantizationSettings(**d["quantization"]),
            input_domain=InputDomainSettings(**d["input_domain"]),
            serialization=SerializationSettings(**d["serialization"]),
            seed=int(d["seed"]),
            max_frames=int(max_frames) if max_frames is not None else None,
            strict=bool(d.get("strict", True)),
            config_version=d["config_version"],
        )

    @classmethod
    def load(cls, path: Path) -> "PipelineConfig":
        return cls.from_dict(_load_json(Path(path)))

    @classmethod
    def default(cls, levels: int = 16) -> "PipelineConfig":
        return cls(
            quantization=QuantizationSettings(levels=levels),
            input_domain=InputDomainSettings(),
            serialization=SerializationSettings(),
        )


def module_info() -> dict:
    return {
        "module": "visual_intensity_engine.config",
        "version": "1.0.0",
        "input_schema": "vie.pipeline-config/1 (schemas/pipeline_config.schema.json)",
        "output_schema": "PipelineConfig dataclass + canonical JSON + sha256",
        "config_schema": "self",
        "error_behavior": "ConfigError on missing/invalid config or schema",
        "logging_behavior": "silent (pure functions)",
        "performance_expectations": "O(config size); validation ~1 ms",
        "test_coverage": "tests/unit/test_config.py",
    }
