"""Quantization baseline benchmark (EXP-0001).

Measures grayscale and quantization latency + memory + representation sizes
across level counts and resolutions, with explicit warm-up and multiple
repetitions (plan §19, §36). Machine-readable result validated against
`schemas/benchmark_result.schema.json`; also emits a human-readable report.

This is a BASELINE of the reference implementation — not a claim of advantage
(plan §39: no superiority claims without comparisons).
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

import numpy as np

from ..config import InputDomainSettings, QuantizationSettings
from ..input.synthetic import SyntheticSource
from ..intensity.vocabulary import IntensityVocabulary
from ..metrics import summarize
from ..preprocessing.grayscale import to_grayscale
from ..preprocessing.quantization import quantize
from ..provenance import capture_provenance, dumps_json, environment_summary

logger = logging.getLogger("vie.benchmarking")

SUPPORTED_LEVELS = (8, 16, 32, 64, 128, 256)


def measure_condition(
    *,
    levels: int,
    width: int,
    height: int,
    frames: int,
    warmup: int,
    luma_standard: str = "bt601",
    scene: str = "gradient",
    seed: int = 0,
) -> dict:
    """One benchmark condition: fixed scene/size/levels, timed repetitions."""
    source = SyntheticSource(scene, (width, height), frames, seed=seed, levels=levels)
    records = list(source.frames())
    input_domain = InputDomainSettings(luma_standard=luma_standard)
    gray_times: list[float] = []
    quant_times: list[float] = []
    e2e_times: list[float] = []
    peak_alloc = 0

    import tracemalloc

    for i, record in enumerate(records):
        tracemalloc.start()
        t0 = time.perf_counter_ns()
        y, _, _ = to_grayscale(record.data, input_domain)
        t1 = time.perf_counter_ns()
        q = quantize(y, QuantizationSettings(levels=levels))
        t2 = time.perf_counter_ns()
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_alloc = max(peak_alloc, peak)
        if i >= warmup:
            gray_times.append(t1 - t0)
            quant_times.append(t2 - t1)
            e2e_times.append(t2 - t0)

    assert q.shape == (height, width)
    return {
        "condition_id": f"L{levels}-{width}x{height}",
        "scene": scene,
        "width": width,
        "height": height,
        "dtype": str(records[0].data.dtype),
        "levels": levels,
        "luma_standard": luma_standard,
        "gray_ns": summarize(gray_times),
        "quantize_ns": summarize(quant_times),
        "end_to_end_ns": summarize(e2e_times),
        "peak_alloc_bytes": int(peak_alloc),
        "bytes_per_frame": {
            "raw_rgb": int(records[0].data.nbytes),
            "gray_f64": int(y.nbytes),
            "intensity_u8": int(q.nbytes),
        },
    }


def run_benchmark(
    outdir: Path | str,
    *,
    experiment_id: str = "EXP-0001",
    levels=SUPPORTED_LEVELS,
    resolutions=((320, 240), (640, 480), (1920, 1080)),
    frames: int = 24,
    warmup: int = 6,
    scene: str = "gradient",
    seed: int = 0,
) -> Path:
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    conditions = []
    for (w, h) in resolutions:
        for lv in levels:
            logger.info("condition L=%d %dx%d", lv, w, h)
            conditions.append(
                measure_condition(
                    levels=lv, width=w, height=h, frames=frames, warmup=warmup, scene=scene, seed=seed
                )
            )
    commit = None
    try:
        import subprocess

        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5
        ).stdout.strip() or None
    except Exception:
        pass
    result = {
        "schema": "vie.benchmark-result/1",
        "experiment_id": experiment_id,
        "title": "Phase 1 quantization baseline: reference implementation latency, memory, representation size",
        "research_questions": ["Q1", "Q2", "Q7", "Q8"],
        "hypotheses": ["H1 (indirect: representation size + cost baseline only; no accuracy claim yet)"],
        "code_commit": commit,
        "created_at_utc": capture_provenance(seed=seed)["created_at_utc"],
        "warmup_frames": warmup,
        "repeats_per_condition": frames - warmup,
        "measurement_method": {
            "clock": "time.perf_counter_ns (monotonic)",
            "memory": "tracemalloc peak of gray+quantize per frame",
            "timer_resolution_note": "ns resolution; single-threaded CPU; sub-microsecond noise expected",
        },
        "environment": environment_summary(),
        "conditions": conditions,
    }
    from ..config import schemas_dir, validate_against_schema

    validate_against_schema(result, schemas_dir() / "benchmark_result.schema.json", what="benchmark result")
    result_path = outdir / "result.json"
    result_path.write_text(dumps_json(result), encoding="utf-8")
    report = render_report(result)
    (outdir / "report.md").write_text(report, encoding="utf-8")
    logger.info("benchmark written to %s", outdir)
    return result_path


def _ms(ns: float) -> str:
    return f"{ns / 1e6:.3f}"


def render_report(result: dict) -> str:
    lines = [
        f"# {result['experiment_id']} — {result['title']}",
        "",
        f"- Created (UTC): `{result['created_at_utc']}`",
        f"- Code commit: `{result['code_commit']}`",
        f"- Warm-up frames excluded per condition: {result['warmup_frames']}; "
        f"measured repeats: {result['repeats_per_condition']}",
        f"- Clock: {result['measurement_method']['clock']}; memory: {result['measurement_method']['memory']}",
        f"- Environment: {result['environment']['platform']}, "
        f"{result['environment']['cpu_model']}, numpy {result['environment']['numpy_version']}",
        "",
        "All numbers are medians (p50) over repeated frames of the synthetic "
        "`gradient` scene; full distributions are in `result.json`. Sizes are per frame.",
        "",
    ]
    by_res: dict[tuple[int, int], list[dict]] = {}
    for cond in result["conditions"]:
        by_res.setdefault((cond["width"], cond["height"]), []).append(cond)
    for (w, h), conds in sorted(by_res.items()):
        lines += [
            f"## {w}×{h}",
            "",
            "| levels | gray p50 (ms) | quantize p50 (ms) | end-to-end p50 (ms) | raw B | gray f64 B | quant u8 B | quant/raw |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for cond in sorted(conds, key=lambda c: c["levels"]):
            b = cond["bytes_per_frame"]
            lines.append(
                f"| {cond['levels']} | {_ms(cond['gray_ns']['p50'])} | {_ms(cond['quantize_ns']['p50'])} | "
                f"{_ms(cond['end_to_end_ns']['p50'])} | {b['raw_rgb']} | {b['gray_f64']} | "
                f"{b['intensity_u8']} | {b['intensity_u8'] / b['raw_rgb']:.4f} |"
            )
        lines.append("")
    lines += [
        "## Reading notes",
        "",
        "- The quantized map is always 1/3 of raw RGB bytes in memory (uint8 vs 3×uint8);",
        "  the float64 luminance intermediate is 8/3 of raw bytes — this cost is part of",
        "  the representation and must be reported, never hidden (plan §25).",
        "- These are **cost** baselines only. No accuracy claims are made in EXP-0001;",
        "  information-retention measurements belong to a later experiment (Q1/Q2).",
        "- Peak Python allocations (tracemalloc) are per-frame transient peaks, not",
        "  steady-state RSS; see `result.json`.",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vie-benchmark", description=__doc__)
    parser.add_argument("--output", default="experiments/EXP-0001-quantization-baseline")
    parser.add_argument("--experiment-id", default="EXP-0001")
    parser.add_argument("--frames", type=int, default=24)
    parser.add_argument("--warmup", type=int, default=6)
    parser.add_argument("--scene", default="gradient")
    parser.add_argument("--levels", default="8,16,32,64,128,256")
    parser.add_argument("--resolutions", default="320x240,640x480,1920x1080")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    levels = tuple(int(x) for x in args.levels.split(","))
    resolutions = tuple(
        tuple(int(v) for v in item.lower().split("x")) for item in args.resolutions.split(",")
    )
    run_benchmark(
        args.output,
        experiment_id=args.experiment_id,
        levels=levels,
        resolutions=resolutions,
        frames=args.frames,
        warmup=args.warmup,
        scene=args.scene,
        seed=args.seed,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
