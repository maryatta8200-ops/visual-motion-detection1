# Discrete Visual Intensity & Motion Representation

**Master Research, Prototype, AI Training, and Future Technology Plan — document of record**

- Plan document version: `1.0.0` (verbatim import of the project brief, 2026-09-17)
- Status: **Controlling document.** Every implementation stage must trace its objective,
  acceptance criteria, and decision records back to sections of this document.
- Stage gate rule (§1): development proceeds sequentially; no stage advances until it is fully
  specified, implemented, tested, documented, and stable under its acceptance criteria.

---

## 1. Project Vision

Develop a new computational representation for visual information in which live camera/video
frames are transformed from raw pixels into discrete intensity objects, encoded into compact
symbolic representations, and analyzed primarily through their spatial and temporal movement
patterns.

The long-term goal is to investigate whether machines can process and understand visual motion
more efficiently by operating on structured intensity representations rather than repeatedly
processing complete raw images.

This project should be treated as a research platform, not as an assumption that the proposed
representation is automatically superior to conventional computer vision.

The central research hypothesis is:

> «A sufficiently expressive discrete representation of visual intensity, spatial
> relationships, and temporal changes may preserve important visual information while reducing
> the computational burden of some motion-analysis and visual-understanding tasks.»

The system should therefore be designed around measurable experiments and comparisons.

Development must proceed sequentially. Do not advance to the next stage until the current stage
has been fully specified, implemented, tested, documented, and shown to be stable under its
defined acceptance criteria. If a stage fails, produces inconsistent results, or contains
unresolved bugs, stop progression, isolate the failure, correct it, rerun all relevant tests,
and update the documentation before continuing.

Every stage must include:

1. A precise objective.
2. Defined inputs and outputs.
3. A formal data schema.
4. Unit tests.
5. Integration tests.
6. Edge-case tests.
7. Performance measurements.
8. Reproducibility metadata.
9. Visualization or inspection tools where applicable.
10. Acceptance criteria.
11. Known limitations.
12. A decision record stating whether the stage is accepted, rejected, or requires revision.

No feature should be added merely because it is conceptually interesting. Each feature must
have a defined research purpose, measurable benefit, computational cost, and rollback path.

---

## 2. Core Concept

```
RAW CAMERA FRAME
→ GRAYSCALE / INTENSITY REPRESENTATION
→ INTENSITY QUANTIZATION
→ INTENSITY TOKENS
→ SPATIAL OBJECT EXTRACTION
→ TEMPORAL TRACKING
→ MOVEMENT PATTERN ENCODING
→ LEARNED VISUAL REPRESENTATION
→ MOTION / EVENT UNDERSTANDING
```

The original image must remain available as ground truth. Never permanently discard the raw
frame during research. Every transformation must be traceable to its source frame through
frame identifiers, timestamps, configuration versions, and processing metadata.

The system must support deterministic replay: given the same input, configuration, software
version, and random seed, it should reproduce the same output within documented numerical
tolerances.

---

## 3. Core Engineering Principles

1. Build the smallest testable version first.
2. Change one major variable at a time during experiments.
3. Separate research code from production runtime code.
4. Keep raw data, intermediate representations, predictions, and metrics separately identifiable.
5. Never compare methods using different input conditions without documenting the difference.
6. Measure accuracy and computational cost together.
7. Preserve failed experiments and negative results.
8. Use versioned configuration files rather than hidden parameters.
9. Validate data schemas at module boundaries.
10. Fail explicitly when inputs are invalid instead of silently producing unreliable outputs.
11. Use synthetic data before real-world data.
12. Establish baselines before optimizing the proposed method.
13. Do not introduce learned components until the non-learned pipeline is understood.
14. Do not optimize performance before correctness is established.
15. Do not claim generalization from a narrow dataset.
16. Do not advance stages based only on visual plausibility.
17. Maintain backward compatibility for stored experiment results whenever practical.
18. Record uncertainty and confidence rather than presenting ambiguous outputs as facts.
19. Treat tracking identity as provisional and allow identity correction.
20. Ensure all experiments can be stopped, resumed, and audited.

---

## 4. Fundamental Representation

A conventional image contains continuous or high-resolution pixel values. The proposed system
converts these values into a finite number of intensity classes. Example with 16 levels:

```
I0  = Black              I8  = Medium
I1  = Very Dark          I9  = Medium-High
I2  = Dark               I10 = High
I3  = Dark-Low           I11 = Bright-Low
I4  = Low                I12 = Bright
I5  = Low-Medium         I13 = Very Bright
I6  = Medium-Low         I14 = Extremely Bright
I7  = Medium             I15 = White
```

The actual number of levels must remain configurable. Test: 8, 16, 32, 64, 128, 256 levels.
Do not assume that more levels are always better. The system must determine experimentally
which representation provides the best trade-off between information preservation and
computational efficiency.

The representation specification must define: numeric range; data type; quantization boundary
behavior; handling of NaN and infinite values; handling of clipped or saturated pixels;
whether intensity IDs begin at zero or one; whether intensity levels are globally fixed or
frame-adaptive; how metadata identifies the quantization configuration; whether the
representation is lossless with respect to the quantized map; serialization and
deserialization rules.

Before any downstream module is implemented, the quantized map must pass round-trip tests and
boundary-value tests.

---

## 5. Intensity Vocabulary

Each quantized intensity receives a machine-readable identity (`I0`, `I1`, …) treated as
visual tokens. The system should eventually support token sequences instead of only raw
numerical pixel values. The vocabulary must include: token ID; numeric intensity interval;
representative intensity value; human-readable label; quantization version; optional semantic
metadata; serialization format; compatibility rules between vocabulary versions.

Token IDs must not be interpreted as naturally ordered semantic concepts unless the ordering
is explicitly defined. A token ID is an identifier; its numerical value must not accidentally
introduce false meaning into models or analyses.

---

## 6. Quantization Engine

Implement an independent intensity-quantization module. Input: RGB frame → grayscale frame →
quantized intensity map. Support multiple quantization strategies (uniform, histogram-based,
adaptive/local, learned, dataset-specific). Initially use uniform quantization because it is
easy to understand and benchmark.

The engine must explicitly define: color-space conversion; luminance coefficients; channel
ordering; alpha-channel handling; input bit depth; normalization range; clipping behavior;
missing-data behavior; quantization boundary rules; output memory layout; CPU and optional GPU
implementations. The first implementation must include reference tests using known RGB values
and expected grayscale outputs; optimized implementations must be compared against the
reference within documented tolerance. Each strategy must be evaluated independently.

---

## 7. Preserve Spatial Information

Every intensity token must retain spatial information:

```
TOKEN = { intensity, x, y, frame_index, timestamp }
```

Later extended with local_gradient, neighborhood, region_id, velocity, direction, persistence.
Build the representation progressively. The coordinate system must be formally defined
(pixel-center vs pixel-corner, origin, axis direction, int vs float coordinates, resize and
crop behavior, coordinate transformation metadata, timestamp source and precision,
frame-index semantics). Every token and region must be traceable to a source frame.

---

## 8. Convert Intensities Into Objects

Determine whether neighboring tokens form meaningful structures (connected-component
analysis). "Object" initially means a computational region, not necessarily a real-world
object — this distinction must remain explicit. The segmentation module must define
connectivity, grouping of neighboring levels, minimum region size, noise filtering, boundary
handling, merge/split rules, deterministic object-ID assignment, holes, touching regions,
empty frames, maximum region count, computational complexity. Object IDs are local to a frame
unless tracking explicitly promotes them. Validate first on synthetic patterns with known
connected components.

---

## 9. Multi-Intensity Objects

Real structures contain multiple intensity levels; represent intensity composition, spatial
arrangement, boundaries, centroid, area, shape, internal gradients. Introduce only after
single-intensity regions are stable. Compare per-level regions vs composite regions;
the grouping policy must be configurable and evaluated.

---

## 10. Frame-to-Frame Comparison

The most important component is temporal analysis: track how intensity regions change
(displacement, area/intensity/shape change, appearance, disappearance, merging, splitting,
persistence). Must explicitly handle missing detections, occlusion, new/vanishing regions,
fragmentation, camera motion, frame drops, variable intervals, timestamp irregularities,
duplicates, out-of-order frames, illumination changes. Begin with deterministic
nearest-neighbor matching on controlled synthetic data. Every match carries a confidence
score and evidence.

---

## 11. Movement Representation

Represent movement mathematically (dx, dy, distance, velocity, acceleration, direction,
rotation, scale change, intensity/shape change, duration) and symbolically (MOVE_RIGHT,
EXPAND, APPEAR, MERGE, …). Labels are initially for analysis/visualization; the eventual AI
may discover latent representations. Feature definitions must respect elapsed time, coordinate
scaling, camera motion compensation, missing observations, smoothing, numerical stability,
threshold selection, uncertainty. Symbolic labels must include UNKNOWN/AMBIGUOUS states.

---

## 12. Movement Pattern Encoding

Convert temporal observations into compact sequences. Compare numeric vectors, symbolic
tokens, binary representations, run-length encoding, event-based encoding, learned embeddings
— evaluated for storage size, serialization/decoding speed, information retention, robustness,
model compatibility, interpretability, error propagation, variable-length support. The
encoding layer must not silently discard information.

---

## 13. Event-Based Representation

Investigate avoiding repeated processing of unchanged information (change detection → process
changed areas only). Must distinguish true change from noise, artifacts, lighting variation,
camera movement, quantization instability. Measure the cost of change detection; evaluate
against full-frame processing with identical accuracy requirements including worst-case
scenes.

---

## 14. Motion Memory

Temporal memory per tracked structure (position history → trajectory, velocity, acceleration,
direction, persistence, periodicity, behavior). Must define history limits, retention policy,
missing-data handling, termination/re-identification rules, eviction, checkpointing, memory
limits, thread-safety. Memory must not grow without bound.

---

## 15. Pattern Library

Database of discovered patterns with versioning, deduplication, similarity search, provenance,
retirement, confidence updates, dataset split isolation, leakage prevention, human inspection,
export/import, reproducible indexing. Evaluation-data patterns must not leak into training.

---

## 16. Self-Supervised Learning

Use temporal structure of video itself: next-state prediction, motion prediction,
missing-state reconstruction, pattern clustering, temporal consistency. Tasks must define
input window, horizon, targets, loss, masking, negatives, leakage prevention, metrics,
baselines. Identify camera/scene memorization via cross-scene evaluation.

---

## 17. AI Architecture

Start small: statistical models → classical ML → small temporal NN → CNN+temporal →
transformer/SSM → hybrid symbolic+neural. Purpose: determine whether the representation itself
provides an advantage before spending compute on large models. Record parameter count,
training/inference time, memory, hardware, splits, seeds, hyperparameters, runs, variance,
failures, calibration. Never compare models with different preprocessing/splits without
labeling the comparison non-equivalent.

---

## 18. Hybrid Vision Architecture

Two information paths (raw frame + discrete representation) fused for visual understanding,
with mandatory ablations: raw-only, discrete-only, fixed fusion, learned fusion, and
equal-computational-budget comparisons. Fusion must justify its cost, not only accuracy.

---

## 19. Benchmark Against Existing Computer Vision

Mandatory. Compare against frame differencing, background subtraction, optical flow,
conventional feature tracking, CNN-based vision, video transformers, event-based vision where
appropriate. Measure time, memory, CPU/GPU, representation size, latency, energy, accuracy,
tracking accuracy, false positives/negatives, robustness, scalability — with identical inputs,
defined preprocessing, equivalent outputs, warm-up policy, multiple runs, uncertainty
estimates, separate train/inference costs, hardware/software records, worst- and average-case
workloads. Include simple baselines before advanced ones.

---

## 20. First Experimental Prototype

Intentionally small: VIDEO → GRAYSCALE → 16-LEVEL QUANTIZATION → INTENSITY MAP → CONNECTED
REGIONS → CENTROID DETECTION → FRAME-TO-FRAME TRACKING → MOVEMENT VECTOR → MOVEMENT PATTERN.
Output shows original, grayscale, quantized map, regions, IDs, trajectories, encoded movement
sequence, processing time, memory. Must include non-interactive batch mode (required for
reproducible experiments) in addition to live visualization, input validation, graceful camera
failure handling, end-of-file handling, frame-drop reporting, configuration export, result
export, logging, deterministic replay for video files, and a synthetic-frame test mode. The
prototype is not accepted until it processes controlled test videos correctly with stable
outputs across repeated runs.

---

## 21. Visualization

Research dashboard displaying original / quantized / intensity objects / trajectories /
symbolic representation / processing metrics, with real-time parameter changes (intensity
levels, frame rate, resolution, threshold, region size, tracking sensitivity, temporal
window). Must show current configuration, frame index/timestamp, dropped frames, active
tracks, confidence, segmentation count, latency, queue depth, CPU/memory, warnings, and
live/delayed/replayed status. Interactive changes must be logged; the dashboard must separate
exploratory visualization from benchmark output.

---

## 22. Experimental Questions

Q1 information loss of discretization; Q2 optimal level count; Q3 movement accuracy from
region trajectories; Q4 ignoring unchanged regions without accuracy loss; Q5 compact symbolic
prediction of future states; Q6 small-model learning on this representation; Q7 memory
reduction; Q8 latency reduction; Q9 energy reduction; Q10 which tasks benefit most. Every
question: variables, controls, baselines, dataset requirements, statistics, minimum
meaningful improvement, failure criteria, confounds — defined before experimentation.

---

## 23. Dataset Strategy

Start synthetic (moving square/circle, multiple objects, crossings, appear/disappear,
rotation, expansion, predictable trajectories), then progress to real-world complexity. Each
dataset documents source, license, resolution, frame rate, duration, categories, annotation,
splits, biases, conditions, density, complexity, quality issues. Synthetic sets must include
randomized variation.

---

## 24. Ground-Truth System

RAW VIDEO + ground-truth motion + quantized representation + detected motion + AI prediction,
distinguishing pixel-, region-, track-, motion-vector-, event-, and prediction-level truth.
Record annotator agreement and uncertainty for weak labels.

---

## 25. Compression Experiment

RAW vs quantized vs object vs movement-event data sizes, plus information retention. Target:
maximum useful information per computational cost. Include in-memory/serialized size,
metadata and index overhead, encode/decode time, random access, error resilience,
reconstruction quality, downstream performance. A representation is not compact if metadata
and indexing costs are excluded.

---

## 26–28. Adaptive Resolution, Adaptive Intensity, Adaptive Temporal Resolution

Region-adaptive detail, locally adaptive quantization, and event-driven frame processing —
each compared against fixed baselines under equal quality/latency constraints, with documented
triggering, boundary handling, temporal consistency, aliasing and missed-event analysis.

---

## 29. Future Visual Token

Token evolution from `I7` to structured tokens (intensity, position, region, direction,
velocity, persistence, gradient, timestamp) and eventually learned embeddings. Every extension
introduced through a schema version; older data remains readable or is explicitly migrated;
optional fields have defined defaults; missing values are not confused with zeros.

---

## 30. Visual Language Hypothesis

Investigate (do not assume) whether recurring structures form a machine-learned visual
vocabulary improving prediction, compression, interpretability, transfer, or downstream
performance. A vocabulary that merely renames features without measurable benefit is not a
successful visual language.

---

## 31. Long-Term AI Architecture

Layered: camera → visual encoder → discrete visual field → spatial object engine → temporal
pattern engine → visual memory → pattern discovery → high-level event model → prediction.
Separation between raw sensory information and structured internal representation; every layer
has a defined contract, measurable output, independent tests; high-level models must not
conceal lower-level failures.

---

## 32. Research Safety and Scope

General CV research platform; no medical/security/surveillance/safety-critical claims from
early prototypes. Sensitive applications require separate validation, privacy review, data
governance, bias evaluation, security testing, human oversight, failure-mode and adversarial
analysis, regulatory review, deployment limits.

---

## 33. Development Phases

| Phase | Deliverable | Key acceptance criteria |
|---|---|---|
| 0 — Mathematical definition | Formal representation specification | fields/units defined; boundaries specified; examples; schemas validate; round-trip serialization tests pass; no downstream work before approval |
| 1 — Basic prototype | Working real-time intensity engine (video → grayscale → quantization → visualization) | correct grayscale; correct quantization at all supported levels; stable repeated runs; invalid input handled; measured latency/memory; unit+integration tests pass |
| 2 — Intensity objects | Intensity-object engine | correct on synthetic components; noise/empty-frame behavior; stable metadata; deterministic region IDs; measured cost |
| 3 — Temporal tracking | Real-time movement tracker | correct on controlled trajectories; appearance/disappearance/merge/split handled; confidences; bounded memory; frame-drop/timestamp tests; ground-truth comparison |
| 4 — Symbolic motion encoding | Movement-language prototype | correct features; thresholds; UNKNOWN states; documented lossiness; perturbation stability; numeric-vs-symbolic comparison |
| 5 — Dataset generation | Training dataset | reproducible; no leakage; valid annotations; integrity checks; versioned metadata; balanced coverage |
| 6 — AI training | First learned representation | baselines included; splits isolated; multiple seeds; overfitting checked; failures documented; cost recorded |
| 7 — Benchmarking | Quantitative benchmark report | equivalent conditions; multiple datasets/hardware; accuracy+resource metrics; uncertainty; reproducible scripts; no unsupported claims |
| 8 — Optimization | Efficient runtime engine | only after profiling finds real bottlenecks; regression-tested vs reference |
| 9 — Hybrid architecture | Hybrid vision model | raw/discrete/hybrid ablations; equal budgets; fusion overhead measured; no hidden raw-data dependence |
| 10 — Generalization | Generalization report | cross-dataset/environment; lighting and camera-motion tests; domain-shift documentation; deployment limits |

---

## 34. Software Architecture

Modular components: input (camera/video), preprocessing (grayscale/normalization/quantization),
intensity (vocabulary/intensity-map), objects, tracking, motion, learning, benchmarks,
visualization, schemas, tests (unit/integration/regression/performance), configs, logs,
experiments. Every component replaceable; each module exposes input/output/config schemas,
error behavior, logging behavior, performance expectations, test coverage, version
information. Dependency injection so reference and optimized implementations can be compared.

---

## 35. Testing and Quality Assurance

Required at every stage: unit, integration, regression, property-based, synthetic scenario,
stress, fault-injection, performance tests. A stage cannot be complete while critical or
high-severity defects remain unresolved.

---

## 36. Reproducibility

Record dataset, resolution, frame rate, levels, quantization method, algorithm/model versions,
hardware, runtime, memory, accuracy, seed; OS, library versions, interpreter version,
configuration file, git commit, input/output checksums, repetitions, warm-up policy,
measurement method, timezone/timestamp format, manual interventions. Machine-readable results
plus human-readable reports.

---

## 37. Versioned Research Hypotheses

H1 discrete intensity preserves sufficient information for basic motion detection; H2
intensity-region tracking represents simple movement; H3 event-based processing reduces
compute for static scenes; H4 temporal symbolic representations support small AI models; H5
hybrid representation can outperform either alone. Each hypothesis: version, motivation, test
design, baseline, success/failure thresholds, confounds, evidence, decision, follow-up. Never
revise a hypothesis after seeing results without preserving the original version.

---

## 38. Experiment Management

Formal registry: unique experiment ID, research question, hypothesis, configuration, dataset
version, code version, hardware, start/end, results, logs, artifacts, decision status.
Experiments resumable; results never overwritten; separate namespaces for raw inputs,
intermediate outputs, final outputs, temporary files, failed runs, published results.

---

## 39. Success Criteria

Not "looks interesting". Success requires measurable evidence (e.g., comparable accuracy +
lower compute/memory/latency/representation, or higher accuracy at similar cost, or new
capabilities). Thresholds defined after baseline experiments; success is task-specific and
reported separately per task.

---

## 40. Failure Analysis

Classify failures (quantization loss, segmentation error, identity switch, missed/false
detection, camera-motion/lighting confusion, occlusion, encoding loss, model error, resource
exhaustion, timing, leakage, reproducibility failure) with input example, expected/actual,
first diverging module, severity, frequency, correction, and whether the correction changes
the research question. Do not hide failures behind aggregate metrics.

---

## 41. Security, Privacy, and Data Governance

Document input sources; access controls; encryption where appropriate; retention policies;
PII removal; audit logs; credential safety; protection against malformed inputs; separation of
research and deployment data. Do not collect or retain camera data unnecessarily.

---

## 42. Deployment Readiness Gates

Correctness, robustness, performance, security review, privacy review, failure-mode analysis,
monitoring design, rollback testing, documentation review, human approval. Research success
does not imply operational safety.

---

## 43. Final Long-Term Vision

Investigate a computational layer between raw visual sensing and high-level AI: camera →
intensity field → discrete visual objects → spatial relationships → temporal movement patterns
→ compact visual representation → AI → understanding/prediction. Evidence-driven: the first
objective is to determine how much useful visual information can be represented through
discrete intensity objects and temporal movement patterns, and at what computational cost.
Progression gated by evidence; complete and validate one stage before beginning the next;
preserve raw data, intermediate results, failed experiments, and decision records; treat every
claimed improvement as provisional until reproduced against appropriate baselines under
documented conditions.
