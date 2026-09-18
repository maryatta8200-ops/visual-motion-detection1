"""Grayscale / luminance conversion — reference implementation.

VIE-SPEC-REP §3. Computes normalized luminance Y ∈ [0,1] as float64:

    Y = c_r·(R/D) + c_g·(G/D) + c_b·(B/D),  D = dtype max

The reference implementation is normative (plan §6); any future optimized
implementation must match it within ±1e-12 absolute AND produce identical
intensity maps. Implementations are registered in a registry so callers can
select via config (dependency injection, plan §34).
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import numpy as np

from ..config import InputDomainSettings
from ..errors import FrameValidationError, NonFinitePixelError
from ..validation import (
    dtype_max,
    validate_dtype,
    validate_frame_array,
    validate_non_empty,
)

logger = logging.getLogger("vie.preprocessing.grayscale")

LUMA_COEFFICIENTS = {
    "bt601": (0.299, 0.587, 0.114),
    "bt709": (0.2126, 0.7152, 0.0722),
    "average": (1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0),
}

# (frame, settings) -> (y_float64, non_finite_coerced, clipped_to_range)
GrayscaleImplementation = Callable[[np.ndarray, InputDomainSettings], tuple[np.ndarray, int, int]]

_IMPLEMENTATIONS: dict[str, GrayscaleImplementation] = {}


def register_implementation(name: str, fn) -> None:
    """Dependency-injection point for optimized implementations (plan §34)."""
    _IMPLEMENTATIONS[name] = fn


def to_grayscale_reference(frame: np.ndarray, settings: InputDomainSettings) -> tuple[np.ndarray, int, int]:
    """Returns (y_float64, non_finite_coerced, clipped_to_range)."""
    frame, has_alpha = validate_frame_array(frame)
    validate_non_empty(frame)
    validate_dtype(frame)
    if has_alpha and settings.alpha_policy == "error":
        raise FrameValidationError("frame has 4 channels but alpha_policy='error'")

    dmax = dtype_max(frame.dtype)
    work = frame.astype(np.float64) / dmax

    non_finite_coerced = 0
    clipped = 0
    finite_mask = np.isfinite(work)
    if not bool(finite_mask.all()):
        bad_samples = int((~finite_mask).sum())
        bad_pixel = ~finite_mask if frame.ndim == 2 else ~finite_mask.all(axis=2)
        if settings.non_finite_policy == "strict":
            ys, xs = np.nonzero(bad_pixel)
            first = (int(ys[0]), int(xs[0]))
            raise NonFinitePixelError(
                f"frame contains {bad_samples} non-finite value(s); first at (row, col)={first}; "
                "set input_domain.non_finite_policy='coerce' to substitute and record"
            )
        work = np.where(np.isnan(work), 0.0, work)
        work = np.where(np.isposinf(work), 1.0, work)
        work = np.where(np.isneginf(work), 0.0, work)
        non_finite_coerced = bad_samples
        logger.warning("coerced %d non-finite sample(s) to domain bounds", non_finite_coerced)

    if frame.ndim == 2:
        y = work.copy()
    else:
        if has_alpha and settings.alpha_policy == "composite_black":
            alpha = work[..., 3:4]
            work = work[..., :3] * alpha
        work = work[..., :3]
        bad_pixel = ((work < 0.0) | (work > 1.0)).any(axis=2)
        n_bad = int(bad_pixel.sum())
        if n_bad and settings.float_range_policy == "strict":
            ys, xs = np.nonzero(bad_pixel)
            first = (int(ys[0]), int(xs[0]))
            raise FrameValidationError(
                f"float frame has {n_bad} pixel(s) with channel values outside [0,1]; "
                f"first pixel (row, col)={first}; set input_domain.float_range_policy='clip' "
                "to clamp and record"
            )
        if n_bad:
            work = np.clip(work, 0.0, 1.0)
            clipped = n_bad
            logger.warning("clamped %d out-of-range float pixel(s) into [0,1]", clipped)
        c_r, c_g, c_b = LUMA_COEFFICIENTS[settings.luma_standard]
        y = c_r * work[..., 0] + c_g * work[..., 1] + c_b * work[..., 2]

    y = np.ascontiguousarray(np.clip(y, 0.0, 1.0), dtype=np.float64)
    return y, non_finite_coerced, clipped


def to_uint8_gray(y: np.ndarray) -> np.ndarray:
    """Display-only conversion (VIE-SPEC-REP §3.4). NOT part of quantization."""
    return np.clip(np.rint(np.asarray(y, dtype=np.float64) * 255.0), 0, 255).astype(np.uint8)


register_implementation("reference", to_grayscale_reference)


def to_grayscale(frame: np.ndarray, settings: InputDomainSettings, *, implementation: str = "reference"):
    """Dispatch to the configured implementation; returns (y, nf, clipped)."""
    fn = _IMPLEMENTATIONS.get(implementation)
    if fn is None:
        raise FrameValidationError(
            f"grayscale implementation '{implementation}' is not registered "
            f"(available: {sorted(_IMPLEMENTATIONS)})"
        )
    return fn(frame, settings)


def reference_vectors() -> dict[tuple[int, int, int], float]:
    """Normative reference vectors from VIE-SPEC-REP §3 (uint8, bt601)."""
    return {
        (0, 0, 0): 0.0,
        (255, 255, 255): 1.0,
        (255, 0, 0): 0.299,
        (0, 255, 0): 0.587,
        (0, 0, 255): 0.114,
        (255, 255, 0): 0.886,
        (49, 49, 49): 49.0 / 255.0,
    }


def module_info() -> dict:
    return {
        "module": "visual_intensity_engine.preprocessing.grayscale",
        "version": "1.0.0",
        "input_schema": "ndarray uint8/uint16/float32/float64, ndim 2 or 3(RGB[A last])",
        "output_schema": "float64 Y in [0,1], C-contiguous (H,W) + anomaly counters",
        "config_schema": "InputDomainSettings (luma_standard, alpha, non-finite, float-range)",
        "error_behavior": "FrameValidationError / NonFinitePixelError (strict policies)",
        "logging_behavior": "WARNING on coerce/clip events, via logger 'vie.preprocessing.grayscale'",
        "performance_expectations": "measured (EXP-0001): p50 2.2 ms 320x240, 8.8 ms 640x480, "
                                    "76 ms 1920x1080 (float64 reference, single core)",
        "test_coverage": "tests/unit/test_grayscale.py, tests/edge/",
        "implementations": sorted(_IMPLEMENTATIONS),
    }
