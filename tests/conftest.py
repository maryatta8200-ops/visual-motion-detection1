"""Shared fixtures. Adds repo root to sys.path for source checkouts."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from visual_intensity_engine.config import PipelineConfig  # noqa: E402
from visual_intensity_engine.intensity.vocabulary import IntensityVocabulary  # noqa: E402

SUPPORTED_LEVELS = (8, 16, 32, 64, 128, 256)


@pytest.fixture
def config_l16() -> PipelineConfig:
    return PipelineConfig.default(levels=16)


@pytest.fixture
def vocab_l16() -> IntensityVocabulary:
    return IntensityVocabulary.build_uniform(16)


@pytest.fixture
def small_rgb() -> np.ndarray:
    rng = np.random.default_rng(7)
    return rng.integers(0, 256, size=(24, 32, 3), dtype=np.uint8)


def config_dict(**overrides) -> dict:
    """Valid base config dict for schema tests; override nested keys by path."""
    cfg = {
        "schema": "vie.pipeline-config/1",
        "config_version": "1.0.0",
        "seed": 0,
        "quantization": {
            "strategy": "uniform",
            "levels": 16,
            "scope": "global_fixed",
            "boundary_rule": "floor_right_open",
            "implementation": "reference",
        },
        "input_domain": {
            "channel_order": "RGB",
            "luma_standard": "bt601",
            "normalization": "dtype_max",
            "alpha_policy": "drop",
            "non_finite_policy": "strict",
            "float_range_policy": "strict",
        },
        "serialization": {"format": "vie-framestore/1", "deterministic": True},
    }
    for dotted, value in overrides.items():
        node = cfg
        parts = dotted.split(".")
        for part in parts[:-1]:
            node = node[part]
        node[parts[-1]] = value
    return cfg


def has_cv2() -> bool:
    try:
        import cv2  # noqa: F401

        return True
    except Exception:
        return False


requires_cv2 = pytest.mark.skipif(not has_cv2(), reason="opencv-python-headless not installed")
