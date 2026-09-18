# Response to the 2026-09-18 execution audit (AUD-01…AUD-11)

- Subject: independent execution audit of commit `6be667d` by an Arena agent, filed as
  `docs/reviews/2026-09-18-arena-execution-audit.md` on PR **#3**
  (`arena/01a0b3da-visual-motion-detection1`). Verdict: **PARTIAL**, no critical blocker,
  eleven required fixes (AUD-01…AUD-11).
- Status of that report: **PR #3 is open and deliberately not merged** (maintainer decision).
  The audit document is therefore *not* part of this tree; it was read from that branch
  (`git show FETCH_HEAD:docs/reviews/2026-09-18-arena-execution-audit.md`) and is referenced
  here by branch, not by a path in this tree.
- Scope of this response: verify every audit claim in this tree by execution, dispose of each
  item (fixed / deferred with reason / rejected with evidence), and state what remains open.
  Code changes are recorded in **DEC-0006** (`docs/decisions/decision_log.md`).
- Nothing in `docs/MASTER_PLAN.md` was changed. No representation semantics, schema id or
  version, vocabulary, config, or golden hash changed.

## 1. Verification performed here (executed, not trusted)

Environment: `.venv` from `scripts/setup_env.sh` (Python 3.11.2, numpy 2.4.6, Pillow 12.3.0,
jsonschema 4.26.0, pytest 9.1.1, opencv-python-headless 5.0.0.93), plus `ruff==0.16.8`,
`mypy==2.3.1`, `build`, `pip-audit`.

| Check | Command | Result |
|---|---|---|
| Full suite | `.venv/bin/python -m pytest tests -q` | **361 passed** in 27.5 s (was 331 at `6be667d`) |
| Lint | `.venv/bin/ruff check visual_intensity_engine tests scripts` | clean |
| Types | `.venv/bin/mypy visual_intensity_engine` | clean (33 files) |
| Self-test | `.venv/bin/vie self-test --levels 16` | `"status": "PASS"` |
| Dependencies | `.venv/bin/pip-audit -r requirements.txt` | no known vulnerabilities |
| Wheel + out-of-checkout use | `python -m build --wheel`, install into `/tmp/wheel-venv`, run `vie process/validate/self-test/benchmark/benchmark-objects` from `/tmp/wheel-run` | all pass; wheel metadata now carries `License: Proprietary-Research` and `License-File: LICENSE` |
| Regression / goldens | `tests/regression/` (golden hashes), `tests/edge/test_fault_injection.py` | pass; no artifact bytes changed |

Pre-fix behaviour was reproduced from a detached worktree of `6be667d` (`git worktree add
/tmp/before 6be667d`) so the "before" column below is measured, not assumed:

```
$ python -m visual_intensity_engine process --input synthetic:gradient --levels 0 --output /tmp/o
ValueError: levels must be in [2,256], got 0     # vocabulary.py:83, rc=1, traceback
$ python -m visual_intensity_engine process --input camera:abc --max-frames 5 --output /tmp/o
ValueError: invalid literal for int() with base 10: 'abc'   # rc=1, traceback
$ python -m visual_intensity_engine benchmark --output experiments/EXP-0001-quantization-baseline \
      --frames 2 --warmup 1
rc=0, result.json and report.md silently replaced
```

## 2. Disposition of every required fix

| ID | Audit finding | Disposition | Evidence |
|---|---|---|---|
| AUD-01 | HIGH — `--levels 0/1/-5/257/300` → raw `ValueError`, exit-code contract broken | **FIXED** | Range-checking `argparse` type (`_bounded_int`) on `--levels` (and every other numeric flag). `--levels 0` now: `vie process: error: argument --levels: --levels must be >= 2, got 0`, **exit 2, no traceback**. `tests/integration/test_cli_validation.py` |
| AUD-02 | MEDIUM — `camera:abc` → raw `ValueError` at `cli.py:65` | **FIXED** | Typed parse: `ConfigError: invalid camera source 'camera:abc': the device index must be an integer, e.g. --input camera:0`, exit 2; negative indices rejected too |
| AUD-03 | MEDIUM — `vie benchmark` silently overwrites output dirs | **FIXED** | Shared `benchmarking.prepare_experiment_outdir()`: non-empty `--output` ⇒ `ConfigError` naming the count and the escape hatch; `--overwrite` (CLI flag) replaces **only** `result.json`/`report.md`, logs a WARNING, deletes nothing. Applied to EXP-0001 **and** EXP-0002 runners, matching `process`/`objects` and the append-only registry |
| AUD-04 | MEDIUM — viewer mutates state on unauthenticated GET (SEC-1) | **FIXED** | State changes require `POST /` carrying a per-process `secrets.token_urlsafe(32)` token embedded in the dashboard's own forms. GET with `?levels=…` renders the page, logs "ignoring query parameters on GET", and changes nothing; token-less/wrong POST ⇒ 403, state untouched, log empty; success ⇒ 303 `Location: /` (POST/redirect/GET) and the usual interaction-log entry. Bodies bounded at 8 KiB (413 beyond). This is a **CSRF control, not authentication** — see §4 |
| AUD-05 | MEDIUM — no `LICENSE` while `pyproject` says `Proprietary-Research` | **FIXED** | `LICENSE` added: proprietary research licence (research/evaluation grant; redistribution by permission; commercial by licence; no medical/security/surveillance/safety-critical use; no warranty; licence changes are decisions). Verified the wheel ships it (`dist-info/licenses/LICENSE`, `License-File: LICENSE`) with **no** packaging change |
| AUD-06 | LOW — dead `pipeline.record_time()` | **FIXED (removed)** | Zero callers; deleted. No stub remains to be mistaken for a feature |
| AUD-07 | LOW — unused helpers (`metrics.Timer`, `extend_history`, `traced_memory`, `rss_kb`, `provenance.monotonic_ns`, `framesource.make_frame_record`, `server.build_viewer`) | **FIXED (removed)** | All deleted with their now-unused imports; `metrics` keeps `summarize`/`human_bytes`/`valid_stats` (both test-asserted). `serve`'s unused `build_viewer` is replaced by the token-carrying `control_form` helper |
| AUD-08 | LOW — objects benchmark reachable only via `python -m` | **FIXED** | New first-class `vie benchmark-objects` (same runner, same arguments, `--overwrite` included); the module entry point still works. Smoke-tested from the wheel outside the checkout |
| AUD-09 | LOW — no-op `except (SourceError, VIEError): raise`; `source.close()` not in `finally` | **FIXED** | No-op handler deleted (propagation is now explicit and commented); `cmd_process`/`cmd_objects` close the source in `finally`, so camera/video handles are released on mid-run failure |
| AUD-10 | LOW — no CLI-boundary or benchmark-overwrite regression tests | **FIXED** | `tests/integration/test_cli_validation.py` (25 cases: every numeric flag, seven bad `--levels` values, two `--levels` boundaries, `camera:abc`, `camera:-1`, benchmark refusal, overwrite-replaces-only-own-files, warm-up ≥ frames, EXP-0001 protection, `benchmark-objects` reachable + `vie.object-benchmark-result/1` valid). Viewer suite rewritten to drive POST forms (15 cases incl. oversized body, foreign Host on POST, unknown path, truncated token) |
| AUD-11 | INFO — stale CI header ("170-test"); provenance commits absent from squashed history | **PART-FIXED / ACCEPTED** | CI header now describes the gates without a count (the suite grows every stage). The provenance gap is **accepted and documented, not "fixed"**: recorded experiments reference commits (`9e338fc`, `a86b70f`, `1ef690f`) that the squashed history no longer contains; the stage↔commit mapping is recorded in the Phase-2 audit response, and rewriting history to manufacture matching hashes would be worse than the gap |

`git status` scope check: changes are confined to `visual_intensity_engine/` (cli, benchmarking,
metrics, provenance, pipeline, framesource, viewer), `tests/`, `LICENSE`, `README.md`,
`SECURITY.md`, `.github/workflows/ci.yml`, and `docs/decisions/decision_log.md`. Nothing under
`schemas/`, `configs/`, `experiments/`, `docs/MASTER_PLAN.md`, or the golden-hash file changed.

## 3. Findings that were left as they are (with reasons)

| Finding | Disposition |
|---|---|
| F-02 / PART-4 — no motion detection, tracking, optical flow, or learned model | **Accepted, unchanged.** `README.md`, `SECURITY.md`, and the Phase-2 report state this explicitly; cross-frame identity is Phase 3 and was frozen as out of scope by DEC-0003/0005. Implementing "motion" to satisfy a repository name would break the stage gate the plan makes controlling |
| F-06 / BUILD-3 — no database, auth, users, deployment | **Accepted.** Declared research scope (plan §32, §42); a database or auth layer here would be unrequested scope with no research purpose (plan §1: no feature without a defined experiment) |
| MOCK-2 / AUD-11 provenance gap | **Accepted** (see AUD-11 above) |
| PART-1 — `CameraSource` success path [UNVERIFIED] | **Accepted.** No camera exists in this environment; the failure path is tested and typed. Unchanged, and still labelled unverified rather than assumed |
| PART-2 — viewer is synthetic-only | **Accepted.** `_make_source` still builds `SyntheticSource`; the viewer remains exploratory and excluded from benchmark output (plan §21) |
| PART-3 — strict-mode mid-stream timestamp anomalies | **Accepted.** Checker-level unit tests exist; an end-to-end malformed-container fixture is still not recorded — listed as open |
| SEC-2 — unbounded threads, no rate limiting, unbounded synthetic streams | **Accepted, unchanged** (declared). New in this change: request bodies are bounded (8 KiB). Rate limiting/idle timeouts remain a documented limitation, not a silent one |
| BUILD-4 — exact `opencv-python-headless==5.0.0.93` pin | **Accepted.** Kept because acceptance runs used it; the availability risk is recorded in the R1 response and in CI (3.12 job installs declared ranges) |
| SEC-3 / AUD-05 licence decision | **Resolved** by adding the proprietary text; if the maintainer wants a different licence, that is a new decision record |
| TEST-3 "no false-confidence mechanisms" | **Confirmed, strengthened**: every new test executes the real CLI/HTTP server — no mocks were added |

## 4. Residual risks and open items

- **The viewer is still unauthenticated.** The token stops *cross-site/page-load* mutation
  (a link, image, prefetch, or foreign origin cannot change state and cannot read the token).
  Anyone who can reach the port **and load the dashboard** can still drive the viewer. Loopback
  bind remains the default; `--host 0.0.0.0` remains an announced opt-in. `SECURITY.md` states
  both halves plainly.
- **The viewer is slightly less convenient**: no shareable `/?levels=32` URLs (by design —
  state-changing GETs are exactly what was removed). Parameters move through the dashboard's
  POST buttons, which is what a human does anyway.
- **No automated CSRF test against a real cross-origin browser** (would need a browser); the
  property is enforced and tested at the HTTP layer instead.
- **CI on this branch**: confirmed green on the pushed commit `95a0064` — workflow `CI`, run
  `35345185319`: `tests (py3.11)`, `tests (py3.12)`, `lint + types`, and
  `wheel install (schemas outside the checkout)` all **success**. CodeQL had not published a
  run for this branch at the time of writing (it is a dynamic workflow, not a repo file), so no
  CodeQL claim is made here.
- **Open, recorded, not claimed fixed**: camera success path [UNVERIFIED]; end-to-end malformed
  container for strict timestamp anomalies; viewer rate limiting; provenance-commit gap.

## 5. Bottom line

Every HIGH/MEDIUM item the execution audit required is fixed and covered by a regression test
that runs the real artifact (subprocess CLI or real HTTP server). The LOW items were deleted or
wired up rather than documented away. `331 → 361` tests pass, ruff/mypy are clean, the wheel
installs and works outside a checkout, and no stored artifact, schema, vocabulary, config, or
golden hash changed. The audit's structural conclusions are agreed with and left intact: this is
a real research prototype, not a production product, and it does not pretend to be one.
