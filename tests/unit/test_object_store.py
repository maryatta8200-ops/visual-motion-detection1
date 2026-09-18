"""Unit tests for the `vie-objectstore/1` bundle (VIE-SPEC-REP 1.1.0 §R7/§R8).

The mandated parity test lives here: the fast structural validator and the
normative JSON Schema must accept/reject generated corpora *identically*.
"""

from __future__ import annotations

import json

import numpy as np
import pytest
from jsonschema import Draft202012Validator

from visual_intensity_engine.config import PipelineConfig, schema_registry, schemas_dir
from visual_intensity_engine.errors import (
    CompatibilityError,
    RegionExtractionError,
    SerializationError,
)
from visual_intensity_engine.intensity.intensity_map import FrameInfo, IntensityMap
from visual_intensity_engine.intensity.vocabulary import IntensityVocabulary
from visual_intensity_engine.objects.extraction import extract_objects
from visual_intensity_engine.objects.objects_config import ObjectsConfig
from visual_intensity_engine.objects.store import (
    ObjectStoreReader,
    ObjectStoreWriter,
    fast_region_set_violations,
    region_set_invariant_violations,
    validate_region_set,
)
from visual_intensity_engine.provenance import capture_provenance

LEVELS = 8
MIN_AREA = 2


def _imap(qmap: np.ndarray, frame_index: int = 0) -> IntensityMap:
    vocabulary = IntensityVocabulary.build_uniform(LEVELS)
    return IntensityMap(
        intensity=np.ascontiguousarray(qmap, dtype=np.uint8),
        levels=LEVELS,
        vocabulary_version=vocabulary.vocabulary_version,
        config_sha256=PipelineConfig.default(levels=LEVELS).sha256(),
        frame=FrameInfo(
            frame_index=frame_index,
            source_frame_id=f"synthetic-{frame_index:06d}",
            timestamp_us=frame_index * 33_333,
            wall_time_utc="2026-09-18T00:00:00.000Z",
            height=int(qmap.shape[0]),
            width=int(qmap.shape[1]),
        ),
    )


def _write_store(outdir, qmaps, objects_config=None, metrics=None):
    objects_config = objects_config or ObjectsConfig(min_area=MIN_AREA)
    vocabulary = IntensityVocabulary.build_uniform(LEVELS)
    config = PipelineConfig.default(levels=LEVELS)
    writer = ObjectStoreWriter(
        outdir,
        config=config,
        objects_config=objects_config,
        vocabulary=vocabulary,
        input_description={
            "kind": "synthetic",
            "name": "unit",
            "sha256": None,
            "declared_fps": None,
            "width": int(qmaps[0].shape[1]),
            "height": int(qmaps[0].shape[0]),
        },
        provenance=capture_provenance(seed=0),
    )
    for i, q in enumerate(qmaps):
        imap = _imap(q, i)
        writer.add(imap, extract_objects(imap, vocabulary, objects_config))
    return writer.close(duration_s=0.01, metrics=metrics)


def _sample_maps():
    return [
        np.array([[0, 0, 1], [0, 2, 1], [3, 3, 3]], dtype=np.int32),
        np.full((4, 4), 1, dtype=np.int32),
    ]


# ------------------------------------------------------------------ write ----
def test_writer_emits_the_spec_bundle_and_reads_back(tmp_path):
    manifest = _write_store(tmp_path / "store", _sample_maps(), metrics={"frames": 2})
    for name in ("region_labels.npz", "regions.json", "manifest.json", "checksums.json",
                 "objects_config.json", "metrics.json"):
        assert (tmp_path / "store" / name).is_file(), name
    assert manifest["schema"] == "vie.objectstore-manifest/1"
    assert manifest["counts"] == {
        "frames": 2,
        "regions": 3 + 1,  # map 1: level-0 (3px), level-1 (2px), level-3 (3px); map 2: 4x4 block
        "dropped_regions": 1,  # the single level-2 pixel of map 1, below min_area=2
        "dropped_pixels": 1,
        "warnings": 0,
    }
    assert [row["region_count"] for row in manifest["frames"]] == [3, 1]
    reader = ObjectStoreReader(tmp_path / "store")
    assert reader.frame_count == 2
    assert np.array_equal(reader.label_map(1), np.full((4, 4), 1, dtype=np.int32))
    assert [r["region_id"] for r in reader.regions_of(0)] == [0, 1, 2]
    assert reader.manifest["objects_config_sha256"] == ObjectsConfig(min_area=MIN_AREA).sha256()


def test_reader_verifies_checksums_and_rejects_tampering(tmp_path):
    _write_store(tmp_path / "store", _sample_maps())
    regions = tmp_path / "store" / "regions.json"
    payload = json.loads(regions.read_text())
    payload["frames"][0]["regions"][0]["area"] = 999  # invisible to checksums? no: bytes change
    regions.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    with pytest.raises(SerializationError, match="checksum mismatch"):
        ObjectStoreReader(tmp_path / "store")


def test_incomplete_store_is_rejected(tmp_path):
    _write_store(tmp_path / "store", _sample_maps())
    (tmp_path / "store" / "manifest.json").unlink()
    with pytest.raises(SerializationError, match="incomplete"):
        ObjectStoreReader(tmp_path / "store")


def test_writer_refuses_out_of_order_frames_and_add_after_close(tmp_path):
    vocabulary = IntensityVocabulary.build_uniform(LEVELS)
    config = PipelineConfig.default(levels=LEVELS)
    objects_config = ObjectsConfig()
    writer = ObjectStoreWriter(
        tmp_path / "store",
        config=config,
        objects_config=objects_config,
        vocabulary=vocabulary,
        input_description=None,
        provenance=capture_provenance(seed=0),
    )
    imap = _imap(np.zeros((3, 3), dtype=np.int32), frame_index=1)
    writer.add(imap, extract_objects(imap, vocabulary, objects_config))
    with pytest.raises(SerializationError, match="increasing"):
        earlier = _imap(np.zeros((3, 3), dtype=np.int32), frame_index=0)
        writer.add(earlier, extract_objects(earlier, vocabulary, objects_config))
    writer.close()
    with pytest.raises(SerializationError, match="already closed"):
        writer.add(imap, extract_objects(imap, vocabulary, objects_config))


def test_reader_detects_config_mismatch(tmp_path):
    manifest = _write_store(tmp_path / "store", _sample_maps())
    with pytest.raises(CompatibilityError, match="objects config"):
        ObjectStoreReader(tmp_path / "store", expected_objects_config_sha256="0" * 64)
    ObjectStoreReader(tmp_path / "store", expected_objects_config_sha256=manifest["objects_config_sha256"])
    with pytest.raises(CompatibilityError, match="vocabulary"):
        ObjectStoreReader(tmp_path / "store", expected_vocabulary=IntensityVocabulary.build_uniform(16))


def test_label_map_shape_mismatch_is_rejected(tmp_path):
    vocabulary = IntensityVocabulary.build_uniform(LEVELS)
    objects_config = ObjectsConfig()
    writer = ObjectStoreWriter(
        tmp_path / "store",
        config=PipelineConfig.default(levels=LEVELS),
        objects_config=objects_config,
        vocabulary=vocabulary,
        input_description=None,
        provenance=capture_provenance(seed=0),
    )
    imap = _imap(np.zeros((3, 3), dtype=np.int32))
    frame = extract_objects(imap, vocabulary, objects_config)
    other = _imap(np.zeros((4, 4), dtype=np.int32))
    with pytest.raises(RegionExtractionError, match="shape"):
        writer.add(other, frame)
    mismatched = _imap(np.zeros((3, 3), dtype=np.int32), frame_index=2)
    with pytest.raises(RegionExtractionError, match="frame index"):
        writer.add(mismatched, frame)


# ------------------------------------------- fast validator ↔ schema parity --
def _schema_validator() -> Draft202012Validator:
    """Region-set schema with relative $refs resolved offline (same registry as the engine)."""
    directory = schemas_dir()
    path = directory / "region_set.schema.json"
    return Draft202012Validator(
        json.loads(path.read_text(encoding="utf-8")), registry=schema_registry(directory)
    )


def _valid_region_set() -> dict:
    qmap = np.array([[0, 1, 1], [0, 2, 1]], dtype=np.int32)
    vocabulary = IntensityVocabulary.build_uniform(4)
    imap = _imap(qmap)
    frame = extract_objects(imap, vocabulary, ObjectsConfig())
    return {
        "schema": "vie.region-set/1",
        "objects_config_sha256": ObjectsConfig().sha256(),
        "frames": [{"frame_index": 0, "regions": [o.to_dict() for o in frame.objects]}],
    }


def test_valid_region_set_passes_schema_fast_check_and_invariants():
    doc = _valid_region_set()
    assert fast_region_set_violations(doc) == []
    assert region_set_invariant_violations(doc, levels=4) == []
    validate_region_set(doc, levels=4)  # JSON Schema path enabled


def _mutations(doc: dict) -> list[tuple[str, dict]]:
    import copy

    out: list[tuple[str, dict]] = []

    def mutate(name, fn):
        clone = copy.deepcopy(doc)
        fn(clone)
        out.append((name, clone))

    mutate("drop-top-key", lambda d: d.pop("frames"))
    mutate("extra-top-key", lambda d: d.update({"extra": 1}))
    mutate("bad-schema-id", lambda d: d.update({"schema": "vie.region-set/2"}))
    mutate("bad-sha", lambda d: d.update({"objects_config_sha256": "zz"}))
    mutate("frames-not-array", lambda d: d.update({"frames": {}}))
    mutate("frame-extra-key", lambda d: d["frames"][0].update({"extra": 1}))
    mutate("frame-index-negative", lambda d: d["frames"][0].update({"frame_index": -1}))
    mutate("frames-empty", lambda d: d.update({"frames": []}))
    mutate("region-extra-key", lambda d: d["frames"][0]["regions"][0].update({"extra": 1}))
    mutate("region-missing-key", lambda d: d["frames"][0]["regions"][0].pop("fingerprint"))
    mutate("area-zero", lambda d: d["frames"][0]["regions"][0].update({"area": 0}))
    mutate("area-float", lambda d: d["frames"][0]["regions"][0].update({"area": 2.0}))
    mutate("level-256", lambda d: d["frames"][0]["regions"][0].update({"level": 256}))
    mutate("level-negative", lambda d: d["frames"][0]["regions"][0].update({"level": -1}))
    mutate("symbol-uppercase", lambda d: d["frames"][0]["regions"][0].update({"symbol": "i0"}))
    mutate("symbol-too-long", lambda d: d["frames"][0]["regions"][0].update({"symbol": "I1000"}))
    mutate("bbox-3-items", lambda d: d["frames"][0]["regions"][0].update({"bbox": [0, 0, 1]}))
    mutate("bbox-negative", lambda d: d["frames"][0]["regions"][0].update({"bbox": [-1, 0, 1, 1]}))
    mutate("bbox-float", lambda d: d["frames"][0]["regions"][0].update({"bbox": [0, 0, 1.5, 1]}))
    mutate("centroid-1-item", lambda d: d["frames"][0]["regions"][0].update({"centroid": [0.0]}))
    mutate("centroid-string", lambda d: d["frames"][0]["regions"][0].update({"centroid": ["a", "b"]}))
    mutate("fingerprint-short", lambda d: d["frames"][0]["regions"][0].update({"fingerprint": "abc"}))
    mutate("fingerprint-uppercase", lambda d: d["frames"][0]["regions"][0].update({"fingerprint": "A" * 64}))
    mutate("region-dict", lambda d: d["frames"][0]["regions"].append({"schema": 1}))
    mutate("regions-not-array", lambda d: d["frames"][0].update({"regions": "x"}))
    return out


def test_fast_validator_matches_json_schema_on_mutations():
    doc = _valid_region_set()
    validator = _schema_validator()
    mismatches = []
    for name, mutant in _mutations(doc):
        schema_ok = validator.is_valid(mutant)
        fast_ok = not fast_region_set_violations(mutant)
        if schema_ok != fast_ok:
            mismatches.append((name, schema_ok, fast_ok, fast_region_set_violations(mutant)))
    assert not mismatches, f"fast validator/schema disagreements: {mismatches}"


def test_fast_validator_matches_json_schema_on_generated_corpora(tmp_path):
    validator = _schema_validator()
    rng = np.random.default_rng(5)
    vocabulary = IntensityVocabulary.build_uniform(4)
    disagreements = 0
    for trial in range(25):
        q = rng.integers(0, 4, size=(int(rng.integers(1, 9)), int(rng.integers(1, 9)))).astype(np.int32)
        frame = extract_objects(_imap(q, trial), vocabulary, ObjectsConfig())
        doc = {
            "schema": "vie.region-set/1",
            "objects_config_sha256": ObjectsConfig().sha256(),
            "frames": [{"frame_index": trial, "regions": [o.to_dict() for o in frame.objects]}],
        }
        assert validator.is_valid(doc), f"generated corpus rejected by schema at trial {trial}"
        assert fast_region_set_violations(doc) == []
        assert region_set_invariant_violations(doc, levels=4) == []
    assert disagreements == 0


def test_invariants_catch_what_the_schema_cannot():
    doc = _valid_region_set()
    doc["frames"][0]["regions"][1]["region_id"] = 7  # schema allows any id >= 0
    assert fast_region_set_violations(doc) == []
    assert any("region_id" in v for v in region_set_invariant_violations(doc))
    with pytest.raises(RegionExtractionError, match="invariants"):
        validate_region_set(doc, levels=4)


def test_invariants_reject_symbol_level_mismatch_and_empty_bbox():
    doc = _valid_region_set()
    doc["frames"][0]["regions"][0]["symbol"] = "I5"
    assert any("symbol" in v for v in region_set_invariant_violations(doc))
    doc = _valid_region_set()
    doc["frames"][0]["regions"][0]["bbox"] = [1, 1, 1, 1]
    assert any("bbox" in v for v in region_set_invariant_violations(doc))


def test_store_is_replay_identical_ignoring_provenance_timestamps(tmp_path):
    for run in ("a", "b"):
        _write_store(tmp_path / run, _sample_maps())
    for artifact in ("region_labels.npz", "regions.json"):
        assert (tmp_path / "a" / artifact).read_bytes() == (tmp_path / "b" / artifact).read_bytes()
    ma = json.loads((tmp_path / "a" / "manifest.json").read_text())
    mb = json.loads((tmp_path / "b" / "manifest.json").read_text())
    for m in (ma, mb):
        m["provenance"].pop("created_at_utc", None)
        m["provenance"].pop("duration_s", None)
    assert ma == mb
