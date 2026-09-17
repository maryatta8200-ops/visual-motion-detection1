"""Regression tests — golden hashes (plan §35).

Policy: the hashes below pin the *normative reference behavior* (grayscale
values, quantized maps, serialized store bytes). If an intentional change
alters an output, regenerate via `scripts/update_goldens.py`, and record the
reason in `tests/regression/golden/CHANGELOG.md`. Silent drift is a bug.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from visual_intensity_engine.config import InputDomainSettings, PipelineConfig
from visual_intensity_engine.input.synthetic import SyntheticSource
from visual_intensity_engine.pipeline import run_pipeline
from visual_intensity_engine.preprocessing.grayscale import to_grayscale
from visual_intensity_engine.preprocessing.quantization import quantize_uniform
from visual_intensity_engine.provenance import sha256_bytes, sha256_file

GOLDEN = Path(__file__).parent / "golden" / "hashes.json"


@pytest.fixture(scope="module")
def golden():
    return json.loads(GOLDEN.read_text())


def test_golden_file_exists(golden):
    assert golden["spec_version"] == "1.0.0"


def test_golden_reference_vectors(golden):
    """Known RGB → grayscale values (VIE-SPEC-REP §3) must never drift."""
    settings = InputDomainSettings()
    for rgb_hex, expected in golden["reference_vectors"].items():
        rgb = tuple(int(rgb_hex[i : i + 2], 16) for i in (0, 2, 4))
        frame = np.array([[rgb]], dtype=np.uint8)
        y, _, _ = to_grayscale(frame, settings)
        assert y[0, 0] == pytest.approx(expected, abs=1e-12), f"rgb={rgb}"


def test_golden_quantized_ramp(golden):
    y = np.array([v / 255.0 for v in range(256)])
    for levels, expected_sha in golden["quantized_ramp_sha256"].items():
        q = quantize_uniform(y, int(levels))
        assert sha256_bytes(q.tobytes()) == expected_sha


def test_golden_pipeline_store_bytes(golden, tmp_path):
    """Full store bytes for a fixed synthetic run must be stable."""
    config = PipelineConfig.default(levels=16)
    source = SyntheticSource("moving_square", (64, 48), 20, seed=42, levels=16)
    run_pipeline(source, config, tmp_path / "store")
    actual_npz = sha256_file(tmp_path / "store" / "intensity_maps.npz")
    assert actual_npz == golden["store_npz_sha256"], (
        "store bytes drifted — if intentional, run scripts/update_goldens.py and "
        "record the reason in tests/regression/golden/CHANGELOG.md"
    )


def test_golden_gradient_frame_gray(golden):
    frame = SyntheticSource("gradient", (64, 32), 1).frames().__next__().data
    y, _, _ = to_grayscale(frame, InputDomainSettings())
    assert sha256_bytes(y.tobytes()) == golden["gradient_gray_sha256"]
