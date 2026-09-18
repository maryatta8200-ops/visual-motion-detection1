"""Property-based tests (plan §35): general invariants over generated inputs.

Deterministic generation (fixed seeds) keeps failures reproducible; the seed
is varied systematically across ranges so each run covers new ground without
sacrificing replay stability (plan §36).
"""

from __future__ import annotations

import numpy as np
import pytest

from visual_intensity_engine.config import PipelineConfig
from visual_intensity_engine.input.synthetic import SyntheticSource
from visual_intensity_engine.intensity.vocabulary import IntensityVocabulary
from visual_intensity_engine.pipeline import process_frame
from visual_intensity_engine.preprocessing.grayscale import to_grayscale
from visual_intensity_engine.preprocessing.quantization import quantize_uniform
from visual_intensity_engine.serialization.store import write_npz_deterministic

from ..conftest import SUPPORTED_LEVELS


@pytest.mark.parametrize("seed", range(5))
def test_range_invariant_on_random_frames(seed):
    rng = np.random.default_rng(1000 + seed)
    frame = rng.integers(0, 256, (rng.integers(1, 40), rng.integers(1, 60), 3), dtype=np.uint8)
    y, _, _ = to_grayscale(frame, PipelineConfig.default().input_domain)
    assert y.shape == frame.shape[:2]
    assert float(y.min()) >= 0.0 and float(y.max()) <= 1.0
    for levels in SUPPORTED_LEVELS:
        q = quantize_uniform(y, levels)
        assert q.dtype == np.uint8
        assert int(q.max()) <= levels - 1 and int(q.min()) >= 0


def test_shape_preservation():
    rng = np.random.default_rng(7)
    for _ in range(10):
        h, w = rng.integers(1, 50), rng.integers(1, 70)
        frame = rng.integers(0, 256, (h, w, 3), dtype=np.uint8)
        y, _, _ = to_grayscale(frame, PipelineConfig.default().input_domain)
        q = quantize_uniform(y, 16)
        assert q.shape == y.shape == (h, w)


def test_monotonicity_and_sensitivity():
    rng = np.random.default_rng(21)
    y = np.sort(rng.random(2048))
    for levels in (8, 16, 64, 256):
        q = quantize_uniform(y, levels).astype(np.int64)
        assert (np.diff(q) >= 0).all(), "quantization must be monotone"
        # strict monotonicity of classes where bins are actually crossed:
        crossed = np.nonzero(np.diff(q))[0]
        for i in crossed:
            assert y[i] < (q[i] + 1) / levels <= y[i + 1]


def test_npz_round_trip_random_maps(tmp_path):
    rng = np.random.default_rng(31)
    arrays = {f"f{i:06d}": rng.integers(0, 256, (rng.integers(1, 20), rng.integers(1, 20)), dtype=np.uint8)
              for i in range(7)}
    write_npz_deterministic(tmp_path / "a.npz", arrays)
    write_npz_deterministic(tmp_path / "b.npz", arrays)
    assert (tmp_path / "a.npz").read_bytes() == (tmp_path / "b.npz").read_bytes()
    with np.load(tmp_path / "a.npz", allow_pickle=False) as npz:
        for name, arr in arrays.items():
            assert np.array_equal(npz[name], arr)


@pytest.mark.parametrize("seed", range(3))
@pytest.mark.parametrize("levels", (8, 16, 64))
def test_pipeline_process_frame_invariants(seed, levels):
    config = PipelineConfig.default(levels=levels)
    vocab = IntensityVocabulary.build_uniform(levels)
    src = SyntheticSource("moving_square", (48, 36), 6, seed=seed, levels=levels)
    for rec in src.frames():
        pf = process_frame(rec, config, vocab)
        m = pf.imap
        assert m.levels == levels
        assert m.frame.frame_index == rec.frame_index
        assert m.frame.timestamp_us == rec.timestamp_us
        assert m.intensity.shape == rec.data.shape[:2]
        assert int(m.intensity.max()) < levels


def test_writer_determinism_across_order_and_instances(tmp_path):
    rng = np.random.default_rng(41)
    maps = [rng.integers(0, 16, (8, 10), dtype=np.uint8) for _ in range(5)]
    from visual_intensity_engine.serialization.store import npz_key

    a = tmp_path / "a.npz"
    b = tmp_path / "b.npz"
    write_npz_deterministic(a, {npz_key(i): m for i, m in enumerate(maps)})
    write_npz_deterministic(b, {npz_key(i): m for i, m in enumerate(reversed(maps))})
    # different logical order must produce different bytes (keys differ)
    assert a.read_bytes() != b.read_bytes()
    # same logical content must produce identical bytes
    c = tmp_path / "c.npz"
    write_npz_deterministic(c, {npz_key(i): m for i, m in enumerate(maps)})
    assert a.read_bytes() == c.read_bytes()


def test_frame_writer_unaffected_by_extra_whitespace_in_config(tmp_path):
    """Config identity is canonical: whitespace/formatting cannot change hashes."""
    import json

    from visual_intensity_engine.config import config_sha256

    d = PipelineConfig.default().to_dict()
    h1 = config_sha256(d)
    text_a = json.dumps(d, indent=4)
    text_b = json.dumps(d, separators=(",", ":"))
    h2 = config_sha256(json.loads(text_a))
    h3 = config_sha256(json.loads(text_b))
    assert h1 == h2 == h3


# ---------------------------------------------------------------------------
# Phase 2 properties (VIE-SPEC-REP 1.1.0 §R2–§R6)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_region_invariants_hold_for_random_maps(seed):
    from visual_intensity_engine.objects.labeling import label_level_uniform_regions
    from visual_intensity_engine.objects.objects_config import ObjectsConfig

    rng = np.random.default_rng(seed)
    height, width = int(rng.integers(1, 30)), int(rng.integers(1, 30))
    levels = int(rng.integers(2, 9))
    min_area = int(rng.integers(1, 6))
    qmap = rng.integers(0, levels, size=(height, width)).astype(np.int32)
    result = label_level_uniform_regions(qmap, levels, ObjectsConfig(min_area=min_area))

    # §R6.3: the frame is fully covered
    assert sum(r.area for r in result.regions) + result.dropped_pixels == height * width
    # §R4.2: ids are contiguous 1..n in the label map
    labels = set(np.unique(result.labels).tolist())
    assert labels <= set(range(len(result.regions) + 1))
    assert labels == set(range(len(result.regions) + 1)) or 0 in labels
    # §R2: every region has exactly one level, and its pixels all carry that level
    for index, region in enumerate(result.regions):
        ys, xs = np.nonzero(result.labels == index + 1)
        assert ys.size == region.area
        assert np.all(qmap[ys, xs] == region.level)
        assert (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1) == (
            region.x0, region.y0, region.x1, region.y1,
        )
    # min_area is honoured exactly
    assert all(r.area >= min_area for r in result.regions)


@pytest.mark.parametrize("seed", [4, 5])
def test_production_and_reference_labelers_agree(seed):
    from visual_intensity_engine.objects.labeling import (
        label_level_uniform_regions,
        label_level_uniform_regions_reference,
    )
    from visual_intensity_engine.objects.objects_config import ObjectsConfig

    rng = np.random.default_rng(seed)
    qmap = rng.integers(0, 5, size=(int(rng.integers(1, 14)), int(rng.integers(1, 14)))).astype(np.int32)
    config = ObjectsConfig(min_area=2)
    fast = label_level_uniform_regions(qmap, 8, config)
    ref = label_level_uniform_regions_reference(qmap, 8, config)
    assert np.array_equal(fast.labels, ref.labels)
    assert fast.regions == ref.regions
