"""Command-line interface (plan §20: batch mode + synthetic test mode).

Subcommands
-----------
process      batch-process a video file or synthetic scene into a frame store
self-test    deterministic synthetic end-to-end check incl. replay byte-equality
benchmark    run the EXP-0001 quantization baseline benchmark
validate     validate a config file or a frame-store bundle
serve        exploratory live viewer (NOT benchmark output)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from . import STAGE, __version__
from .config import PipelineConfig
from .errors import ConfigError, VIEError
from .input.synthetic import SCENES, SyntheticSource
from .intensity.vocabulary import IntensityVocabulary
from .provenance import dumps_json

if TYPE_CHECKING:  # typing-only imports; the CLI stays importable without numpy
    import numpy as np

    from .intensity.intensity_map import IntensityMap

logger = logging.getLogger("vie.cli")


def _resolve_source(spec: str, *, config: PipelineConfig):
    """Input resolution: synthetic:<scene>, camera:<index>, or a file path."""
    if spec.startswith("synthetic:"):
        scene = spec.split(":", 1)[1] or "moving_square"
        if scene not in SCENES:
            raise ConfigError(
                f"unknown synthetic scene '{scene}' (available: {', '.join(SCENES)})"
            )
        return SyntheticSource(
            scene,
            (160, 120),
            config.max_frames or 32,
            seed=config.seed,
            levels=config.quantization.levels,
        )
    if spec.startswith("camera:"):
        if config.max_frames is None:
            # A live camera has no end-of-stream: an unbounded batch run would never
            # return, so require an explicit stop condition (plan §20 stop/resume).
            raise ConfigError(
                "camera batch processing requires an explicit stop condition: "
                "pass --max-frames N (or use --input <file> for a finite source)"
            )
        from .input.video import CameraSource

        return CameraSource(int(spec.split(":", 1)[1]), strict=config.strict)
    from .input.video import VideoFileSource

    return VideoFileSource(spec, max_frames=config.max_frames, strict=config.strict)


def cmd_process(args) -> int:
    config = PipelineConfig.load(args.config) if args.config else PipelineConfig.default(levels=args.levels)
    overrides = {}
    if args.max_frames is not None:
        overrides["max_frames"] = args.max_frames
    if args.seed is not None:
        overrides["seed"] = args.seed
    if args.lenient:
        overrides["strict"] = False
    if overrides:
        config = PipelineConfig(
            quantization=config.quantization,
            input_domain=config.input_domain,
            serialization=config.serialization,
            seed=overrides.get("seed", config.seed),
            max_frames=overrides.get("max_frames", config.max_frames),
            strict=overrides.get("strict", config.strict),
        )
    source = _resolve_source(args.input, config=config)
    outdir = Path(args.output)
    if outdir.exists():
        raise ConfigError(f"output directory already exists (experiments never overwrite): {outdir}")
    from .pipeline import run_pipeline

    result = run_pipeline(
        source, config, outdir,
        previews=args.previews,
    )
    source.close()
    config.save(outdir / "config.json")
    metrics_path = outdir / "metrics.json"
    metrics_path.write_text(dumps_json(result.metrics), encoding="utf-8")
    print(dumps_json({
        "outdir": str(outdir),
        "frames": result.metrics["frames"],
        "config_sha256": config.sha256(),
        "end_to_end_p50_ms": result.metrics["end_to_end"]["p50"] / 1e6,
        "warnings": result.warnings,
    }))
    return 0


def cmd_self_test(args) -> int:
    """Synthetic end-to-end test mode (plan §20): pipeline invariants + replay."""
    from .pipeline import run_pipeline
    from .serialization.store import FrameStoreReader

    levels = args.levels
    config = PipelineConfig.default(levels=levels)
    config = PipelineConfig(
        quantization=config.quantization, input_domain=config.input_domain,
        serialization=config.serialization, seed=42,
    )
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="vie-selftest-") as td:
        root = Path(td)
        # run 1: ramp scene must exercise every level
        src = SyntheticSource("ramp_bands", (256, 32), 4, levels=levels, seed=42)
        run_pipeline(src, config, root / "ramp")
        reader = FrameStoreReader(root / "ramp", expected_vocabulary=IntensityVocabulary.build_uniform(levels))
        maps = reader.load_all()
        if len(maps) != 4:
            failures.append(f"expected 4 frames, got {len(maps)}")
        hist = np_histogram(maps)
        missing = [k for k in range(levels) if hist[k] == 0]
        if missing:
            failures.append(f"ramp scene missed levels {missing}")
        # run 2 + 3: byte-identical replay (plan §2)
        src_b = SyntheticSource("moving_square", (160, 120), 24, seed=42)
        run_pipeline(src_b, config, root / "replay_a")
        src_c = SyntheticSource("moving_square", (160, 120), 24, seed=42)
        run_pipeline(src_c, config, root / "replay_b")
        a = (root / "replay_a" / "intensity_maps.npz").read_bytes()
        b = (root / "replay_b" / "intensity_maps.npz").read_bytes()
        if a != b:
            failures.append("replay produced different intensity_maps.npz bytes")
        ma = json.loads((root / "replay_a" / "manifest.json").read_text())
        mb = json.loads((root / "replay_b" / "manifest.json").read_text())
        for m in (ma, mb):
            m["provenance"].pop("created_at_utc", None)
            m["provenance"].pop("duration_s", None)
        if ma != mb:
            failures.append("replay manifests differ beyond created_at/duration")
        # round-trip equality
        src_d = SyntheticSource("moving_square", (160, 120), 24, seed=42)
        reloaded = FrameStoreReader(root / "replay_a").load_all()
        for rec, stored in zip(src_d.frames(), reloaded, strict=True):
            from .pipeline import process_frame

            pf = process_frame(rec, config, IntensityVocabulary.build_uniform(levels))
            if not (pf.imap.intensity == stored.intensity).all():
                failures.append(f"round-trip mismatch at frame {rec.frame_index}")
                break
    report = {
        "self_test": "phase1",
        "engine_version": __version__,
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
    }
    print(dumps_json(report))
    if args.output:
        Path(args.output).write_text(dumps_json(report), encoding="utf-8")
    return 0 if not failures else 1


def np_histogram(maps: Sequence[IntensityMap]) -> np.ndarray:
    total = None
    for m in maps:
        h = m.histogram
        total = h if total is None else total + h
    if total is None:  # explicit, never a silent empty result (plan §3.10)
        raise VIEError("np_histogram: no intensity maps to summarize")
    return total


def cmd_benchmark(args) -> int:
    from .benchmarking.runner import main as bench_main

    argv = ["--output", args.output, "--experiment-id", args.experiment_id,
            "--frames", str(args.frames), "--warmup", str(args.warmup),
            "--scene", args.scene, "--seed", str(args.seed)]
    return bench_main(argv)


def cmd_validate(args) -> int:
    target = Path(args.target)
    if target.is_dir():
        from .serialization.store import FrameStoreReader

        reader = FrameStoreReader(target)  # verifies checksums + schema
        n = len(reader.frame_indices())
        print(dumps_json({"kind": "frame-store", "path": str(target), "frames": n,
                          "config_sha256": reader.config_sha256,
                          "vocabulary": reader.vocabulary.vocabulary_version, "status": "VALID"}))
    else:
        config = PipelineConfig.load(target)
        print(dumps_json({"kind": "config", "path": str(target), "sha256": config.sha256(),
                          "status": "VALID"}))
    return 0


def cmd_serve(args) -> int:
    from .visualization.server import is_loopback_bind, serve

    logger.warning("live viewer is EXPLORATORY ONLY — never benchmark output (plan §21)")
    log_path = Path(args.log_path) if args.log_path else Path("logs/viewer_interactions.jsonl")
    logger.info("viewer interaction log: %s", log_path.resolve())
    if not is_loopback_bind(args.host):
        logger.warning(
            "binding the viewer to %s exposes it to the network without authentication; "
            "it is for local inspection on trusted networks only (plan §41)",
            args.host,
        )
    server = serve(
        host=args.host,
        port=args.port,
        seed=args.seed,
        log_path=log_path,
        allowed_hosts=tuple(args.allowed_host or ()),
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover
        server.shutdown()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vie",
        description=(
            f"Visual Intensity Engine v{__version__} — stage {STAGE} "
            "(Discrete Visual Intensity & Motion Representation)"
        ),
    )
    parser.add_argument("--version", action="version", version=f"vie {__version__} ({STAGE})")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("process", help="batch-process a source into a frame store")
    p.add_argument("--input", required=True,
                   help="video file path | synthetic:<scene> | camera:<index>")
    p.add_argument("--config", help="config JSON (defaults to uniform L=16)")
    p.add_argument("--levels", type=int, default=16)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--max-frames", type=int, default=None)
    p.add_argument("--lenient", action="store_true", help="record anomalies instead of failing (strict by default)")
    p.add_argument("--previews", type=int, default=3, help="render N preview panels")
    p.add_argument("--output", required=True)
    p.set_defaults(func=cmd_process)

    p = sub.add_parser("self-test", help="deterministic synthetic end-to-end check")
    p.add_argument("--levels", type=int, default=16)
    p.add_argument("--output", default=None, help="optional path for the JSON report")
    p.set_defaults(func=cmd_self_test)

    p = sub.add_parser("benchmark", help="run the quantization baseline benchmark")
    p.add_argument("--output", default="experiments/EXP-0001-quantization-baseline")
    p.add_argument("--experiment-id", default="EXP-0001")
    p.add_argument("--frames", type=int, default=30)
    p.add_argument("--warmup", type=int, default=8)
    p.add_argument("--scene", default="gradient")
    p.add_argument("--seed", type=int, default=0)
    p.set_defaults(func=cmd_benchmark)

    p = sub.add_parser("validate", help="validate a config file or frame-store bundle")
    p.add_argument("--target", required=True)
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("serve", help="exploratory live viewer (NOT benchmark output)")
    p.add_argument("--host", default="127.0.0.1",
                   help="bind address (default loopback; the viewer has no authentication, "
                        "so network exposure is an explicit opt-in, e.g. --host 0.0.0.0)")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--allowed-host", action="append", default=None, metavar="NAME",
                   help="extra Host header name to accept (repeatable; for reverse proxies "
                        "or tunnels that rewrite Host)")
    p.add_argument("--log-path", default=None, metavar="PATH",
                   help="interaction log location (default: logs/viewer_interactions.jsonl "
                        "relative to the working directory)")
    p.set_defaults(func=cmd_serve)
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except VIEError as exc:
        logger.error("%s: %s", type(exc).__name__, exc)
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
