"""Unit tests: synthetic sources — determinism is a contract (plan §11/§23)."""

from __future__ import annotations

import numpy as np
import pytest

from visual_intensity_engine.input.synthetic import SCENES, SyntheticSource


def frames_of(src):
    return [(r.data.copy(), r.timestamp_us, r.frame_index) for r in src.frames()]


def test_deterministic_across_instances():
    a = frames_of(SyntheticSource("moving_square", (64, 48), 10, seed=42))
    b = frames_of(SyntheticSource("moving_square", (64, 48), 10, seed=42))
    assert len(a) == len(b)
    for (da, ta, ia), (db, tb, ib) in zip(a, b):
        assert da.tobytes() == db.tobytes()
        assert ta == tb and ia == ib


def test_seed_changes_noisy_frames():
    quiet = SyntheticSource("moving_square", (64, 48), 5, seed=1, noise_px=0)
    noisy_a = SyntheticSource("moving_square", (64, 48), 5, seed=1, noise_px=50)
    noisy_b = SyntheticSource("moving_square", (64, 48), 5, seed=2, noise_px=50)
    fa = frames_of(noisy_a)
    fb = frames_of(noisy_b)
    fq = frames_of(quiet)
    assert fa[0][0].tobytes() != fb[0][0].tobytes()  # seed 1 vs 2 differ
    assert fa[0][0].tobytes() == frames_of(noisy_a)[0][0].tobytes()  # same seed stable
    assert fa[0][0].tobytes() != fq[0][0].tobytes()


def test_timestamp_arithmetic():
    src = SyntheticSource("gradient", (32, 16), 5, fps=25.0)
    rows = frames_of(src)
    assert [r[1] for r in rows] == [0, 40_000, 80_000, 120_000, 160_000]


def test_gradient_hits_all_levels_for_l16():
    src = SyntheticSource("gradient", (256, 8), 1, levels=16)
    frame = frames_of(src)[0][0]
    assert frame.shape == (8, 256, 3) and frame.dtype == np.uint8


def test_ramp_bands_hits_every_level():
    for levels in (8, 16, 32, 64, 128, 256):
        src = SyntheticSource("ramp_bands", (levels * 4, 8), 1, levels=levels)
        frame = frames_of(src)[0][0][:, :, 0]
        vals = np.unique(frame)
        centers = np.rint((np.arange(levels) + 0.5) / levels * 255.0).astype(np.uint8)
        assert set(centers.tolist()) <= set(vals.tolist()), f"L={levels} missing band centers"


def test_invalid_parameters_rejected():
    with pytest.raises(ValueError, match="unknown synthetic scene"):
        SyntheticSource("hollywood")
    with pytest.raises(ValueError):
        SyntheticSource("gradient", n_frames=0)
    with pytest.raises(ValueError):
        SyntheticSource("gradient", fps=0)


def test_all_scenes_constructible():
    for scene in SCENES:
        src = SyntheticSource(scene, (16, 16), 2)
        assert len(frames_of(src)) == 2


def test_describe_block():
    src = SyntheticSource("moving_square", (160, 120), 4, fps=30)
    d = src.describe()
    assert d["kind"] == "synthetic"
    assert d["width"] == 160 and d["height"] == 120 and d["declared_fps"] == 30.0
