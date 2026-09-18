"""Performance measurement helpers (plan §35 performance tests, §36 method).

Timing uses `time.perf_counter_ns` (monotonic, high resolution). Memory uses
`tracemalloc` (Python allocation peaks). Warm-up policy is explicit at every
call site: warm-up samples are excluded from reported statistics.
"""

from __future__ import annotations

import contextlib
import math
import tracemalloc
from collections.abc import Iterable, Sequence


def summarize(values: Sequence[float]) -> dict:
    """Summary statistics over per-frame measurements (nanoseconds)."""
    if not values:
        return {"n": 0, "mean": 0.0, "std": 0.0, "min": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0}
    ordered = sorted(values)
    n = len(ordered)

    def pct(p: float) -> float:
        k = max(0, min(n - 1, int(math.ceil(p / 100.0 * n)) - 1))
        return float(ordered[k])

    mean = sum(ordered) / n
    var = sum((v - mean) ** 2 for v in ordered) / n
    return {
        "n": n,
        "mean": mean,
        "std": math.sqrt(var),
        "min": float(ordered[0]),
        "p50": pct(50),
        "p95": pct(95),
        "p99": pct(99),
        "max": float(ordered[-1]),
    }


class Timer:
    """One-shot wall timer in nanoseconds."""

    def __enter__(self) -> Timer:
        import time

        self.start_ns = time.perf_counter_ns()
        return self

    def __exit__(self, *exc) -> None:
        import time

        self.elapsed_ns = time.perf_counter_ns() - self.start_ns


@contextlib.contextmanager
def traced_memory():
    """Yields a dict that receives Python-allocation peak in bytes."""
    tracemalloc.start()
    info = {"peak_bytes": 0}
    try:
        yield info
    finally:
        _, peak = tracemalloc.get_traced_memory()
        info["peak_bytes"] = peak
        tracemalloc.stop()


def rss_kb() -> int | None:
    """Resident set size in KiB (Linux) or None when unavailable."""
    try:
        with open("/proc/self/status", encoding="ascii") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
    except OSError:
        pass
    return None


def human_bytes(n: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB"):
        if abs(n) < 1024 or unit == "GiB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024.0
    return f"{n:.1f} GiB"


def valid_stats(stats: dict) -> bool:
    """Invariants of a summarize() dict (used by tests and the benchmark validator)."""
    keys = ("min", "p50", "p95", "p99", "max")
    return (
        stats["n"] > 0
        and all(stats[k] >= 0 for k in keys)
        and stats["min"] <= stats["p50"] <= stats["p95"] <= stats["p99"] <= stats["max"] + 1e-9
    )


def extend_history(history: list[float], values: Iterable[float]) -> None:
    history.extend(values)
