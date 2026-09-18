# VIE-SPEC-REP 1.1.1 — Intensity Objects (clarification of 1.1.0)

- Document version: **1.1.1** · Supersedes: `VIE-SPEC-REP` 1.1.0 **editorially only**
- Status: normative from Phase 2 onward (1.1.0 approved by DEC-0003; the 1.1.1 clarifications
  are adopted by DEC-0005)
- Base document: [`docs/phase-0/representation_specification.md`](../phase-0/representation_specification.md)
  (1.0.0). **Every rule of 1.0.0 remains binding and unchanged.** This revision only *adds*
  the intensity-object representation; nothing in 1.0.0 is redefined, and no Phase-1 artifact
  changes meaning or bytes.
- **1.1.1 adds no semantics.** It makes explicit what an external Phase-2 design audit
  (2026-09-18) found implicit: grouping-policy scope (R2.4), boundary handling, holes and
  zero-kept frames (R3.5–R3.7, R6.5), config identity (R5.5), and complexity/measurement
  method (R11). The reference implementation, every stored byte, every schema id, the §R9
  worked example and all pre-existing tests are unchanged; new tests lock the clarified
  behavior. `docs/phase-2/representation_specification_1.1.0.md` is kept for provenance.

## R1. Changelog and migration

| Change | Kind | Migration |
|---|---|---|
| §6.5 regions: level-uniform 4-connected components | addition | none — new record family |
| §8.5 `vie.intensity-object/1`, `vie.region-set/1` | new schemas | none — new files |
| §9.8 `vie-objectstore/1` bundle (`region_labels.npz`, `regions.json`) | additional bundle format | Phase-1 stores unchanged and still readable |
| §10.5 `vie.objects-config/1` | new config schema | Phase-1 configs unchanged |
| §11 `RegionExtractionError` | new typed error | none |
| 1.1.1: R2.4, R3.5–R3.7, R5.5, R6.5, R11 (below) | editorial clarifications | none — no artifact changes |

Note on the 1.0.0 §8.2 extension policy: adding fields to *tokens* requires `vie.token/2`.
This revision does not touch tokens; it defines a **new aggregate record type** with its own
schema ids. Per-pixel `region_id` attached to tokens (the `vie.token/2` route) is *not* used
in Phase 2 and remains reserved.

## R2. Region (intensity object) — definition

1. **Object definition.** For a quantized map `M` (uint8 level ids, `H×W`) and a level
   `k ∈ [0, L)`, the *objects of level k* are the **4-connected components** (von Neumann
   neighbourhood: `(x±1, y)`, `(x, y±1)`) of the pixel set `{(x,y) : M[y,x] = k}`.
   An object therefore has exactly one intensity level — a region never spans two levels, and
   a gradual-intensity structure fragments at level boundaries (documented limitation).
2. **Connectivity is fixed at 4 in v1.1.0.** `connectivity: 8` is an explicit extension
   point: it MUST fail config validation (no silent acceptance) until a later revision
   specifies it (diagonal-connectivity merging rules interact with identity stability).
3. **Empty case.** A monotone frame cannot produce zero *candidates*: every pixel belongs
   to exactly one component of its own level. Candidates become zero kept objects only
   through an explicit filter (`min_area`), which is representable and counted (§R3.7).
   A frame itself cannot be empty: §2.4 of 1.0.0 forbids 0-sized frames (min 1×1 still
   yields 1 object).
4. **Grouping policy is a specification-level choice, not a run-time toggle.** v1.1.x is
   *exact-level* grouping (R2.1) and composite grouping is deliberately deferred: plan §9
   requires single-intensity regions to be stable first, and then requires the grouping
   policy to be "configurable and evaluated". That revision will introduce its own config
   schema (e.g. `vie.objects-config/2` with an explicit `grouping` field) rather than an
   unspecified flag here. Until then the policy is fixed by this document, is covered by
   `objects_config_sha256` (R5.5), and composite regions are neither produced nor silently
   approximated.

## R3. Geometry and metadata (extends 1.0.0 §6)

All coordinates follow 1.0.0 §6: integer `(x, y)` is the **center** of the pixel at column
`x`, row `y`; origin is the top-left pixel center; `x` grows right, `y` grows **down**.

For an object with pixel set `P`:

| Field | Definition |
|---|---|
| `level` | intensity id `k ∈ [0, L)`; `symbol` = `I<k>` (diagnostic convenience, derived) |
| `area` | `|P|`, integer ≥ 1 |
| `bbox` | half-open integer box `[x0, x1) × [y0, y1)`: `x0 = min x`, `x1 = max x + 1`, `y0 = min y`, `y1 = max y + 1` (matches the half-open pixel coverage of 1.0.0 §6.1; `width = x1−x0`, `height = y1−y0`) |
| `centroid` | arithmetic mean of pixel **centers**: `cx = (Σx)/area`, `cy = (Σy)/area`, float64. The centroid lies inside the bbox (asserted), not necessarily on a pixel of the object |
| `region_id` | integer assigned by §R4 |
| `frame_index` | 1.0.0 §7.1 frame index of the frame the object belongs to |
| `fingerprint` | SHA-256 (hex, lowercase) of the canonical JSON (1.0.0 §10.2 form) of `{"area": …, "bbox": [x0,y0,x1,y1], "centroid": [cx,cy], "level": …}`. Content signature only: it is **not** a cross-frame identity (plan §3.19 — tracking identity is Phase 3 and provisional) |

5. **Boundary handling.** Frame borders are not region boundaries and create no special
   cases: a region may touch or cover a border, its `bbox` always lies inside
   `[0, W] × [0, H]`, and no padding, reflection or edge trimming is applied. `max_regions`
   counts kept regions regardless of border contact.
6. **Holes.** A hole is any non-member pixel fully enclosed by a region. Holes are not a
   metadata field in v1.1.x: `area`, `bbox` and `centroid` describe the member set only, and
   `x1`/`y1` are the extremes of *members*, not of a convex hull. Because the label map
   (§R6) is a lossless membership map, hole topology is recoverable from the bundle; shape
   and topology fields are explicitly deferred (R10.6) and MUST NOT be assumed present.
   Enclosed pixels may belong to further objects (of other levels), which are extracted
   independently.
7. **Merge/split.** Within a single frame nothing merges or splits: regions are maximal
   connected sets by construction, and exceeding `max_regions` **fails the run** rather than
   merging, splitting or truncating regions (R5.2). Merge/split semantics exist only in
   temporal linkage (Phase 3, plan §10) and in a future composite-grouping revision (R2.4).

## R4. Region identity

1. **Discovery order** is raster order: rows top→bottom, columns left→right. Objects are
   discovered at their first pixel (lowest `y`, then lowest `x`).
2. **IDs are `0..n−1`** in discovery order, where `n` is the number of objects **kept** after
   the `min_area` filter (§R5). IDs are contiguous; the third object discovered has
   `region_id = 2` even if earlier candidates were dropped.
3. **Determinism.** With the same map, config, and library versions, IDs are identical across
   runs and platforms (no hashing, no randomness, no dictionary ordering). Because IDs are
   positional, a one-pixel change may renumber later objects — this is deliberate: Phase 2
   claims *reproducible* identity, not *robust* identity (that is Phase 3's problem, where
   cross-frame matching will define its own, explicitly provisional, identity).

## R5. Configuration: `vie.objects-config/1`

```json
{"schema": "vie.objects-config/1", "objects_config_version": "1.0.0",
 "connectivity": 4, "min_area": 1, "max_regions": null, "implementation": "reference"}
```

1. `min_area` (int ≥ 1): objects with `area < min_area` are **discarded, counted, and
   reported** — never silently removed. Discarded pixels get label `0` (§R6). Discarding is
   not an error: it is an explicit, documented filter, and `counts.dropped_regions` /
   `counts.dropped_pixels` are mandatory manifest fields.
2. `max_regions` (int ≥ 1 or `null`): `null` means unlimited. If the number of *kept* objects
   in any frame exceeds `max_regions`, extraction **fails** with `RegionExtractionError`
   (plan §3.10) — the run stops rather than emitting a truncated frame. The manifest records
   the limit in the config block for every store.
3. `implementation` ∈ {`reference`} in v1.1.0; other values MUST fail validation (1.0.0 §11).
4. Config identity is the SHA-256 of its canonical JSON (`objects_config_sha256`), exactly as
   in 1.0.0 §10.2.
5. **Config identity covers the whole policy.** Because (4) hashes the entire document,
   connectivity, grouping, `min_area`, `max_regions` and `implementation` are all part of
   every store's provenance: two stores can never share a config hash while differing in
   segmentation policy, and `connectivity: 8` (rejected by R2.2) can never appear in a
   recorded store. Per-region copies of the hash are not stored — the hash is per document,
   and every region is linked to its document by `frame_index` (R3).

## R6. Label map

1. `region_labels.npz` entries are **int32**, C-contiguous, shape `(H, W)`, key `f%06d`
   matching the frame's `npz_key` (1.0.0 §9.2).
2. `labels[y, x] = region_id + 1` for pixels of kept objects; `labels[y, x] = 0` for pixels of
   discarded (sub-`min_area`) objects. **`0` never denotes a kept object**, so
   `region_id = label − 1` is total on kept pixels.
3. Every pixel of the frame is covered: `Σ areas(kept) + dropped_pixels = H·W` (invariant,
   asserted by tests and by `vie self-test`).
4. Label maps are losslessly round-trippable; they are a derived artifact of
   (`intensity map`, objects config) and MUST NOT be treated as an independent source of
   truth (§2 of 1.0.0: the raw frame remains the ground truth).
5. **Frames with zero kept regions are representable and valid.** If every candidate is
   discarded (all areas < `min_area`), the frame is written with an all-zero label map,
   `region_count = 0`, `dropped_regions > 0` and `dropped_pixels = H·W`. Zero means
   "no regions" — never `null`, never an error. Failure is distinguishable and
   non-representable: a typed error aborts the run and no valid store is written (R8.3).

## R7. Determinism and serialization (`vie-objectstore/1`)

Bundle layout:

```
<outdir>/
├── region_labels.npz      # int32 label maps, keys f%06d (streamed, fixed ZIP attrs)
├── regions.json           # vie.region-set/1 — frame-major object list
├── manifest.json          # vie.objectstore-manifest/1
├── checksums.json         # sha256 of the three artifacts above
├── objects_config.json    # config export (human-readable)
└── metrics.json           # per-run measurements (not checksummed; reporting only)
```

1. **Byte determinism** follows 1.0.0 §9.3 with the same writer rules (sorted keys, fixed ZIP
   date `1980-01-01 00:00:00`, zlib level 6). `regions.json` is written with sorted keys and
   compact separators; float values use CPython's shortest round-trip repr, so identical
   float64 values serialize identically.
2. **Integrity:** `checksums.json` covers `region_labels.npz`, `regions.json`, and
   `manifest.json`; readers verify before use (1.0.0 §9.6 applied to this bundle).
3. **Replay rule** (1.0.0 §9.7 applied): two runs are replay-identical iff `region_labels.npz`
   and `regions.json` are byte-identical and manifests are equal ignoring
   `provenance.created_at_utc` and `provenance.duration_s`.
4. **Manifest** (`vie.objectstore-manifest/1`) records: pipeline config + `config_sha256`
   (the Phase-1 config used to produce the maps), objects config + `objects_config_sha256`,
   vocabulary, input description, provenance, per-frame rows
   (`region_count`, `dropped_regions`, `dropped_pixels`, `label_dtype`, `npz_key`,
   `frame_index`, `source_frame_id`, `timestamp_us`, `wall_time_utc`, `height`, `width`),
   aggregate counts, and `npz_key_format`.

## R8. Validation policy (extends 1.0.0 §11)

1. The JSON Schemas named in §R7 are **normative**. `vie validate` and every reader validate
   in full against them.
2. The writer additionally runs a **fast structural validator** with the same constraints
   (keys, types, ranges, contiguity of ids, `Σ areas + dropped_pixels = H·W`), so that
   writing does not pay a JSON-Schema cost proportional to the object count. Parity between
   the fast validator and the schemas is itself a test obligation (generated corpora and
   mutations must be accepted/rejected identically).
3. New typed error: **`RegionExtractionError`** — raised when extraction cannot honour the
   configuration (`max_regions` exceeded, inconsistent region set, label/map size mismatch).
   All other error rules of 1.0.0 §11 are unchanged.

## R9. Worked example (normative)

Let `L = 4`, frame 5×4 (`W = 5`, `H = 4`), intensity ids:

```
row 0:  0 0 1 1 1
row 1:  0 2 2 1 1
row 2:  3 2 2 1 1
row 3:  3 3 3 3 3
```

With `min_area = 1`, the objects (discovery order = id order) are:

| id | level | area | bbox `[x0,y0,x1,y1)` | centroid `(cx, cy)` | pixels |
|---|---|---|---|---|---|
| 0 | 0 | 3 | `[0,0,2,2)` | `(0.3333333333333333, 0.3333333333333333)` | (0,0),(1,0),(0,1) |
| 1 | 1 | 7 | `[2,0,5,3)` | `(3.2857142857142856, 0.8571428571428571)` | (2,0),(3,0),(4,0),(3,1),(4,1),(3,2),(4,2) |
| 2 | 2 | 4 | `[1,1,3,3)` | `(1.5, 1.5)` | (1,1),(2,1),(1,2),(2,2) |
| 3 | 3 | 6 | `[0,2,5,4)` | `(1.6666666666666667, 2.8333333333333335)` | (0,2),(0,3),(1,3),(2,3),(3,3),(4,3) |

Label map (`region_id + 1`):

```
1 1 2 2 2
1 3 3 2 2
4 3 3 2 2
4 4 4 4 4
```

Same map with `min_area = 4`: object 0 (area 3 < 4) is discarded →
`dropped_regions = 1`, `dropped_pixels = 3`; ids become `0` (level 1), `1` (level 2),
`2` (level 3); label map:

```
0 0 1 1 1
0 2 2 1 1
3 2 2 1 1
3 3 3 3 3
```

This example is executable: `tests/unit/test_spec_example_phase2.py` asserts exactly these
numbers (including fingerprints computed by the reference implementation), so the normative
example cannot drift from the code without failing the suite.

## R10. Known limitations of 1.1.x

1. 4-connectivity only; 8-connectivity is reserved (R2.2).
2. Level-uniform objects fragment gradual-intensity structures at level boundaries.
3. IDs are reproducible but positional (R4.3); no cross-frame identity (Phase 3).
4. Single reference implementation; no optimized variant yet (Phase 8).
5. Region records carry first-order statistics only (area, bbox, centroid); moments,
   shape descriptors, and local gradients belong to later revisions.
6. Holes and shape/topology are not described by metadata; they are recoverable only from
   the label map (R3.6).

## R11. Computational complexity and measurement method

1. **Complexity.** Run discovery is one pass per row, `O(H·W)`; union-find is near-linear in
   the number of runs (path compression + union by rank); record construction is `O(R)` with
   a fixed-size SHA-256 per region, `R` = kept regions. Measured cost therefore tracks frame
   size *and* region count — run-heavy scenes (one-pixel-wide runs) dominate at any
   resolution, and many tiny kept regions make record construction the larger term
   (measured: 70% of extraction at 227,660 kept regions; 11% at 877). No optimization is
   claimed: this is the Phase-8 baseline (plan §3.14/§8).
2. **What a cost experiment must separate.** Frame size (resolution), region count (scene
   structure, noise, `min_area`) and configuration (connectivity, grouping, `min_area`,
   `max_regions`) are recorded per condition. Latency is reported **untraced**, with the
   memory peak taken in a separate untimed pass, because `tracemalloc` tracing inflates this
   code by 1.36×–16× (measured). The labeling/construction split is measured, not inferred.
3. **Comparability.** Phase-1 and Phase-2 timings are comparable only when measured with the
   same method; the experiment registry records the method per experiment, and a
   re-measured baseline supersedes an older method for incremental-cost arithmetic (see
   `experiments/registry.json` and `docs/phase-2/phase2_report.md`).
