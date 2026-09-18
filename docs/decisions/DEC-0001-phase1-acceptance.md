# DEC-0001 — Phase 1 (basic prototype / intensity engine) ACCEPTED

This file is the stage decision record referenced by `docs/phase-1/phase1_report.md` §10
and by the append-only entry of the same id in [`decision_log.md`](decision_log.md).
The log entry remains the canonical text; this page exists so the stage-gate paperwork
resolves (an external audit, 2026-09-18, found this reference dangling).

- **Date:** 2026-09-17 · **Status:** Accepted · **Stage:** Phase 1 (MASTER_PLAN §33)
- **Depends on:** DEC-0000 / `VIE-SPEC-REP` 1.0.0 (frozen)
- **Evidence:** `docs/phase-1/phase1_report.md` (test log, EXP-0001 benchmark, acceptance table)

## Decision

Accept Phase 1. The acceptance criteria in MASTER_PLAN §33 were verified with recorded
evidence:

| Criterion | Verified by |
|---|---|
| Correct grayscale conversion | reference vectors (1e-12), RGB/BGR channel-order proof, three luma standards |
| Correct quantization at all supported levels | boundary rule at L∈{8,16,32,64,128,256} + off-grid {2,3,7}, monotonicity, error bound ≤ 1/(2L) |
| Stable repeated runs | byte-identical `intensity_maps.npz` replay + manifest equality modulo wall-clock |
| Invalid input handled explicitly | typed error hierarchy, fault-injection suite, corrupt/absent source tests |
| Measured latency and memory | EXP-0001 (`result.json` schema-validated + `report.md`), per-run `metrics.json` |
| Unit + integration tests pass | 170/170 at acceptance (`phase1_test_log.txt`) |

## Consequences

- The gate to **Phase 2 — Intensity Objects** is open, contingent on maintainer review and
  on a Phase-2 plan written against `VIE-SPEC-REP` §6 (coordinate system, binding from
  Phase 2 onward) and §8 (token/record extension policy). Phase 2 is **not** started.
- Known limitations carried forward are listed in `phase1_report.md` §9.
- Post-acceptance revision: see **DEC-0002** (2026-09-18) — audit-driven hardening that
  changed no representation semantics (golden hashes unchanged) and did not advance the
  stage.
