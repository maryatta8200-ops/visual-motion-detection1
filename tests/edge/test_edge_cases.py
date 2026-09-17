"""Edge-case tests: boundaries of the input domain and level counts (plan §35)."""

from __future__ import annotations

import numpy as np
import pytest

from visual_intensity_engine.config import InputDomainSettings, PipelineConfig
from visual_intensity_engine.input.synthetic import SyntheticSource
from visual_intensity_engine.intensity.vocabulary import IntensityVocabulary
from visual_intensity_engine.pipeline import process_frame
from visual_intensity_engine.preprocessing.grayscale import to_grayscale
from visual_intensity_engine.preprocessing.quantization import quantize

from ..conftest import SUPPORTED_LEVELS


def test_minimum_frame_size_1x1():
    frame = np.full((1, 1, 3), 200, np.uint8)
    y, _, _ = to_grayscale(frame, InputDomainSettings())
    assert y.shape == (1, 1)
    q = quantize(y, PipelineConfig.default().quantization)
    assert q[0, 0] == 12  # 200/255*16 = 12.54 → 12


def test_empty_frame_rejected():
    with pytest.raises(Exception):
        to_grayscale(np.zeros((0, 0, 3), np.uint8), InputDomainSettings())


def test_uniform_frame_maps_to_single_level():
    for value in (0, 1, 64, 127, 128, 255):
        frame = np.full((5, 5, 3), value, np.uint8)
        y, _, _ = to_grayscale(frame, InputDomainSettings())
        q = quantize(y, PipelineConfig.default().quantization)
        assert np.all(q == q.flat[0])
        assert 0 <= int(q.flat[0]) <= 15


@pytest.mark.parametrize("levels", [2, 3, 7, SUPPORTED_LEVELS[0], SUPPORTED_LEVELS[-1]])
def test_extreme_level_counts(levels):
    y = np.linspace(0, 1, 65)[:-1].reshape(1, 64)
    q = quantize(y, PipelineConfig.default(levels).quantization)
    assert q.max() <= levels - 1
    if levels in (2, 256):
        assert len(np.unique(q)) == min(levels, 64)


def test_saturated_pixels_reach_top_level():
    frame = np.full((3, 3, 3), 255, np.uint8)
    y, _, _ = to_grayscale(frame, InputDomainSettings())
    assert quantize(y, PipelineConfig.default(256).quantization)[0, 0] == 255


def test_zero_pixels_reach_level_zero():
    frame = np.zeros((3, 3, 3), np.uint8)
    y, _, _ = to_grayscale(frame, InputDomainSettings())
    assert quantize(y, PipelineConfig.default(256).quantization)[0, 0] == 0


def test_pure_channels_l16_mapping():
    for rgb, expected in (((255, 0, 0), 4), ((0, 255, 0), 9), ((0, 0, 255), 1)):
        frame = np.array([[rgb]], np.uint8)
        y, _, _ = to_grayscale(frame, InputDomainSettings())
        q = int(quantize(y, PipelineConfig.default(16).quantization)[0, 0])
        assert q == expected, f"{rgb} → I{q}, expected I{expected}"


def test_variable_frame_sizes_in_one_store(tmp_path):
    """Writer supports heterogeneous shapes; reader restores exact arrays."""
    from visual_intensity_engine.serialization.store import (
        FrameStoreWriter,
        write_npz_deterministic,
    )
    import json as _json
    from dataclasses import replace

    config = PipelineConfig.default()
    vocab = IntensityVocabulary.build_uniform(16)
    writer = FrameStoreWriter(
        tmp_path, config=config, vocabulary=vocab,
        input_description={"kind": "synthetic", "name": "mixed", "sha256": None,
                           "declared_fps": 30.0, "width": 16, "height": 16},
        provenance={"git_commit": None, "git_dirty": None, "python_version": "t",
                    "numpy_version": "t", "pillow_version": None, "jsonschema_version": None,
                    "platform": "t", "created_at_utc": "1970-01-01T00:00:00.000Z",
                    "duration_s": None, "seed": 0},
    )
    rng = np.random.default_rng(2)
    sizes = [(4, 6), (9, 3), (16, 16)]
    from visual_intensity_engine.intensity.intensity_map import FrameInfo, IntensityMap as IM

    for i, (h, w) in enumerate(sizes):
        arr = rng.integers(0, 16, (h, w), dtype=np.uint8)
        writer.add(IM(
            intensity=arr, levels=16, vocabulary_version=vocab.vocabulary_version,
            config_sha256=config.sha256(),
            frame=FrameInfo(i, None, i * 33333, None, h, w),
        ))
    manifest = writer.close()
    assert [f["width"] for f in manifest["frames"]] == [6, 3, 16]
    with np.load(tmp_path / "intensity_maps.npz", allow_pickle=False) as npz:
        assert npz["f000000"].shape == (4, 6)
        assert npz["f000001"].shape == (9, 3)


def test_source_frame_id_and_warnings_round_trip():
    from visual_intensity_engine.input.framesource import FrameRecord

    config = PipelineConfig.default()
    vocab = IntensityVocabulary.build_uniform(16)
    rec = FrameRecord(
        data=np.full((4, 4, 3), 90, np.uint8), frame_index=3, source_frame_id="custom-3",
        timestamp_us=99_999, wall_time_utc="2026-09-17T00:00:00.000Z",
        warnings=("duplicate timestamp 99999 at frames 2,3",),
    )
    pf = process_frame(rec, config, vocab)
    assert pf.imap.frame.source_frame_id == "custom-3"
    assert pf.imap.warnings == ("duplicate timestamp 99999 at frames 2,3",)
    row = pf.imap.manifest_row("f000003")
    assert row["warnings"] and row["timestamp_us"] == 99_999


def test_non_monotonic_timestamps_detected():
    from visual_intensity_engine.input.framesource import check_timestamp_sequence

    warnings = check_timestamp_sequence([0, 33_000, 33_000, 20_000, 200_000], 33_333)
    joined = " | ".join(warnings)
    assert "duplicate timestamp" in joined
    assert "non-monotonic" in joined
    assert "frame drop suspected" in joined
    assert check_timestamp_sequence([0, 33_333, 66_666], 33_333) == []
