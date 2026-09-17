"""Performance tests (plan §35) — generous thresholds, CI-stable.

These guard against gross regressions (10x slowdowns), not micro-benchmarks;
precise measurements live in experiments/EXP-0001 (plan §19/§39: correctness
before optimization; optimization starts only after profiling).
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from visual_intensity_engine.config import InputDomainSettings, QuantizationSettings
from visual_intensity_engine.metrics import summarize
from visual_intensity_engine.preprocessing.grayscale import to_grayscale
from visual_intensity_engine.preprocessing.quantization import quantize

pytestmark = pytest.mark.performance


def timed(fn, repeat=15):
    times = []
    for _ in range(repeat):
        t0 = time.perf_counter_ns()
        fn()
        t1 = time.perf_counter_ns()
        times.append(t1 - t0)
    return summarize(times)


def test_1080p_gray_latency_bound():
    frame = np.random.default_rng(0).integers(0, 256, (1080, 1920, 3), dtype=np.uint8)
    stats = timed(lambda: to_grayscale(frame, InputDomainSettings()), repeat=10)
    p50_ms = stats["p50"] / 1e6
    assert p50_ms < 100, f"1080p grayscale p50={p50_ms:.1f} ms exceeds 100 ms guard"


def test_1080p_quantize_latency_bound():
    y = np.random.default_rng(1).random((1080, 1920))
    stats = timed(lambda: quantize(y, QuantizationSettings(levels=16)), repeat=10)
    p50_ms = stats["p50"] / 1e6
    assert p50_ms < 50, f"1080p quantization p50={p50_ms:.1f} ms exceeds 50 ms guard"


def test_vga_pipeline_throughput_guard():
    frame = np.random.default_rng(2).integers(0, 256, (480, 640, 3), dtype=np.uint8)
    settings = InputDomainSettings()
    qcfg = QuantizationSettings(levels=16)
    stats = timed(lambda: quantize(to_grayscale(frame, settings)[0], qcfg), repeat=20)
    p50_ms = stats["p50"] / 1e6
    assert p50_ms < 30, f"VGA gray+quantize p50={p50_ms:.1f} ms exceeds 30 ms guard (need >30 fps)"
