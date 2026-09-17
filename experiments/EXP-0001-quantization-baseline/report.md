# EXP-0001 — Phase 1 quantization baseline: reference implementation latency, memory, representation size

- Created (UTC): `2026-09-17T21:18:41.362Z`
- Code commit: `4a47765bccc2c233ab6e56c58b9e703214870157`
- Warm-up frames excluded per condition: 8; measured repeats: 22
- Clock: time.perf_counter_ns (monotonic); memory: tracemalloc peak of gray+quantize per frame
- Environment: Linux-x86_64/6.1.158+, Intel(R) Xeon(R) Processor @ 2.60GHz, numpy 2.4.6

All numbers are medians (p50) over repeated frames of the synthetic `gradient` scene; full distributions are in `result.json`. Sizes are per frame.

## 320×240

| levels | gray p50 (ms) | quantize p50 (ms) | end-to-end p50 (ms) | raw B | gray f64 B | quant u8 B | quant/raw |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 8 | 2.214 | 0.158 | 2.398 | 230400 | 614400 | 76800 | 0.3333 |
| 16 | 2.243 | 0.167 | 2.410 | 230400 | 614400 | 76800 | 0.3333 |
| 32 | 2.256 | 0.163 | 2.429 | 230400 | 614400 | 76800 | 0.3333 |
| 64 | 2.379 | 0.173 | 2.595 | 230400 | 614400 | 76800 | 0.3333 |
| 128 | 2.263 | 0.164 | 2.430 | 230400 | 614400 | 76800 | 0.3333 |
| 256 | 2.279 | 0.167 | 2.442 | 230400 | 614400 | 76800 | 0.3333 |

## 640×480

| levels | gray p50 (ms) | quantize p50 (ms) | end-to-end p50 (ms) | raw B | gray f64 B | quant u8 B | quant/raw |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 8 | 8.806 | 0.632 | 9.464 | 921600 | 2457600 | 307200 | 0.3333 |
| 16 | 9.074 | 0.653 | 9.727 | 921600 | 2457600 | 307200 | 0.3333 |
| 32 | 9.159 | 0.662 | 9.868 | 921600 | 2457600 | 307200 | 0.3333 |
| 64 | 8.588 | 0.599 | 9.204 | 921600 | 2457600 | 307200 | 0.3333 |
| 128 | 8.706 | 0.635 | 9.347 | 921600 | 2457600 | 307200 | 0.3333 |
| 256 | 8.794 | 0.632 | 9.418 | 921600 | 2457600 | 307200 | 0.3333 |

## 1920×1080

| levels | gray p50 (ms) | quantize p50 (ms) | end-to-end p50 (ms) | raw B | gray f64 B | quant u8 B | quant/raw |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 8 | 76.451 | 7.411 | 83.873 | 6220800 | 16588800 | 2073600 | 0.3333 |
| 16 | 76.405 | 7.556 | 84.111 | 6220800 | 16588800 | 2073600 | 0.3333 |
| 32 | 74.453 | 6.896 | 81.679 | 6220800 | 16588800 | 2073600 | 0.3333 |
| 64 | 79.331 | 8.073 | 87.511 | 6220800 | 16588800 | 2073600 | 0.3333 |
| 128 | 74.852 | 6.990 | 81.777 | 6220800 | 16588800 | 2073600 | 0.3333 |
| 256 | 75.111 | 7.527 | 82.483 | 6220800 | 16588800 | 2073600 | 0.3333 |

## Reading notes

- The quantized map is always 1/3 of raw RGB bytes in memory (uint8 vs 3×uint8);
  the float64 luminance intermediate is 8/3 of raw bytes — this cost is part of
  the representation and must be reported, never hidden (plan §25).
- These are **cost** baselines only. No accuracy claims are made in EXP-0001;
  information-retention measurements belong to a later experiment (Q1/Q2).
- Peak Python allocations (tracemalloc) are per-frame transient peaks, not
  steady-state RSS; see `result.json`.
