"""Unit tests: grayscale reference implementation (VIE-SPEC-REP §3)."""

from __future__ import annotations

import numpy as np
import pytest

from visual_intensity_engine.config import InputDomainSettings
from visual_intensity_engine.errors import FrameValidationError, NonFinitePixelError
from visual_intensity_engine.preprocessing.grayscale import (
    LUMA_COEFFICIENTS,
    reference_vectors,
    to_grayscale,
    to_uint8_gray,
)


def test_reference_vectors_bt601():
    settings = InputDomainSettings()  # bt601 default
    for rgb, expected in reference_vectors().items():
        frame = np.array([[rgb]], dtype=np.uint8)
        y, nf, clipped = to_grayscale(frame, settings)
        assert y.shape == (1, 1)
        assert y.dtype == np.float64
        assert y[0, 0] == pytest.approx(expected, abs=1e-12)
        assert nf == 0 and clipped == 0


def test_bt709_and_average_standards():
    white = np.full((1, 1, 3), 255, np.uint8)
    for std, coeffs in LUMA_COEFFICIENTS.items():
        y, _, _ = to_grayscale(white, InputDomainSettings(luma_standard=std))
        assert y[0, 0] == pytest.approx(sum(coeffs), abs=1e-12)
    red = np.array([[[255, 0, 0]]], dtype=np.uint8)
    y, _, _ = to_grayscale(red, InputDomainSettings(luma_standard="bt709"))
    assert y[0, 0] == pytest.approx(0.2126, abs=1e-12)


def test_channel_order_is_rgb_not_bgr():
    red_first = np.array([[[255, 0, 0]]], dtype=np.uint8)
    blue_first = np.array([[[0, 0, 255]]], dtype=np.uint8)
    y_red, _, _ = to_grayscale(red_first, InputDomainSettings())
    y_blue, _, _ = to_grayscale(blue_first, InputDomainSettings())
    assert y_red[0, 0] > y_blue[0, 0]  # 0.299 vs 0.114 — proves R is index 0
    assert y_red[0, 0] == pytest.approx(0.299)
    assert y_blue[0, 0] == pytest.approx(0.114)


def test_uint16_input():
    frame = np.array([[65535, 0, 0]], dtype=np.uint16).reshape(1, 1, 3)
    y, _, _ = to_grayscale(frame, InputDomainSettings())
    assert y[0, 0] == pytest.approx(0.299, abs=1e-12)


def test_float_input_in_range_ok_out_of_range_strict_raises():
    ok = np.full((2, 2, 3), 0.5, dtype=np.float32)
    y, _, clipped = to_grayscale(ok, InputDomainSettings())
    assert float(y.mean()) == pytest.approx(0.5)
    assert clipped == 0

    bad = ok.copy()
    bad[1, 1, 0] = 1.5
    with pytest.raises(FrameValidationError, match="outside \\[0,1\\]"):
        to_grayscale(bad, InputDomainSettings())

    y, _, clipped = to_grayscale(bad, InputDomainSettings(float_range_policy="clip"))
    assert clipped >= 1
    assert y.min() >= 0.0 and y.max() <= 1.0


def test_nan_strict_raises_with_location():
    frame = np.full((4, 5, 3), 0.5, dtype=np.float64)
    frame[2, 3, 1] = np.nan
    with pytest.raises(NonFinitePixelError, match=r"\(2, 3\)") as excinfo:
        to_grayscale(frame, InputDomainSettings())
    assert "1 non-finite" in str(excinfo.value)


def test_nan_inf_coerce_counts():
    frame = np.full((2, 2, 3), 0.5, dtype=np.float64)
    frame[0, 0, 0] = np.nan
    frame[1, 1, 2] = np.inf
    frame[1, 0, 1] = -np.inf
    y, nf, _ = to_grayscale(frame, InputDomainSettings(non_finite_policy="coerce"))
    assert nf == 3  # three coerced samples
    assert np.isfinite(y).all()
    assert y.min() >= 0.0 and y.max() <= 1.0


def test_alpha_policies():
    rgba = np.zeros((1, 1, 4), dtype=np.uint8)
    rgba[0, 0] = (255, 128, 0, 128)
    y_drop, _, _ = to_grayscale(rgba, InputDomainSettings(alpha_policy="drop"))
    rgb_ref = np.array([[[255, 128, 0]]], dtype=np.uint8)
    y_ref, _, _ = to_grayscale(rgb_ref, InputDomainSettings())
    assert y_drop[0, 0] == pytest.approx(y_ref[0, 0])
    y_comp, _, _ = to_grayscale(rgba, InputDomainSettings(alpha_policy="composite_black"))
    assert y_comp[0, 0] < y_drop[0, 0]  # composited over black dims the pixel
    with pytest.raises(FrameValidationError, match="alpha"):
        to_grayscale(rgba, InputDomainSettings(alpha_policy="error"))


def test_two_dimensional_gray_passthrough():
    gray = np.array([[0, 128], [255, 64]], dtype=np.uint8)
    y, _, _ = to_grayscale(gray, InputDomainSettings())
    assert y[0, 0] == 0.0
    assert y[1, 0] == pytest.approx(1.0)
    assert y[0, 1] == pytest.approx(128 / 255, abs=1e-12)


def test_determinism_same_bytes():
    rng = np.random.default_rng(3)
    frame = rng.integers(0, 256, (16, 16, 3), dtype=np.uint8)
    y1, _, _ = to_grayscale(frame, InputDomainSettings())
    y2, _, _ = to_grayscale(frame, InputDomainSettings())
    assert y1.tobytes() == y2.tobytes()


def test_structural_rejections():
    with pytest.raises(FrameValidationError):
        to_grayscale(np.zeros((2, 2, 5), np.uint8), InputDomainSettings())  # 5 channels
    with pytest.raises(FrameValidationError):
        to_grayscale(np.zeros((2, 2, 3, 3), np.uint8), InputDomainSettings())  # ndim 4
    with pytest.raises(FrameValidationError):
        to_grayscale(np.zeros((0, 4, 3), np.uint8), InputDomainSettings())  # empty
    with pytest.raises(FrameValidationError):
        to_grayscale(np.zeros((2, 2), dtype=np.int32), InputDomainSettings())  # dtype


def test_to_uint8_gray_display_only():
    assert to_uint8_gray(np.array([0.0, 0.5, 1.0])).tolist() == [0, 128, 255]
