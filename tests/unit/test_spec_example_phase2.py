"""Executable form of the VIE-SPEC-REP 1.1.0 §R9 normative worked example.

The spec text and these assertions are the same numbers: if the implementation
drifts, this test fails and the spec cannot silently become false (plan §3.21,
§39: normative examples must be executable).
"""

from __future__ import annotations

import hashlib

import numpy as np
import pytest

from visual_intensity_engine.config import canonical_json
from visual_intensity_engine.intensity.vocabulary import IntensityVocabulary
from visual_intensity_engine.objects.extraction import object_fingerprint
from visual_intensity_engine.objects.labeling import label_level_uniform_regions
from visual_intensity_engine.objects.objects_config import ObjectsConfig

R9_MAP = np.array(
    [
        [0, 0, 1, 1, 1],
        [0, 2, 2, 1, 1],
        [3, 2, 2, 1, 1],
        [3, 3, 3, 3, 3],
    ],
    dtype=np.int32,
)
R9_LABELS = np.array(
    [
        [1, 1, 2, 2, 2],
        [1, 3, 3, 2, 2],
        [4, 3, 3, 2, 2],
        [4, 4, 4, 4, 4],
    ],
    dtype=np.int32,
)
R9_OBJECTS = [  # (level, area, bbox, (cx, cy))
    (0, 3, (0, 0, 2, 2), (0.3333333333333333, 0.3333333333333333)),
    (1, 7, (2, 0, 5, 3), (3.2857142857142856, 0.8571428571428571)),
    (2, 4, (1, 1, 3, 3), (1.5, 1.5)),
    (3, 6, (0, 2, 5, 4), (1.6666666666666667, 2.8333333333333335)),
]


def test_r9_min_area_one_exact_numbers():
    result = label_level_uniform_regions(R9_MAP, 4, ObjectsConfig(min_area=1))
    assert np.array_equal(result.labels, R9_LABELS)
    assert (result.dropped_regions, result.dropped_pixels) == (0, 0)
    assert len(result.regions) == 4
    for region, (level, area, bbox, centroid) in zip(result.regions, R9_OBJECTS, strict=True):
        assert region.level == level
        assert region.area == area
        assert (region.x0, region.y0, region.x1, region.y1) == bbox
        assert (region.centroid_x, region.centroid_y) == centroid  # byte-exact float64 values


def test_r9_min_area_four_renumbers_and_counts_drops():
    result = label_level_uniform_regions(R9_MAP, 4, ObjectsConfig(min_area=4))
    expected = np.array(
        [
            [0, 0, 1, 1, 1],
            [0, 2, 2, 1, 1],
            [3, 2, 2, 1, 1],
            [3, 3, 3, 3, 3],
        ],
        dtype=np.int32,
    )
    assert np.array_equal(result.labels, expected)
    assert (result.dropped_regions, result.dropped_pixels) == (1, 3)
    assert [r.level for r in result.regions] == [1, 2, 3]
    assert [r.area for r in result.regions] == [7, 4, 6]
    # ids are contiguous over *kept* objects: the level-1 object is now region 0
    r0 = result.regions[0]
    assert (r0.x0, r0.y0, r0.x1, r0.y1) == (2, 0, 5, 3)


def test_r9_invariant_areas_plus_dropped_pixels_equals_frame():
    for min_area in (1, 2, 3, 4, 7, 8):
        result = label_level_uniform_regions(R9_MAP, 4, ObjectsConfig(min_area=min_area))
        kept = sum(r.area for r in result.regions)
        assert kept + result.dropped_pixels == R9_MAP.size
        assert result.shapes_consistent


def test_r9_fingerprints_are_content_signatures_of_the_listed_fields():
    vocabulary = IntensityVocabulary.build_uniform(4)
    symbols = [tok.symbol for tok in vocabulary.tokens]
    result = label_level_uniform_regions(R9_MAP, 4, ObjectsConfig(min_area=1))
    expected_payloads = [
        {
            "area": area,
            "bbox": list(bbox),
            "centroid": [centroid[0], centroid[1]],
            "level": level,
        }
        for level, area, bbox, centroid in R9_OBJECTS
    ]
    for region, payload in zip(result.regions, expected_payloads, strict=True):
        expected = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
        actual = object_fingerprint(
            level=region.level,
            area=region.area,
            bbox=(region.x0, region.y0, region.x1, region.y1),
            centroid=(region.centroid_x, region.centroid_y),
        )
        assert actual == expected
        assert symbols[region.level] == f"I{region.level}"
    # fingerprints must be 64-hex content signatures that differ per object
    fingerprints = [
        object_fingerprint(
            level=level, area=area, bbox=bbox, centroid=centroid
        )
        for level, area, bbox, centroid in R9_OBJECTS
    ]
    assert all(len(fp) == 64 and set(fp) <= set("0123456789abcdef") for fp in fingerprints)
    assert len(set(fingerprints)) == 4


@pytest.mark.parametrize("min_area", [1, 2, 3, 4])
def test_r9_oracle_agrees_with_production_path(min_area):
    from visual_intensity_engine.objects.labeling import label_level_uniform_regions_reference

    fast = label_level_uniform_regions(R9_MAP, 4, ObjectsConfig(min_area=min_area))
    ref = label_level_uniform_regions_reference(R9_MAP, 4, ObjectsConfig(min_area=min_area))
    assert np.array_equal(fast.labels, ref.labels)
    assert fast.regions == ref.regions
    assert (fast.dropped_regions, fast.dropped_pixels) == (ref.dropped_regions, ref.dropped_pixels)
