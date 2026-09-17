"""Deterministic synthetic frame sources (plan §11 "synthetic data first",
§23 dataset strategy: controlled videos with randomized variation).

All generators are pure functions of (scene, size, frame count, seed, fps):
same parameters → byte-identical frames. Noise (when enabled) uses a
seeded `numpy.random.Generator` (PCG64), never global RNG state.
"""

from __future__ import annotations

from typing import Iterator

import numpy as np

from .framesource import FrameRecord

SCENES = ("gradient", "ramp_bands", "moving_square", "static")


def _gradient(size: tuple[int, int]) -> np.ndarray:
    w, h = size
    xs = np.linspace(0.0, 255.0, num=w, endpoint=True, dtype=np.float64)
    row = np.rint(xs).astype(np.uint8)
    gray = np.tile(row, (h, 1))
    return np.stack([gray, gray, gray], axis=-1)


def _ramp_bands(size: tuple[int, int], levels: int) -> np.ndarray:
    """Horizontal bands hitting every level center exactly (for L-level tests)."""
    w, h = size
    centers = (np.arange(levels) + 0.5) / levels
    values = np.rint(centers * 255.0).astype(np.uint8)
    bands = np.resize(values, (w,))
    gray = np.tile(bands, (h, 1))
    return np.stack([gray, gray, gray], axis=-1)


def _moving_square(
    size: tuple[int, int],
    index: int,
    *,
    background: int = 40,
    square: int = 220,
    square_size: int = 24,
    velocity: tuple[int, int] = (4, 2),
    noise_px: int = 0,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    w, h = size
    frame = np.full((h, w, 3), background, dtype=np.uint8)
    x0 = int((velocity[0] * index) % max(1, w - square_size))
    y0 = int((velocity[1] * index) % max(1, h - square_size))
    frame[y0 : y0 + square_size, x0 : x0 + square_size, :] = square
    if noise_px and rng is not None:
        ys = rng.integers(0, h, size=noise_px)
        xs = rng.integers(0, w, size=noise_px)
        vals = rng.integers(0, 256, size=noise_px, dtype=np.uint8)
        frame[ys, xs, 0] = vals
        frame[ys, xs, 1] = vals
        frame[ys, xs, 2] = vals
    return frame


class SyntheticSource:
    """Yields deterministic FrameRecords for a named scene."""

    def __init__(
        self,
        scene: str = "moving_square",
        size: tuple[int, int] = (160, 120),
        n_frames: int = 32,
        *,
        fps: float = 30.0,
        seed: int = 0,
        levels: int = 16,
        noise_px: int = 0,
        name: str | None = None,
    ):
        if scene not in SCENES:
            raise ValueError(f"unknown synthetic scene '{scene}' (available: {SCENES})")
        if n_frames < 1:
            raise ValueError("n_frames must be >= 1")
        if fps <= 0:
            raise ValueError("fps must be > 0")
        self.scene = scene
        self.size = (int(size[0]), int(size[1]))
        self.n_frames = int(n_frames)
        self.fps = float(fps)
        self.seed = int(seed)
        self.levels = int(levels)
        self.noise_px = int(noise_px)
        self._name = name or f"synthetic:{scene}"

    def describe(self) -> dict:
        return {
            "kind": "synthetic",
            "name": self._name,
            "sha256": None,
            "declared_fps": self.fps,
            "width": self.size[0],
            "height": self.size[1],
        }

    def _frame(self, index: int, rng: np.random.Generator | None) -> np.ndarray:
        if self.scene == "gradient":
            return _gradient(self.size)
        if self.scene == "ramp_bands":
            return _ramp_bands(self.size, self.levels)
        if self.scene == "static":
            return _moving_square(
                self.size, 0, noise_px=self.noise_px, rng=rng
            )
        return _moving_square(self.size, index, noise_px=self.noise_px, rng=rng)

    def frames(self) -> Iterator[FrameRecord]:
        period_us = int(round(1_000_000 / self.fps))
        rng = np.random.default_rng(self.seed) if self.noise_px else None
        for index in range(self.n_frames):
            data = self._frame(index, rng)
            yield FrameRecord(
                data=data,
                frame_index=index,
                source_frame_id=f"synthetic-{index:06d}",
                timestamp_us=index * period_us,
                wall_time_utc=None,
                warnings=(),
            )

    def close(self) -> None:  # pragma: no cover - nothing to release
        return None


def module_info() -> dict:
    return {
        "module": "visual_intensity_engine.input.synthetic",
        "version": "1.0.0",
        "input_schema": "scene/size/n_frames/fps/seed/levels/noise_px",
        "output_schema": "FrameRecord iterator (uint8 RGB)",
        "config_schema": "SCENES enum; deterministic given (params, seed)",
        "error_behavior": "ValueError for unknown scene / bad parameters",
        "logging_behavior": "silent",
        "performance_expectations": ">100 fps at 160x120",
        "test_coverage": "tests/unit/test_synthetic_source.py",
    }
