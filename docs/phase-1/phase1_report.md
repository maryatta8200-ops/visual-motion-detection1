# Phase 1 Stage Report — Basic Prototype (Intensity Engine)

- Stage: **Phase 1** (MASTER_PLAN §33) — depends on Phase 0 (`VIE-SPEC-REP` 1.0.0, frozen)
- Code version: 0.1.0 · Spec version: 1.0.0 · Report date: 2026-09-17
- Decision: **ACCEPTED** (see `docs/decisions/DEC-0001-phase1-acceptance.md`)

This report contains all twelve stage-mandated elements (plan §1): objective,
inputs/outputs, schema, unit/integration/edge tests, performance measurements,
reproducibility metadata, visualization, acceptance criteria, known limitations,
and the decision record reference.

---

## 1. Objective

Implement and validate the smallest testable version of the core representation:
**video/synthetic input → grayscale (normalized luminance) → configurable discrete
intensity quantization → traceable, deterministic frame store → visualization** —
with correct quantization at every supported level count, stable repeated runs,
explicit invalid-input handling, and measured latency/memory (plan §33 Phase 1).

Scope discipline: no segmentation, tracking, or learned components were built
(Phases 2–6 are gated on this stage's acceptance).

## 2. Inputs and outputs

| | Definition |
|---|---|
| Inputs | uint8/uint16/float32/float64 frames; ndim 2 (gray) or 3 (RGB, RGBA by policy); sources: synthetic scenes, video file (opencv), camera; config JSON (`vie.pipeline-config/1`) |
| Outputs | per-frame `IntensityMap` (uint8 ids + traceability + anomaly counters); bundle `intensity_maps.npz + manifest.json + checksums.json` (`vie-framestore/1`); metrics JSON; preview PNGs; palette legend |
| Side outputs | configuration export (`config.json` in every store), CLI self-test report |

## 3. Formal data schemas

- `schemas/pipeline_config.schema.json` (`vie.pipeline-config/1`)
- `schemas/intensity_vocabulary.schema.json` (`vie.vocabulary/1`)
- `schemas/framestore_manifest.schema.json` (`vie.framestore-manifest/1`)
- `schemas/benchmark_result.schema.json` (`vie.benchmark-result/1`)

All manifests and benchmark results are schema-validated **at write time and read time**
(module-boundary validation, plan §3.9). Config identity = SHA-256 of canonical JSON.

## 4. Test evidence

Full suite: **170 passed, 0 failed** (run: `.venv/bin/python -m pytest tests -v`,
see `docs/phase-1/phase1_test_log.txt` for the recorded run).

| Layer (plan §35) | Location | Count | Covers |
|---|---|---|---|
| Unit | `tests/unit/` | 77 | reference grayscale vectors (bt601/bt709/average), RGB-vs-BGR proof, uint16/float domains, NaN/Inf strict+coerce, alpha policies, quantization boundary rule at all L∈{8…256}, monotonicity, error bounds, vocabulary intervals/labels/compatibility, config schema rejections, determinism |
| Property | `tests/property/` | 27 | range/shape invariants on generated frames, boundary-crossing arithmetic, byte-deterministic NPZ, per-frame pipeline invariants across seeds |
| Integration | `tests/integration/` | 27 | full round-trip exactness, replay byte-equality, checksum tamper detection, vocabulary compatibility on read, CLI end-to-end incl. video file, levels matrix |
| Edge | `tests/edge/` | 15 | 1×1 frames, empty frames, L∈{2,3,7}, saturated/zero pixels, pure-channel level mappings, variable frame sizes in one store, timestamp anomaly detection |
| Fault injection | `tests/edge/test_fault_injection.py` | 7 | mid-stream decode failure, NaN mid-stream, non-frame objects, corrupt zip, checksum mismatch, missing bundle files, add-after-close |
| Regression | `tests/regression/` | 4 | golden hashes: reference vectors, quantized ramps, full store bytes (regenerate only via `scripts/update_goldens.py` + changelog entry) |
| Performance | `tests/performance/` | 3 | generous latency guards (see §5) |

Edge-case summary (all explicit, none silent): NaN/±Inf → `NonFinitePixelError` (strict)
or coerced+counted; out-of-range floats → error (strict) or clipped+counted; empty frames
rejected; alpha per policy; unsupported strategies/levels/scope/boundary → `ConfigError`
(never a silent fallback); corrupt store → `SerializationError`; missing/corrupt video →
`SourceError`; unknown scene → `ConfigError`.

## 5. Performance measurements

Recorded run EXP-0001 (this machine, 2026-09-17, p50 over 22 measured frames per
condition after 8 warm-up; full distributions in `experiments/EXP-0001-quantization-baseline/result.json`):

| Resolution | gray p50 | quantize p50 | end-to-end p50 | ≈fps (single core) |
|---|---:|---:|---:|---:|
| 320×240 | 2.2 ms | 0.16 ms | 2.4 ms | ~415 |
| 640×480 | 8.8 ms | 0.63 ms | 9.5 ms | ~105 |
| 1920×1080 | 76 ms | 7.5 ms | 84 ms | ~12 |

Findings (baseline facts, not claims of advantage):

1. **Quantization cost is independent of L** (uniform/floor is a multiply+floor+cast).
   Choosing the number of levels trades information retention, not speed — the
   information/computation trade-off (Q2) will be decided on information grounds.
2. The quantized map occupies **1/3 of raw RGB bytes** in memory; the float64
   luminance intermediate occupies **8/3** — its cost is part of the representation
   and is reported, never hidden (plan §25).
3. Grayscale conversion dominates cost (float64 conversion of the full frame).
   This is the first optimization target *if and when* Phase 8 profiling confirms it
   matters for research throughput. No optimization was performed now (plan §3.14).

## 6. Reproducibility metadata

- Determinism contract verified by tests: same input bytes + config + library versions
  → byte-identical `intensity_maps.npz` (fixed ZIP timestamps, sorted entries, zlib-6).
- Every store carries: config + `config_sha256`, vocabulary (self-describing levels/
  boundary/domain), input checksum (files), git commit + dirty flag, Python/numpy/
  Pillow/jsonschema versions, platform, UTC creation time, seed, per-frame anomaly counters.
- Environment pin: `requirements.txt` (numpy 2.4.6, Pillow 12.3.0, jsonschema 4.26.0,
  pytest 9.1.1, opencv-python-headless 5.0.0.93, Python 3.11.2). Recreate: `scripts/setup_env.sh`.
- Replay comparison rule (two runs identical iff npz bytes equal and manifests equal
  modulo `created_at_utc`/`duration_s`) is implemented in `vie self-test` and tested.

## 7. Visualization / inspection tools

- Batch preview panels (ORIGINAL | GRAYSCALE | QUANTIZED) with vocabulary footer —
  `--previews N`, deterministic bytes (tested).
- Palette legend charts (token ↔ color ↔ interval ↔ representative value), deterministic
  in `(levels, palette_seed)`.
- Live viewer (`vie serve`, port 8000): three MJPEG panels, legend, live metrics JSON,
  interactive levels/scene/fps changes **logged with UTC timestamps** to
  `logs/viewer_interactions.jsonl`; every page carries the
  "EXPLORATORY — NOT BENCHMARK OUTPUT" banner (plan §21). Requires a browser; batch mode
  is fully functional without it.
- Assets: `docs/phase-1/assets/*.png` (generated by `scripts/make_phase1_assets.py`).

## 8. Acceptance criteria — verification (plan §33 Phase 1)

| Criterion | Result | Evidence |
|---|---|---|
| Correct grayscale conversion | ✅ | reference vectors exact to 1e-12 (uint8/uint16/float); RGB-vs-BGR channel-order proof; bt601/bt709/average |
| Correct quantization at all supported levels | ✅ | boundary rule tested at L∈{8,16,32,64,128,256} + off-grid {2,3,7}; all levels reachable; max-error bound ≤ 1/(2L); monotonicity |
| Stable output on repeated runs | ✅ | replay byte-equality tests (npz + manifest modulo wall-clock) |
| Valid handling of invalid input | ✅ | typed errors everywhere; fault-injection suite; corrupt video/camera absence fail gracefully with `SourceError` |
| Measured latency and memory | ✅ | EXP-0001 (schema-validated result.json + report.md); per-run metrics.json in every store |
| Passing unit and integration tests | ✅ | 170/170 (log recorded) |

Batch mode + deterministic replay + synthetic test mode: ✅ (`vie process`, `vie self-test`).
Prototype acceptance gate ("processes controlled test videos correctly, stable across
repeated runs"): ✅ — synthetic scenes and a real mp4 round-trip both pass with stable bytes.

## 9. Known limitations

1. Uniform quantization only; histogram/adaptive/learned are named extension points that
   fail loudly if requested (by design, plan §3.10).
2. float64 luminance intermediate is memory-heavy (8/3 × raw). Documented; Phase 8 concern.
3. Chroma discarded by design — irrecoverable information loss, relevant to Q1 (recorded
   in spec §14.4).
4. Camera timestamps: media time set to 0 with wall-time provenance; proper monotonic
   clock capture deferred to Phase 3 (temporal tracking needs it and will define it).
5. Live viewer is single-threaded per stream and exploratory only; it is not part of
   acceptance measurements (plan §21 boundary).
6. MP4 writing for dataset generation is Phase 5 work; current stores keep maps, not
   re-encodable video (raw frames remain at the source, per plan §2).

## 10. Decision record

**ACCEPTED** — all Phase 1 acceptance criteria verified with recorded evidence;
no critical or high-severity defects open (plan §35). Gate to Phase 2 (intensity
objects) is hereby unlocked, contingent on maintainer review of this report.
Details: `docs/decisions/DEC-0001-phase1-acceptance.md`.

---

## Addendum A — audit-driven revision R1 (2026-09-18)

The sections above remain the record of the **acceptance run at `9e338fc`** (170 tests,
16–17 Sep 2026) and are not rewritten. A post-acceptance external audit produced
`DEC-0002` (see `docs/decisions/decision_log.md` and
`docs/reviews/2026-09-18-external-audit-response.md`). Summary of what changed and what did
not:

- **Unchanged:** `docs/MASTER_PLAN.md`, `VIE-SPEC-REP` 1.0.0, all four JSON Schemas and
  their versions, the golden hashes (`tests/regression/golden/hashes.json`, store npz
  `bfcd8492…`), quantization/grayscale semantics, and the Phase-2 gate (still closed).
- **Changed (engineering hygiene, no representation change):** viewer binds loopback by
  default with Host-header validation and explicit exposure logging; store writer streams
  frames (bounded memory) and writes each bundle artifact once; schemas ship as package data
  (repo-root `schemas/` are symlinks); camera media timestamps are monotonic cumulative µs;
  camera batch runs require `--max-frames`; every `module_info()` performance string is
  measured or explicitly disclaimed; CI + ruff + mypy gates added.
- **Test suite after R1:** **215 passed** — unit 132, integration 36, edge 20, property 19,
  regression 5, performance 3 (`.venv/bin/python -m pytest tests -q`, 2026-09-18).
- **Known limitations §9 status:** (2) float64 luminance cost unchanged and still a Phase 8
  concern; (4) camera timestamps **resolved** in R1; (5) viewer now has automated HTTP
  coverage but remains exploratory and excluded from benchmark output; others unchanged.
