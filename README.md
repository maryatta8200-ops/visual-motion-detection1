# Visual Intensity Engine — Discrete Visual Intensity & Motion Representation

Stage-gated research platform that transforms raw frames into **discrete intensity
tokens** with full traceability, deterministic replay, and measured costs. The research
question is *whether* structured discrete representations can preserve useful visual
information at lower computational cost — decided by experiments, not assumption
([master plan](docs/MASTER_PLAN.md) §1, §39).

> **Scope — read first.** Despite the repository name, this is **not** a motion-detection,
> tracking, or surveillance component. The implemented stages are a *discrete intensity
> tokenizer* and a *per-frame intensity-object labeller*: grayscale → quantized intensity
> map → checksummed frame store, and level-uniform 4-connected regions with positional ids
> and counted discards. There is no optical flow, background subtraction, object detection,
> cross-frame tracking, or learned model here; motion representation is the long-term
> research question (Hypothesis registry), not current capability. Not for medical,
> security, surveillance, or safety-critical use ([SECURITY.md](SECURITY.md)).

**Status: Phase 2 accepted** (intensity objects, DEC-0004; the Phase-2 contract was clarified
editorially in `VIE-SPEC-REP` 1.1.1, DEC-0005). Phase 0 (formal representation specification),
Phase 1 (basic intensity engine) and Phase 2 (intensity objects) evidence are complete; motion /
temporal linkage is the next stage and has not been started (it needs its own gate, plan §3.19).

| Document | Purpose |
|---|---|
| [`docs/MASTER_PLAN.md`](docs/MASTER_PLAN.md) | Controlling research plan (§1–§43) |
| [`docs/phase-0/representation_specification.md`](docs/phase-0/representation_specification.md) | `VIE-SPEC-REP` 1.0.0 — frozen formal representation spec |
| [`docs/phase-2/representation_specification_1.1.1.md`](docs/phase-2/representation_specification_1.1.1.md) | `VIE-SPEC-REP` 1.1.1 — **current** Phase-2 object contract (1.1.0 + editorial clarifications; 1.1.0 is kept in the same directory for provenance) |
| [`schemas/`](schemas/) | JSON Schemas (`vie.pipeline-config/1`, `vie.vocabulary/1`, `vie.framestore-manifest/1`, `vie.benchmark-result/1`, `vie.intensity-object/1`, `vie.region-set/1`, `vie.objects-config/1`, `vie.objectstore-manifest/1`, `vie.object-benchmark-result/1`); canonical copies ship inside the package, root files are symlinks |
| [`docs/phase-1/phase1_report.md`](docs/phase-1/phase1_report.md) | Phase 1 stage report (acceptance evidence) |
| [`docs/phase-2/phase2_report.md`](docs/phase-2/phase2_report.md) | Phase 2 stage report (acceptance evidence) |
| [`docs/decisions/decision_log.md`](docs/decisions/decision_log.md) | Decision records (append-only; DEC-0000/0001 stage gates, DEC-0002 audit revision, DEC-0003/0004 Phase-2 gates, DEC-0005 Phase-2 clarifications) |
| [`docs/reviews/2026-09-18-external-audit-response.md`](docs/reviews/2026-09-18-external-audit-response.md) | Point-by-point dispositions of the first external audit (DEC-0002) |
| [`docs/reviews/2026-09-18-phase2-audit-response.md`](docs/reviews/2026-09-18-phase2-audit-response.md) | Point-by-point dispositions of the Phase-2 design/readiness audit (DEC-0005) |
| [`SECURITY.md`](SECURITY.md) · [`CONTRIBUTING.md`](CONTRIBUTING.md) | Exposure rules and contribution rules |
| [`docs/hypotheses/registry.md`](docs/hypotheses/registry.md) | Versioned hypotheses H1–H5 |
| [`experiments/registry.json`](experiments/registry.json) | Formal experiment registry (EXP-0001 … EXP-0005, append-only) |

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

# Phase 2: intensity objects → object store (region labels + records + checksums)
.venv/bin/vie objects --input synthetic:moving_square --max-frames 32 \
                      --min-area 2 --output out/objects --previews 3

# validate a store (frame store or object store) or a config
.venv/bin/vie validate --target out/demo
.venv/bin/vie validate --target out/objects

# benchmarks: recorded experiments are append-only, so a non-empty --output is refused.
# Use a fresh directory for a repro run; --overwrite (deliberate, WARNING logged)
# replaces only that experiment's result.json/report.md and deletes nothing.
.venv/bin/vie benchmark --output out/bench-exp0001-repro --frames 30 --warmup 8
.venv/bin/vie benchmark-objects --output out/bench-exp0002-repro
.venv/bin/vie benchmark --output experiments/EXP-0001-quantization-baseline --overwrite

# camera batch runs need an explicit stop condition (a live camera has no end-of-stream)
.venv/bin/vie process --input camera:0 --max-frames 300 --output out/cam_store

# exploratory live viewer (NOT benchmark output; interactions are logged)
.venv/bin/vie serve --port 8000                      # loopback only (default)
.venv/bin/vie serve --host 0.0.0.0 --allowed-host preview.example.test   # explicit exposure
# the dashboard's parameter buttons POST a per-process token; plain GETs cannot
# change the viewer (state changes are logged with UTC timestamps)
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

## Intensity objects (Phase 2)

```
quantized intensity map
  → label level-uniform, 4-connected regions (von Neumann; raster discovery order)
  → ids 0..n−1 over kept regions (positional, reproducible — NOT cross-frame tracking)
  → min_area discards are counted and reported (dropped_regions / dropped_pixels); label 0
  → max_regions exceeded ⇒ RegionExtractionError (the run stops; output is never truncated)
  → vie-objectstore/1: region_labels.npz (int32) + regions.json + manifest.json
                        + checksums.json + objects_config.json + metrics.json
```

The object contract is [VIE-SPEC-REP 1.1.0](docs/phase-2/representation_specification_1.1.0.md),
an additive revision of 1.0.0: Phase-1 stores and golden hashes are unchanged, and tokens
keep their 1.0.0 semantics. Entity identity *across frames* (tracking) is explicitly out of
scope — Phase 3 owns it, and the `fingerprint` field is only a content signature (§R3.4).
Costs (extraction latency, label-map bytes, region-metadata bytes) are measured in
`experiments/EXP-0002-object-extraction/`; the reference implementation is deliberately
un-optimized until a profiling phase (plan §3.14).

JSON Schemas live in the package (`visual_intensity_engine/schemas/`) and are shipped as
package data; the repo-root [`schemas/`](schemas) entries are symlinks for browsing.

## Testing

```bash
scripts/run_tests.sh        # unit / property / integration / edge / fault-injection /
                            # regression (golden hashes) / performance
.venv/bin/ruff check visual_intensity_engine tests scripts
.venv/bin/mypy visual_intensity_engine
```

The same checks run in CI on every push and pull request
([`.github/workflows/ci.yml`](.github/workflows/ci.yml)): full suite on Python 3.11 (exact
`requirements.txt` pins — the acceptance environment) and 3.12, `vie self-test`, ruff, mypy,
and a wheel-install smoke test that proves the packaged schemas work outside a checkout.

## Engineering rules in force

Explicit typed errors (no silent fallbacks) · schema validation at module boundaries ·
versioned configs only · accuracy and cost measured together · correctness before
optimization · synthetic before real data · no stage advances without acceptance evidence
· exploratory visualization never contaminates benchmark output · failures are recorded,
not hidden.

## Scope notice

Research prototype. No medical, security, surveillance, or safety-critical use
([master plan](docs/MASTER_PLAN.md) §32, §42). The live viewer binds 127.0.0.1 by default and
has no authentication — network exposure is an explicit opt-in; no video is retained beyond
explicitly exported stores. Details: [SECURITY.md](SECURITY.md).
