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

## DEC-0002 — Phase 1 revision R1: audit-driven hardening (no plan/stage change)

- Date: 2026-09-18 · Status: **Accepted** · Scope: engineering hygiene around the frozen
  `VIE-SPEC-REP` 1.0.0 and the accepted Phase 1 implementation
- Context: an external audit of `9e338fc` (verdict: research-grade engineering with an
  incomplete product shell) raised findings H1–H3, M1–M8, L1–L6. The controlling plan
  (`docs/MASTER_PLAN.md`) and the representation spec are unchanged; no representation
  semantics, schema versions, or golden hashes changed. Verification trail for every
  finding: `docs/reviews/2026-09-18-external-audit-response.md`.
- Decisions taken:
  1. **H1 network exposure** — `vie serve` now binds `127.0.0.1` by default; while
     loopback-bound it rejects non-localhost `Host` headers with 403 (DNS-rebinding
     defence, plan §41). Network exposure is an explicit opt-in (`--host 0.0.0.0`) with a
     startup WARNING and optional `--allowed-host NAME` for proxies/tunnels.
  2. **H2 missing CI** — `.github/workflows/ci.yml` runs the full test suite on Python
     3.11 (exact `requirements.txt` pins) and 3.12 (declared ranges), plus `vie self-test`,
     ruff, mypy, and a wheel-install smoke test that exercises the packaged schemas.
  3. **H3 name/scope mismatch** — README states the phase scope and explicitly says this is
     not a motion-detection or surveillance component.
  4. **M1** — `docs/decisions/DEC-0001-phase1-acceptance.md` added (the report's reference
     had no file behind it).
  5. **M3** — all `module_info()` performance strings replaced with EXP-0001 / measured
     values or explicit non-claims; enforced by `tests/unit/test_module_info.py`.
  6. **M4/M7** — `FrameStoreWriter` streams frames to the NPZ as they arrive (no unbounded
     RAM growth) and the bundle is written **once**: `close(duration_s=…)` finalizes
     provenance before manifest validation, so checksums always cover the final bytes.
     Byte-for-byte store output is unchanged (golden hash `bfcd8492…` still passes).
  7. **M5** — schemas moved into the package (`visual_intensity_engine/schemas/`, shipped as
     package data); repo-root `schemas/` are symlinks; `schemas_dir()` resolves
     env → package → checkout; `configs_dir()` added for shipped configs.
  8. **M6** — `CameraSource` emits cumulative monotonic media timestamps instead of a
     hard-coded `0` (VIE-SPEC-REP §7.2/§7.4 compliance).
  9. **M8** — the mandatory full-file provenance hash (spec §10.3) is announced (size at
     INFO, WARNING ≥ 512 MiB) instead of surprising the operator. A partial-hash mode would
     require a schema version increment (§8.2) and was deliberately not invented.
  10. **L1** — ruff + mypy configured and clean; `FrameObserver = callable` and
      `dict[str, "callable"]` replaced with real `Callable` types.
  11. **L3/L4** — viewer HTTP behavior covered by tests (routes, Host policy, query-param
      robustness, interaction log, MJPEG); `--log-path` makes the interaction-log location
      explicit; camera batch runs require `--max-frames`.
  12. **M2 (LICENSE)** and **L2 (SECURITY/CONTRIBUTING)** — see below; the license remains
      the maintainer's decision.
- Deliberately **not** done: any Phase 2 work (the stage gate stays closed until the
  maintainer accepts a Phase-2 plan), any change to `docs/MASTER_PLAN.md`, any schema
  version bump, any golden-hash regeneration, any performance optimization (plan §3.14).
- Consequences: Phase 1 is now covered by CI and lint/type gates; the audit's remaining
  product-level items (license, packaging polish) are tracked in the audit-response
  document. Test suite: **215 passed** (was 170; +4 module-contract, +30 host-policy,
  +10 viewer-HTTP, +1 camera CLI split), golden hashes unchanged.
