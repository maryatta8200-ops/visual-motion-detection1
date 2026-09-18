"""`vie-objectstore/1` bundle: deterministic object store (VIE-SPEC-REP 1.1.0 §R7).

Layout:

    <outdir>/
    ├── region_labels.npz      int32 label maps, keys f%06d (streamed, fixed ZIP attrs)
    ├── regions.json           vie.region-set/1 — frame-major object list
    ├── manifest.json          vie.objectstore-manifest/1
    ├── checksums.json         sha256 of the three artifacts above
    ├── objects_config.json    config export (human-readable)
    └── metrics.json           per-run measurements (not checksummed; reporting only)

Validation policy (§R8): the JSON Schemas are normative and every reader validates
in full. The writer *additionally* runs a fast structural validator with the same
schema constraints (`fast_region_set_violations`) plus the cross-field invariants
the schema cannot express (`region_set_invariant_violations`), so writing does not
pay a JSON-Schema cost proportional to the object count. Parity between the fast
validator and the schemas is a test obligation in `tests/unit/test_object_store.py`.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import TypeGuard

import numpy as np

from ..config import PipelineConfig, canonical_json, schemas_dir, validate_against_schema
from ..errors import CompatibilityError, RegionExtractionError, SerializationError
from ..intensity.intensity_map import IntensityMap
from ..intensity.vocabulary import IntensityVocabulary
from ..provenance import sha256_file
from ..serialization.store import DeterministicNpzWriter, npz_key
from .extraction import ExtractedFrame
from .objects_config import ObjectsConfig

logger = logging.getLogger("vie.objects.store")

OBJECTSTORE_MANIFEST_SCHEMA = "vie.objectstore-manifest/1"
REGION_SET_SCHEMA = "vie.region-set/1"
NPZ_NAME = "region_labels.npz"
REGIONS_NAME = "regions.json"
MANIFEST_NAME = "manifest.json"
CHECKSUMS_NAME = "checksums.json"
OBJECTS_CONFIG_NAME = "objects_config.json"
METRICS_NAME = "metrics.json"

_REGION_KEYS = frozenset(
    {"schema", "frame_index", "region_id", "level", "symbol", "area", "bbox", "centroid", "fingerprint"}
)
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_SYMBOL = re.compile(r"^I[0-9]{1,3}$")


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------
def _int_in(value: object, *, minimum: int | None = None, maximum: int | None = None) -> bool:
    """`_is_int` plus optional bounds, without exposing `object` to comparisons."""
    if not _is_int(value):
        return False
    number = int(value)
    if minimum is not None and number < minimum:
        return False
    return not (maximum is not None and number > maximum)


def _is_int(value: object) -> TypeGuard[int | float]:
    """JSON-Schema `"type": "integer"` semantics: `2` and `2.0` are both integers.

    Matching the schema (not Python's stricter `isinstance(x, int)`) is what makes
    the fast validator and the normative schemas accept/reject identically — the
    parity test in `tests/unit/test_object_store.py` pins this.
    """
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    return isinstance(value, float) and value.is_integer()


def fast_region_set_violations(doc: object) -> list[str]:
    """Hand-written equivalent of `region_set.schema.json` (+ its `$ref`).

    Returns a list of human-readable violations; empty means "the schema would
    accept this document". Kept in lock-step with the schema by a parity test.
    """
    v: list[str] = []
    if not isinstance(doc, dict):
        return [f"region set must be an object, got {type(doc).__name__}"]
    unknown = sorted(set(doc) - {"schema", "objects_config_sha256", "frames"})
    if unknown:
        v.append(f"unknown top-level keys: {unknown}")
    for key in ("schema", "objects_config_sha256", "frames"):
        if key not in doc:
            v.append(f"missing required key: {key}")
    if doc.get("schema") != REGION_SET_SCHEMA:
        v.append(f"schema must be {REGION_SET_SCHEMA!r}")
    sha = doc.get("objects_config_sha256")
    if not isinstance(sha, str) or not _HEX64.match(sha):
        v.append("objects_config_sha256 must be 64 lowercase hex chars")
    frames = doc.get("frames")
    if not isinstance(frames, list):
        return v + ["frames must be an array"]
    for i, frame in enumerate(frames):
        if not isinstance(frame, dict):
            v.append(f"frames[{i}] must be an object")
            continue
        unknown = sorted(set(frame) - {"frame_index", "regions"})
        if unknown:
            v.append(f"frames[{i}] unknown keys: {unknown}")
        if not _is_int(frame.get("frame_index")) or frame.get("frame_index", -1) < 0:
            v.append(f"frames[{i}].frame_index must be an integer >= 0")
        regions = frame.get("regions")
        if not isinstance(regions, list):
            v.append(f"frames[{i}].regions must be an array")
            continue
        for j, region in enumerate(regions):
            v.extend(_region_violations(region, f"frames[{i}].regions[{j}]"))
    return v


def _region_violations(region: object, where: str) -> list[str]:
    v: list[str] = []
    if not isinstance(region, dict):
        return [f"{where} must be an object"]
    unknown = sorted(set(region) - _REGION_KEYS)
    if unknown:
        v.append(f"{where} unknown keys: {unknown}")
    for key in _REGION_KEYS:
        if key not in region:
            v.append(f"{where} missing required key: {key}")
    if region.get("schema") != "vie.intensity-object/1":
        v.append(f"{where}.schema must be 'vie.intensity-object/1'")
    for key in ("frame_index", "region_id"):
        if not _int_in(region.get(key), minimum=0):
            v.append(f"{where}.{key} must be an integer >= 0")
    if not _int_in(region.get("level"), minimum=0, maximum=255):
        v.append(f"{where}.level must be an integer in [0, 255]")
    symbol = region.get("symbol")
    if not isinstance(symbol, str) or not _SYMBOL.match(symbol):
        v.append(f"{where}.symbol must match ^I[0-9]{{1,3}}$")
    if not _int_in(region.get("area"), minimum=1):
        v.append(f"{where}.area must be an integer >= 1")
    bbox = region.get("bbox")
    if (
        not isinstance(bbox, list)
        or len(bbox) != 4
        or not all(_int_in(b, minimum=0) for b in bbox)
    ):
        v.append(f"{where}.bbox must be 4 integers >= 0")
    centroid = region.get("centroid")
    if (
        not isinstance(centroid, list)
        or len(centroid) != 2
        or not all(isinstance(c, (int, float)) and not isinstance(c, bool) for c in centroid)
    ):
        v.append(f"{where}.centroid must be 2 numbers")
    fp = region.get("fingerprint")
    if not isinstance(fp, str) or not _HEX64.match(fp):
        v.append(f"{where}.fingerprint must be 64 lowercase hex chars")
    return v


def region_set_invariant_violations(doc: dict, *, levels: int | None = None) -> list[str]:
    """Cross-field invariants the JSON Schemas cannot express (§R4, §R6, §R8.2)."""
    v: list[str] = []
    frames = doc.get("frames") if isinstance(doc, dict) else None
    if not isinstance(frames, list):
        return ["frames must be an array"]
    previous = -1
    for i, frame in enumerate(frames):
        if not isinstance(frame, dict):
            continue
        fi = frame.get("frame_index")
        if _is_int(fi):
            fi_value = int(fi)
            if fi_value <= previous:
                v.append(
                    f"frames[{i}].frame_index must be strictly increasing "
                    f"(got {fi_value} after {previous})"
                )
            previous = fi_value
        regions = frame.get("regions")
        if not isinstance(regions, list):
            continue
        for j, region in enumerate(regions):
            if not isinstance(region, dict):
                continue
            if region.get("region_id") != j:
                v.append(f"frames[{i}].regions[{j}].region_id must equal its index {j} (ids are 0..n-1, §R4.2)")
            if region.get("frame_index") != fi:
                v.append(f"frames[{i}].regions[{j}].frame_index must match the frame ({fi})")
            if levels is not None and _is_int(region.get("level")) and not (0 <= region["level"] < levels):
                v.append(f"frames[{i}].regions[{j}].level must lie in [0, {levels})")
            symbol = region.get("symbol")
            if _is_int(region.get("level")) and isinstance(symbol, str) and symbol != f"I{region['level']}":
                v.append(f"frames[{i}].regions[{j}].symbol must be I{region['level']} for level {region['level']}")
            bbox = region.get("bbox")
            if isinstance(bbox, list) and len(bbox) == 4 and all(_is_int(b) for b in bbox):
                x0, y0, x1, y1 = bbox
                if not (x0 < x1 and y0 < y1):
                    v.append(f"frames[{i}].regions[{j}].bbox must be half-open with x0<x1 and y0<y1")
                if (x1 - x0) * (y1 - y0) < region.get("area", 0):
                    v.append(f"frames[{i}].regions[{j}].area cannot exceed its bounding box")
    return v


def validate_region_set(doc: dict, *, levels: int | None = None, full_schema: bool = True) -> None:
    """Validate a region set: fast structural checks always, JSON Schema by default."""
    violations = fast_region_set_violations(doc)
    stage = "schema-equivalent checks"
    if not violations:
        violations = region_set_invariant_violations(doc, levels=levels)
        stage = "invariants"
    if violations:
        raise RegionExtractionError(
            f"region set failed {stage} ({len(violations)} violation(s)): " + "; ".join(violations[:4])
        )
    if full_schema:
        validate_against_schema(doc, schemas_dir() / "region_set.schema.json", what="region set")


# --------------------------------------------------------------------------
# writer
# --------------------------------------------------------------------------
class ObjectStoreWriter:
    """Streams extracted frames into a `vie-objectstore/1` bundle.

    Memory contract: label maps are written to `region_labels.npz` as they arrive,
    so memory is bounded by the per-frame object records (metadata), not by the
    pixel payload. Same consequence as the Phase-1 store: an aborted run leaves an
    incomplete bundle that readers reject — no partial store is presented as valid.
    """

    def __init__(
        self,
        outdir: Path | str,
        *,
        config: PipelineConfig,
        objects_config: ObjectsConfig,
        vocabulary: IntensityVocabulary,
        input_description: dict | None,
        provenance: dict,
        stage: str = "phase2",
    ):
        self.outdir = Path(outdir)
        self.config = config
        self.objects_config = objects_config
        self.vocabulary = vocabulary
        self.input_description = input_description
        self.provenance = provenance
        self.stage = stage
        self._npz = DeterministicNpzWriter(self.outdir / NPZ_NAME)
        self._region_frames: list[dict] = []
        self._rows: list[dict] = []
        self._regions_total = 0
        self._dropped_regions = 0
        self._dropped_pixels = 0
        self._warnings = 0
        self._closed = False

    @property
    def npz_path(self) -> Path:
        return self.outdir / NPZ_NAME

    @property
    def frame_count(self) -> int:
        return len(self._rows)

    @property
    def region_count(self) -> int:
        return self._regions_total

    def add(self, imap: IntensityMap, frame: ExtractedFrame) -> None:
        if self._closed:
            raise SerializationError("writer already closed")
        if imap.frame.frame_index != frame.frame_index:
            raise RegionExtractionError(
                f"frame index mismatch: intensity map {imap.frame.frame_index} vs "
                f"extracted frame {frame.frame_index}"
            )
        if frame.labels.shape != imap.intensity.shape:
            raise RegionExtractionError(
                f"label map shape {frame.labels.shape} does not match intensity map "
                f"{imap.intensity.shape} (frame {frame.frame_index})"
            )
        if (
            int(frame.labels.max(initial=0)) != frame.region_count
            or int(np.count_nonzero(frame.labels)) + frame.dropped_pixels != frame.labels.size
        ):
            raise RegionExtractionError(
                f"frame {frame.frame_index}: label map inconsistent with region records "
                f"(§R6.2/§R6.3 invariants)"
            )
        key = npz_key(frame.frame_index)
        self._npz.add(key, np.ascontiguousarray(frame.labels, dtype=np.int32))
        regions = [obj.to_dict() for obj in frame.objects]
        self._region_frames.append({"frame_index": frame.frame_index, "regions": regions})
        row = {
            "frame_index": imap.frame.frame_index,
            "npz_key": key,
            "source_frame_id": imap.frame.source_frame_id,
            "timestamp_us": imap.frame.timestamp_us,
            "wall_time_utc": imap.frame.wall_time_utc,
            "height": imap.frame.height,
            "width": imap.frame.width,
            "region_count": frame.region_count,
            "dropped_regions": frame.dropped_regions,
            "dropped_pixels": frame.dropped_pixels,
            "label_dtype": "int32",
            "warnings": list(imap.warnings),
        }
        self._rows.append(row)
        self._regions_total += frame.region_count
        self._dropped_regions += frame.dropped_regions
        self._dropped_pixels += frame.dropped_pixels
        self._warnings += len(imap.warnings)

    def _manifest(self) -> dict:
        return {
            "schema": OBJECTSTORE_MANIFEST_SCHEMA,
            "stage": self.stage,
            "config": self.config.to_dict(),
            "config_sha256": self.config.sha256(),
            "objects_config": self.objects_config.to_dict(),
            "objects_config_sha256": self.objects_config.sha256(),
            "vocabulary": self.vocabulary.to_dict(),
            "regions_schema": REGION_SET_SCHEMA,
            "input": self.input_description,
            "provenance": self.provenance,
            "frames": self._rows,
            "counts": {
                "frames": len(self._rows),
                "regions": self._regions_total,
                "dropped_regions": self._dropped_regions,
                "dropped_pixels": self._dropped_pixels,
                "warnings": self._warnings,
            },
            "npz_key_format": "f%06d",
        }

    def close(self, *, duration_s: float | None = None, metrics: dict | None = None) -> dict:
        """Finalize: npz → regions.json → manifest.json → checksums.json [→ metrics.json].

        Each artifact is written exactly once; `duration_s` is folded into the
        provenance block *before* the manifest is validated and checksummed, so
        checksums always cover the final bytes (1.0.0 §9.6, plan §36).
        """
        if self._closed:
            raise SerializationError("writer already closed")
        self._closed = True
        self.outdir.mkdir(parents=True, exist_ok=True)
        self._npz.close()
        if duration_s is not None:
            self.provenance["duration_s"] = round(float(duration_s), 6)

        regions_doc = {
            "schema": REGION_SET_SCHEMA,
            "objects_config_sha256": self.objects_config.sha256(),
            "frames": self._region_frames,
        }
        validate_region_set(regions_doc, levels=self.vocabulary.levels)
        regions_path = self.outdir / REGIONS_NAME
        regions_path.write_text(canonical_json(regions_doc) + "\n", encoding="utf-8")

        config_path = self.outdir / OBJECTS_CONFIG_NAME
        config_path.write_text(
            json.dumps(self.objects_config.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

        manifest = self._manifest()
        validate_against_schema(
            manifest,
            schemas_dir() / "objectstore_manifest.schema.json",
            what="object-store manifest",
        )
        manifest_path = self.outdir / MANIFEST_NAME
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        checksums = {
            "algorithm": "sha256",
            "artifacts": {
                NPZ_NAME: sha256_file(self.npz_path),
                REGIONS_NAME: sha256_file(regions_path),
                MANIFEST_NAME: sha256_file(manifest_path),
            },
        }
        (self.outdir / CHECKSUMS_NAME).write_text(
            json.dumps(checksums, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        if metrics is not None:
            (self.outdir / METRICS_NAME).write_text(
                json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        logger.info(
            "wrote object store: %d frame(s), %d object(s) → %s",
            len(self._rows),
            self._regions_total,
            self.outdir,
        )
        return manifest


# --------------------------------------------------------------------------
# reader
# --------------------------------------------------------------------------
class ObjectStoreReader:
    """Reads and verifies an object store (checksums + schemas + invariants)."""

    def __init__(
        self,
        outdir: Path | str,
        *,
        expected_vocabulary: IntensityVocabulary | None = None,
        expected_objects_config_sha256: str | None = None,
        verify_checksums: bool = True,
    ):
        self.outdir = Path(outdir)
        manifest_path = self.outdir / MANIFEST_NAME
        checksums_path = self.outdir / CHECKSUMS_NAME
        if not manifest_path.is_file():
            raise SerializationError(f"object store incomplete: {manifest_path} missing")
        if verify_checksums:
            if not checksums_path.is_file():
                raise SerializationError(f"object store incomplete: {checksums_path} missing")
            recorded = json.loads(checksums_path.read_text(encoding="utf-8"))
            artifacts = recorded.get("artifacts", {})
            for name in (NPZ_NAME, REGIONS_NAME, MANIFEST_NAME):
                path = self.outdir / name
                if not path.is_file():
                    raise SerializationError(f"object store incomplete: {name} missing")
                actual = sha256_file(path)
                if artifacts.get(name) != actual:
                    raise SerializationError(
                        f"checksum mismatch for {name}: recorded {artifacts.get(name)}, actual {actual}"
                    )
        self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        validate_against_schema(
            self.manifest,
            schemas_dir() / "objectstore_manifest.schema.json",
            what="object-store manifest",
        )
        stored_vocabulary = self.manifest["vocabulary"]["vocabulary_version"]
        if (
            expected_vocabulary is not None
            and stored_vocabulary != expected_vocabulary.vocabulary_version
        ):
            raise CompatibilityError(
                f"store vocabulary {stored_vocabulary} != expected "
                f"{expected_vocabulary.vocabulary_version}"
            )
        if (
            expected_objects_config_sha256 is not None
            and self.manifest["objects_config_sha256"] != expected_objects_config_sha256
        ):
            raise CompatibilityError(
                "store was produced with a different objects config "
                f"({self.manifest['objects_config_sha256']} != {expected_objects_config_sha256})"
            )
        self.region_set = json.loads((self.outdir / REGIONS_NAME).read_text(encoding="utf-8"))
        validate_region_set(
            self.region_set,
            levels=int(self.manifest["vocabulary"]["quantization"]["levels"]),
        )
        self._check_cross_consistency()
        self._npz = np.load(self.outdir / NPZ_NAME)

    def _check_cross_consistency(self) -> None:
        rows = self.manifest["frames"]
        frames = self.region_set["frames"]
        if len(rows) != len(frames):
            raise SerializationError(
                f"manifest lists {len(rows)} frame(s) but regions.json has {len(frames)}"
            )
        for row, frame in zip(rows, frames, strict=True):
            if row["frame_index"] != frame["frame_index"]:
                raise SerializationError(
                    f"frame order mismatch: manifest {row['frame_index']} vs regions {frame['frame_index']}"
                )
            if row["region_count"] != len(frame["regions"]):
                raise SerializationError(
                    f"frame {row['frame_index']}: manifest region_count {row['region_count']} != "
                    f"{len(frame['regions'])} records in regions.json"
                )

    @property
    def frame_count(self) -> int:
        return len(self.manifest["frames"])

    def label_map(self, frame_index: int) -> np.ndarray:
        try:
            return np.asarray(self._npz[npz_key(frame_index)])
        except KeyError as exc:
            raise SerializationError(f"no label map for frame {frame_index}") from exc

    def iter_label_maps(self):
        for row in self.manifest["frames"]:
            yield row["frame_index"], self.label_map(row["frame_index"])

    def regions_of(self, frame_index: int) -> list[dict]:
        for frame in self.region_set["frames"]:
            if frame["frame_index"] == frame_index:
                return frame["regions"]
        raise SerializationError(f"no region records for frame {frame_index}")


def module_info() -> dict:
    return {
        "module": "visual_intensity_engine.objects.store",
        "version": "1.0.0",
        "input_schema": "IntensityMap + ExtractedFrame + vie.objects-config/1",
        "output_schema": "vie-objectstore/1 bundle (region_labels.npz, regions.json, manifest.json, checksums.json)",
        "config_schema": "vie.objects-config/1",
        "error_behavior": (
            "SerializationError for I/O/checksum/completeness, RegionExtractionError for "
            "invalid region sets, CompatibilityError for config/vocabulary mismatch"
        ),
        "logging_behavior": "INFO summary on 'vie.objects.store'",
        "performance_expectations": "streaming writer, O(1) extra memory per frame; store cost measured in EXP-0002",
        "test_coverage": "tests/unit/test_object_store.py, tests/integration/, tests/edge/",
    }
