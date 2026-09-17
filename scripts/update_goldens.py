#!/usr/bin/env python
"""Regenerate golden hashes after an INTENTIONAL output change.

Usage: .venv/bin/python scripts/update_goldens.py
Then:  1. run the full test suite (must pass)
       2. record the reason + decision in tests/regression/golden/CHANGELOG.md
Never regenerate to make an unexplained failure disappear (plan §3.7/§40).
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from visual_intensity_engine.config import InputDomainSettings, PipelineConfig
from visual_intensity_engine.input.synthetic import SyntheticSource
from visual_intensity_engine.pipeline import run_pipeline
from visual_intensity_engine.preprocessing.grayscale import to_grayscale
from visual_intensity_engine.preprocessing.quantization import quantize_uniform
from visual_intensity_engine.provenance import sha256_bytes, sha256_file

SUPPORTED = (8, 16, 32, 64, 128, 256)


def main() -> int:
    vectors = {}
    for rgb in ((0, 0, 0), (255, 255, 255), (255, 0, 0), (0, 255, 0), (0, 0, 255),
                (255, 255, 0), (49, 49, 49)):
        frame = np.array([[rgb]], dtype=np.uint8)
        y, _, _ = to_grayscale(frame, InputDomainSettings())
        vectors["".join(f"{v:02x}" for v in rgb)] = float(y[0, 0])

    ramp = {}
    y = np.array([v / 255.0 for v in range(256)])
    for levels in SUPPORTED:
        ramp[str(levels)] = sha256_bytes(quantize_uniform(y, levels).tobytes())

    with tempfile.TemporaryDirectory() as td:
        config = PipelineConfig.default(levels=16)
        source = SyntheticSource("moving_square", (64, 48), 20, seed=42, levels=16)
        run_pipeline(source, config, Path(td) / "store")
        store_sha = sha256_file(Path(td) / "store" / "intensity_maps.npz")

    frame = SyntheticSource("gradient", (64, 32), 1).frames().__next__().data
    y_grad, _, _ = to_grayscale(frame, InputDomainSettings())

    golden = {
        "spec_version": "1.0.0",
        "reference_vectors": vectors,
        "quantized_ramp_sha256": ramp,
        "store_npz_sha256": store_sha,
        "gradient_gray_sha256": sha256_bytes(y_grad.tobytes()),
        "note": "store hash is environment-stable (zlib version pinned via requirements.txt)",
    }
    out = ROOT / "tests" / "regression" / "golden" / "hashes.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(golden, indent=2, sort_keys=True) + "\n")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
