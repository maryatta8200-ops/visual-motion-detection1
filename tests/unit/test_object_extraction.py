"""Unit tests for object records (`vie.intensity-object/1`, VIE-SPEC-REP §R3)."""

from __future__ import annotations

import hashlib

import numpy as np
import pytest

from visual_intensity_engine.config import PipelineConfig, canonical_json, schemas_dir
from visual_intensity_engine.errors import RegionExtractionError
from visual_intensity_engine.intensity.intensity_map import FrameInfo, IntensityMap
from visual_intensity_engine.intensity.vocabulary import IntensityVocabulary
from visual_intensity_engine.objects.extraction import extract_objects, object_fingerprint
from visual_intensity_engine.objects.objects_config import ObjectsConfig

LEVELS = 16


def _imap(qmap: np.ndarray, frame_index: int = 3) -> IntensityMap:
    vocabulary = IntensityVocabulary.build_uniform(LEVELS)
    return IntensityMap(
        intensity=np.ascontiguousarray(qmap, dtype=np.uint8),
        levels=LEVELS,
        vocabulary_version=vocabulary.vocabulary_version,
        config_sha256=PipelineConfig.default(levels=LEVELS).sha256(),
        frame=FrameInfo(
            frame_index=frame_index,
            source_frame_id="synthetic-000003",
            timestamp_us=100_000,
            wall_time_utc="2026-09-18T00:00:00.000Z",
            height=int(qmap.shape[0]),
            width=int(qmap.shape[1]),
        ),
    )


def test_records_validate_against_the_packaged_schema():
    from jsonschema import Draft202012Validator

    from visual_intensity_engine.config import schema_registry

    qmap = np.array([[0, 0, 1], [2, 2, 1]], dtype=np.uint8)
    frame = extract_objects(_imap(qmap), IntensityVocabulary.build_uniform(LEVELS), ObjectsConfig())
    schema = schemas_dir() / "intensity_object.schema.json"
    validator = Draft202012Validator(
        __import__("json").loads(schema.read_text()), registry=schema_registry(schemas_dir())
    )
    for obj in frame.objects:
        validator.validate(obj.to_dict())


def test_record_fields_and_symbol_mapping():
    qmap = np.array([[0, 0, 5], [5, 5, 5]], dtype=np.uint8)
    frame = extract_objects(_imap(qmap), IntensityVocabulary.build_uniform(LEVELS), ObjectsConfig())
    first, second = frame.objects
    assert first.to_dict() == {
        "schema": "vie.intensity-object/1",
        "frame_index": 3,
        "region_id": 0,
        "level": 0,
        "symbol": "I0",
        "area": 2,
        "bbox": [0, 0, 2, 1],
        "centroid": [0.5, 0.0],
        "fingerprint": first.fingerprint,
    }
    assert second.region_id == 1 and second.symbol == "I5" and second.area == 4
    assert len(first.fingerprint) == 64


def test_fingerprint_is_sha256_of_canonical_json_of_the_four_fields():
    payload = {"area": 4, "bbox": [1, 2, 3, 4], "centroid": [1.5, 2.5], "level": 7}
    expected = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    assert object_fingerprint(level=7, area=4, bbox=(1, 2, 3, 4), centroid=(1.5, 2.5)) == expected


@pytest.mark.parametrize(
    "kwargs",
    [
        {"level": 8, "area": 4, "bbox": (1, 2, 3, 4), "centroid": (1.5, 2.5)},
        {"level": 7, "area": 5, "bbox": (1, 2, 3, 4), "centroid": (1.5, 2.5)},
        {"level": 7, "area": 4, "bbox": (0, 2, 3, 4), "centroid": (1.5, 2.5)},
        {"level": 7, "area": 4, "bbox": (1, 2, 3, 4), "centroid": (1.5, 2.0)},
    ],
)
def test_fingerprint_changes_when_any_field_changes(kwargs):
    base = object_fingerprint(level=7, area=4, bbox=(1, 2, 3, 4), centroid=(1.5, 2.5))
    assert object_fingerprint(**kwargs) != base


def test_extraction_reports_drops_and_keeps_ids_contiguous():
    qmap = np.array([[0, 1, 0], [0, 1, 1]], dtype=np.uint8)
    frame = extract_objects(
        _imap(qmap), IntensityVocabulary.build_uniform(LEVELS), ObjectsConfig(min_area=2)
    )
    assert [obj.region_id for obj in frame.objects] == [0, 1]
    # level-0 blob is L-shaped and 4-connected (area 2), the lone (0,2) pixel is dropped
    assert frame.dropped_regions == 1 and frame.dropped_pixels == 1
    assert frame.labels[0, 0] == 1 and frame.labels[0, 2] == 0
    assert sum(o.area for o in frame.objects) + frame.dropped_pixels == qmap.size


def test_extraction_fails_when_a_level_has_no_token_in_the_vocabulary():
    """Defensive guard: symbolisation must fail loudly if a vocabulary has gaps.

    `IntensityVocabulary` rejects gaps at construction, so this guard protects
    future vocabularies; a stub vocabulary exercises it without pretending the
    packaged vocabulary can be malformed.
    """
    from types import SimpleNamespace

    stub = SimpleNamespace(
        levels=16,
        vocabulary_version="stub-partial",
        tokens=(SimpleNamespace(token_id=0, symbol="I0"),),
    )
    with pytest.raises(RegionExtractionError, match="no token"):
        extract_objects(_imap(np.array([[0, 7]], dtype=np.uint8)), stub, ObjectsConfig())


def test_extraction_fails_when_intensity_exceeds_vocabulary_levels():
    qmap = np.array([[0, 15]], dtype=np.uint8)
    with pytest.raises(RegionExtractionError, match="must lie in"):
        extract_objects(_imap(qmap), IntensityVocabulary.build_uniform(4), ObjectsConfig())


def test_region_count_matches_record_count_and_label_maximum():
    rng = np.random.default_rng(12)
    qmap = rng.integers(0, LEVELS, size=(21, 13)).astype(np.uint8)
    frame = extract_objects(_imap(qmap), IntensityVocabulary.build_uniform(LEVELS), ObjectsConfig())
    assert frame.region_count == len(frame.objects)
    assert int(frame.labels.max()) == frame.region_count
    assert max(o.region_id for o in frame.objects) == frame.region_count - 1
