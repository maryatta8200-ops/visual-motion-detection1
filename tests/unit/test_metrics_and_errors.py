"""Unit tests: metrics helpers + error hierarchy contract (VIE-SPEC-REP §11)."""

from __future__ import annotations

import pytest

from visual_intensity_engine import (
    CompatibilityError,
    ConfigError,
    FrameValidationError,
    NonFinitePixelError,
    SerializationError,
    SourceError,
    VIEError,
)
from visual_intensity_engine.metrics import human_bytes, summarize, valid_stats


def test_error_hierarchy():
    for exc in (
        ConfigError, FrameValidationError, NonFinitePixelError, SourceError,
        SerializationError, CompatibilityError,
    ):
        assert issubclass(exc, VIEError)
    assert issubclass(NonFinitePixelError, FrameValidationError)


def test_summarize_invariants():
    s = summarize([5.0, 1.0, 3.0, 2.0, 4.0] * 20)
    assert s["n"] == 100
    assert valid_stats(s)
    assert s["min"] == 1.0 and s["max"] == 5.0
    assert s["mean"] == pytest.approx(3.0)
    assert summarize([])["n"] == 0


def test_human_bytes():
    assert human_bytes(999) == "999 B"
    assert "KiB" in human_bytes(2048)
    assert "MiB" in human_bytes(5 * 1024 * 1024)
