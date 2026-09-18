"""Phase 1 pipeline: source → grayscale → quantization → frame store.

Implements MASTER_PLAN §33 Phase 1 (video → grayscale → quantization →
visualization) with per-frame timing, anomaly counting, and full provenance.
Raw frames stay available at the source; every emitted IntensityMap is
traceable to its frame (plan §2). The per-frame core is `process_frame`;
`run_pipeline` wires a FrameSource, collects metrics, and persists the store.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .config import PipelineConfig
from .errors import SourceError, VIEError
from .input.framesource import FrameRecord
from .intensity.intensity_map import FrameInfo, IntensityMap
from .intensity.vocabulary import IntensityVocabulary
from .metrics import summarize
from .preprocessing.grayscale import to_grayscale
from .preprocessing.quantization import quantize
from .provenance import capture_provenance
from .serialization.store import FrameStoreWriter

logger = logging.getLogger("vie.pipeline")


@dataclass
class ProcessedFrame:
    imap: IntensityMap
    y: np.ndarray            # float64 luminance (visualization / inspection)
    gray_ns: float
    quantize_ns: float


def process_frame(record: FrameRecord, config: PipelineConfig, vocabulary: IntensityVocabulary) -> ProcessedFrame:
    """One frame through the Phase 1 core; pure except for anomaly counters."""
    t0 = time.perf_counter_ns()
    y, non_finite_coerced, clipped = to_grayscale(
        record.data, config.input_domain, implementation=config.quantization.implementation
    )
    t1 = time.perf_counter_ns()
    q = quantize(y, config.quantization)
    t2 = time.perf_counter_ns()
    if vocabulary.levels != config.quantization.levels:
        raise VIEError(
            f"vocabulary levels {vocabulary.levels} != configured levels {config.quantization.levels}"
        )
    imap = IntensityMap(
        intensity=q,
        levels=vocabulary.levels,
        vocabulary_version=vocabulary.vocabulary_version,
        config_sha256=config.sha256(),
        frame=FrameInfo(
            frame_index=record.frame_index,
            source_frame_id=record.source_frame_id,
            timestamp_us=record.timestamp_us,
            wall_time_utc=record.wall_time_utc,
            height=int(q.shape[0]),
            width=int(q.shape[1]),
        ),
        non_finite_coerced=non_finite_coerced,
        clipped_to_range=clipped,
        alpha_dropped=bool(
            record.data.ndim == 3 and record.data.shape[2] == 4
            and config.input_domain.alpha_policy == "drop"
        ),
        warnings=record.warnings,
    )
    return ProcessedFrame(imap=imap, y=y, gray_ns=t1 - t0, quantize_ns=t2 - t1)


@dataclass
class PipelineMetrics:
    gray_ns: list[float] = field(default_factory=list)
    quantize_ns: list[float] = field(default_factory=list)
    end_to_end_ns: list[float] = field(default_factory=list)
    source_warnings: int = 0

    def summary(self) -> dict:
        return {
            "frames": len(self.end_to_end_ns),
            "gray": summarize(self.gray_ns),
            "quantize": summarize(self.quantize_ns),
            "end_to_end": summarize(self.end_to_end_ns),
            "source_warnings": self.source_warnings,
        }


@dataclass
class PipelineResult:
    outdir: Path
    manifest: dict
    metrics: dict
    warnings: list[str] = field(default_factory=list)


# (frame_index, raw_rgb, gray_float64, quantized_map) -> None
FrameObserver = Callable[[int, np.ndarray, np.ndarray, np.ndarray], None]


def run_pipeline(
    source,
    config: PipelineConfig,
    outdir: Path | str,
    *,
    previews: int = 0,
    on_frame: FrameObserver | None = None,
) -> PipelineResult:
    """Run the Phase 1 pipeline over a FrameSource and persist a frame store.

    `on_frame(frame_index, raw, gray, qmap)` is an optional observer for the
    live viewer; it is excluded from batch timing semantics.
    """
    started = time.perf_counter()
    outdir = Path(outdir)
    vocabulary = IntensityVocabulary.build_uniform(
        config.quantization.levels, luma_standard=config.input_domain.luma_standard
    )
    writer = FrameStoreWriter(
        outdir,
        config=config,
        vocabulary=vocabulary,
        input_description=source.describe(),
        provenance=capture_provenance(seed=config.seed),
    )
    metrics = PipelineMetrics()
    warnings: list[str] = []
    preview_dir = outdir / "previews" if previews else None
    if preview_dir is not None:
        preview_dir.mkdir(parents=True, exist_ok=True)
    n_seen = 0
    try:
        for record in source.frames():
            t_start = time.perf_counter_ns()
            pf = process_frame(record, config, vocabulary)
            t_end = time.perf_counter_ns()
            metrics.gray_ns.append(pf.gray_ns)
            metrics.quantize_ns.append(pf.quantize_ns)
            metrics.end_to_end_ns.append(t_end - t_start)
            if record.warnings:
                metrics.source_warnings += len(record.warnings)
                warnings.extend(record.warnings)
            writer.add(pf.imap)
            if preview_dir is not None and n_seen < previews:
                from .visualization.render import render_frame_panel

                render_frame_panel(
                    record.data,
                    pf.y,
                    pf.imap.intensity,
                    vocabulary,
                    title=f"frame {record.frame_index}",
                    out_path=preview_dir / f"preview_{n_seen:06d}.png",
                )
            if on_frame is not None:
                on_frame(record.frame_index, record.data, pf.y, pf.imap.intensity)
            n_seen += 1
    except (SourceError, VIEError):
        raise

    if config.max_frames is not None and n_seen < config.max_frames:
        msg = f"source ended early: {n_seen}/{config.max_frames} requested frames"
        if config.strict:
            raise SourceError(msg + " (strict mode)")
        warnings.append(msg)
        logger.warning(msg)

    manifest = writer.close(duration_s=time.perf_counter() - started)
    duration = manifest["provenance"]["duration_s"]
    logger.info("pipeline done: %d frame(s), %d warning(s), %.2fs", n_seen, len(warnings), duration)
    return PipelineResult(outdir=outdir, manifest=manifest, metrics=metrics.summary(), warnings=warnings)


def record_time(record: FrameRecord) -> float:
    """Placeholder hook (frame arrival time) — currently 0; keeps timing honest."""
    return 0.0


def module_info() -> dict:
    return {
        "module": "visual_intensity_engine.pipeline",
        "version": "1.0.0",
        "input_schema": "FrameSource + PipelineConfig",
        "output_schema": "vie-framestore/1 bundle + PipelineResult.metrics",
        "config_schema": "PipelineConfig (schemas/pipeline_config.schema.json)",
        "error_behavior": "SourceError/FrameValidationError/ConfigError propagated; strict early-end raises",
        "logging_behavior": "INFO summaries on 'vie.pipeline'",
        "performance_expectations": "measured (EXP-0001): end-to-end p50 2.4 ms 320x240, "
                                    "9.5 ms 640x480, 84 ms 1920x1080 single-core "
                                    "(float64 luminance dominates); no target claimed",
        "test_coverage": "tests/integration/, tests/property/, tests/regression/, tests/unit/test_module_info.py",
    }
