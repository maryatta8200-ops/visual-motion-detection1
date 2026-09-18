"""Integration tests: CLI boundary validation and benchmark output policy.

Regression suite for the 2026-09-18 execution audit (AUD-01, AUD-02, AUD-03,
AUD-08, AUD-10). Every case runs the real CLI as a subprocess — no mocks — and
asserts the observable contract:

- a bad numeric flag or a malformed `camera:` source is a *typed* failure
  (exit 2, message on stderr, **no traceback**), never an escaping `ValueError`;
- `vie benchmark` / `vie benchmark-objects` refuse an existing non-empty output
  directory (recorded experiments are append-only) unless `--overwrite` is given;
- `--overwrite` replaces only the runner's own files and never deletes anything;
- the object benchmark is reachable from `vie` (AUD-08) and writes a
  schema-valid `vie.object-benchmark-result/1` document.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable
MODULE = [PY, "-m", "visual_intensity_engine"]


def run_cli(*args, expect=0, cwd=ROOT):
    proc = subprocess.run(
        MODULE + list(args), cwd=cwd, capture_output=True, text=True, timeout=300
    )
    assert proc.returncode == expect, (
        f"expected rc={expect}, got {proc.returncode}\n"
        f"stdout:\n{proc.stdout[-2000:]}\nstderr:\n{proc.stderr[-2000:]}"
    )
    return proc


def stdout_json(proc):
    return json.loads(proc.stdout.strip())


@pytest.mark.parametrize("bad_levels", ["0", "1", "-5", "257", "300", "abc", "16.5"])
def test_out_of_range_levels_is_a_usage_error(tmp_path, bad_levels):
    """AUD-01: `--levels` was a raw ValueError traceback before this fix."""
    out = tmp_path / "store"
    proc = run_cli(
        "process", "--input", "synthetic:gradient", "--levels", bad_levels,
        "--output", str(out), expect=2,
    )
    assert "argument --levels" in proc.stderr
    assert "Traceback" not in proc.stderr, "a bad flag must never print a traceback"
    assert not out.exists(), "a rejected invocation must not create an output directory"


def test_levels_boundaries_are_accepted(tmp_path):
    for lv in ("2", "256"):
        out = tmp_path / f"store_l{lv}"
        run_cli("process", "--input", "synthetic:ramp_bands", "--max-frames", "1",
                "--levels", lv, "--output", str(out), "--previews", "0")
        manifest = json.loads((out / "manifest.json").read_text())
        assert manifest["vocabulary"]["quantization"]["levels"] == int(lv)


@pytest.mark.parametrize(
    "args",
    [
        ("process", "--input", "synthetic:gradient", "--max-frames", "0"),
        ("process", "--input", "synthetic:gradient", "--previews", "-1"),
        ("process", "--input", "synthetic:gradient", "--max-frames", "abc"),
        ("objects", "--input", "synthetic:gradient", "--min-area", "0"),
        ("objects", "--input", "synthetic:gradient", "--max-regions", "0"),
        ("self-test", "--levels", "999"),
        ("benchmark", "--frames", "0"),
        ("benchmark", "--warmup", "-1"),
        ("serve", "--port", "70000"),
    ],
)
def test_every_numeric_flag_is_validated_at_the_boundary(tmp_path, args):
    proc = run_cli(*args, "--output", str(tmp_path / "o"), expect=2)
    assert "error: argument" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_camera_index_must_be_an_integer(tmp_path):
    """AUD-02: `camera:abc` used to raise a bare ValueError at cli.py:65."""
    out = tmp_path / "cam"
    proc = run_cli(
        "process", "--input", "camera:abc", "--max-frames", "5", "--output", str(out), expect=2
    )
    assert "ConfigError" in proc.stderr and "camera" in proc.stderr
    assert "Traceback" not in proc.stderr
    assert not out.exists()


def test_negative_camera_index_is_rejected(tmp_path):
    out = tmp_path / "cam"
    proc = run_cli(
        "process", "--input", "camera:-1", "--max-frames", "5", "--output", str(out), expect=2
    )
    assert "ConfigError" in proc.stderr and ">= 0" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_benchmark_refuses_to_overwrite_a_recorded_experiment(tmp_path):
    """AUD-03: recorded experiments are append-only, exactly as for process/objects."""
    out = tmp_path / "exp"
    run_cli("benchmark", "--output", str(out), "--frames", "3", "--warmup", "1")
    first = (out / "result.json").read_text()
    proc = run_cli("benchmark", "--output", str(out), "--frames", "3", "--warmup", "1", expect=2)
    assert "already exists" in proc.stderr and "never overwritten" in proc.stderr
    assert "--overwrite" in proc.stderr, "the error must say how to proceed deliberately"
    assert (out / "result.json").read_text() == first, "the recorded result must be untouched"


def test_benchmark_overwrite_replaces_only_the_runners_own_files(tmp_path):
    out = tmp_path / "exp"
    run_cli("benchmark", "--output", str(out), "--frames", "3", "--warmup", "1")
    (out / "result.json").write_text("{not json any more}\n")
    keep = out / "keep_me.txt"
    keep.write_text("unrelated file\n")
    proc = run_cli(
        "benchmark", "--output", str(out), "--frames", "3", "--warmup", "1", "--overwrite"
    )
    report = stdout_json(proc)
    assert report["overwritten"] is True
    assert json.loads((out / "result.json").read_text())["schema"] == "vie.benchmark-result/1"
    assert keep.read_text() == "unrelated file\n", "--overwrite must not delete other files"


def test_benchmark_needs_a_measured_frame(tmp_path):
    proc = run_cli(
        "benchmark", "--output", str(tmp_path / "exp"), "--frames", "3", "--warmup", "3", expect=2
    )
    assert "ConfigError" in proc.stderr and "measured frame" in proc.stderr
    assert not (tmp_path / "exp").exists()


def test_checked_in_experiment_dirs_are_protected_by_default():
    """The repository's own recorded experiments cannot be clobbered by accident."""
    default_dir = ROOT / "experiments" / "EXP-0001-quantization-baseline"
    if not default_dir.is_dir():  # pragma: no cover - checkout without recorded results
        pytest.skip("recorded EXP-0001 artifacts are not present in this checkout")
    before = (default_dir / "result.json").read_text()
    proc = run_cli("benchmark", "--frames", "2", "--warmup", "1", expect=2)
    assert "already exists" in proc.stderr
    assert (default_dir / "result.json").read_text() == before


def test_objects_benchmark_is_reachable_from_the_cli(tmp_path):
    """AUD-08: the EXP-0002 runner is a first-class `vie` subcommand."""
    out = tmp_path / "exp2"
    proc = run_cli(
        "benchmark-objects", "--output", str(out), "--frames", "2", "--warmup", "1",
        "--levels", "8", "--resolutions", "32x24", "--scenes", "gradient",
        "--adversarial", "32x24:1:2", "--note", "tiny smoke condition",
    )
    report = stdout_json(proc)
    assert report["experiment_id"] == "EXP-0002" and report["outdir"] == str(out)
    result = json.loads((out / "result.json").read_text())
    assert result["schema"] == "vie.object-benchmark-result/1"
    assert result["conditions"], "the run must record at least one condition"
    assert "tiny smoke condition" in (out / "report.md").read_text()


def test_objects_benchmark_refuses_to_overwrite(tmp_path):
    out = tmp_path / "exp2"
    args = ("benchmark-objects", "--output", str(out), "--frames", "2", "--warmup", "1",
            "--levels", "8", "--resolutions", "32x24", "--scenes", "gradient",
            "--adversarial", "32x24:1:2")
    run_cli(*args)
    proc = run_cli(*args, expect=2)
    assert "already exists" in proc.stderr
    run_cli(*args, "--overwrite")
