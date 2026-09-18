# EXP-0004 — min_area sensitivity on dense per-pixel noise (640x480, L=256)

- Created (UTC): `2026-09-18T09:07:53.068Z`
- Code commit: `163bf39f5e9d92a10402e7e7316b124b9fb3924c`
- Warm-up frames excluded per condition: 1; measured repeats: 2 (adversarial: 1 warm-up + N)
- Clock: time.perf_counter_ns (monotonic)
- Memory: tracemalloc peak of the extraction call (label map + records), measured in a separate untimed pass: tracing inflates latency ~1.6x, so timings are untraced
- Environment: Linux-x86_64/6.1.158+, Intel(R) Xeon(R) Processor @ 2.60GHz, numpy 2.4.6, python 3.11.2

All numbers are per-frame medians (p50) over the measured frames of a deterministic
synthetic scene; full distributions and memory peaks are in `result.json`.
`region_metadata_json` is the exact serialized size of the frame's object records
(compact canonical JSON, as written to `regions.json`).

## Main matrix — 320×240

| scene | L | extract p50 (ms) | labeling p50 (ms) | records p50 (ms) | p95 (ms) | regions/frame | dropped/frame | raw B | intensity B | labels B | metadata B | metadata/raw | peak MB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| static | 256 | 3.587 | 3.505 | 0.083 | 3.958 | 2 | 0 | 230400 | 76800 | 307200 | 484 | 0.0021 | 4.0 |

## Adversarial — dense per-pixel noise (L=256)

`static` scene with every frame pixel replaced by a random level: the worst case for
the number of 4-connected runs, and therefore for region-count-dependent costs.

| size | noise_px | min_area | extract p50 (ms) | regions/frame | dropped/frame | labels B | metadata B | metadata/raw | peak MB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 640×480 | 307200 | 1 | 2338.047 | 227660 | 0 | 1228800 | 53946770 | 58.5360 | 159.9 |
| 640×480 | 307200 | 2 | 228.763 | 18528 | 209160 | 1228800 | 4488740 | 4.8706 | 30.2 |
| 640×480 | 307200 | 4 | 124.974 | 9071 | 218586 | 1228800 | 2213129 | 2.4014 | 30.1 |
| 640×480 | 307200 | 8 | 73.861 | 3538 | 224143 | 1228800 | 875074 | 0.9495 | 30.0 |
| 640×480 | 307200 | 16 | 49.432 | 877 | 226795 | 1228800 | 217592 | 0.2361 | 30.0 |

## Method / envelope notes (recorded facts)

- Threshold sweep: identical dense-noise frames, only min_area changes. Discards are counted (dropped_regions/dropped_pixels), so both the raw and the filtered counts remain recoverable; extraction cost is roughly flat across min_area because labeling runs before filtering.

## Reading notes (honesty rules, plan §25/§39)

- Label maps are int32, so they are 4 bytes/pixel — 4/3 of the uint8 intensity map and
  exactly 4/3 of one raw RGB channel-set (i.e. 4/9 of raw RGB bytes). This is reported,
  not hidden: an int32 label map is not a compression of the frame.
- Region metadata grows with the number of regions, not with area: at high level counts
  and noisy scenes it dominates every other artifact. The adversarial block above is the
  honest envelope of the reference implementation; `min_area` is the designed lever
  (discards are counted, never silent).
- These are **cost** numbers only; no accuracy, robustness or tracking claims are made.
  Cross-frame identity is explicitly out of scope for Phase 2 (VIE-SPEC-REP 1.1.0 §R3.4).
- Optimization is deliberately deferred (plan §3.14/§8); these numbers are the baseline
  a later profiling phase must beat.
