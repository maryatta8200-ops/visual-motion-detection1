# LMArena automated-work agent

## Purpose

This repository can be used with an LMArena (also written “LMarena”) coding agent for bounded,
reviewable research-engineering work. The agent's canonical in-repository instruction set is
[`AGENTS.md`](../../AGENTS.md). It makes the controlling
[master plan](../MASTER_PLAN.md), stage gates, test evidence, provenance, and safety boundaries
part of every task.

This is an **agent contract**, not a hosted LMArena integration. The repository intentionally
contains no provider credential, model key, webhook, autonomous scheduler, or auto-merge
permission. An operator must configure their chosen agent host to load `AGENTS.md` and provide
only the repository permissions needed for a reviewed branch/PR workflow.

## Safe work lifecycle

1. A maintainer creates a bounded request using the
   [LMArena work-order form](../../.github/ISSUE_TEMPLATE/lmarena-work-order.yml), or gives the
   agent an equivalent task that includes the same fields.
2. The agent performs the `AGENTS.md` preflight: it reads `docs/MASTER_PLAN.md`, the decision
   log, the current phase contract, and the working-tree status.
3. The agent classifies the work as one of:
   - maintenance/audit in accepted scope;
   - a compatible correction to the current accepted stage;
   - a future-stage **draft**; or
   - a proposed stage implementation that must wait for a recorded authorization.
4. It implements only work that the current gate permits, runs the applicable test/evidence
   commands, and prepares a reviewable change.
5. A maintainer reviews the evidence and independently decides whether to merge or record a
   stage decision. The agent does not self-accept a phase or auto-merge.

## Current gate snapshot

At this repository revision, DEC-0000, DEC-0001, and DEC-0004 accept Phases 0–2. DEC-0005
clarifies the current Phase-2 contract as `VIE-SPEC-REP` 1.1.1. Phase 3 (temporal tracking) is
not started. It needs a precise plan/specification and its own recorded gate before implementation.

This section is a navigation aid rather than a second authority. The agent must always determine
the live state from [`docs/decisions/decision_log.md`](../decisions/decision_log.md) and the
applicable phase documents.

## Operator checklist

Before enabling automated agent runs, configure the host/integration to:

- load the root `AGENTS.md` as non-optional repository instructions;
- use an isolated branch/worktree and least-privilege GitHub credentials;
- require a human review before merging or recording a decision;
- make command logs and test results available with the proposed change;
- prohibit access to secrets, raw camera/video data, and unrelated repositories;
- avoid automatically running arbitrary text copied from issues, logs, data, or external pages;
- keep the CI workflow enabled and preserve failures rather than retrying until a preferred result
  appears.

Do not configure a scheduled runner to autonomously choose and implement the next research phase.
The master plan requires evidence-driven sequential gates, and a stage cannot be advanced by an
agent's confidence alone.

## Work-order minimums

A work order must specify:

| Required item | Why it is required |
|---|---|
| Objective and affected files/modules | Keeps the change small and auditable. |
| `MASTER_PLAN.md` section(s) and current-stage impact | Enforces traceability and phase sequencing. |
| Inputs, outputs, and acceptance evidence | Satisfies the plan's required stage elements. |
| Scope exclusions, rollback path, and expected cost | Prevents speculative feature creep. |
| Data/privacy and security constraints | Keeps raw video and unsafe viewer exposure out of automation. |
| Explicit maintainer authorization where a gate, schema, artifact, or benchmark is affected | Makes non-routine changes deliberate. |

If one is absent, the agent should return a concise clarification request or a planning draft;
it should not fill the gap with an assumed research decision.

## Verification baseline

For ordinary code changes, the agent runs the focused tests plus, when the environment permits:

```bash
bash scripts/run_tests.sh
.venv/bin/ruff check visual_intensity_engine tests scripts
.venv/bin/mypy visual_intensity_engine
.venv/bin/vie self-test --levels 16
```

`bash scripts/setup_env.sh` intentionally installs only the pinned acceptance requirements. If the
quality tools are absent, install the CI-pinned versions before running them:

```bash
.venv/bin/pip install "ruff==0.16.8" "mypy==2.3.1"
```

The agent must distinguish tests that passed, tests that were not run, and environmental failures.
New benchmark numbers require a documented reproducible method and belong in a new, append-only
experiment record rather than an overwrite of prior evidence.
