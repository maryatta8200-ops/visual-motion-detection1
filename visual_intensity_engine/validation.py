"""Module-boundary validation helpers (plan §3.9: validate at boundaries).

All checks raise typed errors from `errors.py`; none mutate inputs.
"""

from __future__ import annotations

import numpy as np

from .errors import FrameValidationError

_FLOAT_DTYPES = (np.float32, np.float64)
_INT_DTYPES = (np.uint8, np.uint16)

_DTYPE_MAX = {np.dtype("uint8"): 255, np.dtype("uint16"): 65535}


def dtype_max(dtype: np.dtype) -> float:
    """Normalization divisor per VIE-SPEC-REP §2.5 (float domain max = 1.0)."""
    dt = np.dtype(dtype)
    if dt in _DTYPE_MAX:
        return float(_DTYPE_MAX[dt])
    if dt in _FLOAT_DTYPES:
        return 1.0
    raise FrameValidationError(
        f"unsupported dtype {dt} (allowed: uint8, uint16, float32, float64)"
    )


def validate_frame_array(frame: np.ndarray, *, name: str = "frame") -> tuple[np.ndarray, bool]:
    """Validate structural contract of a frame; returns (frame, has_alpha).

    Structural only: value-range/non-finite policies are applied during
    grayscale conversion where the policy is known.
    """
    if not isinstance(frame, np.ndarray):
        raise FrameValidationError(f"{name}: expected numpy.ndarray, got {type(frame)!r}")
    if frame.ndim == 3:
        c = frame.shape[2]
        if c == 4:
            return frame, True
        if c != 3:
            raise FrameValidationError(
                f"{name}: expected 3 channels (RGB) or 4 (RGBA), got {c}"
            )
        return frame, False
    if frame.ndim == 2:
        return frame, False
    raise FrameValidationError(f"{name}: expected ndim 2 (gray) or 3 (RGB/RGBA), got {frame.ndim}")


def validate_dtype(frame: np.ndarray, *, name: str = "frame") -> None:
    dt = frame.dtype
    if dt not in (np.dtype(d) for d in (*_INT_DTYPES, *_FLOAT_DTYPES)):
        raise FrameValidationError(
            f"{name}: unsupported dtype {dt}; allowed: uint8, uint16, float32, float64"
        )


def validate_non_empty(frame: np.ndarray, *, name: str = "frame") -> None:
    if frame.shape[0] < 1 or frame.shape[1] < 1:
        raise FrameValidationError(f"{name}: empty frame with shape {frame.shape} (min 1x1)")


def validate_intensity_map(arr: np.ndarray, levels: int, *, name: str = "intensity map") -> None:
    """Contract for a quantized map: 2-D uint8 within [0, levels-1]."""
    if arr.ndim != 2:
        raise FrameValidationError(f"{name}: expected 2-D array, got ndim={arr.ndim}")
    if arr.dtype != np.uint8:
        raise FrameValidationError(f"{name}: expected dtype uint8, got {arr.dtype}")
    if levels < 2 or levels > 256:
        raise FrameValidationError(f"{name}: levels must be in [2, 256], got {levels}")
    if arr.size and int(arr.max()) >= levels:
        raise FrameValidationError(
            f"{name}: found intensity id {int(arr.max())} >= levels={levels}"
        )
