"""Video file and camera sources (plan §20: batch mode + graceful camera failure).

Requires the optional `video` dependency (opencv-python-headless). The engine
converts BGR→RGB at the source boundary so the pipeline contract stays RGB
(VIE-SPEC-REP §2.2). Temporal anomalies are detected and reported, and in
strict mode raise SourceError (VIE-SPEC-REP §7.4).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from pathlib import Path

import numpy as np

from ..errors import SourceError
from ..provenance import sha256_file, utc_now_rfc3339
from .framesource import FrameRecord, check_timestamp_sequence

logger = logging.getLogger("vie.input.video")

# Whole-file provenance hashing is required (VIE-SPEC-REP §10.3); past this size
# the cost stops being negligible, so it is announced explicitly (plan §3.18).
LARGE_INPUT_WARN_BYTES = 512 * 1024 * 1024

try:  # optional dependency
    import cv2
except Exception:  # pragma: no cover
    cv2 = None  # type: ignore[assignment]


def _require_cv2() -> None:
    if cv2 is None:  # pragma: no cover
        raise SourceError(
            "opencv-python-headless is required for video/camera input; "
            "install with: pip install 'visual-intensity-engine[video]'"
        )


class VideoFileSource:
    """Decoded video file; deterministic for a given file + build."""

    def __init__(self, path: Path | str, *, max_frames: int | None = None, strict: bool = True):
        _require_cv2()
        self.path = Path(path)
        self.max_frames = max_frames
        self.strict = strict
        if not self.path.is_file():
            raise SourceError(f"video file not found: {self.path}")
        self._probe()

    def _probe(self) -> None:
        cap = cv2.VideoCapture(str(self.path))
        if not cap.isOpened():
            raise SourceError(
                f"cannot open video file: {self.path} (missing codec or corrupted container)"
            )
        try:
            self.width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self.declared_fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
            self.frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        finally:
            cap.release()
        if self.width < 1 or self.height < 1:
            raise SourceError(f"video reports invalid geometry {self.width}x{self.height}: {self.path}")

    def describe(self) -> dict:
        """Input description, including the SHA-256 provenance checksum.

        Cost note: the checksum covers the **entire file** and is therefore
        I/O-bound (~1–2 GB/s on local SSD, minutes on multi-GB network mounts).
        VIE-SPEC-REP §10.3 requires it for provenance, so it is not skippable;
        the size is logged at INFO before hashing and files above
        `LARGE_INPUT_WARN_BYTES` also raise a WARNING so the cost is never a
        surprise. (A partial-hash mode would need a schema version increment per
        §8.2 and is deliberately not invented here.)
        """
        size = self.path.stat().st_size
        if size >= LARGE_INPUT_WARN_BYTES:
            logger.warning(
                "input file is %.2f GiB; computing its full SHA-256 for provenance "
                "(I/O-bound, this may take a while): %s",
                size / (1 << 30),
                self.path,
            )
        else:
            logger.info("hashing input file (%d bytes) for provenance", size)
        return {
            "kind": "video_file",
            "name": self.path.name,
            "sha256": sha256_file(self.path),
            "declared_fps": self.declared_fps or None,
            "width": self.width,
            "height": self.height,
        }

    def frames(self) -> Iterator[FrameRecord]:
        cap = cv2.VideoCapture(str(self.path))
        if not cap.isOpened():
            raise SourceError(f"cannot open video file: {self.path}")
        index = 0
        anomalies: list[str] = []
        timestamps: list[int] = []
        nominal_period_us = int(round(1_000_000 / self.declared_fps)) if self.declared_fps else None
        try:
            while True:
                if self.max_frames is not None and index >= self.max_frames:
                    break
                ok, bgr = cap.read()
                if not ok:
                    break  # graceful end-of-file (plan §20)
                rgb = np.ascontiguousarray(bgr[..., ::-1])
                msec = cap.get(cv2.CAP_PROP_POS_MSEC)
                ts = int(round(msec * 1000.0)) if msec and msec > 0 else index * (
                    nominal_period_us or 33333
                )
                warnings: tuple[str, ...] = ()
                if ts < 0 or (timestamps and ts <= timestamps[-1] - 1):
                    msg = f"non-monotonic timestamp at frame {index}: {ts} after {timestamps[-1]}"
                    anomalies.append(msg)
                    if self.strict:
                        raise SourceError(f"{msg} (strict mode; rerun with strict=False to record and continue)")
                    warnings = (msg,)
                timestamps.append(ts)
                yield FrameRecord(
                    data=rgb,
                    frame_index=index,
                    source_frame_id=f"file-{index:06d}",
                    timestamp_us=max(0, ts),
                    wall_time_utc=None,
                    warnings=warnings,
                )
                index += 1
        finally:
            cap.release()
        for w in check_timestamp_sequence(timestamps, nominal_period_us):
            logger.warning("timestamp anomaly: %s", w)
        self.anomaly_count = len(anomalies)

    def close(self) -> None:
        return None


class CameraSource:
    """Live camera; fails gracefully and explicitly when unavailable."""

    def __init__(self, device_index: int = 0, *, strict: bool = True):
        _require_cv2()
        self.device_index = int(device_index)
        self.strict = strict
        self._cap = cv2.VideoCapture(self.device_index)
        if not self._cap.isOpened():
            self._cap.release()
            raise SourceError(
                f"camera device {self.device_index} could not be opened "
                "(no device present or permission denied); use a video file or synthetic source"
            )

    def describe(self) -> dict:
        return {
            "kind": "camera",
            "name": f"camera:{self.device_index}",
            "sha256": None,
            "declared_fps": float(self._cap.get(cv2.CAP_PROP_FPS) or 0.0) or None,
            "width": int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        }

    def frames(self) -> Iterator[FrameRecord]:
        """Yield camera frames with media time from a monotonic clock.

        `timestamp_us` is cumulative media time in µs since the first delivered
        frame (VIE-SPEC-REP §7.2, which conventionally starts at 0). Cameras
        expose no container timestamps, so `time.monotonic_ns()` deltas are the
        honest measurement available; unlike a hard-coded zero they let the
        shared sequence checker detect duplicates and stalls (§7.4). Wall-clock
        time is recorded as provenance only (§7.3).
        """
        index = 0
        first_ns: int | None = None
        timestamps: list[int] = []
        while True:
            ok, bgr = self._cap.read()
            if not ok:
                logger.warning("camera frame grab failed at index %d; stopping", index)
                break
            now_ns = time.monotonic_ns()
            if first_ns is None:
                first_ns = now_ns  # media time starts at 0 on the first delivered frame
            timestamp_us = (now_ns - first_ns) // 1000
            timestamps.append(int(timestamp_us))
            rgb = np.ascontiguousarray(bgr[..., ::-1])
            yield FrameRecord(
                data=rgb,
                frame_index=index,
                source_frame_id=f"cam-{index:06d}",
                timestamp_us=int(timestamp_us),
                wall_time_utc=utc_now_rfc3339(),
            )
            index += 1
        for warning in check_timestamp_sequence(timestamps, None):
            if "non-monotonic" in warning or "duplicate" in warning:
                logger.warning("camera timestamp anomaly: %s", warning)

    def close(self) -> None:
        if getattr(self, "_cap", None) is not None:
            self._cap.release()


def module_info() -> dict:
    return {
        "module": "visual_intensity_engine.input.video",
        "version": "1.0.0",
        "input_schema": "video file path or camera index (opencv)",
        "output_schema": "FrameRecord iterator (uint8 RGB, media timestamps µs)",
        "config_schema": "max_frames, strict",
        "error_behavior": "SourceError on open failure, corrupt file, non-monotonic timestamps (strict)",
        "logging_behavior": "WARNING on EOF anomalies and camera failures",
        "performance_expectations": "input-bound: decode rate and provenance hashing depend on "
                                    "codec/disk; no rate claimed",
        "test_coverage": "tests/edge/test_fault_injection.py (corrupt/missing files)",
    }
