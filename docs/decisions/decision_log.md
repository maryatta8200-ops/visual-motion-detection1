# Decision Records

Append-only log. Each decision: id, date, status, context, decision, consequences.
Superseding a decision requires a new entry referencing the old one — never edit
history (plan §3.7, §37).

---

## DEC-0000 — Phase 0 (formal representation specification) ACCEPTED

- Date: 2026-09-17 · Status: **Accepted** · Scope: `docs/phase-0/representation_specification.md` (`VIE-SPEC-REP` 1.0.0)
- Context: plan §33 gates all downstream implementation on a frozen formal spec with
  schemas, boundary cases, examples, and round-trip rules.
- Decision: freeze `VIE-SPEC-REP` 1.0.0 with four JSON Schemas
  (pipeline-config, intensity-vocabulary, framestore-manifest, benchmark-result) and the
  normative rules for input domain, luminance, quantization (`floor_right_open`),
  vocabulary semantics, coordinates, timestamps, serialization, and errors.
- Consequences: Phases ≥1 may reference the spec; any representational change requires a
  new spec version with migration notes. Verified by schema-validation tests and
  round-trip integration tests before any Phase 1 code was written.

## DEC-0001 — Phase 1 (basic prototype / intensity engine) ACCEPTED

- Date: 2026-09-17 · Status: **Accepted**
- Context: acceptance criteria in MASTER_PLAN §33 Phase 1; evidence in
  `docs/phase-1/phase1_report.md` (test log + EXP-0001 benchmark).
- Decision: accept Phase 1. Rationale: 170/170 tests pass across all mandated test
  layers; quantization verified at L∈{8,16,32,64,128,256} (+ off-grid 2,3,7); replay is
  byte-identical; invalid inputs fail explicitly with typed errors; latency/memory
  measured and schema-recorded; visualization tools delivered with exploratory/benchmark
  separation.
- Defects found and fixed during the stage (preserved per plan §40):
  - schema `$ref` resolution attempted network fetch (HTTP 404) → replaced with offline
    `referencing` registry keyed by schema `$id`;
  - `store.py` reader referenced an undefined `FrameInfo` import → fixed, covered by
    round-trip tests;
  - non-finite coercion counted samples per pixel inconsistently (9 vs 3 in test) →
    contract fixed to per-sample counting, test aligned;
  - CLI config overrides silently dropped when `--max-frames` absent → override logic
    made per-flag; unknown scene now raises `ConfigError` (typed) not raw `ValueError`;
  - benchmark result schema rejection (`_config_sha256` leakage) → removed field.
  All fixes re-tested; full suite re-run green after each change.
- Consequences: gate opens for **Phase 2 — Intensity Objects** (connected components on
  the quantized map, region metadata, deterministic region IDs). Phase 2 must not begin
  until its plan exists against `VIE-SPEC-REP` §6/§8 (coordinate system now binding).
- Known limitations carried forward: see phase1_report §9 (uniform-only quantization,
  float64 intermediate cost, camera timestamp semantics deferred).
