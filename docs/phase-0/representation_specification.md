# Formal Representation Specification — Phase 0 Deliverable

- Spec ID: `VIE-SPEC-REP` — **version 1.0.0 (FROZEN)**
- Date frozen: 2026-09-17
- Governing plan: [`docs/MASTER_PLAN.md`](../MASTER_PLAN.md) §4, §5, §6, §7, §33 (Phase 0)
- Status: **Accepted** (see `docs/decisions/DEC-0000-phase-gates.md` and the Phase 0 row in
  `docs/phase-1/phase1_report.md` §Acceptance)
- Normative language: **MUST / MUST NOT / SHOULD / MAY** per RFC 2119.
- Implementation binding: schemas in [`schemas/`](../../schemas/), code in
  `visual_intensity_engine/`, acceptance evidence in `docs/phase-1/phase1_report.md`.

No downstream module (segmentation, tracking, learning) may be implemented against any
behavior not defined here. Changes require a new spec version; v1.0.0 stays readable.

---

## 1. Definitions

| Term | Definition |
|---|---|
| **frame** | A 2-D array of pixels, one point in time, produced by a frame source. |
| **sample** | One numeric value of a frame (per channel). |
| **luminance Y** | Weighted combination of channels mapped to `[0.0, 1.0]` (normalized). |
| **intensity level (token ID)** | Integer in `{0 … L−1}` produced by quantizing `Y`. |
| **L (levels)** | Number of discrete intensity classes. Supported: any integer `2 ≤ L ≤ 256`; REQUIRED test matrix: `{8, 16, 32, 64, 128, 256}`. |
| **intensity map** | 2-D `uint8` array of intensity levels, shape `(H, W)`, C-contiguous, row-major. |
| **token** | `{intensity_id, x, y, frame_index, timestamp_us}` — spatial/temporal binding of a level (Phase 0 defines it; instantiation begins Phase 2). |
| **frame store** | On-disk bundle: `intensity_maps.npz` + `manifest.json` + `checksums.json`. |

---

## 2. Frame & source contract (input domain)

1. **Array type:** `numpy.ndarray`, ndim `2` (already-gray) or `3` (channel-last).
2. **Channel order:** **RGB** (red = index 0). Sources that decode BGR MUST convert before
   handing frames to the engine; the engine validates and rejects other orders explicitly.
3. **Channels:** exactly 3, or 4 (RGBA) only when `alpha_policy` is set:
   - `drop` (default): alpha channel discarded; count recorded in frame metadata.
   - `composite_black`: RGB composite over black, `rgb' = rgb · a` in normalized space.
   - `error`: 4-channel input raises `FrameValidationError`.
4. **Bit depth / dtypes:** `uint8` (max 255), `uint16` (max 65535), `float32`/`float64`
   (domain `[0.0, 1.0]`). Mixed dtypes across frames of one store are NOT allowed; the
   source records one dtype per store.
5. **Normalization:** divide by the dtype maximum (float: divide by 1.0, i.e. identity).
   This is the ONLY normalization in Phase 1. No histogram stretching, no gamma.
6. **Float range policy:** values outside `[0,1]`:
   - `strict` (default): `FrameValidationError` (fail explicitly, plan §3.10).
   - `clip`: values clamped into `[0,1]`; clamp count recorded in frame metadata.
7. **Non-finite values (NaN, +Inf, −Inf):**
   - `strict` (default): `NonFinitePixelError` (subclass of `FrameValidationError`) including
     the offending count and first `(y, x)` location.
   - `coerce`: `NaN → 0.0`, `+Inf → 1.0`, `−Inf → 0.0`; per-frame `non_finite_coerced` count
     MUST be recorded in the manifest. Silent loss is prohibited (plan §3.10).
8. **Clipped / saturated pixels:** no special-casing. `255` (uint8) is simply `Y = 1.0 → I(L−1)`;
   `0 → I0`. Saturation *detection* is future work and out of scope for v1.0.0.
9. **Missing data:** a frame that cannot be produced (read failure, EOF) is never replaced by a
   synthetic blank silently. Sources report it; the pipeline records a dropped-frame entry.
   An `ndarray` of the wrong shape/dtype is invalid input, not missing data.
10. **Empty frames:** `H = 0` or `W = 0` → `FrameValidationError`. Minimum supported: `1×1`.

---

## 3. Grayscale / luminance representation

1. **Conversion (channel → Y), normalized domain:**

   ```
   Y = c_r · (R / D) + c_g · (G / D) + c_b · (B / D),      D = dtype max
   ```

2. **Luminance standards (configurable, one per store):**

   | id | coefficients (R, G, B) | note |
   |---|---|---|
   | `bt601` (default) | 0.299, 0.587, 0.114 | ITU-R BT.601 luma; matches common CV convention |
   | `bt709` | 0.2126, 0.7152, 0.0722 | ITU-R BT.709 |
   | `average` | 1/3, 1/3, 1/3 | unweighted mean; control condition |

   Coefficient sums are 1.0 within float64 rounding; Y ∈ `[0,1]` for in-range inputs.
3. **Working dtype:** the reference implementation computes in **float64** and returns a
   normalized float64 array in `[0.0, 1.0]`. This float64 field is the canonical input to
   quantization.
4. **Display convenience:** `to_uint8_gray(y) = min(rint(y·255), 255)` — visualization only;
   it is NOT part of the quantization chain.
5. **Reference vs optimized implementations:** the reference implementation is normative.
   Any future optimized implementation MUST match it within tolerance **±1e-12** absolute on
   `Y` for identical inputs, and MUST produce **identical** intensity maps (integer outputs
   admit no tolerance). Registering an implementation without such a test is prohibited.

**Reference vectors (uint8, bt601):**

| RGB | Y (float64) |
|---|---|
| (0,0,0) | 0.0 |
| (255,255,255) | 1.0 |
| (255,0,0) | 0.299 |
| (0,255,0) | 0.587 |
| (0,0,255) | 0.114 |
| (255,255,0) | 0.886 |
| (49,49,49) | 49/255 ≈ 0.19215686… |

---

## 4. Discrete intensity representation

1. **IDs begin at 0**: `I0 … I(L−1)`. `uint8` storage supports all `L ≤ 256`.
2. **Boundary rule — `floor_right_open` (the only rule in v1.0.0):**

   ```
   level(y) = min( floor( y · L ),  L − 1 )        for y ∈ [0, 1]
   ```

   Half-open bins: `y ∈ [k/L, (k+1)/L) → I(k)`; the right-most bin is closed: `y = 1 → I(L−1)`.
   Boundary values therefore round **up** (e.g. `y = 0.0625, L = 16 → I1`, while
   `y = 0.06249… → I0`). For the required power-of-two level counts, `k/L` and `y·L` are
   exact in binary floating point at the boundaries, so the rule is exact, not approximate.
3. **Monotonicity (invariant):** `y₁ ≤ y₂ ⟹ level(y₁) ≤ level(y₂)`. Guaranteed by construction;
   enforced by property tests.
4. **Quantization scope:** `global_fixed` — bin edges depend only on `L` and are identical for
   every frame of a store. `per_frame_adaptive` is reserved for a later phase and MUST NOT be
   emitted by Phase 1 code.
5. **Losslessness:** the intensity map is stored **losslessly** (exact `uint8` round-trip).
   The transform raw→map is **lossy** with respect to `Y` (bin width `1/L`, max quantization
   error `1/(2L)` in normalized units, e.g. ≤ 0.03125 for `L = 16`). This loss is the subject
   of research question Q1 and must never be described as negligible without measurement.
6. **Determinism:** quantization is a pure function of `(Y, L)`; no RNG, no environment
   dependence. Same input bytes → same output bytes on any platform.
7. **Memory layout:** `(H, W)` `uint8`, C-contiguous, row-major, x = column index, y = row index.

**Boundary example table (L = 16, uint8 input domain):**

| input value v (uint8) | Y = v/255 | Y·16 | level |
|---|---|---|---|
| 0 | 0.0 | 0.0 | I0 |
| 15 | 0.05882… | 0.9412 | I0 |
| 16 | 0.06274… | 1.0039 | I1 |
| 127 | 0.49803… | 7.9686 | I7 |
| 128 | 0.50196… | 8.0314 | I8 |
| 254 | 0.99608… | 15.937 | I15 |
| 255 | 1.0 | 16.0 (clamped) | I15 |

Float-domain boundary values: `y = 1/16 → I1`, `y = 7/16 → I7`, `y = 15/16 → I15`,
`y = (1/16) − ε → I0`.

---

## 5. Intensity vocabulary

1. Machine-readable identity per level. Serialized JSON (schema
   [`schemas/intensity_vocabulary.schema.json`](../../schemas/intensity_vocabulary.schema.json),
   `vie.vocabulary/1`).
2. Per token: `token_id` (0-based), `symbol` (`I<k>`), half-open numeric interval
   `[lower_inclusive, upper_exclusive)` (last token closed), `representative_value`
   (interval midpoint `(k + 0.5)/L`, deterministic), `label` (human-readable).
3. **Canonical labels for L = 16** (from plan §4): `Black, Very Dark, Dark, Dark-Low, Low,
   Low-Medium, Medium-Low, Medium, Medium, Medium-High, High, Bright-Low, Bright, Very Bright,
   Extremely Bright, White`. Note two distinct tokens are both labeled “Medium” (I7, I8) —
   labels are human metadata only. For other `L`, labels are systematic
   (`Level <k>` with `I0 = Black`, `I(L−1) = White`).
4. **Identifier semantics (plan §5):** `token_id` is an identifier. Downstream models MUST NOT
   receive raw token IDs as numeric features without an explicitly documented ordering
   decision; until such a decision is recorded, models consume either one-hot encodings or the
   `representative_value` (which IS ordered by construction).
5. **Vocabulary version:** `uniform-l<L>-v1`. The vocabulary embeds the quantization identity
   (strategy, levels, boundary rule, scope) and the source domain (`bt601-normalized`), so a
   store is self-describing.
6. **Compatibility rule:** two vocabulary instances are **compatible** iff strategy, levels,
   boundary rule, scope, and source domain are all equal. Readers MUST reject stores whose
   vocabulary is incompatible with the requested configuration (`CompatibilityError`).
   ID remapping across incompatible vocabularies is future work.
7. **Deterministic palette:** visualization colors are generated from a recorded
   `palette_seed` (default 0) with a documented deterministic algorithm — same seed + levels →
   same colors, so published figures are reproducible.

---

## 6. Spatial representation & coordinate system (normative from Phase 2 onward)

1. **Pixel-center convention.** Integer coordinate `(x, y)` denotes the **center** of the
   pixel at column `x`, row `y`. A pixel covers the half-open unit square
   `[x − 0.5, x + 0.5) × [y − 0.5, y + 0.5)`.
2. **Origin & axes:** origin `(0, 0)` = center of the **top-left** pixel; `x` grows right
   (column index), `y` grows **down** (row index). This matches array indexing
   `frame[y, x]`.
3. **Types:** pixel coordinates are integers; derived quantities (centroids, velocities) are
   float64. Sub-pixel quantities never claim pixel-center semantics without saying so.
4. **Resize:** scaling by `(sx, sy)` maps pixel-center `(x, y) → (x·sx, y·sy)` **only** when
   the resize uses pixel-center-aligned interpolation (e.g. area/INTER_AREA conventions);
   the transform `(sx, sy, method)` MUST be recorded in frame metadata when it occurs.
5. **Crop:** cropping at offset `(x₀, y₀)` maps `(x, y) → (x − x₀, y − y₀)`; the offset MUST be
   recorded.
6. **Frame-index ↔ geometry:** `W` = number of columns (x extent), `H` = number of rows
   (y extent). Bounds checks: `0 ≤ x < W`, `0 ≤ y < H`.

---

## 7. Temporal representation

1. **`frame_index`:** 0-based, assigned in **processing order**, increments by 1 per processed
   frame within a store. It is a storage/order identifier, NOT a time measurement.
2. **`timestamp_us`:** int64 **media time** in microseconds since the start of the stream
   (first frame conventionally 0). Derived for synthetic sources as
   `frame_index · 10⁶ / fps`; decoded for files from the container (e.g. `POS_MSEC · 1000`).
3. **Wall clock:** RFC 3339 UTC (`…Z`), recorded only as provenance (processing time), never
   as media time.
4. **Irregularities:** sources MUST detect and report (never silently fix): duplicate
   timestamps, non-monotonic timestamps, frame drops (timestamp gap > 1.5 × nominal frame
   period), duplicate frames (identical payloads), out-of-order delivery. Phase 1 behavior:
   `strict=True` → `SourceError`; `strict=False` → proceed, record in
   `manifest.frames[].warnings` and `counts.dropped_frames`.
5. **Precision:** media timestamps are integer microseconds; no floating seconds in stored
   data.

---

## 8. Token & record schemas; extension policy

1. **Minimal token (Phase 0/1 definition):**
   ```json
   {"intensity_id": 0, "x": 12, "y": 34, "frame_index": 5, "timestamp_us": 200000}
   ```
2. **Extensions** (local_gradient, neighborhood, region_id, velocity, …) arrive exclusively
   through **schema version increments** (`vie.token/2`, …). Rules: optional fields MUST have
   defined defaults; absence (`null`) MUST be distinguishable from zero; readers MUST accept
   any older version they declare support for (plan §29).
3. **Phase 1 frame record** (one row of `manifest.frames`, schema
   [`schemas/framestore_manifest.schema.json`](../../schemas/framestore_manifest.schema.json)):
   `frame_index`, `source_frame_id`, `timestamp_us`, `wall_time_utc` (nullable),
   `non_finite_coerced`, `clipped_to_range`, `warnings[]`.
4. **Uncertainty representation:** confidence values are float in `[0,1]`; **unknown is
   `null`, never 0** (plan §3.18). Phase 1 emits no confidence values; this rule is binding on
   all future phases.

---

## 9. Serialization & storage rules

1. **Bundle layout (`vie-framestore/1`):**

   ```
   <outdir>/
   ├── intensity_maps.npz   # zip of .npy entries, one per frame, key f%06d
   ├── manifest.json        # config + vocabulary + provenance + per-frame table
   └── checksums.json       # sha256 of every other artifact
   ```

2. **NPZ rules:** entries stored as raw `.npy` (no pickle, `allow_pickle=False`), keys
   `f000000`, `f000001`, … in ascending frame order. Variable frame sizes within one store
   are supported.
3. **Byte determinism:** the writer MUST emit byte-identical `.npz` files for identical
   inputs in the same environment: sorted entry names, fixed ZIP timestamps
   (`1980-01-01 00:00:00`), fixed compression level. Stored data therefore has a stable
   checksum across repeated runs (plan §2, §36).
4. **Cross-environment determinism:** array-level equality is guaranteed; byte-level equality
   is guaranteed only with the recorded library versions (provenance block).
5. **Round-trip guarantee:** `read(store)` reproduces every intensity map **exactly**
   (`uint8` equality), plus config hash and vocabulary. Verified by integration tests.
6. **Integrity:** `checksums.json` covers `intensity_maps.npz` and `manifest.json`; readers
   MUST verify before use (`SerializationError` on mismatch). Manifest wall-clock fields are
   excluded from replay comparisons but included in integrity checksums.
7. **Replay comparison rule:** two runs are *replay-identical* iff `intensity_maps.npz` bytes
   are equal and manifests are equal ignoring `provenance.created_at_utc` and
   `provenance.duration_s`.

---

## 10. Configuration & provenance

1. **Configuration is a versioned JSON file** (plan §3.8), schema
   [`schemas/pipeline_config.schema.json`](../../schemas/pipeline_config.schema.json),
   `vie.pipeline-config/1`, `additionalProperties: false` everywhere. Hidden parameters are
   prohibited.
2. **Config identity:** SHA-256 over the canonical form (UTF-8, sorted keys, no insignificant
   whitespace). Every output references `config_sha256`; that reference is the config version
   identifier.
3. **Provenance block** (written into every manifest): code git commit + dirty flag, Python
   version, numpy/PIL/jsonschema versions, platform, `created_at_utc`, input file checksum
   (SHA-256) when the input is a file, seed.
4. **Seeds:** every stochastic component (synthetic generators now; training later) takes the
   config `seed`. Default 0. No hidden global RNG state.

---

## 11. Validation & error behavior (module boundary contract)

Typed error hierarchy — modules fail explicitly, never silently (plan §3.10):

| Error | Raised when |
|---|---|
| `ConfigError` | config missing, unreadable, fails JSON-Schema validation, or references unavailable strategy/implementation |
| `FrameValidationError` | frame wrong ndim/channels/dtype/shape, out-of-range floats (strict), bad alpha |
| `NonFinitePixelError` | NaN/±Inf pixels under `non_finite_policy = strict` |
| `SourceError` | camera/video cannot be opened, unreadable, or violates timestamp rules in strict mode |
| `SerializationError` | store I/O failure, checksum mismatch, malformed manifest |
| `CompatibilityError` | vocabulary/config incompatibility on read |

All inherit from `VIEError`. Loggers: module-level `logging.getLogger("vie.<module>")`; the
pipeline logs stage transitions and per-run summaries at INFO; frame anomalies at WARNING.

---

## 12. Worked example (normative)

3×3 patch, uint8, `bt601`, `L = 16`:

```
input (R=G=B):        Y (= v/255):          level:
 51  51  51           0.2000                I3      (0.2·16 = 3.2 → 3)
 51  68  51           0.2000 0.2667 0.2000  I3 I4 I3 (0.2667·16 = 4.27 → 4)
 51  51  51           0.2000                I3
```

This is the plan §8 example; the center pixel crosses the I3/I4 boundary at `y = 4/16 = 0.25`
(`v = 63.75`, so v = 64 → I4, v = 63 → I3).

---

## 13. Phase 0 acceptance criteria — status

| Criterion (plan §33 Phase 0) | Evidence |
|---|---|
| All fields and units defined | this document §1–§8 |
| Boundary cases specified | §2.6–2.10, §4.2, §4.6 table |
| Example inputs and outputs provided | §3 reference vectors, §4 table, §12 |
| Schemas validate correctly | `schemas/*.schema.json` + `tests/unit/test_config.py`, `tests/integration/test_cli.py` |
| Round-trip serialization tests pass | `tests/integration/test_pipeline_roundtrip.py`, `tests/property/test_properties.py` |
| No downstream implementation before approval | decision record `docs/decisions/DEC-0000-phase-gates.md`; Phases 2+ not implemented |

## 14. Known limitations (v1.0.0)

1. Only uniform, globally fixed quantization is implemented; histogram/adaptive/learned
   strategies are specified as extension points but untested (and MUST raise
   `ConfigError` if requested).
2. No GPU implementation; reference CPU implementation only (plan §6 requires optimized
   variants to be measured against the reference first — that is Phase 8 work).
3. Coordinate system is defined but unexercised until Phase 2 introduces spatial objects.
4. Color is reduced to luma; chroma is discarded and NOT recoverable — recorded here as an
   explicit representational limit of the whole approach (relevant to Q1).
5. `uint16` inputs are accepted but the test matrix emphasizes `uint8` (dominant sensor case).
