# Execution audit — 2026-09-18 (Arena agent)

Independent execution audit of this repository at commit `6be667d` on branch
`arena/01a0b3da-visual-motion-detection1`. Every claim below was verified by
running code in this checkout, not by trusting documentation, tests, or this
repository's own prior audit responses.

- Repository: `visual-motion-detection1` (Visual Intensity Engine, `visual-intensity-engine` 0.1.0)
- Branch: `arena/01a0b3da-visual-motion-detection1` (from `main`)
- Commit: `6be667d26206cf8a4023a096794fc3693e1d2954`
- Audit date: 2026-09-18
- Overall status: **PARTIAL** — real, functional, verified research tool; not a
  production product (single-stage research scope, no database/auth/deployment,
  and the motion-detection capability implied by the repository name does not
  exist, as README/SECURITY.md correctly disclaim).

## Verification performed (executed, not trusted)

- `scripts/setup_env.sh` — deterministic env (numpy 2.4.6, pillow 12.3.0,
  jsonschema 4.26.0, pytest 9.1.1, opencv-python-headless 5.0.0.93).
- Full suite: `pytest tests -q` → **331 passed** in 15.4 s.
- `ruff==0.16.8` → clean; `mypy==2.3.1` → clean (33 files).
- `pip-audit -r requirements.txt` → no known vulnerabilities.
- Wheel build + scratch-venv install + `vie process/validate/self-test` outside
  the checkout (schemas ship as package data) — pass.
- CLI executed: synthetic batch, real 60-frame MP4 batch, `objects`, `validate`
  (frame store, object store, config), `self-test` (PASS), `benchmark`,
  camera-failure path, invalid-input paths.
- Tamper injection: flipped checksum byte → `SerializationError`, exit 2.
- Unimplemented-strategy injection (`learned`) → typed `ConfigError`, no silent fallback.
- Live viewer over real HTTP: routes, MJPEG JFIF bytes, Host-header 403s
  (`evil.example.com`, `127.0.0.1.evil.com`), interaction log, XSS probe
  neutralized by query allowlist.
- Replay determinism: two independent runs → byte-identical `intensity_maps.npz`.
- CI verified via `gh run list`: tests (py3.11/py3.12), lint+types, packaging,
  and CodeQL green on this commit.

## Executive findings

| ID | Severity | Finding |
|---|---|---|
| F-01 | INFO | No mocks, stubs, fake APIs, hardcoded outputs, or simulated processing anywhere on the production path. Runtime behavior matched documentation in every probe except where noted below. |
| F-02 | INFO | Despite the repository name, there is no motion detection, tracking, optical flow, background subtraction, or learned model. Delivered scope: grayscale → uniform quantization → checksummed deterministic frame store (Phase 1) + level-uniform 4-connected region labeling with counted discards (Phase 2). README/SECURITY.md state this explicitly. |
| F-03 | INFO | Test suite is mock-free (zero `unittest.mock`/`monkeypatch` uses) and includes an independent algorithm oracle (flood fill vs. run-length union-find), golden byte hashes, real-HTTP viewer tests, and fault injection. Passing tests are meaningful evidence. |
| F-04 | HIGH | CLI numeric-argument validation gaps: raw unhandled tracebacks for `--levels 0/1/-5/257/300` and `camera:abc` (`ValueError` escapes the `VIEError`-only catch at `cli.py:433`). |
| F-05 | MEDIUM | `vie benchmark` silently overwrites its output directory, contradicting the "experiments never overwrite" rule enforced by `process`/`objects` and the append-only experiment registry. |
| F-06 | MEDIUM | No database, no authentication, no users/tenants, no deployment target — correct for declared research scope, disqualifying for PRODUCTION status. |
| F-07 | INFO | CI is real and green on this commit; the workflow header still says "170-test Phase-1 acceptance suite" while the suite is now 331 tests (stale phrasing). |

## Real functionality (all executed during this audit)

| ID | Class | Evidence |
|---|---|---|
| REAL-1 | [REAL] | Phase-1 batch pipeline: synthetic 32 frames and a real MP4 → bt601 luminance → `floor(y·L)` quantization → `vie-framestore/1` bundle (npz + schema-validated manifest + checksums + PNG previews). Replay byte-equality confirmed with `cmp`. |
| REAL-2 | [REAL] | `VideoFileSource`: real OpenCV decode, BGR→RGB at boundary, container timestamps, monotonicity checks, typed errors on missing/garbage files. |
| REAL-3 | [REAL] | Phase-2 extraction: production run-length+union-find path verified against an independent flood-fill oracle; discards counted; `max_regions` → `RegionExtractionError`, never truncation. `vie objects` produced a valid 6-artifact store. |
| REAL-4 | [REAL] | Store integrity: deterministic NPZ (fixed ZIP timestamps), SHA-256 checksums, JSON-Schema validation at boundaries, compatibility checks; tamper rejected with typed error. |
| REAL-5 | [REAL] | Config system: canonical-JSON SHA-256 identity, `additionalProperties:false` schemas, unimplemented strategies fail closed. |
| REAL-6 | [REAL] | `vie self-test` PASS (ramp coverage, replay byte-equality, round-trip, object invariants, counted discards). Output-dir reuse blocked for `process`/`objects`. |
| REAL-7 | [REAL] | Live viewer: real threaded HTTP server — dashboard, `/state.json`, `/legend.png`, `/stream.mjpg` (verified JFIF frames); interactions logged; DNS-rebinding Host defence returns 403; XSS probe ignored via allowlist. |
| REAL-8 | [REAL] | Benchmarking: `vie benchmark` and the EXP-0002 runner produce schema-validated results; checked-in EXP-0001…0005 artifacts contain full distributions and honest negative results. |
| REAL-9 | [REAL] | Packaging & CI: wheel builds, out-of-checkout smoke test passes, GitHub Actions (3 jobs) + CodeQL green. |

## Partial functionality

| ID | Class | Finding |
|---|---|---|
| PART-1 | [PARTIAL] | `CameraSource`: real code path, but only the failure path is executable/tested here (no camera); success path [UNVERIFIED]. |
| PART-2 | [PARTIAL] | Viewer is "live" only over synthetic scenes (`_make_source` instantiates `SyntheticSource` exclusively); labeled exploratory on every page. |
| PART-3 | [PARTIAL] | Strict-mode mid-stream timestamp anomalies: implemented and unit-tested at the checker level, not exercised end-to-end with a malformed container. |
| PART-4 | [PARTIAL] | Phase 3+ (motion/temporal linkage, learned strategies) deliberately fails as a specified extension point; not implemented, not claimed. |

## Mock / simulation / fake / demo findings

- MOCK-1 [INFO]: no fabricated behavior on any production path; synthetic sources
  are legitimately labeled (`kind: "synthetic"`, `sha256: null`), never presented as real input.
- MOCK-2 [INFO]: recorded experiment artifacts reference commits (`9e338fc`,
  `a86b70a`, `1ef690f`) absent from this single-commit git history — a
  provenance-traceability gap, not evidence of fabrication.
- MOCK-3 [STUB, LOW]: `pipeline.py:181` `record_time()` — self-declared placeholder returning `0.0`, zero callers.

## Security findings

| ID | Severity | Finding |
|---|---|---|
| SEC-1 | MEDIUM | Viewer mutates state on unauthenticated GET (`/?levels=32&scene=…`) — CSRF-style drive-by from any loopback browser page; blast radius limited to the viewer's own synthetic stream (no file access, no exfiltration channel found). |
| SEC-2 | LOW | Viewer: unbounded per-connection threads and per-request infinite synthetic sources; no rate limiting (declared). Local resource-exhaustion surface. |
| SEC-3 | LOW | No LICENSE file while `pyproject.toml` declares `Proprietary-Research` (prior internal audit deferred as maintainer decision, §M2). |
| SEC-4 | INFO | Positive controls: no secrets; no `eval`/`exec`/`pickle`; `allow_pickle=False`; subprocess limited to `git` with 5 s timeouts, no `shell=True`; offline `$ref` registry; `nosniff` headers; Host-header rebinding defence works; `pip-audit` clean. |
| SEC-5 | INFO | Viewer exposure is explicit opt-in with WARNING logs; no SSRF/IDOR/path-traversal surface (four fixed routes, no user-supplied paths opened). |

## Database findings

- DB-1 [INFO]: no database. Persistence is file-based store bundles; schema
  (9 packaged JSON Schemas), versioning, cross-field invariants, completeness
  (aborted runs never validate), single-writer ordering enforcement — all verified.
- DB-2 [LOW→INFO]: `duration_s` folded into provenance before checksumming — verified correct ordering.

## API / integration findings

- INT-1 [REAL]: OpenCV integration is real (decode verified end-to-end; typed failures verified).
- INT-2 [REAL]: jsonschema draft-2020-12 validation at every module boundary.
- INT-3 [INFO]: no network integrations exist — nothing to fake or time out.
- INT-4 [LOW]: `benchmarking/objects_runner.py` reachable only via `python -m`, not a `vie` subcommand.

## Testing findings

- TEST-1 [REAL]: 331 tests executed and passing — unit, property, integration
  (round-trip, replay, CLI, real video, real HTTP viewer), edge, fault injection,
  golden regression, performance guards.
- TEST-2 [REAL]: strongest evidence — production labeler vs. independent oracle
  parity; fast validator vs. normative schema parity; executable §R9 spec example.
- TEST-3 [LOW]: untested critical paths — camera success path, CLI argument
  validation (where the HIGH defect lives), benchmark overwrite, end-to-end
  strict timestamp anomalies. No false-confidence mechanisms found.
- TEST-4 [INFO]: recorded suite growth (170 → 215 → 314 → 331) is internally consistent.

## Build / deployment findings

- BUILD-1 [REAL]: deterministic env setup, wheel build, out-of-checkout smoke test — all pass.
- BUILD-2 [REAL]: CI green (tests py3.11 exact pins / py3.12 ranges, lint+types, packaging) + CodeQL.
- BUILD-3 [LOW]: no deployment story exists or is claimed (correct for scope).
- BUILD-4 [LOW]: exact `opencv-python-headless==5.0.0.93` pin is an availability risk acknowledged by the project's own audit response.
- BUILD-5 [INFO]: recorded runtime failures are the CLI validation gaps (AUD-01/02 below).

## Architecture findings

- ARCH-1 [INFO]: clean layering, typed error hierarchy, schema validation at
  boundaries, fail-closed dependency-injection points; Phase 2 reuses the Phase-1 core.
- ARCH-2 [INFO]: streaming writers bound memory; aborted runs cannot masquerade
  as valid stores; no silent fallbacks anywhere; scalability limits honestly measured.
- ARCH-3 [LOW]: `pipeline.py:165-166` `except (SourceError, VIEError): raise` is a no-op re-raise.
- ARCH-4 [LOW]: `source.close()` not in `finally` (`cli.py:112,138`) — capture handle leaks on mid-run exception.
- ARCH-5 [INFO]: observability via per-module logging and `module_info()` with a
  test enforcing honest performance claims.

## Dead / disconnected / unused code

- AUD-06 [STUB/DEAD, LOW]: `pipeline.py:181` `record_time()` placeholder, zero callers.
- AUD-07 [DEAD, LOW]: unused helpers — `metrics.Timer`, `metrics.extend_history`,
  `metrics.traced_memory`, `metrics.rss_kb`, `provenance.monotonic_ns`
  (misleading name; wraps `perf_counter_ns`), `framesource.make_frame_record`,
  `server.build_viewer`.
- AUD-08 [DISCONNECTED, LOW]: objects benchmark `main()` only reachable via `python -m`.
- AUD-09 [INFO]: root `schemas/` are intentional symlinks to package copies.

## Critical blockers

None. No CRITICAL-severity defect: no fabricated functionality, no exploitable
attack path beyond the documented local unauthenticated dev viewer, no
data-integrity failure, no build/CI failure.

## Required fixes

| ID | Severity | Finding | Action |
|---|---|---|---|
| AUD-01 | HIGH | `--levels` out of range (0/1/-5/257/300) → raw `ValueError` traceback from `vocabulary.py:83`; `cli.py:433` catches `VIEError` only; exit-code contract broken. | Validate `--levels` in the CLI; map argument-coercion `ValueError` to a typed CLI error. |
| AUD-02 | MEDIUM | `camera:abc` → raw `ValueError` at `cli.py:65` (`int(...)` unchecked). | Parse with error handling; emit `ConfigError` with usage hint. |
| AUD-03 | MEDIUM | `vie benchmark` overwrites existing output dirs (`runner.py:112`, `objects_runner.py`), violating the append-only experiment policy. | Refuse existing dirs or require explicit `--overwrite` with WARNING. |
| AUD-04 | MEDIUM | Viewer state changes via unauthenticated GET (SEC-1). | POST + token, or document the CSRF surface in SECURITY.md. |
| AUD-05 | MEDIUM | Missing LICENSE (SEC-3). | Add LICENSE per the deferred §M2 decision. |
| AUD-06–09 | LOW | Dead code items listed above; no-op `except` at `pipeline.py:165`; `source.close()` not in `finally` (`cli.py:112,138`); objects benchmark not a `vie` subcommand. | Remove/wire up as indicated. |
| AUD-10 | LOW | No CLI-boundary tests; no regression test for AUD-03. | Add tests for argument validation and benchmark overwrite behavior. |
| AUD-11 | INFO | Stale CI header ("170-test"); provenance commits referenced by accepted-stage evidence absent from squashed history. | Refresh wording; consider vendoring provenance metadata. |

## Bottom line

Every feature this repository claims — and it claims narrowly and honestly —
was traced end-to-end and verified operational by execution: real input sources
(synthetic + real video decode + camera-with-typed-failure), real processing
(bt601 luma, uniform quantization, union-find region labeling proven against an
independent oracle), real persistence (deterministic checksummed stores that
reject tampering), a real (deliberately synthetic-only, unauthenticated,
loopback) viewer, real measurements, real CI, real packaging. The defects found
are usability/policy violations and hygiene items, not fakes. It is a genuine,
well-engineered research prototype — not a production system, and it does not
pretend to be one.
