"""Phase-2 acceptance fixtures with exact ground truth (VIE-SPEC-REP 1.1.1 §R2–§R6).

Named static fixtures in the spirit of the external Phase-2 design audit's SYN-001..SYN-010
list: every fixture has an exact expected component count, level, area, half-open bbox,
centroid and id assignment (ids = raster discovery order). Nothing here uses motion — the
audit's point was to remove motion from the Phase-2 acceptance question.

Also covered here, per the audit's checklist: corner-touching vs edge-touching regions,
regions touching the frame border, hole/nested structure, the zero-kept case, and the
per-frame area invariant. Three-run byte-identical serialization is asserted in
`tests/integration/test_objects_pipeline.py`.
"""

from __future__ import annotations

import numpy as np
import pytest

from visual_intensity_engine.config import PipelineConfig
from visual_intensity_engine.intensity.intensity_map import FrameInfo, IntensityMap
from visual_intensity_engine.intensity.vocabulary import IntensityVocabulary
from visual_intensity_engine.objects.extraction import extract_objects
from visual_intensity_engine.objects.labeling import label_level_uniform_regions
from visual_intensity_engine.objects.objects_config import ObjectsConfig

LEVELS = 4


def label(qmap, *, levels: int = LEVELS, **config):
    return label_level_uniform_regions(
        np.asarray(qmap, dtype=np.int32), levels, ObjectsConfig(**config)
    )


def summary(result):
    """(level, area, half-open bbox) per region, in id order."""
    return [(r.level, r.area, (r.x0, r.y0, r.x1, r.y1)) for r in result.regions]


# --------------------------------------------------------------- SYN-001..SYN-010 ----
def test_syn_001_single_solid_square():
    q = np.zeros((8, 8), dtype=np.int32)
    q[2:5, 2:5] = 1
    r = label(q)
    assert summary(r) == [(0, 55, (0, 0, 8, 8)), (1, 9, (2, 2, 5, 5))]
    assert (r.regions[1].centroid_x, r.regions[1].centroid_y) == (3.0, 3.0)
    assert (r.dropped_regions, r.dropped_pixels) == (0, 0)


def test_syn_002_two_separated_squares():
    q = np.zeros((8, 8), dtype=np.int32)
    q[1:3, 1:3] = 1
    q[3:5, 5:7] = 1
    r = label(q)
    # discovery order is raster order: background, then the square at (1,1), then (5,3)
    assert summary(r) == [(0, 56, (0, 0, 8, 8)), (1, 4, (1, 1, 3, 3)), (1, 4, (5, 3, 7, 5))]


def test_syn_003_diagonal_touching_squares_stay_separate_under_4_connectivity():
    q = np.zeros((6, 6), dtype=np.int32)
    q[1:3, 1:3] = 1
    q[3:5, 3:5] = 1
    r = label(q)  # corner contact only: 8-connectivity would merge these
    assert summary(r) == [(0, 28, (0, 0, 6, 6)), (1, 4, (1, 1, 3, 3)), (1, 4, (3, 3, 5, 5))]


def test_syn_004_nested_ring_with_hole():
    q = np.array(
        [
            [1, 1, 1, 1, 1],
            [1, 0, 0, 0, 1],
            [1, 0, 2, 0, 1],
            [1, 0, 0, 0, 1],
            [1, 1, 1, 1, 1],
        ],
        dtype=np.int32,
    )
    r = label(q)
    assert summary(r) == [(1, 16, (0, 0, 5, 5)), (0, 8, (1, 1, 4, 4)), (2, 1, (2, 2, 3, 3))]
    # the hole is preserved exactly by the label map: ring label 1 surrounds labels 2 and 3
    assert r.labels[0, 0] == 1 and r.labels[1, 1] == 2 and r.labels[2, 2] == 3
    # area and bbox describe members only: 16 = 25 - 9 enclosed cells
    assert r.regions[0].area == 16


def test_syn_005_three_intensity_levels():
    q = np.array(
        [[0, 0, 1, 1, 2, 2], [0, 0, 1, 1, 2, 2]],
        dtype=np.int32,
    )
    r = label(q)
    assert summary(r) == [(0, 4, (0, 0, 2, 2)), (1, 4, (2, 0, 4, 2)), (2, 4, (4, 0, 6, 2))]
    assert [(reg.centroid_x, reg.centroid_y) for reg in r.regions] == [
        (0.5, 0.5),
        (2.5, 0.5),
        (4.5, 0.5),
    ]


def test_syn_006_single_pixel_region():
    q = np.zeros((3, 3), dtype=np.int32)
    q[2, 1] = 1
    r = label(q)
    assert summary(r) == [(0, 8, (0, 0, 3, 3)), (1, 1, (1, 2, 2, 3))]
    assert (r.regions[1].centroid_x, r.regions[1].centroid_y) == (1.0, 2.0)


def test_syn_007_no_qualifying_regions_is_a_valid_empty_frame():
    q = np.tile(np.arange(4, dtype=np.int32), (4, 1))  # four 4-pixel columns
    r = label(q, min_area=5)
    assert r.regions == ()
    assert (r.dropped_regions, r.dropped_pixels) == (4, 16)
    assert int(np.count_nonzero(r.labels)) == 0  # zero means "no regions", not an error


def test_syn_008_full_frame_region():
    q = np.full((4, 6), 3, dtype=np.int32)
    r = label(q)
    assert summary(r) == [(3, 24, (0, 0, 6, 4))]
    assert (r.regions[0].centroid_x, r.regions[0].centroid_y) == (2.5, 1.5)


def test_syn_009_checkerboard_is_all_isolated_pixels():
    q = (np.add.outer(np.arange(16), np.arange(16)) % 2).astype(np.int32)
    r = label(q)
    assert len(r.regions) == 256
    assert all(reg.area == 1 for reg in r.regions)
    assert sum(reg.area for reg in r.regions) + r.dropped_pixels == 16 * 16


def test_syn_010_many_tiny_components():
    q = np.zeros((6, 12), dtype=np.int32)
    for x in (0, 4, 8):
        q[1:3, x : x + 2] = 1
    r = label(q)
    assert summary(r) == [
        (0, 60, (0, 0, 12, 6)),
        (1, 4, (0, 1, 2, 3)),
        (1, 4, (4, 1, 6, 3)),
        (1, 4, (8, 1, 10, 3)),
    ]


# ------------------------------------------- contact, border and invariant cases ----
def test_edge_touching_regions_merge_while_corner_touching_ones_do_not():
    q = np.zeros((4, 8), dtype=np.int32)
    q[1:3, 1:3] = 1
    q[1:3, 3:5] = 1  # shares a full edge with the previous block -> one region
    q[1:3, 6:8] = 1  # separated by a one-pixel lane -> its own region
    r = label(q)
    assert summary(r) == [(0, 20, (0, 0, 8, 4)), (1, 8, (1, 1, 5, 3)), (1, 4, (6, 1, 8, 3))]


def test_region_touching_the_frame_border_is_ordinary():
    q = np.zeros((5, 5), dtype=np.int32)
    q[3:, 3:] = 1  # covers the bottom-right corner
    r = label(q)
    assert summary(r) == [(0, 21, (0, 0, 5, 5)), (1, 4, (3, 3, 5, 5))]
    assert r.regions[1].x1 == 5 and r.regions[1].y1 == 5


@pytest.mark.parametrize(
    ("qmap", "levels", "config"),
    [
        (np.zeros((8, 8), dtype=np.int32), LEVELS, {}),
        (np.tile(np.arange(4, dtype=np.int32), (4, 1)), LEVELS, {"min_area": 5}),
        ((np.add.outer(np.arange(16), np.arange(16)) % 2).astype(np.int32), 2, {}),
        (np.full((4, 6), 3, dtype=np.int32), LEVELS, {"min_area": 2}),
    ],
)
def test_every_fixture_upholds_the_area_invariant(qmap, levels, config):
    r = label(qmap, levels=levels, **config)
    assert sum(reg.area for reg in r.regions) + r.dropped_pixels == qmap.size


# ------------------------------------------------------- record-level ground truth ----
def _imap(qmap: np.ndarray) -> IntensityMap:
    vocabulary = IntensityVocabulary.build_uniform(LEVELS)
    return IntensityMap(
        intensity=np.ascontiguousarray(qmap, dtype=np.uint8),
        levels=LEVELS,
        vocabulary_version=vocabulary.vocabulary_version,
        config_sha256=PipelineConfig.default(levels=LEVELS).sha256(),
        frame=FrameInfo(
            frame_index=0,
            source_frame_id="synthetic-000000",
            timestamp_us=0,
            wall_time_utc="2026-09-18T00:00:00.000Z",
            height=int(qmap.shape[0]),
            width=int(qmap.shape[1]),
        ),
    )


def test_fixture_records_carry_levels_symbols_ids_and_fingerprints():
    q = np.array([[0, 0, 1, 1, 2, 2], [0, 0, 1, 1, 2, 2]], dtype=np.uint8)
    frame = extract_objects(_imap(q), IntensityVocabulary.build_uniform(LEVELS), ObjectsConfig())
    assert [o.region_id for o in frame.objects] == [0, 1, 2]
    assert [o.symbol for o in frame.objects] == ["I0", "I1", "I2"]
    assert [o.level for o in frame.objects] == [0, 1, 2]
    assert [o.area for o in frame.objects] == [4, 4, 4]
    assert all(len(o.fingerprint) == 64 for o in frame.objects)
    assert frame.region_count == 3 and frame.dropped_pixels == 0
