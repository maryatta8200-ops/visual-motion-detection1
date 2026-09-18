# EXP-0002 — Phase 2 intensity-object extraction: cost of labeling, identity and metadata

- Created (UTC): `2026-09-18T08:52:51.259Z`
- Code commit: `a86b70a888d6e5cb08aed0cf3f002aa05f266bd5`
- Warm-up frames excluded per condition: 2; measured repeats: 5 (adversarial: 1 warm-up + N)
- Clock: time.perf_counter_ns (monotonic)
- Memory: tracemalloc peak of the extraction call (label map + records), measured in a separate untimed pass: tracing inflates latency ~1.6x, so timings are untraced
- Environment: Linux-x86_64/6.1.158+, Intel(R) Xeon(R) Processor @ 2.60GHz, numpy 2.4.6, python 3.11.2

All numbers are per-frame medians (p50) over the measured frames of a deterministic
synthetic scene; full distributions and memory peaks are in `result.json`.
`region_metadata_json` is the exact serialized size of the frame's object records
(compact canonical JSON, as written to `regions.json`).

## Main matrix — 320×240

| scene | L | extract p50 (ms) | p95 (ms) | regions/frame | dropped/frame | raw B | intensity B | labels B | metadata B | metadata/raw | peak MB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| gradient | 8 | 5.183 | 5.665 | 8 | 0 | 230400 | 76800 | 307200 | 1840 | 0.0080 | 4.0 |
| gradient | 16 | 6.329 | 8.580 | 16 | 0 | 230400 | 76800 | 307200 | 3699 | 0.0161 | 4.0 |
| gradient | 64 | 12.841 | 13.025 | 64 | 0 | 230400 | 76800 | 307200 | 14883 | 0.0646 | 4.0 |
| gradient | 256 | 43.522 | 46.751 | 256 | 0 | 230400 | 76800 | 307200 | 59825 | 0.2597 | 8.3 |
| moving_square | 8 | 3.593 | 3.684 | 2 | 0 | 230400 | 76800 | 307200 | 483 | 0.0021 | 4.0 |
| moving_square | 16 | 3.601 | 3.749 | 2 | 0 | 230400 | 76800 | 307200 | 485 | 0.0021 | 4.0 |
| moving_square | 64 | 3.548 | 3.567 | 2 | 0 | 230400 | 76800 | 307200 | 487 | 0.0021 | 4.0 |
| moving_square | 256 | 3.622 | 3.741 | 2 | 0 | 230400 | 76800 | 307200 | 489 | 0.0021 | 4.0 |
| ramp_bands | 8 | 52.417 | 53.245 | 320 | 0 | 230400 | 76800 | 307200 | 73803 | 0.3203 | 10.0 |
| ramp_bands | 16 | 56.352 | 56.874 | 320 | 0 | 230400 | 76800 | 307200 | 74043 | 0.3214 | 10.0 |
| ramp_bands | 64 | 52.473 | 53.334 | 320 | 0 | 230400 | 76800 | 307200 | 74343 | 0.3227 | 10.0 |
| ramp_bands | 256 | 63.024 | 65.675 | 320 | 0 | 230400 | 76800 | 307200 | 74715 | 0.3243 | 10.0 |
| static | 8 | 3.640 | 3.753 | 2 | 0 | 230400 | 76800 | 307200 | 478 | 0.0021 | 4.0 |
| static | 16 | 3.440 | 3.510 | 2 | 0 | 230400 | 76800 | 307200 | 480 | 0.0021 | 4.0 |
| static | 64 | 3.472 | 3.564 | 2 | 0 | 230400 | 76800 | 307200 | 482 | 0.0021 | 4.0 |
| static | 256 | 3.691 | 4.055 | 2 | 0 | 230400 | 76800 | 307200 | 484 | 0.0021 | 4.0 |

## Main matrix — 640×480

| scene | L | extract p50 (ms) | p95 (ms) | regions/frame | dropped/frame | raw B | intensity B | labels B | metadata B | metadata/raw | peak MB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| gradient | 8 | 18.432 | 18.643 | 8 | 0 | 921600 | 307200 | 1228800 | 1852 | 0.0020 | 16.0 |
| gradient | 16 | 21.159 | 21.499 | 16 | 0 | 921600 | 307200 | 1228800 | 3722 | 0.0040 | 16.0 |
| gradient | 64 | 35.383 | 36.071 | 64 | 0 | 921600 | 307200 | 1228800 | 14912 | 0.0162 | 16.0 |
| gradient | 256 | 103.202 | 104.439 | 256 | 0 | 921600 | 307200 | 1228800 | 60081 | 0.0652 | 19.3 |
| moving_square | 8 | 15.061 | 15.160 | 2 | 0 | 921600 | 307200 | 1228800 | 482 | 0.0005 | 16.0 |
| moving_square | 16 | 14.743 | 15.642 | 2 | 0 | 921600 | 307200 | 1228800 | 484 | 0.0005 | 16.0 |
| moving_square | 64 | 16.060 | 19.976 | 2 | 0 | 921600 | 307200 | 1228800 | 486 | 0.0005 | 16.0 |
| moving_square | 256 | 14.160 | 14.378 | 2 | 0 | 921600 | 307200 | 1228800 | 488 | 0.0005 | 16.0 |
| ramp_bands | 8 | 236.702 | 250.446 | 640 | 0 | 921600 | 307200 | 1228800 | 148043 | 0.1606 | 40.0 |
| ramp_bands | 16 | 264.240 | 297.261 | 640 | 0 | 921600 | 307200 | 1228800 | 148523 | 0.1612 | 40.0 |
| ramp_bands | 64 | 238.461 | 258.048 | 640 | 0 | 921600 | 307200 | 1228800 | 149123 | 0.1618 | 40.0 |
| ramp_bands | 256 | 245.891 | 250.464 | 640 | 0 | 921600 | 307200 | 1228800 | 149943 | 0.1627 | 40.0 |
| static | 8 | 14.030 | 14.143 | 2 | 0 | 921600 | 307200 | 1228800 | 481 | 0.0005 | 16.0 |
| static | 16 | 14.055 | 14.143 | 2 | 0 | 921600 | 307200 | 1228800 | 483 | 0.0005 | 16.0 |
| static | 64 | 13.997 | 14.106 | 2 | 0 | 921600 | 307200 | 1228800 | 485 | 0.0005 | 16.0 |
| static | 256 | 14.019 | 14.147 | 2 | 0 | 921600 | 307200 | 1228800 | 487 | 0.0005 | 16.0 |

## Main matrix — 1920×1080

| scene | L | extract p50 (ms) | p95 (ms) | regions/frame | dropped/frame | raw B | intensity B | labels B | metadata B | metadata/raw | peak MB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| gradient | 8 | 143.144 | 152.031 | 8 | 0 | 6220800 | 2073600 | 8294400 | 1882 | 0.0003 | 107.8 |
| gradient | 16 | 148.461 | 149.859 | 16 | 0 | 6220800 | 2073600 | 8294400 | 3783 | 0.0006 | 107.8 |
| gradient | 64 | 186.526 | 196.420 | 64 | 0 | 6220800 | 2073600 | 8294400 | 15156 | 0.0024 | 107.8 |
| gradient | 256 | 390.685 | 395.189 | 256 | 0 | 6220800 | 2073600 | 8294400 | 60921 | 0.0098 | 107.8 |
| moving_square | 8 | 122.353 | 122.980 | 2 | 0 | 6220800 | 2073600 | 8294400 | 484 | 0.0001 | 107.8 |
| moving_square | 16 | 127.270 | 143.090 | 2 | 0 | 6220800 | 2073600 | 8294400 | 486 | 0.0001 | 107.8 |
| moving_square | 64 | 127.157 | 150.149 | 2 | 0 | 6220800 | 2073600 | 8294400 | 488 | 0.0001 | 107.8 |
| moving_square | 256 | 125.595 | 129.623 | 2 | 0 | 6220800 | 2073600 | 8294400 | 490 | 0.0001 | 107.8 |
| ramp_bands | 8 | 2016.877 | 2182.337 | 1920 | 0 | 6220800 | 2073600 | 8294400 | 452524 | 0.0727 | 269.7 |
| ramp_bands | 16 | 1953.428 | 2003.573 | 1920 | 0 | 6220800 | 2073600 | 8294400 | 453964 | 0.0730 | 269.7 |
| ramp_bands | 64 | 2098.691 | 2187.564 | 1920 | 0 | 6220800 | 2073600 | 8294400 | 455764 | 0.0733 | 269.7 |
| ramp_bands | 256 | 2334.652 | 2671.086 | 1920 | 0 | 6220800 | 2073600 | 8294400 | 458444 | 0.0737 | 269.7 |
| static | 8 | 111.272 | 112.178 | 2 | 0 | 6220800 | 2073600 | 8294400 | 482 | 0.0001 | 107.8 |
| static | 16 | 105.568 | 107.091 | 2 | 0 | 6220800 | 2073600 | 8294400 | 484 | 0.0001 | 107.8 |
| static | 64 | 108.138 | 114.142 | 2 | 0 | 6220800 | 2073600 | 8294400 | 486 | 0.0001 | 107.8 |
| static | 256 | 111.046 | 123.061 | 2 | 0 | 6220800 | 2073600 | 8294400 | 488 | 0.0001 | 107.8 |

## Adversarial — dense per-pixel noise (L=256)

`static` scene with every frame pixel replaced by a random level: the worst case for
the number of 4-connected runs, and therefore for region-count-dependent costs.

| size | noise_px | min_area | extract p50 (ms) | regions/frame | dropped/frame | labels B | metadata B | metadata/raw | peak MB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 320×240 | 76800 | 1 | 595.362 | 56802 | 0 | 307200 | 13343457 | 57.9143 | 36.5 |
| 640×480 | 307200 | 1 | 2359.844 | 227660 | 0 | 1228800 | 53946770 | 58.5360 | 159.9 |
| 1920×1080 | 2073600 | 2 | 1714.437 | 124787 | 1413125 | 8294400 | 30603326 | 4.9195 | 203.8 |

## Method / envelope notes (recorded facts)

- Latency measured with tracemalloc inactive; tracing regressions were measured separately at 1.36x (640x480 structured) to 16x (1920x1080 one-pixel-wide runs), so traced timings are never reported as latency.
- The fully dense 1920x1080 adversarial condition (noise_px=2073600, min_area=1, ~2.07M regions) exhausted this machine's 3 GB memory and was killed before producing numbers; it is therefore NOT measured, and the 1920x1080 adversarial row uses min_area=2 (isolated noise pixels discarded and counted). The 320x240 and 640x480 dense rows use min_area=1.

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

## Provenance note (added after the run, 2026-09-18)

`result.json` records `code_commit = a86b70a`. The run executed that commit's measurement
code from the working tree; the only delta recorded in a later commit (0a1138c) is the
`--adversarial` CLI parser — a86b70a's inline parser could not unpack the
`WIDTHxHEIGHT:min_area:frames` triples it was handed, and the fix shipped as
`_parse_adversarial()`. The diff between the two commits is confined to that CLI helper, so
no measured quantity is affected; this note exists so the recorded commit can be audited.
