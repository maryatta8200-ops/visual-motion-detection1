# Phase 2 report — Intensity objects

- Stage: Phase 2 (**Intensity Objects**), plan §33 / [`phase2_plan.md`](phase2_plan.md)
- Specification: [`VIE-SPEC-REP 1.1.1`](representation_specification_1.1.1.md) (current; 1.1.0 plus editorial clarifications, DEC-0005 — no semantic change)
- Gates: DEC-0003 (spec + plan accepted) → this report → DEC-0004 (acceptance)
- Code: commits `1ef690f` (implementation) and `a86b70a` (EXP-0002 runner correction); implementation recorded in
  `experiments/EXP-0002-object-extraction/result.json` as `code_commit = a86b70a`
- Evidence: full test suite, `vie self-test`, EXP-0002 (`result.json` + `report.md`)

## 1. What was built

| Component | Path | Contract |
|---|---|---|
| Objects config | `visual_intensity_engine/objects/objects_config.py` | `vie.objects-config/1`; `connectivity: 8` fails by design; `min_area ≥ 1`; `max_regions` null/int ≥ 1; `implementation ∈ {reference}` |
| Labeling core | `visual_intensity_engine/objects/labeling.py` | level-uniform **4-connected** regions; vectorized run-length + union-find (production) and a per-pixel flood fill (test oracle); O(H·W) run discovery |
| Extraction | `visual_intensity_engine/objects/extraction.py` | `vie.intensity-object/1` records: id, level+symbol, area, half-open bbox, float64 centroid, content fingerprint (`sha256` of canonical JSON of `{area,bbox,centroid,level}`) |
| Object store | `visual_intensity_engine/objects/store.py` | `vie-objectstore/1`: streamed `region_labels.npz` (int32) + `regions.json` + `manifest.json` + `checksums.json` + `objects_config.json` + `metrics.json`; fast structural validator + invariants; reader verifies checksums, schemas, cross-artifact consistency |
| Pipeline | `visual_intensity_engine/objects/pipeline.py` | source → grayscale → quantization → extraction → object store, with the `Σ areas + dropped_pixels = H·W` invariant asserted per frame |
| CLI | `visual_intensity_engine/cli.py` | `vie objects …` batch mode; `vie validate` auto-detects object stores; `vie self-test` now checks Phase 2 (replay bytes, invariants, counted discards) |
| Visualization | `visual_intensity_engine/visualization/render.py` | deterministic `render_object_overlay` (boundaries, counted dropped pixels, largest-object labels) |
| Schemas | `visual_intensity_engine/schemas/*.json` (repo-root `schemas/` = symlinks) | `vie.intensity-object/1`, `vie.region-set/1`, `vie.objects-config/1`, `vie.objectstore-manifest/1`, `vie.object-benchmark-result/1` |
| Benchmark | `visual_intensity_engine/benchmarking/objects_runner.py` | EXP-0002 cost measurement |

Frozen Phase-1 behavior is untouched: 1.0.0 semantics, `vie-framestore/1` layout, and the
golden store hash `bfcd8492…` still pass unchanged (the label map is int32, but tokens and
intensity maps are unchanged; no token gained a `region_id` field — that remains `vie.token/2` work).

## 2. Test evidence (this machine, Python 3.11.2, numpy 2.4.6)

| Gate | Result |
|---|---|
| `pytest` (full suite) | **314 passed** in 13.4 s (was 215) — +99 Phase-2 tests |
| `ruff check .` | clean (E,F,W,I,UP,B,C4,SIM @ 120 cols) |
| `mypy` | clean, 33 source files |
| `vie self-test --levels 16` | **PASS** (`phase1+phase2`): ramp coverage, replay byte-equality, object replay byte-equality, per-frame invariants, `min_area` discards counted |
| Wheel install | schemas ship as package data (9 JSON Schemas in the wheel); `vie validate` works from an installed wheel without a checkout |

The §R9 normative worked example is executable
(`tests/unit/test_spec_example_phase2.py`): region ids, areas, half-open bboxes, exact float64
centroids, label maps, drop accounting and fingerprint derivation are asserted as printed in
the spec. The production labeler is checked **label-for-label** against the independent
flood-fill oracle on generated corpora (`tests/unit/test_labeling.py`,
`tests/property/test_properties.py`), and the fast structural validator is checked against
the normative JSON Schema on a mutation corpus so the two accept/reject identically
(`tests/unit/test_object_store.py`).

## 3. Acceptance criteria (plan §10)

| Criterion | Pass condition | Status | Evidence |
|---|---|---|---|
| Correct on synthetic components | exact region count/areas/bboxes/levels on known-geometry scenes, L ∈ {8,16,64,256}; diagonal-touch and hole cases correct for the specified connectivity | **Met** | §R9 executable example; `test_labeling.py` (diagonal-touch ⇒ four separate objects under 4-connectivity); oracle parity on 250+ generated maps × 4 `min_area` values |
| Noise / empty-frame behavior | drops always counted; `max_regions` enforced with a typed error; fully uniform frame ⇒ exactly one region | **Met** | `test_labeling.py` (`dropped_regions`/`dropped_pixels`; `RegionExtractionError` never truncates), `test_edge_cases.py` (1×1 frame, all-pixels-dropped, zero-region store), `test_objects_pipeline.py` (aborted run writes no valid store) |
| Stable metadata | identical bytes on replay; JSON floats round-trip; fingerprint recomputable from the record | **Met** | `test_object_store.py::test_store_is_replay_identical_ignoring_provenance_timestamps`, `test_objects_pipeline.py::test_objects_pipeline_replay_is_byte_identical`, `vie self-test`; fingerprint recomputation asserted in `test_spec_example_phase2.py` |
| Deterministic region IDs | raster discovery order; identical ids on re-extraction; contiguity asserted | **Met** | `test_labeling.py` (discovery order, contiguity after drops, repeated runs identical, C/F order agreement); `test_object_store.py` (reader rejects non-contiguous ids) |
| Measured cost | EXP-0002 recorded (schema-validated `result.json` + `report.md`), including metadata overhead and the adversarial case | **Met** | [`experiments/EXP-0002-object-extraction/`](../../experiments/EXP-0002-object-extraction/) — 51 conditions |

## 4. EXP-0002 headline numbers (reference implementation, untraced latency)

Main matrix (3 sizes × 4 scenes × 4 level counts): per-frame extraction p50.

| Size | p50 range | Median | Peak allocation | Label map | Worst metadata/raw |
|---|---:|---:|---:|---:|---:|
| 320×240 | 3.4–63.0 ms | 4.4 ms | ≤ 10 MB | 4 bytes/px | 0.32× |
| 640×480 | 14.0–264.2 ms | 17.2 ms | ≤ 40 MB | 4 bytes/px | 0.16× |
| 1920×1080 | 105.6–2334.7 ms | 135.2 ms | ≤ 270 MB | 4 bytes/px | 0.074× |

Slowest condition: `ramp_bands L=256 @1920×1080` = **2.33 s/frame** (1920 runs per row —
one-pixel-wide vertical stripes — where the union step, not image size, dominates).
Fastest: `static L=16 @320×240` = 3.4 ms. Zero-cost identity: ids come from the raster scan,
so determinism adds no measured overhead beyond the label map itself.

Adversarial block (dense per-pixel noise, L=256 — the run-count worst case):

| Size | `min_area` | regions/frame | p50 | region metadata/frame | metadata ÷ raw RGB | peak |
|---|---:|---:|---:|---:|---:|---:|
| 320×240 | 1 | 56 802 | 0.60 s | 13.3 MB | **57.9×** | 37 MB |
| 640×480 | 1 | 227 660 | 2.36 s | 53.9 MB | **58.5×** | 160 MB |
| 1920×1080 | 2 | 124 787 kept (2.07M candidates) | 1.71 s | 30.6 MB | 4.9× | 204 MB |

Reading: for structured scenes the cost is close to the label-map write itself
(≈ 4 bytes/pixel) and metadata is negligible; for per-pixel noise the **region records
dominate by ~60× the raw frame**, and `min_area` is the designed lever (discards are
counted, never silent). One attempt to measure the fully dense 1920×1080 case at
`min_area = 1` (~2.07 M records) exceeded this machine's 3 GB memory and was killed; that
condition is recorded as **not measured** in the experiment report rather than estimated.

Method note: latencies are measured with `tracemalloc` **inactive** and memory in a separate
untimed pass, because tracing inflates this allocation-heavy reference by 1.36× (structured
640×480) to 16× (one-pixel-wide runs at 1920×1080) — measured, and recorded in the experiment
notes.

## 5. Deviations, limits and open items

- **Performance is deliberately un-optimized** (plan §3.14/§8). The run-heavy case above is
  the clearest target for the profiling phase; nothing here claims a rate or a bound.
- **Research-question framing**: Phase 2 builds the representation H2 needs; it does not
  test H1 or H2 (no accuracy claim is made anywhere in this report).
- **Cross-frame identity is out of scope** (Phase 3). `fingerprint` is a content signature
  only; the spec says so in §R3.4 and the report repeats it so it cannot be misread.
- **Memory envelope on this machine** (3 GB) bounds the measured adversarial envelope; the
  unmeasured dense-1080p cell is stated as such.
- **No `vie.token/2`**, no change to tokens, no change to `docs/MASTER_PLAN.md` or the
  hypothesis registry, no golden regeneration.
- The upstream design question "objects per frame vs. objects per video" is deliberately not
  answered: Phase 2 defines per-frame objects only, with ids that are positional.

## 6. Decision

`visual_intensity_engine/__init__.py` now reports `STAGE = "phase2"` and the package
description follows (the live viewer's own status marker is unchanged — it remains
exploratory-only). DEC-0004 (append-only entry in `docs/decisions/decision_log.md`) accepts
Phase 2 on this evidence:
all five acceptance criteria met, all gates green, costs measured including the adversarial
case and the metadata overhead, and the remaining gaps recorded explicitly rather than
smoothed over.
