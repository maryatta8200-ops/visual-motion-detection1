"""Fault-injection tests (plan §35): corrupted/missing inputs degrade loudly."""

from __future__ import annotations

import json

import numpy as np
import pytest

from visual_intensity_engine.config import PipelineConfig
from visual_intensity_engine.errors import (
    ConfigError,
    FrameValidationError,
    SerializationError,
    SourceError,
)
from visual_intensity_engine.input.synthetic import SyntheticSource
from visual_intensity_engine.pipeline import run_pipeline
from visual_intensity_engine.serialization.store import FrameStoreReader, FrameStoreWriter
from visual_intensity_engine.intensity.vocabulary import IntensityVocabulary


def test_process_not_a_frame_object():
    config = PipelineConfig.default()
    from visual_intensity_engine.pipeline import process_frame
    from visual_intensity_engine.input.framesource import FrameRecord

    with pytest.raises(FrameValidationError):
        process_frame(
            FrameRecord(data=None, frame_index=0, source_frame_id=None, timestamp_us=0, wall_time_utc=None),
            config, IntensityVocabulary.build_uniform(16),
        )


def test_strict_source_error_aborts_pipeline(tmp_path):
    class BrokenSource:
        def describe(self):
            return {"kind": "synthetic", "name": "broken", "sha256": None,
                    "declared_fps": 30.0, "width": 4, "height": 4}

        def frames(self):
            yield from SyntheticSource("gradient", (4, 4), 2).frames()
            raise SourceError("simulated decode failure mid-stream")

        def close(self):
            pass

    with pytest.raises(SourceError, match="simulated decode failure"):
        run_pipeline(BrokenSource(), PipelineConfig.default(), tmp_path / "out")


def test_invalid_frame_mid_stream_aborts(tmp_path):
    from visual_intensity_engine.input.framesource import FrameRecord

    class BadFrameSource:
        def describe(self):
            return {"kind": "synthetic", "name": "bad", "sha256": None,
                    "declared_fps": 30.0, "width": 4, "height": 4}

        def frames(self):
            yield FrameRecord(np.zeros((4, 4, 3), np.uint8), 0, None, 0, None)
            yield FrameRecord(np.zeros((4, 4), np.float32), 1, None, 33_333, None)  # NaN-free but structurally fine...

        def close(self):
            pass

    # float32 gray frame is structurally valid; make it invalid via NaN instead
    class NaNFrameSource(BadFrameSource):
        def frames(self):
            yield FrameRecord(np.zeros((4, 4, 3), np.uint8), 0, None, 0, None)
            bad = np.zeros((4, 4), np.float32)
            bad[1, 1] = np.nan
            yield FrameRecord(bad, 1, None, 33_333, None)

    with pytest.raises(Exception, match="non-finite"):
        run_pipeline(NaNFrameSource(), PipelineConfig.default(), tmp_path / "out2")


def test_reader_on_empty_directory(tmp_path):
    with pytest.raises(SerializationError, match="missing"):
        FrameStoreReader(tmp_path / "nothing")


def test_corrupt_npz_zip(tmp_path):
    config = PipelineConfig.default()
    vocab = IntensityVocabulary.build_uniform(16)
    writer = FrameStoreWriter(
        tmp_path, config=config, vocabulary=vocab,
        input_description={"kind": "synthetic", "name": "x", "sha256": None,
                           "declared_fps": 30.0, "width": 4, "height": 4},
        provenance={"git_commit": None, "git_dirty": None, "python_version": "t",
                    "numpy_version": "t", "pillow_version": None, "jsonschema_version": None,
                    "platform": "t", "created_at_utc": "1970-01-01T00:00:00.000Z",
                    "duration_s": None, "seed": 0},
    )
    from visual_intensity_engine.intensity.intensity_map import FrameInfo, IntensityMap as IM

    writer.add(IM(np.zeros((4, 4), np.uint8), 16, vocab.vocabulary_version, config.sha256(),
                  FrameInfo(0, None, 0, None, 4, 4)))
    writer.close()
    npz_path = tmp_path / "intensity_maps.npz"
    npz_path.write_bytes(b"PK\x03\x04 garbage not a zip")
    # checksums still match the new corrupted file if attacker recomputes; zip open fails
    checksums = {"algorithm": "sha256",
                 "artifacts": {"intensity_maps.npz": __import__("hashlib").sha256(npz_path.read_bytes()).hexdigest(),
                               "manifest.json": __import__("hashlib").sha256((tmp_path / "manifest.json").read_bytes()).hexdigest()}}
    (tmp_path / "checksums.json").write_text(json.dumps(checksums))
    reader = FrameStoreReader(tmp_path)
    with pytest.raises(Exception):
        reader.load_all()


def test_writer_rejects_add_after_close(tmp_path):
    config = PipelineConfig.default()
    vocab = IntensityVocabulary.build_uniform(16)
    writer = FrameStoreWriter(
        tmp_path, config=config, vocabulary=vocab,
        input_description={"kind": "synthetic", "name": "x", "sha256": None,
                           "declared_fps": 30.0, "width": 4, "height": 4},
        provenance={"git_commit": None, "git_dirty": None, "python_version": "t",
                    "numpy_version": "t", "pillow_version": None, "jsonschema_version": None,
                    "platform": "t", "created_at_utc": "1970-01-01T00:00:00.000Z",
                    "duration_s": None, "seed": 0},
    )
    writer.close()
    from visual_intensity_engine.intensity.intensity_map import FrameInfo, IntensityMap as IM

    with pytest.raises(SerializationError, match="closed"):
        writer.add(IM(np.zeros((4, 4), np.uint8), 16, vocab.vocabulary_version, config.sha256(),
                      FrameInfo(1, None, 33_333, None, 4, 4)))
