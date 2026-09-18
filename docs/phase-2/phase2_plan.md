# Phase 2 — Intensity Objects: stage plan

- Stage: **Phase 2** (MASTER_PLAN §33) · Depends on: DEC-0000 (`VIE-SPEC-REP` 1.0.0) and DEC-0001 (Phase 1 accepted)
- Governing documents: `docs/MASTER_PLAN.md` (unchanged), `docs/phase-2/representation_specification_1.1.0.md` (revision R1.1.0, additive)
- Status of this plan: **approved for execution** by DEC-0003; Phase 2 is accepted only by DEC-0004 **after** the evidence below exists

Rule in force (plan §1): no stage advances until it is fully specified, implemented, tested,
documented, and stable under its acceptance criteria. This document defines all twelve
stage-mandated elements before implementation code is written.

---

## 1. Objective

Implement and validate the smallest testable **intensity-object engine**: for each
quantized intensity map, partition the pixels into **intensity objects** — connected
components of equal intensity — and give every object deterministic identity, exact
geometry, and complete provenance, with the cost measured.

Scope discipline: no tracking (Phase 3), no motion/symbolic encoding (Phase 4), no learned
components (Phase 6). Identity here is *per-frame and positional only*; the plan (§3.19)
treats cross-frame identity as provisional and reserves it for Phase 3.

## 2. Inputs and outputs

| | Definition |
|---|---|
| Inputs | Phase-1 `IntensityMap` (uint8 ids, L ∈ {2..256}) + `vie.objects-config/1` (connectivity, `min_area`, `max_regions`, implementation) |
| Outputs | per-frame `ObjectFrame` (int32 label map + region records + counters); bundle `region_labels.npz + regions.json + manifest.json + checksums.json` (`vie-objectstore/1`); metrics; deterministic overlay previews |
| Side outputs | `objects_config.json` export, per-run `metrics.json`, `vie objects` CLI summary |

## 3. Formal data schemas (new; nothing frozen is modified)

- `schemas/intensity_object.schema.json` — `vie.intensity-object/1` (one region record)
- `schemas/region_set.schema.json` — `vie.region-set/1` (all regions of all frames)
- `schemas/objects_config.schema.json` — `vie.objects-config/1`
- `schemas/objectstore_manifest.schema.json` — `vie.objectstore-manifest/1`
- `schemas/object_benchmark_result.schema.json` — `vie.object-benchmark-result/1` (EXP-0002)

Phase-1 artifacts (`vie.pipeline-config/1`, `vie.vocabulary/1`, `vie.framestore-manifest/1`,
`vie.benchmark-result/1`) and `VIE-SPEC-REP` 1.0.0 semantics are byte-frozen; existing
stores stay readable and unchanged.

## 4. Unit tests

Labeling on hand-built arrays (single pixel; two blobs; diagonal touching → separate under
4-connectivity; full-constant frame; checkerboard singletons; nested ring/hole; L=2 and
L=256 extremes), deterministic ID assignment and raster discovery order, `min_area` and
`max_regions` behavior, object-config validation and canonical hashing, region record
construction (area/bbox/centroid/fingerprint), fast-validator ↔ JSON-Schema parity.

## 5. Integration tests

End-to-end `vie objects` on synthetic scenes with **known component structure** (e.g.
`static` = one 24×24 square on background ⇒ exactly 2 objects per frame for L=16),
round-trip exactness (labels and regions reload equal), byte-identical replay of the whole
object store, CLI behavior, `vie validate` on both store kinds, `vie self-test` object
invariants.

## 6. Edge-case tests

1×1 frames; frames where every pixel is one object; frames where every pixel is its own
object (checkerboard); empty/zero-region frames cannot occur (every pixel belongs to some
component — asserted instead via `dropped_pixels == H·W` under `min_area`); `min_area`
larger than the frame; `max_regions` exceeded → typed `RegionExtractionError`; variable
frame sizes in one store; L=2 and L=256; region touching all four borders.

## 7. Performance measurements

EXP-0002: extraction latency (p50/p95) and memory across {320×240, 640×480, 1920×1080} ×
L ∈ {8, 16, 64, 256} × scenes {gradient, moving_square, ramp_bands, static}, plus an
adversarial noise scene (L=256, `noise_px` high) to expose the run-count worst case.
Recorded representation sizes: intensity map bytes vs label-map bytes vs region-metadata
bytes vs raw RGB bytes (metadata overhead is part of the cost, plan §25).

## 8. Reproducibility metadata

Store manifest carries: pipeline config + `config_sha256`, objects config +
`objects_config_sha256`, vocabulary, input description, provenance block (git commit + dirty
flag, library versions, platform, UTC, seed, duration), per-frame rows, counters. Determinism
contract: identical input + config + library versions ⇒ byte-identical
`region_labels.npz`, `regions.json`, and manifest modulo wall-clock fields (verified by
tests, including a golden hash).

## 9. Visualization / inspection

Deterministic object-overlay panel (region colors from the existing vocabulary palette, bbox
outlines, centroids, ids for regions ≥ a size threshold, counters in the caption) written by
`--previews N`; a machine-readable `regions.json` for external inspection.

## 10. Acceptance criteria (MASTER_PLAN §33 Phase 2)

| Criterion | Pass condition |
|---|---|
| Correct on synthetic components | exact region count/areas/bboxes/levels on scenes with known geometry, L ∈ {8,16,64,256}; diagonal-touch and hole cases correct per the specified connectivity |
| Noise / empty-frame behavior | sub-`min_area` components are always counted (`dropped_regions`, `dropped_pixels`), never silently dropped; `max_regions` is enforced with a typed error; a fully uniform frame yields exactly one region |
| Stable metadata | identical bytes for replayed runs; JSON floats round-trip exactly; fingerprint recomputation from the record matches |
| Deterministic region IDs | IDs are assigned in raster order of each object's first pixel; re-running extraction on the same map yields identical IDs; ID contiguity `0..n−1` asserted |
| Measured cost | EXP-0002 recorded (schema-validated `result.json` + `report.md`), including metadata overhead and the adversarial case |

## 11. Known limitations (expected)

1. 4-connectivity only in v1.1.0; `connectivity: 8` is an explicit extension point that
   fails validation (no silent acceptance).
2. Per-level components: an object never spans two intensity levels (by definition, so a
   gradual-intensity object fragments at level boundaries — relevant to Q1/Q3).
3. No temporal identity: IDs are per-frame; cross-frame correspondence is Phase 3.
4. Reference implementation only (pure numpy); optimization is Phase 8 after profiling.
5. Overlay previews are exploratory, never benchmark output (plan §21).

## 12. Decision plan

- **DEC-0003**: accept `VIE-SPEC-REP` 1.1.0 + this plan (specification gate).
- **DEC-0004**: accept/reject Phase 2 on the §10 evidence (implementation gate).
Any change to the region representation after data exists requires a new spec revision plus
migration notes — never an in-place edit.
