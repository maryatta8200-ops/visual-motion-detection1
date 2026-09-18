"""Unit tests for level-uniform 4-connected labeling (VIE-SPEC-REP 1.1.0 §R2–§R6).

The production path (vectorized run-length + union-find) is checked against:
  * the per-pixel flood-fill oracle on generated corpora (same labels, byte-equal
    metadata, same drop accounting) — the oracle is a different algorithm, so
    agreement is real evidence rather than a self-comparison;
  * hand-built cases where 4-connectivity differs from 8-connectivity;
  * the §R9 normative worked example (separate test module).
"""

from __future__ import annotations

import numpy as np
import pytest

from visual_intensity_engine.errors import RegionExtractionError
from visual_intensity_engine.objects.labeling import (
    label_level_uniform_regions,
    label_level_uniform_regions_reference,
)
from visual_intensity_engine.objects.objects_config import ObjectsConfig


def both(qmap: np.ndarray, levels: int, config: ObjectsConfig):
    fast = label_level_uniform_regions(qmap, levels, config)
    ref = label_level_uniform_regions_reference(qmap, levels, config)
    return fast, ref


# ---------------------------------------------------------------- basics ----
def test_uniform_frame_is_exactly_one_region():
    q = np.full((7, 5), 3, dtype=np.int32)
    result = label_level_uniform_regions(q, 8, ObjectsConfig())
    assert len(result.regions) == 1
    assert np.all(result.labels == 1)
    region = result.regions[0]
    assert (region.level, region.area, region.x0, region.y0, region.x1, region.y1) == (3, 35, 0, 0, 5, 7)
    assert (region.centroid_x, region.centroid_y) == (2.0, 3.0)


def test_single_pixel_and_single_row_frames():
    one = label_level_uniform_regions(np.array([[5]], dtype=np.int32), 8, ObjectsConfig())
    r = one.regions[0]
    assert r.area == 1 and (r.x0, r.y0, r.x1, r.y1) == (0, 0, 1, 1)

    row = label_level_uniform_regions(np.array([[1, 1, 2]], dtype=np.int32), 8, ObjectsConfig())
    assert [r.area for r in row.regions] == [2, 1]
    assert [r.level for r in row.regions] == [1, 2]


def test_diagonal_pixels_are_separate_objects_under_4_connectivity():
    q = np.array([[1, 2], [2, 1]], dtype=np.int32)
    result = label_level_uniform_regions(q, 4, ObjectsConfig())
    assert len(result.regions) == 4  # 8-connectivity would merge the two 2s
    assert np.array_equal(result.labels, np.array([[1, 2], [3, 4]], dtype=np.int32))


def test_discovery_order_is_raster_order_not_area_order():
    # the 1-pixel object at (0,0) is discovered first, so it is id 0 even though
    # the big regions below it are far larger
    q = np.zeros((4, 4), dtype=np.int32)
    q[0, 0] = 1
    q[2:, :] = 2
    result = label_level_uniform_regions(q, 4, ObjectsConfig())
    assert [r.area for r in result.regions] == [1, 7, 8]
    assert [r.level for r in result.regions] == [1, 0, 2]
    assert result.labels[0, 0] == 1


def test_ids_are_contiguous_after_dropping():
    # an early tiny object is dropped; later ids renumber contiguously
    q = np.zeros((3, 3), dtype=np.int32)
    q[0, 0] = 1  # isolated single pixel, dropped for min_area=2
    q[1:, 1:] = 2
    result = label_level_uniform_regions(q, 4, ObjectsConfig(min_area=2))
    assert (result.dropped_regions, result.dropped_pixels) == (1, 1)
    # level 0 background splits under 4-connectivity: {(0,1),(0,2)} and {(1,0),(2,0)}
    assert len(result.regions) == 3
    assert result.labels[0, 0] == 0  # dropped pixel gets label 0
    assert set(np.unique(result.labels).tolist()) == {0, 1, 2, 3}
    assert [r.area for r in result.regions] == [2, 2, 4]


# ------------------------------------------------------------ max_regions ----
def test_max_regions_exceeded_raises_and_never_truncates():
    q = np.array([[0, 1, 0, 1]], dtype=np.int32)
    with pytest.raises(RegionExtractionError, match="max_regions"):
        label_level_uniform_regions(q, 4, ObjectsConfig(max_regions=3))
    ok = label_level_uniform_regions(q, 4, ObjectsConfig(max_regions=4))
    assert len(ok.regions) == 4


def test_max_regions_counts_only_kept_objects():
    # two 2-pixel objects are kept, three single-pixel objects are dropped
    q = np.array([[0, 0, 2, 0, 2, 0, 0]], dtype=np.int32)
    result = label_level_uniform_regions(q, 4, ObjectsConfig(min_area=2, max_regions=2))
    assert len(result.regions) == 2
    assert (result.dropped_regions, result.dropped_pixels) == (3, 3)
    with pytest.raises(RegionExtractionError, match="max_regions"):
        label_level_uniform_regions(q, 4, ObjectsConfig(min_area=2, max_regions=1))


# -------------------------------------------------------------- validation ---
@pytest.mark.parametrize(
    "qmap,levels,message",
    [
        (np.zeros((2, 2), dtype=np.float64), 4, "integer dtype"),
        (np.zeros((2, 2, 1), dtype=np.int32), 4, "2-D"),
        (np.zeros((0, 0), dtype=np.int32), 4, "must not be empty"),
        (np.full((2, 2), 4, dtype=np.int32), 4, "must lie in"),
        (np.full((2, 2), -1, dtype=np.int32), 4, "must lie in"),
        (np.zeros((2, 2), dtype=np.int32), 1, "levels must be"),
    ],
)
def test_malformed_maps_fail_explicitly(qmap, levels, message):
    for impl in (label_level_uniform_regions, label_level_uniform_regions_reference):
        with pytest.raises(RegionExtractionError, match=message):
            impl(qmap, levels, ObjectsConfig())


def test_connectivity_8_is_rejected_by_config_not_silently_treated_as_4():
    from visual_intensity_engine.errors import ConfigError

    with pytest.raises(ConfigError, match="connectivity=8"):
        ObjectsConfig(connectivity=8)


# ------------------------------------------------------------ determinism ----
def test_repeated_runs_are_identical():
    rng = np.random.default_rng(3)
    q = rng.integers(0, 5, size=(23, 31)).astype(np.int32)
    first = label_level_uniform_regions(q, 8, ObjectsConfig(min_area=2))
    second = label_level_uniform_regions(q, 8, ObjectsConfig(min_area=2))
    assert np.array_equal(first.labels, second.labels)
    assert first.regions == second.regions
    assert (first.dropped_regions, first.dropped_pixels) == (second.dropped_regions, second.dropped_pixels)


def test_transposed_input_is_not_an_accident_of_memory_order():
    # C-contiguous and Fortran-ordered copies of the same logical map must agree
    rng = np.random.default_rng(4)
    q = rng.integers(0, 6, size=(17, 11)).astype(np.int32)
    fortran = np.asfortranarray(q)
    a = label_level_uniform_regions(q, 8, ObjectsConfig())
    b = label_level_uniform_regions(fortran, 8, ObjectsConfig())
    assert np.array_equal(a.labels, b.labels)
    assert a.regions == b.regions


# ---------------------------------------------------- oracle parity corpus ---
@pytest.mark.parametrize("trial", range(12))
def test_production_path_matches_flood_fill_oracle(trial):
    rng = np.random.default_rng(100 + trial)
    height = int(rng.integers(1, 18))
    width = int(rng.integers(1, 18))
    levels = int(rng.integers(2, 7))
    min_area = int(rng.integers(1, 5))
    q = rng.integers(0, levels, size=(height, width)).astype(np.int32)
    if trial % 3 == 0:  # also exercise large uniform areas
        q[: height // 2, :] = 0
    config = ObjectsConfig(min_area=min_area)
    fast, ref = both(q, levels, config)
    assert np.array_equal(fast.labels, ref.labels)
    assert fast.regions == ref.regions
    assert (fast.dropped_regions, fast.dropped_pixels) == (ref.dropped_regions, ref.dropped_pixels)
    assert fast.shapes_consistent


@pytest.mark.parametrize("trial", range(4))
def test_oracle_parity_on_larger_structured_maps(trial):
    rng = np.random.default_rng(900 + trial)
    q = np.zeros((40, 60), dtype=np.int32)
    for _ in range(6):
        y = int(rng.integers(0, 30))
        x = int(rng.integers(0, 50))
        h = int(rng.integers(1, 10))
        w = int(rng.integers(1, 10))
        q[y : y + h, x : x + w] = int(rng.integers(0, 4))
    fast, ref = both(q, 8, ObjectsConfig(min_area=3))
    assert np.array_equal(fast.labels, ref.labels)
    assert fast.regions == ref.regions


def test_bboxes_are_half_open_and_contain_their_pixels():
    rng = np.random.default_rng(7)
    q = rng.integers(0, 4, size=(25, 25)).astype(np.int32)
    result = label_level_uniform_regions(q, 4, ObjectsConfig())
    assert int(np.count_nonzero(result.labels == 0)) == 0  # no drops for min_area=1
    for index, region in enumerate(result.regions):
        ys, xs = np.nonzero(result.labels == index + 1)
        assert region.area == ys.size
        assert (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1) == (
            region.x0,
            region.y0,
            region.x1,
            region.y1,
        )
        assert region.x0 <= region.centroid_x <= region.x1 - 1
        assert region.y0 <= region.centroid_y <= region.y1 - 1
