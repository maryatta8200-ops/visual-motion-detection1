"""Integration tests: video source behavior (plan §20 frame handling)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from ..conftest import requires_cv2
from visual_intensity_engine.errors import SourceError

cv2 = pytest.importorskip("cv2")

from visual_intensity_engine.input.video import CameraSource, VideoFileSource  # noqa: E402


def write_test_video(path: Path, n=8, fps=30.0):
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (32, 24))
    assert vw.isOpened()
    for i in range(n):
        frame = np.zeros((24, 32, 3), np.uint8)
        frame[...] = (i * 20 % 256, 0, 0)  # BGR red channel ramp (writer expects BGR)
        vw.write(frame)
    vw.release()
    return path


@requires_cv2
def test_video_source_yields_rgb_and_monotonic_time(tmp_path):
    path = write_test_video(tmp_path / "v.mp4", n=10)
    src = VideoFileSource(path)
    d = src.describe()
    assert d["kind"] == "video_file" and d["width"] == 32 and d["height"] == 24
    ts = []
    for rec in src.frames():
        assert rec.data.shape == (24, 32, 3)
        assert rec.data.dtype == np.uint8
        ts.append(rec.timestamp_us)
    assert ts == sorted(ts)
    assert all(t >= 0 for t in ts)


@requires_cv2
def test_max_frames_limits_stream(tmp_path):
    path = write_test_video(tmp_path / "v.mp4", n=10)
    src = VideoFileSource(path, max_frames=4)
    assert len(list(src.frames())) == 4


@requires_cv2
def test_missing_file_fails_explicitly(tmp_path):
    with pytest.raises(SourceError, match="not found"):
        VideoFileSource(tmp_path / "absent.mp4")


@requires_cv2
def test_garbage_file_fails_explicitly(tmp_path):
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"\x00" * 4096)
    with pytest.raises(SourceError):
        VideoFileSource(bad)


@requires_cv2
def test_camera_missing_fails_gracefully():
    # device 99 does not exist in CI sandboxes; must raise a clear SourceError
    with pytest.raises(SourceError, match="camera device 99"):
        CameraSource(99)
