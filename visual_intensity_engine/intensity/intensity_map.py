"""Quantized intensity map record (plan §4/§7, VIE-SPEC-REP §4/§7/§8).

An `IntensityMap` is the Phase-1 product of the pipeline for one frame:
uint8 level ids + full traceability (frame index, media timestamp, config
hash, vocabulary version) + per-frame anomaly counters. Raw frames are never
required to construct it, but sources keep them available as ground truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..errors import FrameValidationError
from ..validation import validate_intensity_map

__all__ = ["FrameInfo", "IntensityMap", "validate_intensity_map"]


@dataclass(frozen=True)
class FrameInfo:
    frame_index: int
    source_frame_id: str | None
    timestamp_us: int
    wall_time_utc: str | None
    height: int
    width: int


@dataclass(frozen=True)
class IntensityMap:
    intensity: np.ndarray  # uint8 (H, W)
    levels: int
    vocabulary_version: str
    config_sha256: str
    frame: FrameInfo
    non_finite_coerced: int = 0
    clipped_to_range: int = 0
    alpha_dropped: bool = False
    warnings: tuple[str, ...] = field(default=())

    def __post_init__(self):
        validate_intensity_map(self.intensity, self.levels)
        if self.frame.height != self.intensity.shape[0] or self.frame.width != self.intensity.shape[1]:
            raise FrameValidationError(
                f"FrameInfo geometry {self.frame.height}x{self.frame.width} does not match "
                f"intensity map shape {self.intensity.shape}"
            )
        if self.frame.timestamp_us < 0:
            raise FrameValidationError(f"timestamp_us must be >= 0, got {self.frame.timestamp_us}")

    @property
    def histogram(self) -> np.ndarray:
        """Count of each level 0..L-1 (int64, length L)."""
        return np.bincount(self.intensity.ravel(), minlength=self.levels).astype(np.int64)

    def manifest_row(self, npz_key: str) -> dict:
        return {
            "frame_index": self.frame.frame_index,
            "npz_key": npz_key,
            "source_frame_id": self.frame.source_frame_id,
            "timestamp_us": self.frame.timestamp_us,
            "wall_time_utc": self.frame.wall_time_utc,
            "height": self.frame.height,
            "width": self.frame.width,
            "non_finite_coerced": self.non_finite_coerced,
            "clipped_to_range": self.clipped_to_range,
            "alpha_dropped": self.alpha_dropped,
            "warnings": list(self.warnings),
        }
