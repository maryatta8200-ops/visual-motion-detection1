# EXP-0003 — Phase-1 baseline re-measurement (untraced latency) for incremental Phase-2 cost comparison

- Created (UTC): `2026-09-18T09:06:24.735Z`
- Code commit: `163bf39f5e9d92a10402e7e7316b124b9fb3924c`
- Warm-up frames excluded per condition: 6; measured repeats: 18
- Clock: time.perf_counter_ns (monotonic); tracemalloc inactive during timing; memory: tracemalloc peak of one representative frame (last), separate untimed pass
- Environment: Linux-x86_64/6.1.158+, Intel(R) Xeon(R) Processor @ 2.60GHz, numpy 2.4.6

All numbers are medians (p50) over repeated frames of the synthetic `gradient` scene; full distributions are in `result.json`. Sizes are per frame.

## 320×240

| levels | gray p50 (ms) | quantize p50 (ms) | end-to-end p50 (ms) | raw B | gray f64 B | quant u8 B | quant/raw |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 8 | 2.133 | 0.169 | 2.287 | 230400 | 614400 | 76800 | 0.3333 |
| 16 | 2.192 | 0.160 | 2.381 | 230400 | 614400 | 76800 | 0.3333 |
| 32 | 2.079 | 0.158 | 2.239 | 230400 | 614400 | 76800 | 0.3333 |
| 64 | 2.053 | 0.146 | 2.213 | 230400 | 614400 | 76800 | 0.3333 |
| 128 | 2.131 | 0.168 | 2.326 | 230400 | 614400 | 76800 | 0.3333 |
| 256 | 2.508 | 0.220 | 2.692 | 230400 | 614400 | 76800 | 0.3333 |

## 640×480

| levels | gray p50 (ms) | quantize p50 (ms) | end-to-end p50 (ms) | raw B | gray f64 B | quant u8 B | quant/raw |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 8 | 9.184 | 0.826 | 10.010 | 921600 | 2457600 | 307200 | 0.3333 |
| 16 | 9.007 | 0.794 | 9.846 | 921600 | 2457600 | 307200 | 0.3333 |
| 32 | 9.052 | 0.810 | 9.882 | 921600 | 2457600 | 307200 | 0.3333 |
| 64 | 8.683 | 0.770 | 9.467 | 921600 | 2457600 | 307200 | 0.3333 |
| 128 | 8.751 | 0.778 | 9.534 | 921600 | 2457600 | 307200 | 0.3333 |
| 256 | 9.202 | 0.884 | 10.077 | 921600 | 2457600 | 307200 | 0.3333 |

## 1920×1080

| levels | gray p50 (ms) | quantize p50 (ms) | end-to-end p50 (ms) | raw B | gray f64 B | quant u8 B | quant/raw |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 8 | 67.812 | 5.113 | 72.925 | 6220800 | 16588800 | 2073600 | 0.3333 |
| 16 | 69.292 | 5.288 | 74.572 | 6220800 | 16588800 | 2073600 | 0.3333 |
| 32 | 69.770 | 5.399 | 74.984 | 6220800 | 16588800 | 2073600 | 0.3333 |
| 64 | 68.335 | 5.123 | 73.785 | 6220800 | 16588800 | 2073600 | 0.3333 |
| 128 | 64.552 | 4.829 | 69.656 | 6220800 | 16588800 | 2073600 | 0.3333 |
| 256 | 63.538 | 4.879 | 68.649 | 6220800 | 16588800 | 2073600 | 0.3333 |

## Method / provenance notes (recorded facts)

- Latency measured with tracemalloc INACTIVE and the memory peak in a separate untimed pass. EXP-0001 measured the same 18 conditions with the same clock but with tracemalloc active inside the timed region, so EXP-0001 p50s are traced numbers; use EXP-0003 for any Phase-1-vs-Phase-2 arithmetic.
## Reading notes

- The quantized map is always 1/3 of raw RGB bytes in memory (uint8 vs 3×uint8);
  the float64 luminance intermediate is 8/3 of raw bytes — this cost is part of
  the representation and must be reported, never hidden (plan §25).
- These are **cost** baselines only. No accuracy claims are made in EXP-0001;
  information-retention measurements belong to a later experiment (Q1/Q2).
- Peak Python allocations (tracemalloc) are per-frame transient peaks, not
  steady-state RSS; see `result.json`.
