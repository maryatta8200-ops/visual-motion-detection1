# Contributing

This is a **stage-gated research platform**. The controlling document is
[`docs/MASTER_PLAN.md`](docs/MASTER_PLAN.md) (§1–§43): development proceeds sequentially and
**no stage advances until the current stage is specified, implemented, tested, documented,
and stable under its acceptance criteria**.

## Ground rules (from the plan)

1. Work on the current stage only; do not start Phase N+1 while Phase N is open (plan §1/§33).
   The gate for each stage is a decision record in `docs/decisions/decision_log.md`.
2. No feature without a research purpose, measured benefit, measured cost, and rollback path.
3. Explicit typed errors — never a silent fallback (`visual_intensity_engine/errors.py`).
4. Validate schemas at module boundaries; configs are versioned JSON files, never hidden
   parameters.
5. Measure accuracy **and** cost together; no optimization before correctness (plan §3.13/§3.14).
6. Preserve failures and negative results; never overwrite experiment results
   (`experiments/` is append-only per experiment id).
7. Never revise a hypothesis or the plan after seeing results without versioning the change
   (plan §37).

## Development setup

```bash
scripts/setup_env.sh                 # deterministic venv (pinned requirements.txt)
scripts/run_tests.sh                 # full suite, verbose
.venv/bin/ruff check visual_intensity_engine tests scripts
.venv/bin/mypy visual_intensity_engine
```

The exact pins in `requirements.txt` are the environment the Phase 0/1 acceptance evidence
was recorded in — do not "helpfully" bump them in a change that is not itself a recorded
stage decision.

## What a change must include

- tests in the layer it belongs to (`tests/unit|property|integration|edge|regression|performance`);
- a decision-log entry when it changes documented behavior, a schema, or an artifact;
- a `tests/regression/golden/CHANGELOG.md` entry **only** if golden hashes were intentionally
  regenerated with `scripts/update_goldens.py` (silent drift is a bug, not a fix);
- updated `module_info()` strings for touched modules — performance numbers must be measured
  or explicitly disclaimed (`tests/unit/test_module_info.py` enforces this).

## Pull requests

CI (`.github/workflows/ci.yml`) must be green: full suite on Python 3.11 and 3.12, ruff,
mypy, and the wheel-install smoke test. Describe which plan section the change serves and
which acceptance criteria it affects. Changes that alter representation semantics must cite
a schema/spec version increment; the frozen spec `VIE-SPEC-REP` 1.0.0 cannot be edited in
place.

## Scope and safety

Research prototype only — no medical, security, surveillance, or safety-critical use
(plan §32, §42; see [`SECURITY.md`](SECURITY.md)). Do not commit raw or personal video,
large outputs, or anything under `logs/`, `out/`, or `tmp/` (git-ignored by design).
