"""Unit tests: quantization engine (VIE-SPEC-REP §4, plan §6)."""

from __future__ import annotations

import numpy as np
import pytest

from visual_intensity_engine.config import QuantizationSettings
from visual_intensity_engine.errors import ConfigError
from visual_intensity_engine.preprocessing.quantization import (
    boundary_levels,
    dequantize,
    quantize,
    quantize_uniform,
)

from ..conftest import SUPPORTED_LEVELS


@pytest.mark.parametrize("levels", SUPPORTED_LEVELS)
def test_all_levels_reachable_via_ramp(levels):
    y = np.linspace(0.0, 1.0, 4096, dtype=np.float64)
    q = quantize_uniform(y, levels)
    assert q.dtype == np.uint8
    assert set(np.unique(q)) == set(range(levels))


@pytest.mark.parametrize("levels", SUPPORTED_LEVELS)
def test_boundary_rule_floor_right_open(levels):
    # y = k/L  -> level k (boundary rounds up)
    for k in range(levels):
        y_edge = np.array([k / levels], dtype=np.float64)
        assert int(quantize_uniform(y_edge, levels)[0]) == k
        y_just_below = np.array([k / levels - 1e-9], dtype=np.float64)
        assert int(quantize_uniform(y_just_below, levels)[0]) == max(0, k - 1)
    assert int(quantize_uniform(np.array([1.0]), levels)[0]) == levels - 1
    assert int(quantize_uniform(np.array([0.0]), levels)[0]) == 0


def test_boundary_documentation_table_matches_implementation():
    for levels in (8, 16, 32, 64, 128, 256):
        table = boundary_levels(levels)
        y_for = {
            "y=0.0": 0.0,
            f"y=1/{levels} (boundary, rounds up)": 1 / levels,
            f"y=1/{levels}-eps": 1 / levels - 1e-9,
            f"y={(levels-1)}/{levels} (boundary)": (levels - 1) / levels,
            "y=1.0 (closed last bin)": 1.0,
        }
        for key, level in table.items():
            assert int(quantize_uniform(np.array([y_for[key]]), levels)[0]) == level


def test_uint8_value_edges_l16():
    y = np.array([v / 255.0 for v in (0, 15, 16, 127, 128, 254, 255)])
    expected = [0, 0, 1, 7, 8, 15, 15]
    assert quantize_uniform(y, 16).tolist() == expected


def test_monotonicity_randomized():
    rng = np.random.default_rng(11)
    y = np.sort(rng.random(10_000))
    for levels in (8, 16, 256):
        q = quantize_uniform(y, levels)
        assert (np.diff(q.astype(np.int64)) >= 0).all()


def test_max_quantization_error_bound():
    for levels in SUPPORTED_LEVELS:
        rng = np.random.default_rng(5)
        y = rng.random(8192)
        rep = (quantize_uniform(y, levels).astype(np.float64) + 0.5) / levels
        assert float(np.abs(rep - y).max()) <= 0.5 / levels + 1e-12


def test_output_contract_2d_uint8():
    y = np.random.default_rng(1).random((7, 9))
    q = quantize(y, QuantizationSettings(levels=16))
    assert q.shape == (7, 9) and q.dtype == np.uint8
    assert q.max() < 16


def test_invalid_levels_rejected():
    for bad in (1, 0, -4, 257, 1000):
        with pytest.raises(ConfigError):
            quantize_uniform(np.zeros((1,)), bad)
        with pytest.raises(ConfigError):
            quantize(np.zeros((1, 1)), QuantizationSettings(levels=bad))


def test_unimplemented_strategies_fail_explicitly():
    # plan §6 lists these; they are extension points and MUST NOT silently run
    for strategy in ("histogram", "adaptive_local", "learned", "dataset_specific"):
        with pytest.raises(ConfigError, match="NOT implemented"):
            quantize(np.zeros((2, 2)), QuantizationSettings(strategy=strategy, levels=16))
    with pytest.raises(ConfigError, match="unknown quantization strategy"):
        quantize(np.zeros((2, 2)), QuantizationSettings(strategy="magic", levels=16))
    with pytest.raises(ConfigError, match="scope"):
        quantize(np.zeros((2, 2)), QuantizationSettings(scope="per_frame_adaptive"))
    with pytest.raises(ConfigError, match="boundary rule"):
        quantize(np.zeros((2, 2)), QuantizationSettings(boundary_rule="round_nearest"))


def test_dequantize_representative_values():
    y = np.array([0.0, 0.24, 0.76, 1.0])
    q = quantize_uniform(y, 16)
    rep = np.array([(k + 0.5) / 16 for k in range(16)])
    dq = dequantize(q, rep)
    assert dq[0] == pytest.approx(0.5 / 16)
    assert dq[3] == pytest.approx(15.5 / 16)


def test_quantization_is_pure_and_deterministic():
    rng = np.random.default_rng(9)
    y = rng.random((32, 32))
    a = quantize_uniform(y, 64)
    b = quantize_uniform(y, 64)
    assert a.tobytes() == b.tobytes()
