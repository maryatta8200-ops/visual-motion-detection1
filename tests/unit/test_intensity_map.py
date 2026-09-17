"""Unit tests: IntensityMap record validation (VIE-SPEC-REP §4/§8)."""

from __future__ import annotations

import numpy as np
import pytest

from visual_intensity_engine.errors import FrameValidationError
from visual_intensity_engine.intensity.intensity_map import FrameInfo, IntensityMap


def make_imap(arr, **overrides):
    h, w = arr.shape[0], arr.shape[1]
    defaults = dict(
        intensity=arr,
        levels=16,
        vocabulary_version="uniform-l16-v1",
        config_sha256="0" * 64,
        frame=FrameInfo(
            frame_index=0, source_frame_id=None, timestamp_us=0,
            wall_time_utc=None, height=h, width=w,
        ),
    )
    defaults.update(overrides)
    return IntensityMap(**defaults)


def test_valid_map_passes():
    arr = np.zeros((4, 6), np.uint8)
    m = make_imap(arr)
    assert m.histogram.tolist() == [24] + [0] * 15
    row = m.manifest_row("f000000")
    assert row["npz_key"] == "f000000" and row["height"] == 4 and row["width"] == 6


def test_wrong_dtype_rejected():
    with pytest.raises(FrameValidationError, match="uint8"):
        make_imap(np.zeros((2, 2), np.int64))


def test_wrong_ndim_rejected():
    with pytest.raises(FrameValidationError, match="2-D"):
        make_imap(np.zeros((2, 2, 1), np.uint8))


def test_level_out_of_range_rejected():
    arr = np.array([[15, 16]], np.uint8)
    with pytest.raises(FrameValidationError, match=">= levels"):
        make_imap(arr, levels=16)


def test_geometry_mismatch_rejected():
    arr = np.zeros((4, 6), np.uint8)
    bad_frame = FrameInfo(0, None, 0, None, 5, 5)
    with pytest.raises(FrameValidationError, match="geometry"):
        make_imap(arr, frame=bad_frame)


def test_negative_timestamp_rejected():
    arr = np.zeros((2, 2), np.uint8)
    bad_frame = FrameInfo(0, None, -5, None, 2, 2)
    with pytest.raises(FrameValidationError, match="timestamp"):
        make_imap(arr, frame=bad_frame)


def test_histogram_counts_all_levels():
    rng = np.random.default_rng(2)
    arr = rng.integers(0, 16, (100, 100), dtype=np.uint8)
    h = make_imap(arr).histogram
    assert h.sum() == 10_000 and len(h) == 16
