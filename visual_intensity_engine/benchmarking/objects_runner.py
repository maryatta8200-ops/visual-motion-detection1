"""Object-extraction cost benchmark (EXP-0002, plan §7/§19/§36).

Measures the Phase-2 extraction stage — labeling + `vie.intensity-object/1`
record construction — across resolutions, level counts and scenes, plus a dense
per-pixel-noise scenario (worst case for the number of runs). Representation
sizes are reported per frame: raw RGB, intensity map, int32 label map, and the
region-metadata JSON actually written into `regions.json` (metadata overhead is
part of the cost, plan §25 — a representation is not compact if its index is
excluded).

Method (explicit, plan §36): grayscale + quantization are computed *outside* the
timed region (they are EXP-0001's subject); each frame's extraction is timed with
`time.perf_counter_ns` and split into **labeling** (connected components, label map)
and **record construction** (`vie.intensity-object/1` records + fingerprints), both
untraced; the first `warmup` frames of each condition are excluded; `tracemalloc`
records the transient peak of the whole extraction call in a separate untimed pass.
Single-threaded reference implementation; no optimization is claimed (plan §3.14/§8).
"""

from __future__ import annotations

import argparse
import logging
import time
import tracemalloc
from pathlib import Path

from ..config import PipelineConfig, canonical_json, schemas_dir, validate_against_schema
from ..input.synthetic import SyntheticSource
from ..intensity.vocabulary import IntensityVocabulary
from ..metrics import summarize
from ..objects.extraction import build_extracted_frame, extract_label_map, extract_objects
from ..objects.objects_config import ObjectsConfig
from ..pipeline import process_frame
from ..provenance import capture_provenance, dumps_json, environment_summary

logger = logging.getLogger("vie.benchmarking.objects")

DEFAULT_SCENES = ("gradient", "moving_square", "ramp_bands", "static")
DEFAULT_LEVELS = (8, 16, 64, 256)
DEFAULT_RESOLUTIONS = ((320, 240), (640, 480), (1920, 1080))


def region_metadata_bytes(objects) -> int:
    """Bytes the frame's records occupy in `regions.json` (compact JSON + commas).

    This is the exact serialized size of the region list as the store writes it
    (canonical JSON = sorted keys, compact separators), not an estimate.
    """
    if not objects:
        return 2  # "[]"
    return sum(len(canonical_json(obj.to_dict())) for obj in objects) + 2 + max(len(objects) - 1, 0)


def measure_condition(
    *,
    scene: str,
    width: int,
    height: int,
    levels: int,
    frames: int,
    warmup: int,
    min_area: int = 1,
    max_regions: int | None = None,
    noise_px: int = 0,
    seed: int = 0,
) -> dict:
    """One EXP-0002 condition: extraction latency/memory/size for fixed inputs."""
    source = SyntheticSource(
        scene, (width, height), frames + warmup, seed=seed, levels=levels, noise_px=noise_px
    )
    config = PipelineConfig.default(levels=levels)
    vocabulary = IntensityVocabulary.build_uniform(levels)
    objects_config = ObjectsConfig(min_area=min_area, max_regions=max_regions)
    prepared = [process_frame(record, config, vocabulary) for record in source.frames()]

    extract_ns: list[float] = []
    labeling_ns: list[float] = []
    records_ns: list[float] = []
    regions_per_frame: list[float] = []
    dropped_per_frame: list[float] = []
    peak_alloc = 0
    raw_bytes = intensity_bytes = label_bytes = metadata_bytes = 0
    regions_kept = regions_dropped = dropped_pixels = 0

    # Latency pass: untraced, because tracemalloc tracing inflates allocation-heavy
    # code by ~1.6x in this implementation (measured; see the report's method note).
    for i, pf in enumerate(prepared):
        # Stage split: labeling and record construction are timed separately so the
        # audit's "segmentation vs object construction" question is answerable; the
        # total extraction time is their sum (same work, one extra call boundary).
        t0 = time.perf_counter_ns()
        label_result = extract_label_map(pf.imap.intensity, vocabulary.levels, objects_config)
        t1 = time.perf_counter_ns()
        eframe = build_extracted_frame(pf.imap.frame.frame_index, label_result, vocabulary)
        t2 = time.perf_counter_ns()
        if i < warmup:
            continue
        extract_ns.append(t2 - t0)
        labeling_ns.append(t1 - t0)
        records_ns.append(t2 - t1)
        regions_per_frame.append(float(eframe.region_count))
        dropped_per_frame.append(float(eframe.dropped_regions))
        raw_bytes = int(pf.imap.intensity.size * 3)  # uint8 RGB source frame
        intensity_bytes = int(pf.imap.intensity.nbytes)
        label_bytes = int(eframe.labels.nbytes)
        metadata_bytes = region_metadata_bytes(eframe.objects)
        regions_kept += eframe.region_count
        regions_dropped += eframe.dropped_regions
        dropped_pixels += eframe.dropped_pixels

    # Memory pass: separate, untimed extraction with tracemalloc active, so the
    # reported peak never contaminates the reported latency.
    tracemalloc.start()
    extract_objects(prepared[-1].imap, vocabulary, objects_config)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    peak_alloc = max(peak_alloc, peak)

    noise_tag = f"-noise{noise_px}" if noise_px else ""
    return {
        "condition_id": f"{scene}{noise_tag}-L{levels}-{width}x{height}-min{min_area}",
        "scene": scene if not noise_px else f"{scene}+noise_px={noise_px}",
        "width": width,
        "height": height,
        "levels": levels,
        "connectivity": 4,
        "min_area": min_area,
        "max_regions": max_regions,
        "noise_px": noise_px,
        "extraction_ns": summarize(extract_ns),
        "labeling_ns": summarize(labeling_ns),
        "records_ns": summarize(records_ns),
        "regions_per_frame": summarize(regions_per_frame),
        "dropped_per_frame": summarize(dropped_per_frame),
        "peak_alloc_bytes": int(peak_alloc),
        "bytes_per_frame": {
            "raw_rgb": raw_bytes,
            "intensity_u8": intensity_bytes,
            "labels_i32": label_bytes,
            "region_metadata_json": metadata_bytes,
        },
        "totals": {
            "regions_kept": regions_kept,
            "regions_dropped": regions_dropped,
            "dropped_pixels": dropped_pixels,
        },
    }


# (width, height, min_area, frames): dense per-pixel noise at L=256 is the run-count
# worst case. The reference implementation's records are one Python object per region,
# so min_area bounds the measured envelope; the fully dense 1920x1080 case (min_area=1,
# ~2.07M regions) was observed to exceed a 3 GB machine and is recorded as such in the
# report instead of being silently skipped.
DEFAULT_ADVERSARIAL = ((320, 240, 1, 3), (640, 480, 1, 3), (1920, 1080, 2, 3))


def run_benchmark(
    outdir: Path | str,
    *,
    experiment_id: str = "EXP-0002",
    title: str = "Phase 2 intensity-object extraction: cost of labeling, identity and metadata",
    resolutions=DEFAULT_RESOLUTIONS,
    levels=DEFAULT_LEVELS,
    scenes=DEFAULT_SCENES,
    frames: int = 5,
    warmup: int = 2,
    adversarial_noise_fraction: float = 1.0,
    adversarial_specs=DEFAULT_ADVERSARIAL,
    notes: tuple[str, ...] = (),
    seed: int = 0,
) -> Path:
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    conditions: list[dict] = []
    for (w, h) in resolutions:
        for scene in scenes:
            for lv in levels:
                logger.info("condition %s L=%d %dx%d", scene, lv, w, h)
                conditions.append(
                    measure_condition(
                        scene=scene, width=w, height=h, levels=lv,
                        frames=frames, warmup=warmup, seed=seed,
                    )
                )
    # adversarial: dense per-pixel noise at L=256, the worst case for run counts
    for (w, h, min_area, adv_frames) in adversarial_specs:
        noise_px = int(w * h * adversarial_noise_fraction)
        logger.info(
            "adversarial condition noise L=256 %dx%d min_area=%d (noise_px=%d)",
            w, h, min_area, noise_px,
        )
        conditions.append(
            measure_condition(
                scene="static", width=w, height=h, levels=256, min_area=min_area,
                frames=adv_frames, warmup=1, noise_px=noise_px, seed=seed,
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
        "schema": "vie.object-benchmark-result/1",
        "experiment_id": experiment_id,
        "title": title,
        "research_questions": ["Q4", "Q7", "Q8"],
        "hypotheses": [
            "H3 (indirect: representation size for objects is measured; accuracy unclaimed)",
            "H5 (partial: cost of deterministic identity is included; robustness is Phase 3)",
        ],
        "code_commit": commit,
        "created_at_utc": capture_provenance(seed=seed)["created_at_utc"],
        "warmup_frames": warmup,
        "repeats_per_condition": frames,
        "measurement_method": {
            "clock": "time.perf_counter_ns (monotonic)",
            "memory": (
                "tracemalloc peak of the extraction call (label map + records), measured in a "
                "separate untimed pass: tracing inflates latency ~1.6x, so timings are untraced"
            ),
            "timer_resolution_note": (
                "ns resolution, single-threaded; extraction only (grayscale+quantization "
                "excluded, they are EXP-0001), split into labeling_ns + records_ns; "
                "region_metadata_json is the exact serialized size of regions.json records "
                "per frame"
            ),
        },
        "environment": environment_summary(),
        "conditions": conditions,
    }
    validate_against_schema(
        result, schemas_dir() / "object_benchmark_result.schema.json", what="object benchmark result"
    )
    result_path = outdir / "result.json"
    result_path.write_text(dumps_json(result), encoding="utf-8")
    (outdir / "report.md").write_text(render_report(result, notes=notes), encoding="utf-8")
    logger.info("object benchmark written to %s", outdir)
    return result_path


def _ms(ns: float) -> str:
    return f"{ns / 1e6:.3f}"


def _pct(part: float, whole: float) -> str:
    return f"{part / whole:.4f}" if whole else "n/a"


def render_report(result: dict, *, notes: tuple[str, ...] = ()) -> str:
    conditions = result["conditions"]
    adversarial = [c for c in conditions if c["noise_px"]]
    main = [c for c in conditions if not c["noise_px"]]
    lines = [
        f"# {result['experiment_id']} — {result['title']}",
        "",
        f"- Created (UTC): `{result['created_at_utc']}`",
        f"- Code commit: `{result['code_commit']}`",
        f"- Warm-up frames excluded per condition: {result['warmup_frames']}; "
        f"measured repeats: {result['repeats_per_condition']} (adversarial: 1 warm-up + N)",
        f"- Clock: {result['measurement_method']['clock']}",
        f"- Memory: {result['measurement_method']['memory']}",
        f"- Environment: {result['environment']['platform']}, {result['environment']['cpu_model']}, "
        f"numpy {result['environment']['numpy_version']}, "
        f"python {result['environment']['python_version']}",
        "",
        "All numbers are per-frame medians (p50) over the measured frames of a deterministic",
        "synthetic scene; full distributions and memory peaks are in `result.json`.",
        "`region_metadata_json` is the exact serialized size of the frame's object records",
        "(compact canonical JSON, as written to `regions.json`).",
        "",
    ]
    by_res: dict[tuple[int, int], list[dict]] = {}
    for cond in main:
        by_res.setdefault((cond["width"], cond["height"]), []).append(cond)
    for (w, h), conds in sorted(by_res.items()):
        lines += [
            f"## Main matrix — {w}×{h}",
            "",
            "| scene | L | extract p50 (ms) | labeling p50 (ms) | records p50 (ms) | p95 (ms) | "
            "regions/frame | dropped/frame | raw B | intensity B | labels B | metadata B | "
            "metadata/raw | peak MB |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for cond in sorted(conds, key=lambda c: (c["scene"], c["levels"])):
            b = cond["bytes_per_frame"]
            lines.append(
                f"| {cond['scene']} | {cond['levels']} | {_ms(cond['extraction_ns']['p50'])} | "
                f"{_ms(cond['labeling_ns']['p50']) if 'labeling_ns' in cond else '—'} | "
                f"{_ms(cond['records_ns']['p50']) if 'records_ns' in cond else '—'} | "
                f"{_ms(cond['extraction_ns']['p95'])} | {cond['regions_per_frame']['p50']:.0f} | "
                f"{cond['dropped_per_frame']['p50']:.0f} | {b['raw_rgb']} | {b['intensity_u8']} | "
                f"{b['labels_i32']} | {b['region_metadata_json']} | "
                f"{_pct(b['region_metadata_json'], b['raw_rgb'])} | "
                f"{cond['peak_alloc_bytes'] / 1e6:.1f} |"
            )
        lines.append("")
    lines += [
        "## Adversarial — dense per-pixel noise (L=256)",
        "",
        "`static` scene with every frame pixel replaced by a random level: the worst case for",
        "the number of 4-connected runs, and therefore for region-count-dependent costs.",
        "",
        "| size | noise_px | min_area | extract p50 (ms) | regions/frame | dropped/frame | "
        "labels B | metadata B | metadata/raw | peak MB |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for cond in sorted(adversarial, key=lambda c: (c["width"], c["height"])):
        b = cond["bytes_per_frame"]
        lines.append(
            f"| {cond['width']}×{cond['height']} | {cond['noise_px']} | {cond['min_area']} | "
            f"{_ms(cond['extraction_ns']['p50'])} | {cond['regions_per_frame']['p50']:.0f} | "
            f"{cond['dropped_per_frame']['p50']:.0f} | {b['labels_i32']} | "
            f"{b['region_metadata_json']} | {_pct(b['region_metadata_json'], b['raw_rgb'])} | "
            f"{cond['peak_alloc_bytes'] / 1e6:.1f} |"
        )
    if notes:
        lines += ["", "## Method / envelope notes (recorded facts)", ""]
        lines += [f"- {note}" for note in notes]
    lines += [
        "",
        "## Reading notes (honesty rules, plan §25/§39)",
        "",
        "- Label maps are int32, so they are 4 bytes/pixel — 4/3 of the uint8 intensity map and",
        "  exactly 4/3 of one raw RGB channel-set (i.e. 4/9 of raw RGB bytes). This is reported,",
        "  not hidden: an int32 label map is not a compression of the frame.",
        "- Region metadata grows with the number of regions, not with area: at high level counts",
        "  and noisy scenes it dominates every other artifact. The adversarial block above is the",
        "  honest envelope of the reference implementation; `min_area` is the designed lever",
        "  (discards are counted, never silent).",
        "- These are **cost** numbers only; no accuracy, robustness or tracking claims are made.",
        "  Cross-frame identity is explicitly out of scope for Phase 2 (VIE-SPEC-REP 1.1.0 §R3.4).",
        "- Optimization is deliberately deferred (plan §3.14/§8); these numbers are the baseline",
        "  a later profiling phase must beat.",
    ]
    return "\n".join(lines) + "\n"


def _parse_adversarial(text: str) -> tuple[tuple[int, int, int, int], ...]:
    """`widthxheight:min_area:frames` list → tuples (the documented envelope)."""
    specs: list[tuple[int, int, int, int]] = []
    for item in text.split(","):
        item = item.strip()
        if not item:
            continue
        size, min_area, frames = item.split(":")
        width, height = size.lower().split("x")
        specs.append((int(width), int(height), int(min_area), int(frames)))
    return tuple(specs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vie-objects-benchmark", description=__doc__)
    parser.add_argument("--output", default="experiments/EXP-0002-object-extraction")
    parser.add_argument("--experiment-id", default="EXP-0002")
    parser.add_argument(
        "--title",
        default="Phase 2 intensity-object extraction: cost of labeling, identity and metadata",
    )
    parser.add_argument("--frames", type=int, default=5)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--levels", default="8,16,64,256")
    parser.add_argument("--resolutions", default="320x240,640x480,1920x1080")
    parser.add_argument("--scenes", default=",".join(DEFAULT_SCENES))
    parser.add_argument(
        "--adversarial", default="320x240:1:3,640x480:1:3,1920x1080:2:3",
        help="widthxheight:min_area:frames list for the dense-noise block",
    )
    parser.add_argument("--note", action="append", default=[], help="fact to record in report.md")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    run_benchmark(
        args.output,
        experiment_id=args.experiment_id,
        title=args.title,
        levels=tuple(int(x) for x in args.levels.split(",")),
        resolutions=tuple(
            tuple(int(v) for v in item.lower().split("x")) for item in args.resolutions.split(",")
        ),
        scenes=tuple(s.strip() for s in args.scenes.split(",") if s.strip()),
        frames=args.frames,
        warmup=args.warmup,
        adversarial_specs=_parse_adversarial(args.adversarial),
        notes=tuple(args.note),
        seed=args.seed,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
