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

## DEC-0003 — Accept VIE-SPEC-REP 1.1.0 (intensity objects) and the Phase-2 plan

- Date: 2026-09-18. Type: stage gate (specification + plan). Status: **accepted**.
- Inputs: [`docs/phase-2/representation_specification_1.1.0.md`](../phase-2/representation_specification_1.1.0.md),
  [`docs/phase-2/phase2_plan.md`](../phase-2/phase2_plan.md), MASTER_PLAN §33 (stage
  structure), VIE-SPEC-REP 1.0.0 (frozen), DEC-0002 (Phase 1 acceptance).
- Decision — adopt 1.1.0 **additively**; 1.0.0 semantics, stores and golden hashes are
  unchanged. The revision fixes, before any code was written:
  1. an intensity object is a **level-uniform 4-connected (von Neumann) region**; the
     partition is the maximal-component partition — connectivity 8 is an extension point
     that MUST fail validation until a later revision defines it (§R2);
  2. region ids are **positional**: raster discovery order, contiguous `0..n−1` over kept
     regions; renumbering after a change is deliberate (§R4);
  3. geometry is exact: bbox is half-open `[x0,y0,x1,y1)`, centroid is the float64 mean of
     pixel centres, `fingerprint` is a **content signature** (sha256 of canonical JSON) and
     explicitly *not* a cross-frame identity (§R3);
  4. `min_area` discards sub-threshold regions **with counting** (`dropped_regions`,
     `dropped_pixels`); label 0 marks discarded pixels; every pixel is covered
     (`Σ areas + dropped_pixels = H·W`); `max_regions` fails the run instead of truncating
     (§R5, §R6);
  5. the `vie-objectstore/1` bundle, its byte-determinism rules, its replay rule and the
     fast-validator ↔ JSON-Schema parity obligation are normative (§R7, §R8);
  6. §R9 is a normative worked example and is executable
     (`tests/unit/test_spec_example_phase2.py`).
- Explicitly out of scope: cross-frame tracking/identity (Phase 3), motion (Phase 3+),
  optimization (plan §3.14/§8), token schema changes (`vie.token/2` is future work and no
  per-pixel `region_id` field was added to tokens).
- Untouched: `docs/MASTER_PLAN.md`, `docs/hypotheses/registry.md`, 1.0.0 documents,
  `configs/`, `experiments/EXP-0001/`.
- Follow-up gate: **DEC-0004** accepts or rejects Phase 2 on evidence (full test suite,
  ruff/mypy, `vie self-test`, EXP-0002 measured cost, plan §10 acceptance table).

## DEC-0004 — Accept Phase 2 (intensity objects) on evidence

- Date: 2026-09-18. Type: stage acceptance (implementation + evidence). Status: **accepted**.
- Inputs: [`docs/phase-2/phase2_report.md`](../phase-2/phase2_report.md),
  [`experiments/EXP-0002-object-extraction/`](../../experiments/EXP-0002-object-extraction/)
  (`result.json` schema-validated against `vie.object-benchmark-result/1` + `report.md`),
  full test suite, `vie self-test`, CI.
- Evidence at acceptance:
  1. **correctness** — the §R9 normative example is executable and passes exactly; the
     production labeler matches an independent flood-fill oracle label-for-label on generated
     corpora (250+ maps × 4 `min_area` values) and the fast validator matches the normative
     JSON Schema on a mutation corpus;
  2. **drops are counted, never silent** — `dropped_regions`/`dropped_pixels` are mandatory
     manifest fields and are asserted by tests and by `vie self-test`; `max_regions` raises
     `RegionExtractionError` and an aborted run leaves no valid store;
  3. **determinism** — replay produces byte-identical `region_labels.npz` and `regions.json`
     and manifests equal modulo `created_at_utc`/`duration_s`; ids are positional and
     contiguous `0..n−1`;
  4. **measured cost** — 51 EXP-0002 conditions: structured 1080p p50 106–148 ms; main-matrix
     worst case 2.33 s/frame (one-pixel-wide run patterns); dense-noise metadata up to ~58×
     the raw frame, with `min_area` as the lever; peak allocations 10/40/270 MB for
     320×240/640×480/1920×1080; latencies measured untraced (tracing inflates 1.36×–16×);
  5. **gates** — 314 tests pass, ruff/mypy clean, `vie self-test` PASS, wheel-installed
     schemas validate stores without a checkout.
- Accepted limitations, stated rather than smoothed over: the reference implementation is
  deliberately un-optimized (plan §3.14/§8); memory bounds the measured adversarial envelope
  on this 3 GB machine (dense 1080p at `min_area=1` is recorded as **not measured**); entity
  identity across frames remains Phase 3 and `fingerprint` is documented as a content
  signature only; tokens and Phase-1 artifacts are untouched (golden `bfcd8492…` unchanged).
- Untouched: `docs/MASTER_PLAN.md`, `docs/hypotheses/registry.md`, VIE-SPEC-REP 1.0.0,
  `configs/`, `experiments/EXP-0001/`.
- Next stage (not started, requires its own gate): Phase 3 — temporal linkage / motion, which
  must define cross-frame identity explicitly and provisionally (plan §3.19).

## DEC-0005 — Phase-2 contract clarifications (1.1.1) and three audit-triggered measurements

- Date: 2026-09-18. Type: specification clarification + evidence. Status: **accepted**.
- Context: an external Phase-2 design/readiness audit (CONDITIONAL PASS; dispositions in
  [`docs/reviews/2026-09-18-phase2-audit-response.md`](../reviews/2026-09-18-phase2-audit-response.md))
  asked for six items to be frozen before implementation. They were frozen by DEC-0003 and
  implemented before the audit arrived; this decision records the clarifications the audit
  legitimately surfaced and the measurements it triggered.
- Decisions:
  1. **VIE-SPEC-REP 1.1.1 adopted as the Phase-2 contract** — editorial clarifications only:
     grouping-policy scope (R2.4), boundary handling / holes / merge-split (R3.5–R3.7),
     zero-kept frames (R6.5), config identity (R5.5), complexity and measurement method (R11).
     No semantic change, no artifact bytes change, every schema id and the §R9 example
     unchanged; `representation_specification_1.1.0.md` is retained for provenance.
  2. **Extension points are deferred explicitly, never silently absent:** 8-connectivity
     (R2.2), composite multi-intensity grouping (plan §9 sequencing; future
     `vie.objects-config/2` with an explicit `grouping` field), shape/topology fields
     (R10.6), and hole descriptors. Each requires its own revision and decision.
  3. **Measurement method:** latency is reported untraced everywhere; memory peaks come from
     a separate untimed pass. EXP-0001 timed with `tracemalloc` active, so it is superseded
     *for arithmetic* by EXP-0003 (same 18 conditions, untraced) — EXP-0001's artifacts stay
     as recorded and the registry records both methods.
  4. **EXP-0004** (min_area 1/2/4/8/16 on dense noise) and **EXP-0005** (labeling vs record
     construction) are recorded; `min_area` is documented as both noise policy and cost
     lever, with discards always counted.
  5. **The only schema change is additive-optional**: `labeling_ns` / `records_ns` in
     `vie.object-benchmark-result/1`; no schema id or version changed and existing documents
     remain valid.
- Untouched: `docs/MASTER_PLAN.md`, `docs/hypotheses/registry.md`, VIE-SPEC-REP 1.0.0,
  `configs/`, golden hashes, EXP-0001 artifacts.

## DEC-0006 — Execution-audit fixes (AUD-01…AUD-11), viewer CSRF rule, proprietary LICENSE

- Date: 2026-09-18 · Status: **Accepted** (scope: engineering hygiene — no representation,
  schema, vocabulary, or golden-hash change) · Evidence:
  [`docs/reviews/2026-09-18-execution-audit-response.md`](../reviews/2026-09-18-execution-audit-response.md)
- Context: an independent execution audit of commit `6be667d` (report filed on the still-open
  PR #3, `arena/01a0b3da-…`, **not merged**) returned **PARTIAL** with no critical blocker and
  eleven required fixes: CLI numeric-argument validation gaps (HIGH), unchecked `camera:`
  index (MEDIUM), benchmark overwrite policy (MEDIUM), viewer state changes on unauthenticated
  GET (MEDIUM), missing LICENSE (MEDIUM), dead code / no-op `except` / missing `finally`,
  the objects benchmark reachable only via `python -m`, missing CLI-boundary tests, and a stale
  CI header. The maintainer directed that the fixes be implemented here while PR #3 stays
  unmerged.
- Decisions:
  1. **AUD-01/02 — validation happens at the CLI boundary.** Every numeric flag is parsed by a
     range-checking `argparse` type (`--levels` ∈ [2,256], `--min-area` ≥ 1, `--max-regions`
     ≥ 1, `--max-frames` ≥ 1, `--previews` ≥ 0, `--frames` ≥ 1, `--warmup` ≥ 0, `--port` ∈
     [0,65535]) so a bad value is a usage error (exit 2, no traceback); `camera:<index>` is
     parsed with a typed `ConfigError`; `--warmup ≥ --frames` is refused rather than measured.
     Exit-code contract: 0 success, 2 for every typed failure.
  2. **AUD-03 — recorded experiments are append-only everywhere.** `run_benchmark` (EXP-0001
     and EXP-0002) refuses an existing non-empty output directory with `ConfigError`; a new
     `--overwrite` flag is the explicit opt-in, logs a WARNING, and replaces only
     `result.json`/`report.md` — nothing is deleted. This makes `vie benchmark` consistent with
     `vie process`/`vie objects` and with `experiments/registry.json`.
  3. **AUD-04 — the viewer no longer mutates on GET.** State changes require `POST /` carrying
     a per-process `secrets.token_urlsafe(32)` token embedded in the dashboard's own forms;
     token-less or wrongly-tokened POSTs are refused (403) with state untouched; request bodies
     are bounded at 8 KiB; successful changes redirect (303, POST/redirect/GET) and are logged
     as before. This is a CSRF control, **not** authentication — the viewer remains local,
     unauthenticated, and exploratory. `build_viewer` (unused) is removed in the same change.
  4. **AUD-05 — LICENSE added** (`Proprietary Research License`, matching the `pyproject.toml`
     declaration): internal research/evaluation grant, redistribution by permission, commercial
     use by licence, prohibited medical/security/surveillance/safety-critical fields, no
     warranty; changes to it are decisions. Verified that the wheel now carries
     `License-File: LICENSE` automatically (no packaging change needed).
  5. **AUD-06…09 — dead/disconnected code resolved, not documented away.** Removed:
     `pipeline.record_time`, the no-op `except (SourceError, VIEError): raise`,
     `metrics.Timer`, `metrics.traced_memory`, `metrics.rss_kb`, `metrics.extend_history`,
     `provenance.monotonic_ns`, `framesource.make_frame_record`, `server.build_viewer`.
     `source.close()` moved into `finally` in `cmd_process`/`cmd_objects`. The EXP-0002 runner
     is now reachable as `vie benchmark-objects` (the module entry point still works).
  6. **AUD-10 — CLI/benchmark boundary tests added** (`tests/integration/test_cli_validation.py`,
     25 cases, mock-free, subprocess-based) plus the viewer CSRF suite in
     `tests/integration/test_viewer_server.py` (15 cases). Interactive-viewer tests now drive
     POST forms exactly as a browser would.
  7. **AUD-11 — stale phrasing refreshed.** The CI header no longer cites a test count (the
     suite grows every stage); `SECURITY.md` states the current stage (Phase 2) and the licence.
- Consequences: no representation semantics, schema id/version, vocabulary, config, or golden
  hash changed; Phase-1/Phase-2 artifacts are byte-identical. The viewer is slightly less
  convenient (buttons instead of links, no shareable `/?levels=32` URLs) and that cost is
  accepted deliberately. Accepted/deferred rather than fixed: provenance commits referenced by
  recorded experiments are absent from the squashed history (mapping is documented in
  `DEC-0005`/the Phase-2 response); no LICENSE reachable from wheels was requested; viewer
  threading/rate-limiting remains a declared limitation (SEC-2); camera success path remains
  [UNVERIFIED] in this environment (PART-1).
