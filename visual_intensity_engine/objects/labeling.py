"""Level-uniform 4-connected region labeling (VIE-SPEC-REP 1.1.0 §R2–§R6).

Production path — **vectorized run-length + union-find** (pure numpy, no C
extension beyond numpy itself):

1. runs: every maximal horizontal run of one level, discovered in raster order
   (`np.nonzero` on the change mask yields C-order, i.e. top→bottom, left→right);
2. edges: two runs are 4-connected iff they overlap in x on adjacent rows with
   the same level. Vertical pixel adjacency (`qmap[1:] == qmap[:-1]`) enumerates
   exactly those pairs; identical (run, run) pairs are deduplicated with one
   `np.unique` sort;
3. union-find over run ids with *union by smaller id*. Because run ids follow
   raster order, the surviving representative is the component's smallest run id,
   i.e. its discovery rank — so ordering representatives gives exactly the §R4
   discovery order with no extra sort;
4. `min_area` is applied to component areas; dropped components are counted and
   their pixels get label 0, ids of the kept components stay contiguous 0..n−1;
5. component root per run is resolved by vectorized pointer jumping
   (`p = p[p]`, O(log depth) numpy passes) rather than a Python loop.

Determinism: every step is a deterministic numpy reduction; no hashing, no
randomness, no iteration-order dependence (§R4.3).

Test oracle — `label_level_uniform_regions_reference`: the straightforward
per-pixel scanline flood fill (also pure Python/numpy). It is O(H·W) with a
Python-level inner loop, so it is *not* the production path, but it is obviously
correct and is used to prove the fast path label-for-label on generated corpora
(`tests/unit/test_labeling.py`).
"""

from __future__ import annotations

from array import array
from dataclasses import dataclass

import numpy as np

from ..errors import RegionExtractionError
from .objects_config import ObjectsConfig

_LABEL_DTYPE = np.int32


@dataclass(frozen=True)
class RegionCandidate:
    """A kept component in raster discovery order (ids are assigned later)."""

    level: int
    area: int
    x0: int
    y0: int
    x1: int
    y1: int
    centroid_x: float
    centroid_y: float


@dataclass(frozen=True)
class LabelMapResult:
    """`labels[y, x]` is `region_id + 1` for kept regions and 0 for dropped pixels."""

    labels: np.ndarray
    regions: tuple[RegionCandidate, ...]
    dropped_regions: int
    dropped_pixels: int

    @property
    def shapes_consistent(self) -> bool:
        h, w = self.labels.shape
        kept = sum(r.area for r in self.regions)
        return kept + self.dropped_pixels == h * w


def label_level_uniform_regions(
    intensity: np.ndarray,
    levels: int,
    config: ObjectsConfig,
) -> LabelMapResult:
    """Label a quantized intensity map; see module docstring for the contract."""
    qmap = _validate_qmap(intensity, levels)
    if config.connectivity != 4:  # defensive: ObjectsConfig already enforces this
        raise RegionExtractionError(f"connectivity={config.connectivity} is not implemented")
    labels, dropped_regions, dropped_pixels = _label_runs(qmap, config.min_area)
    kept = int(labels.max(initial=0))
    if config.max_regions is not None and kept > config.max_regions:
        raise RegionExtractionError(
            f"extracted {kept} regions but max_regions={config.max_regions}; "
            f"region extraction never truncates output (VIE-SPEC-REP 1.1.0 §R5.2)"
        )
    regions = _regions_from_labels(labels, qmap)
    return LabelMapResult(
        labels=labels,
        regions=regions,
        dropped_regions=dropped_regions,
        dropped_pixels=dropped_pixels,
    )


# --------------------------------------------------------------------------
# production: run-length + union-find
# --------------------------------------------------------------------------
def _label_runs(qmap: np.ndarray, min_area: int) -> tuple[np.ndarray, int, int]:
    h, w = qmap.shape
    starts = np.empty((h, w), dtype=bool)
    starts[:, 0] = True
    starts[:, 1:] = qmap[:, 1:] != qmap[:, :-1]
    ys, xs = np.nonzero(starts)  # C-order == raster order of run starts
    n_runs = int(ys.size)
    if n_runs == 0:  # unreachable for a non-empty map, kept explicit
        raise RegionExtractionError("no runs found in a non-empty intensity map")

    same_row = ys[:-1] == ys[1:]  # length n_runs - 1
    run_end = np.empty(n_runs, dtype=np.int64)
    run_end[:-1] = np.where(same_row, xs[1:] - 1, w - 1)
    run_end[-1] = w - 1
    run_len = run_end - xs + 1

    # 1-based run id for every pixel (cumsum of the start mask, offset per row)
    row_offsets = np.zeros(h, dtype=np.int32)
    np.cumsum(starts.sum(axis=1, dtype=np.int32)[:-1], out=row_offsets[1:])
    run_of = np.cumsum(starts, axis=1, dtype=np.int32)
    run_of += row_offsets[:, None]

    par = array("i", range(n_runs))

    def find(x: int) -> int:
        while par[x] != x:
            par[x] = par[par[x]]  # path halving
            x = par[x]
        return x

    if h > 1:
        # Only columns where one of the two run ids changes can introduce a new
        # (run_above, run_below) pair, so candidate count is O(#runs), not O(#pixels).
        above, below = run_of[:-1], run_of[1:]
        candidate = np.zeros((h - 1, w), dtype=bool)
        candidate[:, 0] = True
        candidate[:, 1:] = (above[:, 1:] != above[:, :-1]) | (below[:, 1:] != below[:, :-1])
        candidate &= qmap[1:] == qmap[:-1]
        if candidate.any():
            a = above[candidate]
            b = below[candidate]
            lo = np.minimum(a, b).astype(np.int64) - 1
            hi = np.maximum(a, b).astype(np.int64) - 1
            keys = np.unique(lo * n_runs + hi)  # deterministic, sorted
            lo, hi = keys // n_runs, keys % n_runs
            for i in range(lo.size):
                ra, rb = find(int(lo[i])), find(int(hi[i]))
                if ra != rb:  # union by smaller id ⇒ representative = discovery rank
                    if ra < rb:
                        par[rb] = ra
                    else:
                        par[ra] = rb

    parent = np.frombuffer(par, dtype=np.int32).astype(np.int64)
    root = parent
    for _ in range(64):  # O(log n) pointer jumps; 64 is far above any real depth
        jumped = root[root]
        if np.array_equal(jumped, root):
            break
        root = jumped
    if not np.array_equal(root[root], root):
        raise RegionExtractionError(
            "component-root resolution did not converge (union-find invariant violated)"
        )

    areas = np.bincount(root, weights=run_len.astype(np.float64), minlength=n_runs)
    areas_int = areas.astype(np.int64)
    if not np.array_equal(areas_int.astype(np.float64), areas):
        raise RegionExtractionError("component areas exceeded exact float64 integer range")
    is_root = np.zeros(n_runs, dtype=bool)
    is_root[root] = True
    if int(areas_int.sum()) != int(run_len.sum()):
        raise RegionExtractionError("component areas do not sum to the frame's pixel count")

    kept_mask = (areas_int >= min_area) & is_root
    kept_roots = np.nonzero(kept_mask)[0]  # ascending == discovery order
    dropped_mask = (areas_int < min_area) & is_root
    dropped_regions = int(np.count_nonzero(dropped_mask))
    dropped_pixels = int(areas_int[dropped_mask].sum())

    root_to_label = np.zeros(n_runs, dtype=np.int32)
    root_to_label[kept_roots] = np.arange(1, kept_roots.size + 1, dtype=np.int32)
    run_label = root_to_label[root]
    labels = run_label[run_of.astype(np.int64) - 1].astype(_LABEL_DTYPE)
    return labels, dropped_regions, dropped_pixels


# --------------------------------------------------------------------------
# test oracle: per-pixel scanline flood fill
# --------------------------------------------------------------------------
def label_level_uniform_regions_reference(
    intensity: np.ndarray,
    levels: int,
    config: ObjectsConfig,
) -> LabelMapResult:
    """Reference implementation used as a test oracle (see module docstring)."""
    qmap = _validate_qmap(intensity, levels)
    if config.connectivity != 4:
        raise RegionExtractionError(f"connectivity={config.connectivity} is not implemented")
    h, w = qmap.shape
    rows = qmap.tolist()
    visited = [bytearray(w) for _ in range(h)]
    labels_rows = [[0] * w for _ in range(h)]
    components: list[tuple[int, int]] = []  # (provisional label, area) in discovery order

    for sy in range(h):
        for sx in range(w):
            if visited[sy][sx]:
                continue
            level = rows[sy][sx]
            new_label = len(components) + 1
            area = 0
            stack = [(sy, sx)]
            visited[sy][sx] = 1
            labels_rows[sy][sx] = new_label
            while stack:
                cy, cx = stack.pop()
                area += 1
                if cy > 0 and not visited[cy - 1][cx] and rows[cy - 1][cx] == level:
                    visited[cy - 1][cx] = 1
                    labels_rows[cy - 1][cx] = new_label
                    stack.append((cy - 1, cx))
                if cy + 1 < h and not visited[cy + 1][cx] and rows[cy + 1][cx] == level:
                    visited[cy + 1][cx] = 1
                    labels_rows[cy + 1][cx] = new_label
                    stack.append((cy + 1, cx))
                if cx > 0 and not visited[cy][cx - 1] and rows[cy][cx - 1] == level:
                    visited[cy][cx - 1] = 1
                    labels_rows[cy][cx - 1] = new_label
                    stack.append((cy, cx - 1))
                if cx + 1 < w and not visited[cy][cx + 1] and rows[cy][cx + 1] == level:
                    visited[cy][cx + 1] = 1
                    labels_rows[cy][cx + 1] = new_label
                    stack.append((cy, cx + 1))
            components.append((new_label, area))

    raw = np.asarray(labels_rows, dtype=_LABEL_DTYPE)
    kept_labels = np.asarray(
        [lbl for lbl, area in components if area >= config.min_area], dtype=_LABEL_DTYPE
    )
    dropped_regions = sum(1 for _, area in components if area < config.min_area)
    dropped_pixels = sum(area for _, area in components if area < config.min_area)
    # renumber kept components to contiguous 0..n-1 ids in discovery order (§R4.2)
    remap = np.zeros(int(raw.max(initial=0)) + 1, dtype=_LABEL_DTYPE)
    remap[kept_labels] = np.arange(1, kept_labels.size + 1, dtype=_LABEL_DTYPE)
    labels = remap[raw]
    if config.max_regions is not None and kept_labels.size > config.max_regions:
        raise RegionExtractionError(
            f"extracted {kept_labels.size} regions but max_regions={config.max_regions}; "
            f"region extraction never truncates output (VIE-SPEC-REP 1.1.0 §R5.2)"
        )
    return LabelMapResult(
        labels=labels,
        regions=_regions_from_labels(labels, qmap),
        dropped_regions=dropped_regions,
        dropped_pixels=dropped_pixels,
    )


# --------------------------------------------------------------------------
# shared metadata
# --------------------------------------------------------------------------
def _region_bounds(labels: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(ys, xs) of labelled pixels in ascending label order."""
    ys, xs = np.nonzero(labels)
    if ys.size == 0:
        return ys, xs
    ids = labels[ys, xs].astype(np.int64) - 1
    order = np.argsort(ids, kind="stable")
    return ys[order], xs[order]


def _regions_from_labels(labels: np.ndarray, qmap: np.ndarray) -> tuple[RegionCandidate, ...]:
    """Exact float64 centroids and half-open bounds from a label map (§R3).

    Metadata is derived from the label map (not from the labeling bookkeeping), so
    the production path and the reference oracle produce identical records whenever
    their label maps agree. Group reductions are vectorized (`bincount` for areas
    and coordinate sums, `reduceat` for bounds), so the cost for a frame with n
    regions is O(pixels + n) with no per-pixel Python.
    """
    n = int(labels.max(initial=0))
    if n == 0:
        return ()
    ys, xs = _region_bounds(labels)
    ids = labels[ys, xs].astype(np.int64) - 1
    counts = np.bincount(ids, minlength=n)
    if not np.all(counts > 0):  # explicit: labels are contiguous 1..n by construction (§R4.2)
        raise RegionExtractionError(
            f"label map has gaps: expected contiguous labels 1..{n} "
            f"(missing {int(np.count_nonzero(counts == 0))})"
        )
    starts = np.concatenate(([0], np.cumsum(counts)[:-1]))
    sum_x = np.bincount(ids, weights=xs.astype(np.float64), minlength=n)
    sum_y = np.bincount(ids, weights=ys.astype(np.float64), minlength=n)
    min_x = np.minimum.reduceat(xs, starts)
    max_x = np.maximum.reduceat(xs, starts)
    min_y = np.minimum.reduceat(ys, starts)
    max_y = np.maximum.reduceat(ys, starts)
    levels = qmap[ys[starts], xs[starts]]
    areas = counts.astype(np.int64)
    return tuple(
        RegionCandidate(
            level=int(levels[i]),
            area=int(areas[i]),
            x0=int(min_x[i]),
            y0=int(min_y[i]),
            x1=int(max_x[i]) + 1,
            y1=int(max_y[i]) + 1,
            centroid_x=float(sum_x[i] / areas[i]),
            centroid_y=float(sum_y[i] / areas[i]),
        )
        for i in range(n)
    )


def _validate_qmap(intensity: np.ndarray, levels: int) -> np.ndarray:
    arr = np.asarray(intensity)
    if arr.ndim != 2:
        raise RegionExtractionError(f"intensity map must be 2-D, got shape {arr.shape}")
    if arr.size == 0:
        raise RegionExtractionError("intensity map must not be empty")
    if not np.issubdtype(arr.dtype, np.integer):
        raise RegionExtractionError(f"intensity map must have an integer dtype, got {arr.dtype}")
    if not (2 <= levels <= 256):
        raise RegionExtractionError(f"levels must be in [2, 256], got {levels}")
    lo = int(arr.min())
    hi = int(arr.max())
    if lo < 0 or hi >= levels:
        raise RegionExtractionError(
            f"intensity map values must lie in [0, {levels}); observed [{lo}, {hi}]"
        )
    return arr


def module_info() -> dict:
    return {
        "module": "visual_intensity_engine.objects.labeling",
        "version": "1.0.0",
        "input_schema": "quantized intensity map (int, values in [0, levels)) + vie.objects-config/1",
        "output_schema": "LabelMapResult (int32 labels, region candidates, dropped counts)",
        "config_schema": "vie.objects-config/1",
        "error_behavior": "RegionExtractionError for malformed maps, unsupported connectivity, max_regions overflow",
        "logging_behavior": "silent",
        "performance_expectations": (
            "O(H·W) run-length labeling; extraction cost measured in EXP-0002 (no target claimed)"
        ),
        "test_coverage": "tests/unit/test_labeling.py, tests/unit/test_spec_example_phase2.py, tests/property/",
    }
