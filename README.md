# Visual Intensity Engine — Discrete Visual Intensity & Motion Representation

Stage-gated research platform that transforms raw frames into **discrete intensity
tokens** with full traceability, deterministic replay, and measured costs. The research
question is *whether* structured discrete representations can preserve useful visual
information at lower computational cost — decided by experiments, not assumption
([master plan](docs/MASTER_PLAN.md) §1, §39).

**Status: Phase 1 accepted** (basic intensity engine). Phase 0 (formal representation
specification) and Phase 1 evidence are complete; Phase 2 (intensity objects /
connected components) is next and not yet started.

| Document | Purpose |
|---|---|
| [`docs/MASTER_PLAN.md`](docs/MASTER_PLAN.md) | Controlling research plan (§1–§43) |
| [`docs/phase-0/representation_specification.md`](docs/phase-0/representation_specification.md) | `VIE-SPEC-REP` 1.0.0 — frozen formal representation spec |
| [`schemas/`](schemas/) | JSON Schemas (`vie.pipeline-config/1`, `vie.vocabulary/1`, `vie.framestore-manifest/1`, `vie.benchmark-result/1`) |
| [`docs/phase-1/phase1_report.md`](docs/phase-1/phase1_report.md) | Phase 1 stage report (acceptance evidence) |
| [`docs/decisions/decision_log.md`](docs/decisions/decision_log.md) | Decision records (append-only) |
| [`docs/hypotheses/registry.md`](docs/hypotheses/registry.md) | Versioned hypotheses H1–H5 |
| [`experiments/registry.json`](experiments/registry.json) | Formal experiment registry (EXP-0001) |

## Quickstart

```bash
scripts/setup_env.sh                 # deterministic venv from requirements.txt

# batch: synthetic scene → frame store (previews + metrics + config export)
.venv/bin/vie process --input synthetic:moving_square --config configs/quantization.uniform.l016.v1.json \
                      --max-frames 32 --output out/demo --previews 3

# batch: real video file
.venv/bin/vie process --input path/to/video.mp4 --levels 16 --max-frames 100 --output out/video_store

# deterministic self-check (round-trip + byte-identical replay)
.venv/bin/vie self-test

# validate a store or config; run the baseline benchmark
.venv/bin/vie validate --target out/demo
.venv/bin/vie benchmark --output experiments/EXP-0001-quantization-baseline

# exploratory live viewer (NOT benchmark output; interactions are logged)
.venv/bin/vie serve --port 8000
```

## Pipeline (Phase 1)

```
source (synthetic | video | camera)
  → validate frame (dtype/channels/range/NaN policies — explicit typed errors)
  → grayscale: Y = 0.299R + 0.587G + 0.114B (normalized; bt601 default, bt709/average optional)
  → quantize:  level = min(floor(Y·L), L−1)   L ∈ {2..256}, tested {8,16,32,64,128,256}
  → IntensityMap (uint8 ids + frame index + media timestamp + config hash + vocabulary + anomaly counters)
  → deterministic frame store (npz + schema-validated manifest + sha256 checksums)
```

Raw frames are never required to be discarded — stores are **additive** representations
bound to their source (plan §2). Replays are byte-identical for identical inputs and
library versions (verified by tests, not asserted).

## Testing

```bash
scripts/run_tests.sh        # 170 tests: unit / property / integration / edge /
                            # fault-injection / regression (golden hashes) / performance
```

## Engineering rules in force

Explicit typed errors (no silent fallbacks) · schema validation at module boundaries ·
versioned configs only · accuracy and cost measured together · correctness before
optimization · synthetic before real data · no stage advances without acceptance evidence
· exploratory visualization never contaminates benchmark output · failures are recorded,
not hidden.

## Scope notice

Research prototype. No medical, security, surveillance, or safety-critical use
([master plan](docs/MASTER_PLAN.md) §32, §42). The live viewer processes camera input
only on the local machine; no video is retained beyond explicitly exported stores.
