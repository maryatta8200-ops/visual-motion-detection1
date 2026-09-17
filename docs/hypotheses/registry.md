# Research Hypothesis Registry (plan §37)

Append-only. A hypothesis is never silently revised: changes create version 2 entries
that reference and preserve version 1. Status ∈ {proposed, testing, accepted, rejected,
inconclusive}.

---

## H1 — v1 · proposed

- Statement: A discrete intensity representation preserves sufficient information for
  basic motion detection.
- Motivation: plan §1 central hypothesis; Q1/Q2.
- Test design (planned): detect motion events on synthetic scenes from quantized maps at
  L∈{8…256}; compare event precision/recall against ground truth from the generator.
- Baseline: motion detection on raw grayscale (float) frames, identical detector logic.
- Success threshold: ≥ 0.95 event F1 at L≥16 relative to raw baseline within ±0.02.
- Failure threshold: event F1 < 0.80 at any L ≥ 8 under the noise floors tested.
- Confounding factors: quantization boundary flicker at object edges; sensor-noise model
  fidelity; scene contrast distribution.
- Evidence: none yet (Phases 2–3 required to build the detector).
- Decision: —
- Follow-up: define the motion-event detector precisely in the Phase 3 plan.

## H2 — v1 · proposed

- Statement: Intensity-region tracking can represent simple object movement.
- Baseline: nearest-neighbor tracking on raw-intensity centroids.
- Success: track identity preserved over ≥ 500-frame controlled trajectories with
  ≤ 1 identity switch per 1,000 frames; failure: systematic switches under crossings.
- Evidence: none yet. Decision: —

## H3 — v1 · proposed

- Statement: Event-based processing (unchanged-region skipping) reduces computational
  requirements for mostly-static scenes without accuracy loss.
- Baseline: full-frame processing, identical outputs required (plan §13).
- Success: ≥ 2× end-to-end speedup at ≤ 0.1% accuracy delta on ≥ 90%-static scenes AND
  measured negative overhead on ≥ 50%-changing scenes (honest worst case).
- Evidence: none yet. Decision: —

## H4 — v1 · proposed

- Statement: Temporal symbolic representations support small AI models for motion
  prediction.
- Baseline: numeric-feature models of equal parameter count (plan §12/§17).
- Success: symbolic model ≥ numeric baseline on next-state prediction across ≥ 3 scene
  families; failure: symbolic < 0.9× baseline everywhere.
- Evidence: none yet. Decision: —

## H5 — v1 · proposed

- Statement: A hybrid raw + discrete representation can outperform either alone on
  selected tasks (plan §18/§33 Phase 9).
- Success: hybrid > max(raw-only, discrete-only) on ≥ 2 tasks under equal compute
  budgets; failure: hybrid ≤ best single path everywhere once fusion overhead is priced.
- Evidence: none yet (Phase 9). Decision: —
