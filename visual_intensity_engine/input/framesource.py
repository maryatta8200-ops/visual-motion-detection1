"""Frame source contract (plan §34 input/, VIE-SPEC-REP §7).

A FrameSource yields immutable FrameRecords in processing order and reports
temporal anomalies (duplicates, gaps, out-of-order, identical payloads) as
warnings — never silently (VIE-SPEC-REP §7.4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, Protocol

import numpy as np

from ..errors import SourceError
from ..provenance import utc_now_rfc3339


@dataclass(frozen=True)
class FrameRecord:
    data: np.ndarray          # uint8 RGB (H, W, 3)
    frame_index: int          # 0-based processing order
    source_frame_id: str | None
    timestamp_us: int         # media time, integer microseconds
    wall_time_utc: str | None
    warnings: tuple[str, ...] = field(default=())


class FrameSource(Protocol):
    def frames(self) -> Iterator[FrameRecord]: ...
    def close(self) -> None: ...
    def describe(self) -> dict: ...


def check_timestamp_sequence(
    timestamps: list[int], nominal_period_us: int | None
) -> list[str]:
    """Detect duplicates / non-monotonicity / gaps (VIE-SPEC-REP §7.4)."""
    warnings: list[str] = []
    for i in range(1, len(timestamps)):
        prev, cur = timestamps[i - 1], timestamps[i]
        if cur < prev:
            warnings.append(f"non-monotonic timestamp at frame {i}: {cur} < {prev}")
        elif cur == prev:
            warnings.append(f"duplicate timestamp {cur} at frames {i - 1},{i}")
        elif nominal_period_us and (cur - prev) > int(1.5 * nominal_period_us):
            warnings.append(
                f"frame drop suspected at frame {i}: gap {cur - prev}us > 1.5x nominal {nominal_period_us}us"
            )
    return warnings


def make_frame_record(
    data: np.ndarray, index: int, timestamp_us: int, *, source_frame_id: str | None = None, live: bool = False
) -> FrameRecord:
    return FrameRecord(
        data=data,
        frame_index=index,
        source_frame_id=source_frame_id,
        timestamp_us=int(timestamp_us),
        wall_time_utc=utc_now_rfc3339() if live else None,
    )


__all__ = ["FrameRecord", "FrameSource", "SourceError", "check_timestamp_sequence", "make_frame_record"]
