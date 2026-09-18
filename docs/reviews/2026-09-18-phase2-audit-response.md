# Response to the Phase-2 design/readiness audit (2026-09-18)

- Subject: external audit "Phase 2 audit against the controlling research plan" (pasted by the
  maintainer, verdict **CONDITIONAL PASS**).
- Scope of this response: verify every audit claim against the tree, dispose of each item,
  record the changes the audit legitimately triggered, and state what remains open.
- Companion decision: **DEC-0005** (specification clarifications + the measurements below).

## 0. The premise, checked first

The audit says: *"the current public main still explicitly says Phase 2 has not started. So this
is a Phase-2 design/readiness audit, not an implementation acceptance audit."*

That is **correct for `main` and out of date for the tree under review.** Phase 2 was authorized
by the maintainer on 2026-09-18 and executed on the branch `arena/01a0b370-visual-motion-detection1`
(PR #2, open, non-draft, mergeable, CI green). `main`'s README still says Phase 1 because the PR
is not merged; merging it makes `main` state the same thing the branch does.

| Audit verdict row | Audit value | Status in this tree |
|---|---|---|
| Phase-2 specification | 🟢 strong | ✅ `VIE-SPEC-REP` 1.1.0 (+1.1.1 clarifications), DEC-0003, executable §R9 example |
| Phase-2 acceptance criteria | 🟠 incomplete | ✅ plan §10 table, five criteria met with per-criterion evidence (`docs/phase-2/phase2_report.md` §3) |
| Phase-2 implementation | ⚪ not started on main | Branch: implemented + accepted (DEC-0004); `main`: behind PR #2 |
| Scientific design | 🟢 sound | ✅ preserved; no tracking/semantics crept in |
| Main risk: segmentation ambiguity | — | ✅ addressed *before* implementation (DEC-0003) and made explicit by 1.1.1 |

Gate order actually followed (audit's §21 asked for "freeze first, then implement"):

| Step | Artifact | Commit |
|---|---|---|
| 1. Contract frozen | `docs/phase-2/phase2_plan.md`, `representation_specification_1.1.0.md`, **DEC-0003** | `1ef690f` |
| 2. Implementation, tests | `visual_intensity_engine/objects/`, CLI, 99 tests | `1ef690f`, `a86b70a` |
| 3. Evidence | EXP-0002 (51 conditions), `docs/phase-2/phase2_report.md` | `0a1138c` |
| 4. Acceptance | **DEC-0004** | `0a1138c` |
| 5. This audit's items | **1.1.1**, EXP-0003/0004/0005, acceptance fixtures, **DEC-0005** | this commit |

## 1. The six freeze items (audit §21)

| # | Item the audit requires frozen | Where it is frozen | Evidence |
|---|---|---|---|
| 1 | Connectivity policy | §R2.1–R2.2 (4-connectivity; `connectivity: 8` **must fail** validation); §R5.5: the whole policy is inside `objects_config_sha256` | `test_objects_config.py` (8 rejected), store manifests carry the hash |
| 2 | Intensity grouping policy | §R2.1 exact-level; §R2.4 (new in 1.1.1) states the policy is specification-level, composite is deferred per plan §9, future `vie.objects-config/2` | §R9 example is level-uniform by construction |
| 3 | Region schema | §R3 + `vie.intensity-object/1`, `vie.region-set/1`; §R9 normative worked example | `test_spec_example_phase2.py` asserts the spec's exact numbers |
| 4 | Deterministic region-ID ordering | §R4: raster discovery order, contiguous `0..n−1` over kept regions, reproducible-not-robust documented | `test_labeling.py` (discovery order, contiguity after drops), `test_object_store.py` (reader rejects non-contiguous) |
| 5 | Noise / empty-frame policy | §R5.1 (counted discards), §R6.5 (new in 1.1.1: zero-kept frames are valid data, never `null`/error), §R3.7 (no merge/split inside a frame) | `test_edge_cases.py::test_object_store_survives_zero_regions_and_reports_counts`, `test_phase2_acceptance_fixtures.py::test_syn_007_*` |
| 6 | Synthetic acceptance fixtures | new `tests/unit/test_phase2_acceptance_fixtures.py` (SYN-001…SYN-010 with exact counts/areas/bboxes/centroids/ids; static frames only) | 17 tests, all passing |

## 2. Disposition of every audit section

Legend: **met** = already satisfied, evidence cited · **met+** = satisfied and *strengthened by
this audit* · **open** = genuinely unfinished, stated as such.

| § | Audit ask | Disposition | Where |
|---|---|---|---|
| 1 | "object" = computational region, terminology rigid | **met** | §R2.1; README scope notice; no detection claims anywhere |
| 2 | Freeze the architecture; no tracking in this layer | **met** | `objects/` = config → labeling → extraction → store → pipeline; no tracking code paths |
| 3 | `connectivity = 4 \| 8` as versioned config, hashed | **met as specified, one deliberate narrowing** | §R2.2 specifies 4 and *rejects* 8 as an unimplemented extension point (diagonal merges interact with identity stability); §R5.5 proves the field is hashed into provenance. 8-connectivity is an **open** extension requiring a revision |
| 4 | Do not silently choose exact-level vs composite; 2A first | **met** | §R2.1 + §R2.4; matches the audit's own 2A/2B recommendation |
| 5 | Mandatory vs future metadata; no velocity/track_id | **met** | §R3 table: `level`+`symbol`, `area`, half-open `bbox`, `centroid`, `region_id`, `frame_index`, `fingerprint`; `timestamp_us`/`source_frame_id` per frame row, config hashes per manifest (per-region duplication would add ~64 B × region count for no information); `mean/min/max intensity` are trivially the level because regions are level-uniform; prohibited fields absent |
| 6 | Centroid and coordinate contract explicit, reuse Phase 1 | **met** | §R3 inherits 1.0.0 §6.1: integer `(x,y)` **is** the pixel center, origin top-left, `y` down; centroid = mean of pixel centers, float64; no second coordinate system |
| 7 | Deterministic region-ID ordering | **met** | §R4.1–R4.3; first-pixel raster order is already a total order, so no secondary sort key (level/area) is needed; positional renumbering is documented as deliberate |
| 8 | Empty frame ⇒ `objects = []`, not `None`/error; no-detection ≠ failure | **met** | §R6.5 (1.1.1); SYN-007; zero-region store test; failures raise typed errors and write no store (§R8.3) |
| 9 | Don't filter noise prematurely; keep raw + filtered counts; evaluate thresholds | **met+** | §R5.1 counts both; baseline `min_area = 1`; **EXP-0004** now measures 1/2/4/8/16 (§5 below) |
| 10 | Holes and boundaries explicitly tested | **met** | §R3.5–R3.6 (1.1.1): borders are not special; holes are not a metadata field but are preserved exactly by the label map; SYN-004 nested-ring fixture; border fixture |
| 11 | Touching regions | **met** | corner-contact stays separate, edge-contact merges, one-pixel lane stays separate (`test_edge_touching_regions_*`, SYN-003) |
| 12 | SYN-001…SYN-010 synthetic fixtures | **met** | `test_phase2_acceptance_fixtures.py` implements all ten, static-only, exact ground truth |
| 13 | Acceptance = exact assertions + run1/2/3 identical output | **met** | fixtures assert counts/areas/bboxes/centroids/levels/ids; `test_objects_pipeline_replay_is_byte_identical` now runs **three** runs and compares all bytes |
| 14 | Separate object schema, don't mutate Phase-1 schema | **met** | five new schema ids; Phase-1 schemas and stores untouched. Naming: per-region `vie.intensity-object/1` + per-store `vie.region-set/1` (the audit's conceptual `vie.intensity-objects/1` split in two so a region record and a store document are separately versioned) |
| 15 | region → frame → IntensityMap → raw frame traceability | **met** | region has `frame_index`; manifest frame rows carry `npz_key`, `source_frame_id`, `timestamp_us`, `wall_time_utc`; manifest carries the input description (name/sha256) that produced the maps |
| 16 | Complexity + measure segmentation / construction / serialization separately | **mostly met, one open item** | §R11 (1.1.1) states complexity; **EXP-0005** now measures labeling vs construction separately; memory stays a separate untimed pass; serialization **time** is still not measured (size is, exactly) |
| 17 | Report incremental cost `T_object = T_phase2 − T_phase1`, same method | **met+** | new **EXP-0003** re-measures the Phase-1 baseline untraced (EXP-0001 timed with tracing active; EXP-0002's `extraction_ns` already excludes grayscale/quantization) — §4 below |
| 18 | The research question; Phase 2 serves H2, doesn't prove it | **met** | `phase2_report.md` §5 states cost-only claims; spec §R10; hypothesis registry untouched; no H1/H2 verdict claimed |
| 19 | Explicit prohibitions (tracking, velocity, optical flow, learning, …) | **met** | package-wide inventory: the only matches are the synthetic generator's `velocity` parameter (input generation) and docstrings stating that tracking is out of scope |
| 20 | Acceptance matrix | **met** | §3 below maps every row |
| 21 | Gate: freeze six items, then audit line-by-line | **condition satisfied** | all six frozen by DEC-0003 *before* implementation; the contract is now 1.1.1 — a line-by-line implementation audit can proceed against it |
| 22 | Internal staging 2A…2F | **met, relabelled for audit traceability** | §6 below |

## 3. Acceptance matrix, mapped to artifacts

| Audit matrix row | Status in this tree | Artifact |
|---|---|---|
| Phase-2 objective defined | 🟢 | `docs/phase-2/phase2_plan.md` §1–§2, spec §R2 |
| Connected components as core method | 🟢 | `objects/labeling.py` (production) + flood-fill oracle |
| Computational-object terminology | 🟢 | §R2.1, §R10 |
| Connectivity specified | 🟢 | §R2.1–R2.2, §R5.5 |
| Same-intensity grouping specified | 🟢 | §R2.1 (exact-level) |
| Composite multi-intensity grouping | 🟡 deferred, on purpose | §R2.4 + plan §9 sequencing |
| Region metadata defined | 🟢 | §R3, `vie.intensity-object/1` |
| Centroid definition | 🟢 | §R3 (pixel-center, float64 mean) |
| Bounding box | 🟢 | §R3 half-open `[x0,x1)×[y0,y1)` |
| Empty frame | 🟢 | §R6.5, SYN-007, store test |
| Noise policy | 🟢 (+measured) | §R5.1, EXP-0004 |
| Hole behavior | 🟢 | §R3.6, SYN-004 |
| Touching regions | 🟢 | SYN-003, edge/corner tests |
| Deterministic IDs | 🟢 | §R4, labeling tests, reader validation |
| Object schema / serialization | 🟢 | `vie.intensity-object/1`, `vie.region-set/1`, `vie-objectstore/1` |
| Synthetic fixtures + ground truth | 🟢 | `test_phase2_acceptance_fixtures.py` |
| Unit / integration / property / fault tests | 🟢 | 331 tests total (this commit) |
| Performance benchmark | 🟢 | EXP-0002, EXP-0004, EXP-0005 (+EXP-0003 baseline) |
| Reproducibility evidence | 🟢 | manifest hashes, replay rule §R7.3, registry `code_commit`/environment |
| Decision record | 🟢 | DEC-0003, DEC-0004, DEC-0005 |
| Phase-2 report | 🟢 | `docs/phase-2/phase2_report.md` |
| CI gate | 🟢 | 6 jobs, green on this commit |

## 4. Incremental cost — the number the audit asked for (§17)

Method: `T_phase1` = grayscale + quantization, untraced (EXP-0003, same 18 conditions as EXP-0001);
`T_object` = labeling + record construction, untraced (EXP-0002, gradient scene), p50 per frame.
The two runs are same-method and same-machine.

| Resolution | L | `T_phase1` (ms) | `T_object` (ms) | `T_object/T_phase1` | `T_object` share of pipeline |
|---|---:|---:|---:|---:|---:|
| 320×240 | 8 | 2.29 | 5.18 | 2.27× | 69 % |
| 320×240 | 64 | 2.21 | 12.84 | 5.80× | 85 % |
| 320×240 | 256 | 2.69 | 43.52 | 16.17× | 94 % |
| 640×480 | 8 | 10.01 | 18.43 | 1.84× | 65 % |
| 640×480 | 256 | 10.08 | 103.20 | 10.24× | 91 % |
| 1920×1080 | 8 | 72.92 | 143.14 | 1.96× | 66 % |
| 1920×1080 | 64 | 73.78 | 186.53 | 2.53× | 72 % |
| 1920×1080 | 256 | 68.65 | 390.69 | 5.69× | 85 % |

Reading: Phase 2 roughly doubles the pipeline at low level counts, and its share grows with
region count (level count) and with run-heavy structure — at 1080p `ramp_bands` (one-pixel-wide
runs, EXP-0002) extraction is ~2.3 s/frame. **The cost driver is regions and runs, not pixels.**

Method correction triggered by this audit (item 17's "accounting for measurement methodology"):
EXP-0001 timed with `tracemalloc` active. Re-measuring untraced showed the inflation for the
Phase-1 stages is small — ratios 0.91–1.20 for grayscale/end-to-end, up to 1.58× for the
allocation-light quantization stage at 1080p — so EXP-0001's conclusions survive, but all
arithmetic above uses EXP-0003. EXP-0001's artifacts are unchanged and the registry records both.

## 5. Noise policy quantified (§9)

EXP-0004: identical dense per-pixel noise frames at 640×480 (L=256), only `min_area` changes.

| `min_area` | kept/frame | dropped/frame | extraction p50 | of which labeling | of which records | metadata/frame | metadata/raw | peak |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 227,660 | 0 | 2338 ms | 714 ms | 1624 ms (69 %) | 53.9 MB | 58.5× | 160 MB |
| 2 | 18,528 | 209,160 | 229 ms | 92 ms | 133 ms (58 %) | 4.5 MB | 4.9× | 30 MB |
| 4 | 9,071 | 218,586 | 125 ms | 66 ms | 59 ms (47 %) | 2.2 MB | 2.4× | 30 MB |
| 8 | 3,538 | 224,143 | 74 ms | 52 ms | 22 ms (30 %) | 0.9 MB | 0.9× | 30 MB |
| 16 | 877 | 226,795 | 49 ms | 44 ms | 6 ms (11 %) | 0.2 MB | 0.2× | 30 MB |

Reading: `min_area` is a scientific lever, not just a filter — 1→2 removes 92 % of regions for
~10× less time; and because both raw and filtered counts are recorded, the discarded structure
is recoverable. The baseline for accuracy questions remains `min_area = 1`.

## 6. Audit's 2A–2F staging, mapped

| Audit stage | This tree's artifact |
|---|---|
| 2A exact-level connected components | `objects/labeling.py` + oracle parity + §R9 |
| 2B region metadata | `objects/extraction.py`, `vie.intensity-object/1` |
| 2C deterministic serialization | `objects/store.py`, `vie-objectstore/1`, §R7 |
| 2D synthetic acceptance suite | `test_spec_example_phase2.py`, `test_labeling.py`, new fixtures file |
| 2E performance characterization | EXP-0002 (+EXP-0004/0005), EXP-0003 baseline |
| 2F acceptance report | `phase2_report.md`, DEC-0004 |

## 7. What this audit changed, and what it did not

Changed:

1. **`VIE-SPEC-REP` 1.1.1** — editorial clarifications only (grouping scope, boundaries, holes,
   merge/split, zero-kept frames, config identity, complexity/measurement). No semantics, no
   bytes, no schema id, no §R9 number changes; 1.1.0 retained for provenance.
2. `tests/unit/test_phase2_acceptance_fixtures.py` — the audit's SYN-001…SYN-010, exact ground
   truth, plus corner/edge contact, border, invariant and record-level checks (17 tests).
3. Replay test now runs **three** runs and compares all serialized bytes.
4. **EXP-0003** (Phase-1 untraced baseline), **EXP-0004** (min_area sweep), **EXP-0005**
   (labeling vs record construction) + registry entries.
5. DEC-0005; this response document; README pointers.
6. One **additive-optional** schema change: `labeling_ns`/`records_ns` in
   `vie.object-benchmark-result/1` (no version bump; existing documents stay valid).

Not changed: `docs/MASTER_PLAN.md`, `docs/hypotheses/registry.md`, `VIE-SPEC-REP` 1.0.0,
`configs/`, golden hashes, EXP-0001/0002 artifacts, and the Phase-2 implementation itself —
331 tests (including every pre-existing one) pass unchanged.

## 8. Remaining open items, stated plainly

- **8-connectivity** — unimplemented and rejected by validation, not silently approximated.
  Requires a revision (identity stability under diagonal merging).
- **Composite multi-intensity grouping** — deferred per plan §9 sequencing; needs
  `vie.objects-config/2` with an explicit `grouping` field.
- **Shape/topology (hole) descriptors** — recoverable from the label map, not stored.
- **Serialization time and memory attribution** — sizes and total peaks are measured, the
  write path's time is not.
- **min_area sweep scope** — measured at 640×480/L=256 dense noise; other scenes/resolutions
  are a planned extension (the mechanism is generic).
- **Phase 3 (tracking)** — not started; needs its own gate. The audit's §19 prohibitions remain
  in force for Phase 2.
- **PR #2 is unmerged**, which is the entire cause of the audit's ⚪ row.

## 9. Where the audit was right

Three asks produced real work rather than confirmation: the *incremental-cost* ask exposed that
EXP-0001 had timed with tracing active (now corrected by EXP-0003); the *threshold-evaluation*
ask produced the strongest cost-shape result so far (EXP-0004); and the *ambiguity* risk named in
its verdict is exactly what the 1.1.1 clarifications close. The remaining disagreement is one of
sequencing, not substance: implementation already happened behind a frozen contract, and the
contract has now been tightened where the audit found it implicit.
