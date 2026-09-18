# External audit response — 2026-09-18

Point-by-point answer to the external audit of commit `9e338fc`. Rules applied: every
finding is either **confirmed with evidence and fixed**, **confirmed and deferred with a
reason**, or **rejected with evidence**. Nothing in `docs/MASTER_PLAN.md` was changed; no
representation semantics, schema versions, or golden hashes were altered.

Verification environment: `.venv` from `scripts/setup_env.sh` (Python 3.11.2, numpy 2.4.6,
Pillow 12.3.0, jsonschema 4.26.0, pytest 9.1.1, opencv-python-headless 5.0.0.93).

---

## Claims re-verified before acting

| Audit claim | Verification | Result |
|---|---|---|
| "170 tests, 0 failed" is a checked-in log, not a gate | `.venv/bin/python -m pytest tests -q` | **Confirmed true**: 170 passed in 5.17 s at `9e338fc` (claim was accurate; the gap was CI, not the number) |
| No CI workflows | `.github/` absent; `gh api repos/…/contents/.github/workflows` → 404 | Confirmed |
| No `LICENSE`; `pyproject` says `Proprietary-Research` | file listing + `pyproject.toml` | Confirmed (see M2) |
| `docs/decisions/DEC-0001-phase1-acceptance.md` missing | file listing; report §10 references it | Confirmed → fixed |
| Viewer binds `0.0.0.0` by default | `cli.py:250` (`--host` default), `server.py` `serve()`/`MJPEGServer` defaults | Confirmed (3 places) → fixed |
| `module_info()` claims 60 fps at 1080p vs EXP-0001 ~12 fps | `pipeline.py:208` vs `experiments/EXP-0001-*/result.json` | Confirmed → fixed |
| opencv 5.0.0.93 pin is availability-risky | PyPI JSON API: `cp37-abi3` wheels for macOS/Linux/Windows | **Softened**: wheel exists for 3.11–3.13; kept pinned because acceptance runs used it |

Additional discrepancies found during verification (not in the audit):

- `preprocessing/grayscale.py` claimed "~1-3 ms/frame at 1080p" — EXP-0001 measured
  **76 ms** at 1920×1080 (float64 luminance dominates end-to-end).
- `visualization/render.py` claimed "~10-30 ms per 1080p panel" — measured **~0.4 s**.
- `serialization/store.py` claimed "~30-80 MB/s" — measured **~22 MB/s raw-in** (zlib-6).
- `CameraSource` set `timestamp_us=0` for **every** frame, which is not merely a stub: it
  violates VIE-SPEC-REP §7.2 (media time) and silently defeats §7.4 duplicate/non-monotonic
  detection. Reclassified from "prototype limitation" to a spec-compliance defect.

---

## Findings and dispositions

### H1 — Viewer exposed by default — FIXED

`vie serve` now defaults to `127.0.0.1`. While loopback-bound, any request whose `Host`
header is not a localhost name (loopback literals, `localhost`, `*.localhost`) gets a
`403 — Host header rejected` response; this blocks DNS-rebinding style access. Network
exposure is explicit (`--host 0.0.0.0`) and announced with a WARNING that the server has no
authentication (plan §41); `--allowed-host NAME` (repeatable) covers reverse proxies and
tunnels that rewrite `Host`. Query parameters are allowlisted as before, and unparsable or
out-of-range values are now ignored with a warning instead of killing the connection
(found while testing: `/?fps=abc` used to raise inside the handler thread).
Evidence: `tests/unit/test_viewer_host_policy.py` (30 cases), `tests/integration/test_viewer_server.py` (10 HTTP tests).

### H2 — No project CI — FIXED

`.github/workflows/ci.yml`:

- `test` — full suite on Python 3.11 against the exact `requirements.txt` pins (the
  acceptance environment) and on 3.12 against declared ranges, plus `vie self-test`;
- `quality` — `ruff check` and `mypy` (pinned tool versions), both currently clean;
- `packaging` — builds the wheel, installs it into a scratch venv, and runs
  `vie process` / `vie validate` / `vie self-test` outside the checkout.

### H3 — Name vs capability — FIXED (documentation)

A scope notice now sits at the top of the README: Phase 1 is a discrete-intensity tokenizer
and traceable frame store; there is no optical flow, background subtraction, tracking, or
detection, and the repository must not be used for surveillance or safety-critical
applications. The master plan title itself is unchanged (controlling document).

### M1 — Broken decision link — FIXED

`docs/decisions/DEC-0001-phase1-acceptance.md` created; the append-only log entry remains
canonical.

### M2 — License ambiguity — DEFERRED (maintainer decision)

Adding a license is a legal/intent choice, so it is not made unilaterally here.
`pyproject.toml` still declares `Proprietary-Research` (all rights reserved by default; the
public repository is readable but grants nothing). Two one-line options for the maintainer:
add an Apache-2.0/MIT `LICENSE` **and** change that field, or keep proprietary and add a
`LICENSE` file stating the terms explicitly. Tracked as an open item.

### M3 — Performance claims contradicted measurements — FIXED

Every `module_info()['performance_expectations']` string now either cites EXP-0001/measured
values or states an explicit non-claim. `tests/unit/test_module_info.py` enforces the rule
(a rate may only appear together with a measurement reference or a non-claim) so the defect
cannot silently return.

### M4 — In-memory frame accumulation — FIXED

`FrameStoreWriter` streams each `IntensityMap` into `intensity_maps.npz` as it arrives and
retains only the manifest rows, so memory is bounded by metadata, not pixels. Documented
consequence (deliberate, not hidden): an aborted run leaves an incomplete bundle that
readers reject. Byte layout is unchanged — the golden store hash `bfcd8492…` still passes,
which is the strongest available evidence that serialization semantics did not move.
`window`-style long-video runs remain bounded; camera batch runs additionally require
`--max-frames` (no unbounded run can be launched by accident).

### M5 — Schemas not packaged — FIXED

Canonical schemas now live at `visual_intensity_engine/schemas/*.json` and ship as package
data; repo-root `schemas/` are symlinks to them, so documented paths keep working.
`schemas_dir()` resolves `VIE_SCHEMA_DIR` → package data → checkout; `configs_dir()` was
added for the shipped `configs/`. Verified by building a wheel, installing it into a fresh
venv without the repository, and running `vie process` + `vie validate` (VALID,
`config_sha256 7c584d3e…`) and `vie self-test` — also enforced in CI.

### M6 — Camera timestamps were a stub (and a spec violation) — FIXED

`CameraSource` now reports cumulative media time from `time.monotonic_ns()` (first frame
0 µs), with wall-clock time kept as provenance only, per VIE-SPEC-REP §7.2/§7.3. Frame
sequence anomalies are checked with the shared helper instead of being masked by zeros.

### M7 — Double write of store metadata — FIXED

The writer owns the whole bundle: `close(duration_s=…)` injects duration into provenance
*before* schema validation and checksum computation, so `manifest.json` and `checksums.json`
are each written exactly once and the checksums always cover the final bytes. `run_pipeline`
no longer rewrites artifacts after closing.

### M8 — `describe()` hashes the entire input file — ADDRESSED (cost made explicit)

The full-file SHA-256 is required by VIE-SPEC-REP §10.3, so it was not removed. Instead the
cost is announced: size at INFO, and a WARNING ≥ 512 MiB before hashing. A head/tail
("partial") digest would change the recorded provenance semantics and therefore needs a
schema version increment (§8.2); that is a stage-owned change, not an audit fix, so it is
deferred to Phase 5 dataset work if it is still needed then.

### L1 — No lint/type tooling — FIXED

`[tool.ruff]` (line-length 120, `E/F/W/I/UP/B/C4/SIM`, two justified per-file ignores) and
`[tool.mypy]` are configured; both pass cleanly. `FrameObserver = callable` became
`Callable[[int, np.ndarray, np.ndarray, np.ndarray], None]`; the grayscale registry became
`dict[str, GrayscaleImplementation]`; `cv2`'s optional-import sentinel carries an explicit
`type: ignore[assignment]`. The autofix pass also removed dead imports (e.g. `shutil`, `sys`)
— no behavior change: the full suite passes after the sweep.

### L2 — Governance files — PARTIAL

`SECURITY.md` and `CONTRIBUTING.md` added. CODEOWNERS was not added because it requires
maintainer-specific identity decisions.

### L3 — Viewer had no automated tests — FIXED

40 new test cases (pure host-policy unit cases + live-server HTTP integration cases).

### L4 — Interaction log written relative to CWD — FIXED

`vie serve --log-path PATH` selects the log location explicitly; the resolved path is logged
at startup, and the default (`logs/viewer_interactions.jsonl`, git-ignored) is documented.

### L5 — OpenCV pin — RETAINED with evidence

`5.0.0.93` publishes `cp37-abi3` wheels (3.11–3.13), so the pin stays: it is the environment
the acceptance benchmarks were recorded in. CI additionally exercises 3.12 with ranges.

### L6 — Account/repo discoverability signal — NO ACTION (not a code defect)

---

## What was deliberately not done

- **Phase 2 was not started.** The stage gate (plan §1/§33) stays closed until the
  maintainer accepts a Phase-2 plan written against the frozen spec.
- **No plan edits.** `docs/MASTER_PLAN.md` is byte-identical.
- **No schema version bumps, no golden regeneration.** `tests/regression/golden/hashes.json`
  is unchanged; `scripts/update_goldens.py` was not run.
- **No optimization work.** EXP-0001 facts stand as recorded; float64 luminance cost is a
  Phase 8 concern (plan §3.14).

## Rerun summary (2026-09-18, this checkout)

| Check | Command | Result |
|---|---|---|
| Full suite | `.venv/bin/python -m pytest tests -q` | **215 passed** (10.5 s) — unit 132, integration 36, edge 20, property 19, regression 5, performance 3 |
| Golden store hash | `tests/regression/test_regression_golden.py` | `bfcd8492…` unchanged |
| Lint | `.venv/bin/ruff check visual_intensity_engine tests scripts` | clean |
| Types | `.venv/bin/mypy visual_intensity_engine` | clean (26 files) |
| Wheel isolation | wheel → scratch venv → `vie process`/`validate`/`self-test` in `/tmp` | VALID store, self-test PASS |
