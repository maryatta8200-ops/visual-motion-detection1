"""Integration tests: CLI end-to-end (plan §20 batch mode requirements)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from ..conftest import requires_cv2

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable
MODULE = [PY, "-m", "visual_intensity_engine"]


def run_cli(*args, expect=0):
    import subprocess

    proc = subprocess.run(
        MODULE + list(args), cwd=ROOT, capture_output=True, text=True, timeout=300
    )
    assert proc.returncode == expect, (
        f"cli failed rc={proc.returncode}\nstdout:\n{proc.stdout[-2000:]}\nstderr:\n{proc.stderr[-2000:]}"
    )
    return proc


def stdout_json(proc):
    """CLI writes exactly one JSON document to stdout (logs go to stderr)."""
    return json.loads(proc.stdout.strip())


def test_self_test_passes():
    proc = run_cli("self-test", "--levels", "16")
    report = stdout_json(proc)
    assert report["status"] == "PASS"
    assert report["failures"] == []


def test_process_and_validate_round_trip(tmp_path):
    out = tmp_path / "store"
    run_cli("process", "--input", "synthetic:moving_square", "--max-frames", "6",
            "--output", str(out), "--previews", "1")
    assert (out / "intensity_maps.npz").is_file()
    assert (out / "manifest.json").is_file()
    assert (out / "checksums.json").is_file()
    assert (out / "config.json").is_file()
    assert (out / "metrics.json").is_file()
    assert (out / "previews" / "preview_000000.png").is_file()

    proc = run_cli("validate", "--target", str(out))
    report = stdout_json(proc)
    assert report["status"] == "VALID" and report["frames"] == 6


def test_process_refuses_to_overwrite(tmp_path):
    out = tmp_path / "store"
    run_cli("process", "--input", "synthetic:gradient", "--max-frames", "2", "--output", str(out))
    proc = run_cli("process", "--input", "synthetic:gradient", "--max-frames", "2",
                   "--output", str(out), expect=2)
    assert "already exists" in proc.stderr


def test_validate_config_file():
    proc = run_cli("validate", "--target", str(ROOT / "configs" / "quantization.uniform.l016.v1.json"))
    report = stdout_json(proc)
    assert report["status"] == "VALID" and len(report["sha256"]) == 64


def test_invalid_config_fails_explicitly(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({
        "schema": "vie.pipeline-config/1", "config_version": "1.0.0", "seed": 0,
        "quantization": {"strategy": "uniform", "levels": 999, "scope": "global_fixed",
                         "boundary_rule": "floor_right_open", "implementation": "reference"},
        "input_domain": {
            "channel_order": "RGB", "luma_standard": "bt601", "normalization": "dtype_max",
            "alpha_policy": "drop", "non_finite_policy": "strict", "float_range_policy": "strict",
        },
        "serialization": {"format": "vie-framestore/1", "deterministic": True},
    }))
    proc = run_cli("process", "--input", "synthetic:gradient", "--config", str(bad),
                   "--output", str(tmp_path / "o"), expect=2)
    assert "ConfigError" in proc.stderr


def test_missing_config_file_fails(tmp_path):
    run_cli("process", "--input", "synthetic:gradient", "--config", str(tmp_path / "nope.json"),
            "--output", str(tmp_path / "o"), expect=2)


def test_unknown_scene_fails(tmp_path):
    run_cli("process", "--input", "synthetic:elvis", "--output", str(tmp_path / "o"), expect=2)


def test_corrupt_video_fails_gracefully(tmp_path):
    bad = tmp_path / "corrupt.mp4"
    bad.write_bytes(b"this is not a video file" * 100)
    proc = run_cli("process", "--input", str(bad), "--output", str(tmp_path / "o"), expect=2)
    assert "SourceError" in proc.stderr  # explicit failure, no traceback crash


@requires_cv2
def test_camera_requires_an_explicit_stop_condition(tmp_path):
    """A live camera has no end-of-stream, so an unbounded batch run is refused."""
    proc = run_cli("process", "--input", "camera:99", "--output", str(tmp_path / "o"), expect=2)
    assert "ConfigError" in proc.stderr
    assert "--max-frames" in proc.stderr


@requires_cv2
def test_missing_camera_fails_gracefully(tmp_path):
    proc = run_cli(
        "process", "--input", "camera:99", "--max-frames", "10",
        "--output", str(tmp_path / "o"), expect=2,
    )
    assert "SourceError" in proc.stderr


def test_video_file_batch(tmp_path):
    cv2 = pytest.importorskip("cv2")
    import numpy as np

    video = tmp_path / "tiny.mp4"
    vw = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 30, (64, 48))
    assert vw.isOpened()
    for i in range(12):
        frame = np.full((48, 64, 3), 40, np.uint8)
        frame[8:20, 4 * i : 4 * i + 6] = 200
        vw.write(frame)
    vw.release()
    out = tmp_path / "store"
    run_cli("process", "--input", str(video), "--max-frames", "12", "--output", str(out))
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["input"]["kind"] == "video_file"
    assert manifest["input"]["sha256"]
    assert manifest["counts"]["frames"] == 12
    ts = [f["timestamp_us"] for f in manifest["frames"]]
    assert ts == sorted(ts), "video timestamps must be monotonic"


def test_levels_matrix_via_cli(tmp_path):
    for lv in (8, 16, 32, 64, 128, 256):
        out = tmp_path / f"store_l{lv}"
        run_cli("process", "--input", "synthetic:ramp_bands", "--max-frames", "1",
                "--levels", str(lv), "--output", str(out))
        manifest = json.loads((out / "manifest.json").read_text())
        assert manifest["vocabulary"]["quantization"]["levels"] == lv
