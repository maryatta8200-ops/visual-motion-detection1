"""Provenance capture (plan §36, VIE-SPEC-REP §10.3/§10.4).

Every stored result carries: code revision, runtime versions, platform,
creation time (RFC 3339 UTC), input checksum, and the config seed.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy


def utc_now_rfc3339() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def sha256_file(path: Path, *, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git_info() -> tuple[str | None, bool | None]:
    """(commit, dirty). Tolerates missing git; never raises."""
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5, check=True
        ).stdout.strip()
    except Exception:
        return None, None
    dirty: bool | None
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True, timeout=5, check=True
        ).stdout
        dirty = bool(out.strip())
    except Exception:
        dirty = None
    return commit, dirty


def capture_provenance(*, seed: int, duration_s: float | None = None) -> dict:
    commit, dirty = _git_info()
    try:
        import PIL

        pillow_version = PIL.__version__
    except Exception:
        pillow_version = None
    try:
        from importlib.metadata import version as _version

        jsonschema_version = _version("jsonschema")
    except Exception:
        jsonschema_version = None
    return {
        "git_commit": commit,
        "git_dirty": dirty,
        "python_version": sys.version.split()[0],
        "numpy_version": numpy.__version__,
        "pillow_version": pillow_version,
        "jsonschema_version": jsonschema_version,
        "platform": f"{platform.system()}-{platform.machine()}/{platform.release()}",
        "created_at_utc": utc_now_rfc3339(),
        "duration_s": duration_s,
        "seed": int(seed),
    }


def environment_summary() -> dict:
    """Environment block for benchmark results (no hostname — privacy, plan §41)."""
    cpu_model = None
    cpu_count = None
    try:
        text = Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            if line.startswith("model name"):
                cpu_model = line.split(":", 1)[1].strip()
                break
        cpu_count = len([ln for ln in text.splitlines() if ln.startswith("processor")]) or None
    except OSError:
        pass
    if cpu_count is None:
        import os

        cpu_count = os.cpu_count()
    return {
        "python_version": sys.version.split()[0],
        "numpy_version": numpy.__version__,
        "platform": f"{platform.system()}-{platform.machine()}/{platform.release()}",
        "cpu_model": cpu_model,
        "cpu_count": cpu_count,
    }


def dumps_json(obj: dict) -> str:
    """Stable pretty JSON for reports (sorted keys, trailing newline)."""
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def monotonic_ns() -> int:
    return time.perf_counter_ns()
