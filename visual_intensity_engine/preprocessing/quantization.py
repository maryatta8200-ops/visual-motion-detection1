"""Quantization engine (plan §6, VIE-SPEC-REP §4).

Strategy registry with ONE implemented strategy in Phase 1:

    uniform / global_fixed / floor_right_open:
        level(y) = min(floor(y * L), L - 1)

Requested strategies that are specified as extension points but not
implemented MUST raise ConfigError — requesting one can never silently fall
back to another strategy (plan §3.10).
"""

from __future__ import annotations

import logging

import numpy as np

from ..config import QuantizationSettings
from ..errors import ConfigError
from ..validation import validate_intensity_map

logger = logging.getLogger("vie.preprocessing.quantization")

IMPLEMENTED_STRATEGIES = ("uniform",)
_SPECIFIED_NOT_IMPLEMENTED = (
    "histogram",       # plan §6.2
    "adaptive_local",  # plan §6.3
    "learned",         # plan §6.4
    "dataset_specific",  # plan §6.5
)


def quantize_uniform(y: np.ndarray, levels: int) -> np.ndarray:
    """Normative uniform quantization; uint8 map in [0, levels-1].

    Exact at bin boundaries for power-of-two L (VIE-SPEC-REP §4.2).
    """
    if levels < 2 or levels > 256:
        raise ConfigError(f"levels must be in [2, 256], got {levels}")
    scaled = np.floor(np.asarray(y, dtype=np.float64) * levels)
    np.clip(scaled, 0, levels - 1, out=scaled)
    return scaled.astype(np.uint8)


_STRATEGY_FN = {"uniform": quantize_uniform}


def quantize(y: np.ndarray, settings: QuantizationSettings) -> np.ndarray:
    """Dispatch on the configured strategy; validates the output contract."""
    if settings.strategy not in IMPLEMENTED_STRATEGIES:
        if settings.strategy in _SPECIFIED_NOT_IMPLEMENTED:
            raise ConfigError(
                f"quantization strategy '{settings.strategy}' is a specified extension point "
                f"but is NOT implemented or evaluated yet (implemented: {IMPLEMENTED_STRATEGIES}); "
                "refusing to substitute another strategy"
            )
        raise ConfigError(
            f"unknown quantization strategy '{settings.strategy}' (implemented: "
            f"{IMPLEMENTED_STRATEGIES}; specified-not-implemented: {_SPECIFIED_NOT_IMPLEMENTED})"
        )
    if settings.scope != "global_fixed":
        raise ConfigError(f"quantization scope '{settings.scope}' is not implemented (Phase 1: global_fixed)")
    if settings.boundary_rule != "floor_right_open":
        raise ConfigError(f"boundary rule '{settings.boundary_rule}' is not implemented (v1: floor_right_open)")
    fn = _STRATEGY_FN[settings.strategy]
    out = fn(y, settings.levels)
    validate_intensity_map(out, settings.levels)
    return out


def dequantize(map_: np.ndarray, representative_values: np.ndarray) -> np.ndarray:
    """Reconstruct a *preview* from representative values (lossy, declared).

    Information discarded by quantization cannot be recovered; this returns
    the interval midpoints for visualization/error analysis only.
    """
    rep = np.asarray(representative_values, dtype=np.float64)
    return rep[map_]


def boundary_levels(levels: int) -> dict[str, int]:
    """Normative boundary cases (float domain) for a given L (VIE-SPEC-REP §4.2)."""
    return {
        "y=0.0": 0,
        f"y=1/{levels} (boundary, rounds up)": 1,
        f"y=1/{levels}-eps": 0,
        f"y={(levels-1)}/{levels} (boundary)": levels - 1,
        "y=1.0 (closed last bin)": levels - 1,
    }


def module_info() -> dict:
    return {
        "module": "visual_intensity_engine.preprocessing.quantization",
        "version": "1.0.0",
        "input_schema": "float64 Y in [0,1] + QuantizationSettings",
        "output_schema": "uint8 (H,W) map, ids in [0, L-1], C-contiguous",
        "config_schema": "QuantizationSettings (strategy/levels/scope/boundary/implementation)",
        "error_behavior": "ConfigError for unavailable/unknown strategies or bad level counts",
        "logging_behavior": "silent (pure function)",
        "performance_expectations": "~1-2 ms/frame at 1080p (float64 floor path)",
        "test_coverage": "tests/unit/test_quantization.py, tests/property/, tests/edge/",
    }
