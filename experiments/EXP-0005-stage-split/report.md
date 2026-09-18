# EXP-0005 — Phase-2 stage split: labeling vs record construction (untraced latency)

- Created (UTC): `2026-09-18T09:09:54.286Z`
- Code commit: `163bf39f5e9d92a10402e7e7316b124b9fb3924c`
- Warm-up frames excluded per condition: 2; measured repeats: 5 (adversarial: 1 warm-up + N)
- Clock: time.perf_counter_ns (monotonic)
- Memory: tracemalloc peak of the extraction call (label map + records), measured in a separate untimed pass: tracing inflates latency ~1.6x, so timings are untraced
- Environment: Linux-x86_64/6.1.158+, Intel(R) Xeon(R) Processor @ 2.60GHz, numpy 2.4.6, python 3.11.2

All numbers are per-frame medians (p50) over the measured frames of a deterministic
synthetic scene; full distributions and memory peaks are in `result.json`.
`region_metadata_json` is the exact serialized size of the frame's object records
(compact canonical JSON, as written to `regions.json`).

## Main matrix — 640×480

| scene | L | extract p50 (ms) | labeling p50 (ms) | records p50 (ms) | p95 (ms) | regions/frame | dropped/frame | raw B | intensity B | labels B | metadata B | metadata/raw | peak MB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| gradient | 16 | 20.632 | 20.473 | 0.165 | 21.337 | 16 | 0 | 921600 | 307200 | 1228800 | 3722 | 0.0040 | 16.0 |
| gradient | 64 | 34.331 | 33.897 | 0.495 | 36.256 | 64 | 0 | 921600 | 307200 | 1228800 | 14912 | 0.0162 | 16.0 |
| ramp_bands | 16 | 263.769 | 259.613 | 4.156 | 291.636 | 640 | 0 | 921600 | 307200 | 1228800 | 148523 | 0.1612 | 40.0 |
| ramp_bands | 64 | 254.355 | 249.440 | 3.960 | 255.280 | 640 | 0 | 921600 | 307200 | 1228800 | 149123 | 0.1618 | 40.0 |

## Main matrix — 1920×1080

| scene | L | extract p50 (ms) | labeling p50 (ms) | records p50 (ms) | p95 (ms) | regions/frame | dropped/frame | raw B | intensity B | labels B | metadata B | metadata/raw | peak MB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| gradient | 16 | 157.472 | 157.257 | 0.216 | 168.208 | 16 | 0 | 6220800 | 2073600 | 8294400 | 3783 | 0.0006 | 107.8 |
| gradient | 64 | 201.730 | 201.108 | 0.526 | 208.116 | 64 | 0 | 6220800 | 2073600 | 8294400 | 15156 | 0.0024 | 107.8 |
| ramp_bands | 16 | 2311.360 | 2297.986 | 13.375 | 2354.747 | 1920 | 0 | 6220800 | 2073600 | 8294400 | 453964 | 0.0730 | 269.7 |
| ramp_bands | 64 | 2291.552 | 2279.347 | 12.205 | 2622.424 | 1920 | 0 | 6220800 | 2073600 | 8294400 | 455764 | 0.0733 | 269.7 |

## Adversarial — dense per-pixel noise (L=256)

`static` scene with every frame pixel replaced by a random level: the worst case for
the number of 4-connected runs, and therefore for region-count-dependent costs.

| size | noise_px | min_area | extract p50 (ms) | regions/frame | dropped/frame | labels B | metadata B | metadata/raw | peak MB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|

## Method / envelope notes (recorded facts)

- Instrumentation run: extraction is timed as labeling (4-connected components + label map) plus record construction (vie.intensity-object/1 records + fingerprints), both untraced, so the two stages can be attributed separately; totals are cross-checked against EXP-0002 for overlapping conditions.

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
