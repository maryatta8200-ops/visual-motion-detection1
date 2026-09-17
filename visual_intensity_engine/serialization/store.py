"""Frame store writer/reader (plan §2 deterministic replay, VIE-SPEC-REP §9).

Byte-deterministic NPZ: standard `.npz` is NOT byte-reproducible (ZIP entries
carry wall-clock timestamps), so this module writes the same zip format with
fixed entry timestamps, sorted names, and a fixed compression level. Result:
identical inputs + identical library versions → identical bytes → stable
checksums across repeated runs (plan §36 output checksums).
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import zipfile
from pathlib import Path

import numpy as np

from ..config import PipelineConfig, schemas_dir, validate_against_schema
from ..errors import CompatibilityError, SerializationError
from ..intensity.intensity_map import FrameInfo, IntensityMap
from ..intensity.vocabulary import IntensityVocabulary

logger = logging.getLogger("vie.serialization.store")

MANIFEST_SCHEMA_NAME = "framestore_manifest.schema.json"
MANIFEST_SCHEMA_ID = "vie.framestore-manifest/1"
ZIP_FIXED_DATE = (1980, 1, 1, 0, 0, 0)  # deterministic ZIP entry timestamps
COMPRESSION = zipfile.ZIP_DEFLATED
COMPRESS_LEVEL = 6
NPZ_KEY_FORMAT = "f%06d"


def npz_key(frame_index: int) -> str:
    return NPZ_KEY_FORMAT % frame_index


def _npy_bytes(array: np.ndarray) -> bytes:
    buf = io.BytesIO()
    np.lib.format.write_array(buf, np.asanyarray(array), allow_pickle=False)
    return buf.getvalue()


def write_npz_deterministic(path: Path, arrays: dict[str, np.ndarray]) -> None:
    """Write an .npz-compatible zip with reproducible bytes (VIE-SPEC-REP §9.3)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=COMPRESSION, compresslevel=COMPRESS_LEVEL) as zf:
        for name in sorted(arrays):
            info = zipfile.ZipInfo(filename=f"{name}.npy", date_time=ZIP_FIXED_DATE)
            info.compress_type = COMPRESSION
            info.external_attr = 0o644 << 16
            zf.writestr(info, _npy_bytes(arrays[name]))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class FrameStoreWriter:
    """Accumulates IntensityMaps and writes the store bundle on close()."""

    def __init__(
        self,
        outdir: Path | str,
        *,
        config: PipelineConfig,
        vocabulary: IntensityVocabulary,
        input_description: dict | None,
        provenance: dict,
        stage: str = "phase1",
    ):
        self.outdir = Path(outdir)
        self.config = config
        self.vocabulary = vocabulary
        self.input_description = input_description
        self.provenance = provenance
        self.stage = stage
        self._maps: list[IntensityMap] = []
        self._closed = False

    def add(self, imap: IntensityMap) -> None:
        if self._closed:
            raise SerializationError("writer already closed")
        self._maps.append(imap)

    def _manifest(self) -> dict:
        frames = [m.manifest_row(npz_key(m.frame.frame_index)) for m in self._maps]
        dropped = sum(1 for m in self._maps if any("drop" in w for w in m.warnings))
        warning_count = sum(len(m.warnings) for m in self._maps)
        return {
            "schema": MANIFEST_SCHEMA_ID,
            "stage": self.stage,
            "config": self.config.to_dict(),
            "config_sha256": self.config.sha256(),
            "vocabulary": self.vocabulary.to_dict(),
            "input": self.input_description,
            "provenance": self.provenance,
            "frames": frames,
            "counts": {"frames": len(frames), "dropped_frames": dropped, "warnings": warning_count},
            "npz_key_format": NPZ_KEY_FORMAT,
        }

    def close(self) -> dict:
        """Writes intensity_maps.npz + manifest.json + checksums.json. Returns manifest."""
        if self._closed:
            raise SerializationError("writer already closed")
        self._closed = True
        self.outdir.mkdir(parents=True, exist_ok=True)
        npz_path = self.outdir / "intensity_maps.npz"
        write_npz_deterministic(npz_path, {npz_key(m.frame.frame_index): m.intensity for m in self._maps})
        manifest = self._manifest()
        # validate the manifest against its schema before writing (boundaries, plan §3.9)
        validate_against_schema(
            manifest, schemas_dir() / MANIFEST_SCHEMA_NAME, what="frame-store manifest"
        )
        manifest_path = self.outdir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        checksums = {
            "algorithm": "sha256",
            "artifacts": {
                "intensity_maps.npz": sha256_file(npz_path),
                "manifest.json": sha256_file(manifest_path),
            },
        }
        (self.outdir / "checksums.json").write_text(
            json.dumps(checksums, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        logger.info(
            "wrote frame store: %d frame(s) → %s", len(self._maps), self.outdir
        )
        return manifest


class FrameStoreReader:
    """Reads and verifies a store bundle (checksums + vocabulary compatibility)."""

    def __init__(self, outdir: Path | str, *, expected_vocabulary: IntensityVocabulary | None = None,
                 verify_checksums: bool = True):
        self.outdir = Path(outdir)
        npz_path = self.outdir / "intensity_maps.npz"
        manifest_path = self.outdir / "manifest.json"
        checksums_path = self.outdir / "checksums.json"
        for p in (npz_path, manifest_path, checksums_path):
            if not p.is_file():
                raise SerializationError(f"incomplete frame store, missing {p.name} in {self.outdir}")
        if verify_checksums:
            stored = json.loads(checksums_path.read_text(encoding="utf-8"))
            for name, expected in sorted(stored["artifacts"].items()):
                actual = sha256_file(self.outdir / name)
                if actual != expected:
                    raise SerializationError(
                        f"checksum mismatch for {name}: expected {expected}, got {actual} "
                        f"(store corrupted or tampered: {self.outdir})"
                    )
        self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        validate_against_schema(
            self.manifest, schemas_dir() / MANIFEST_SCHEMA_NAME, what="frame-store manifest"
        )
        self.vocabulary = IntensityVocabulary.from_dict(self.manifest["vocabulary"])
        if expected_vocabulary is not None:
            expected_vocabulary.require_compatible(self.vocabulary, context=f"frame store {self.outdir}")

    @property
    def config_sha256(self) -> str:
        return self.manifest["config_sha256"]

    def frame_indices(self) -> list[int]:
        return [f["frame_index"] for f in self.manifest["frames"]]

    def load_all(self) -> list[IntensityMap]:
        with np.load(self.outdir / "intensity_maps.npz", allow_pickle=False) as npz:
            maps = []
            for row in self.manifest["frames"]:
                arr = npz[row["npz_key"]]
                frame_info = FrameInfo(
                    frame_index=row["frame_index"],
                    source_frame_id=row["source_frame_id"],
                    timestamp_us=row["timestamp_us"],
                    wall_time_utc=row["wall_time_utc"],
                    height=row["height"],
                    width=row["width"],
                )
                maps.append(
                    IntensityMap(
                        intensity=np.ascontiguousarray(arr, dtype=np.uint8),
                        levels=self.vocabulary.levels,
                        vocabulary_version=self.vocabulary.vocabulary_version,
                        config_sha256=self.manifest["config_sha256"],
                        frame=frame_info,
                        non_finite_coerced=row["non_finite_coerced"],
                        clipped_to_range=row["clipped_to_range"],
                        alpha_dropped=row["alpha_dropped"],
                        warnings=tuple(row["warnings"]),
                    )
                )
        return maps

    def load_frame(self, frame_index: int) -> np.ndarray:
        with np.load(self.outdir / "intensity_maps.npz", allow_pickle=False) as npz:
            key = npz_key(frame_index)
            if key not in npz.files:
                raise SerializationError(f"frame {frame_index} ({key}) not present in {self.outdir}")
            return np.ascontiguousarray(npz[key], dtype=np.uint8)


def module_info() -> dict:
    return {
        "module": "visual_intensity_engine.serialization.store",
        "version": "1.0.0",
        "input_schema": "IntensityMap stream → vie-framestore/1 bundle",
        "output_schema": "intensity_maps.npz + manifest.json + checksums.json",
        "config_schema": "serialization.format=vie-framestore/1, deterministic=true",
        "error_behavior": "SerializationError on I/O, checksum mismatch, malformed manifest; "
        "CompatibilityError on vocabulary mismatch",
        "logging_behavior": "INFO on store write",
        "performance_expectations": "write ~30-80 MB/s (zlib-6); read faster",
        "test_coverage": "tests/integration/test_pipeline_roundtrip.py, tests/edge/test_fault_injection.py",
    }
