"""Integration tests: Phase-2 pipeline and CLI (plan §20 batch mode, §33 stage gate)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

from visual_intensity_engine.config import PipelineConfig
from visual_intensity_engine.errors import RegionExtractionError
from visual_intensity_engine.input.synthetic import SyntheticSource
from visual_intensity_engine.objects.objects_config import ObjectsConfig
from visual_intensity_engine.objects.pipeline import run_objects
from visual_intensity_engine.objects.store import ObjectStoreReader

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
    return json.loads(proc.stdout.strip())


def test_objects_pipeline_writes_a_valid_store(tmp_path):
    config = PipelineConfig.default(levels=16)
    source = SyntheticSource("moving_square", (96, 64), 5, seed=3, levels=16)
    result = run_objects(source, config, ObjectsConfig(min_area=2), tmp_path / "store", previews=2)
    assert result.metrics["frames"] == 5
    assert result.metrics["regions"]["kept"] > 0
    assert (tmp_path / "store" / "previews" / "objects_000000.png").is_file()
    assert (tmp_path / "store" / "previews" / "objects_000001.png").is_file()
    assert not (tmp_path / "store" / "previews" / "objects_000002.png").is_file()
    reader = ObjectStoreReader(tmp_path / "store")
    assert reader.frame_count == 5
    # the invariant must hold for every frame of a real run, not only in unit tests
    for row, frame in zip(reader.manifest["frames"], reader.region_set["frames"], strict=True):
        area = sum(r["area"] for r in frame["regions"])
        assert area + row["dropped_pixels"] == row["height"] * row["width"]


def test_objects_pipeline_replay_is_byte_identical(tmp_path):
    config = PipelineConfig.default(levels=8)
    for name in ("a", "b"):
        run_objects(
            SyntheticSource("gradient", (80, 48), 4, seed=5, levels=8),
            config,
            ObjectsConfig(min_area=3),
            tmp_path / name,
        )
    assert (tmp_path / "a" / "region_labels.npz").read_bytes() == (
        tmp_path / "b" / "region_labels.npz"
    ).read_bytes()
    assert (tmp_path / "a" / "regions.json").read_bytes() == (tmp_path / "b" / "regions.json").read_bytes()
    ma = json.loads((tmp_path / "a" / "manifest.json").read_text())
    mb = json.loads((tmp_path / "b" / "manifest.json").read_text())
    for m in (ma, mb):
        m["provenance"].pop("created_at_utc", None)
        m["provenance"].pop("duration_s", None)
    assert ma == mb


def test_min_area_discards_are_counted_and_reported(tmp_path):
    config = PipelineConfig.default(levels=16)
    source = SyntheticSource("static", (64, 64), 1, seed=42, levels=16, noise_px=40)
    result = run_objects(source, config, ObjectsConfig(min_area=8), tmp_path / "store")
    counts = result.manifest["counts"]
    assert counts["dropped_regions"] > 0 and counts["dropped_pixels"] > 0
    assert counts["regions"] > 0
    metrics = json.loads((tmp_path / "store" / "metrics.json").read_text())
    assert metrics["regions"]["dropped"] == counts["dropped_regions"]
    assert metrics["regions"]["dropped_pixels"] == counts["dropped_pixels"]


def test_max_regions_stops_the_run_without_writing_a_valid_store(tmp_path):
    config = PipelineConfig.default(levels=16)
    source = SyntheticSource("static", (64, 64), 1, seed=42, levels=16, noise_px=40)
    with pytest.raises(RegionExtractionError, match="max_regions"):
        run_objects(source, config, ObjectsConfig(max_regions=4), tmp_path / "store")
    # an aborted run must not present a partial store as valid
    assert not (tmp_path / "store" / "manifest.json").exists()
    assert not (tmp_path / "store" / "checksums.json").exists()


def test_empty_source_writes_a_valid_zero_frame_store(tmp_path):
    class EmptySource:
        def describe(self):
            return {
                "kind": "synthetic", "name": "empty", "sha256": None,
                "declared_fps": None, "width": 4, "height": 4,
            }

        def frames(self):
            return iter(())

    config = PipelineConfig.default(levels=16)
    result = run_objects(EmptySource(), config, ObjectsConfig(), tmp_path / "store")
    assert result.manifest["counts"]["frames"] == 0
    reader = ObjectStoreReader(tmp_path / "store")
    assert reader.frame_count == 0
    assert reader.region_set["frames"] == []


def test_cli_objects_round_trip_and_validate(tmp_path):
    out = tmp_path / "store"
    proc = run_cli(
        "objects", "--input", "synthetic:moving_square", "--max-frames", "4",
        "--output", str(out), "--min-area", "2", "--previews", "1",
    )
    report = stdout_json(proc)
    assert report["frames"] == 4 and report["objects"] > 0
    for name in ("region_labels.npz", "regions.json", "manifest.json", "checksums.json",
                 "objects_config.json", "metrics.json", "config.json"):
        assert (out / name).is_file(), name
    validated = stdout_json(run_cli("validate", "--target", str(out)))
    assert validated["kind"] == "object-store" and validated["status"] == "VALID"
    assert validated["regions"] == report["objects"]


def test_cli_objects_refuses_to_overwrite(tmp_path):
    out = tmp_path / "store"
    run_cli("objects", "--input", "synthetic:gradient", "--max-frames", "2", "--output", str(out))
    proc = run_cli(
        "objects", "--input", "synthetic:gradient", "--max-frames", "2",
        "--output", str(out), expect=2,
    )
    assert "already exists" in proc.stderr


def test_cli_objects_config_file_and_max_regions_flag(tmp_path):
    objects_config = tmp_path / "objects.json"
    objects_config.write_text(json.dumps({
        "schema": "vie.objects-config/1", "objects_config_version": "1.0.0",
        "connectivity": 4, "min_area": 2, "max_regions": None, "implementation": "reference",
    }))
    out = tmp_path / "store"
    report = stdout_json(run_cli(
        "objects", "--input", "synthetic:ramp_bands", "--max-frames", "3",
        "--objects-config", str(objects_config), "--output", str(out),
    ))
    assert report["objects_config_sha256"] == ObjectsConfig(min_area=2).sha256()

    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({
        "schema": "vie.objects-config/1", "objects_config_version": "1.0.0",
        "connectivity": 8, "min_area": 1, "max_regions": None, "implementation": "reference",
    }))
    proc = run_cli(
        "objects", "--input", "synthetic:ramp_bands", "--max-frames", "3",
        "--objects-config", str(bad), "--output", str(tmp_path / "store2"), expect=2,
    )
    assert "connectivity" in proc.stderr


def test_cli_validate_detects_corrupted_object_store(tmp_path):
    out = tmp_path / "store"
    run_cli("objects", "--input", "synthetic:gradient", "--max-frames", "2", "--output", str(out))
    regions = out / "regions.json"
    regions.write_text(regions.read_text().replace('"area":1', '"area":2', 1))
    proc = run_cli("validate", "--target", str(out), expect=2)
    assert "checksum mismatch" in proc.stderr


def test_viewer_state_and_object_store_are_independent(tmp_path):
    """Sanity: Phase 1 and Phase 2 stores of the same frames are separate bundles."""
    from visual_intensity_engine.pipeline import run_pipeline
    from visual_intensity_engine.serialization.store import FrameStoreReader

    config = PipelineConfig.default(levels=8)
    run_pipeline(
        SyntheticSource("moving_square", (64, 48), 3, seed=1, levels=8), config, tmp_path / "p1"
    )
    run_objects(
        SyntheticSource("moving_square", (64, 48), 3, seed=1, levels=8),
        config,
        ObjectsConfig(),
        tmp_path / "p2",
    )
    assert isinstance(FrameStoreReader(tmp_path / "p1").load_all(), list)
    assert isinstance(ObjectStoreReader(tmp_path / "p2").label_map(0), np.ndarray)
    assert (tmp_path / "p1" / "intensity_maps.npz").is_file()
    assert (tmp_path / "p2" / "region_labels.npz").is_file()
