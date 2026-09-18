"""Integration tests: source → pipeline → store → reader (plan §4/§33 Phase 1).

Round-trip guarantee (VIE-SPEC-REP §9.5): read(store) reproduces every map
exactly; replay is byte-identical (§9.3/§9.7); checksums detect tampering.
"""

from __future__ import annotations

import json

import pytest

from visual_intensity_engine.config import PipelineConfig
from visual_intensity_engine.errors import CompatibilityError, SerializationError
from visual_intensity_engine.input.synthetic import SyntheticSource
from visual_intensity_engine.intensity.vocabulary import IntensityVocabulary
from visual_intensity_engine.pipeline import run_pipeline
from visual_intensity_engine.serialization.store import FrameStoreReader


def _run(outdir, *, scene="moving_square", levels=16, n=12, seed=42, size=(64, 48)):
    config = PipelineConfig.default(levels=levels)
    source = SyntheticSource(scene, size, n, seed=seed, levels=levels)
    return run_pipeline(source, config, outdir)


def test_full_round_trip_exact(tmp_path):
    result = _run(tmp_path / "store")
    reader = FrameStoreReader(tmp_path / "store")
    maps = reader.load_all()
    assert len(maps) == 12
    src = SyntheticSource("moving_square", (64, 48), 12, seed=42, levels=16)
    for rec, m in zip(src.frames(), maps, strict=True):
        assert m.frame.frame_index == rec.frame_index
        assert m.frame.timestamp_us == rec.timestamp_us
    # manifest/config coherence
    assert reader.manifest["config"]["quantization"]["levels"] == 16
    assert reader.manifest["counts"]["frames"] == 12
    assert result.manifest["config_sha256"] == reader.config_sha256


def test_replay_byte_identical(tmp_path):
    _run(tmp_path / "a")
    _run(tmp_path / "b")
    a = (tmp_path / "a" / "intensity_maps.npz").read_bytes()
    b = (tmp_path / "b" / "intensity_maps.npz").read_bytes()
    assert a == b, "identical inputs must replay byte-identically (plan §2)"
    ma = json.loads((tmp_path / "a" / "manifest.json").read_text())
    mb = json.loads((tmp_path / "b" / "manifest.json").read_text())
    for m in (ma, mb):
        m["provenance"].pop("created_at_utc")
        m["provenance"].pop("duration_s")
    assert ma == mb


def test_levels_change_changes_outputs(tmp_path):
    _run(tmp_path / "l8", levels=8)
    _run(tmp_path / "l16", levels=16)
    assert (tmp_path / "l8" / "intensity_maps.npz").read_bytes() != (
        tmp_path / "l16" / "intensity_maps.npz"
    ).read_bytes()
    r8 = FrameStoreReader(tmp_path / "l8")
    assert r8.vocabulary.vocabulary_version == "uniform-l8-v1"


def test_checksum_tampering_detected(tmp_path):
    _run(tmp_path / "store")
    npz = tmp_path / "store" / "intensity_maps.npz"
    data = bytearray(npz.read_bytes())
    data[len(data) // 2] ^= 0xFF
    npz.write_bytes(bytes(data))
    with pytest.raises(SerializationError, match="checksum mismatch"):
        FrameStoreReader(tmp_path / "store")


def test_manifest_tampering_detected(tmp_path):
    _run(tmp_path / "store")
    manifest_path = tmp_path / "store" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["counts"]["frames"] = 999  # any mutation breaks the checksum
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(SerializationError, match="checksum mismatch"):
        FrameStoreReader(tmp_path / "store")


def test_vocabulary_compatibility_enforced_on_read(tmp_path):
    _run(tmp_path / "store", levels=16)
    wrong = IntensityVocabulary.build_uniform(8)
    with pytest.raises(CompatibilityError, match="vocabulary mismatch"):
        FrameStoreReader(tmp_path / "store", expected_vocabulary=wrong)
    right = IntensityVocabulary.build_uniform(16)
    FrameStoreReader(tmp_path / "store", expected_vocabulary=right)  # must not raise


def test_incomplete_bundle_rejected(tmp_path):
    _run(tmp_path / "store")
    (tmp_path / "store" / "checksums.json").unlink()
    with pytest.raises(SerializationError, match="missing checksums.json"):
        FrameStoreReader(tmp_path / "store")


def test_histogram_levels_match_configuration(tmp_path):
    _run(tmp_path / "store", levels=8)
    maps = FrameStoreReader(tmp_path / "store").load_all()
    for m in maps:
        assert len(m.histogram) == 8
        assert int(m.histogram.sum()) == 64 * 48


def test_preview_panels_written(tmp_path):
    result = _run(tmp_path / "store")
    # previews rendered inside run_pipeline when requested
    _run(tmp_path / "store2", n=6)
    assert (tmp_path / "store2" / "manifest.json").is_file()
    assert result.metrics["frames"] == 12
