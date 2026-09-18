"""Phase 2 pipeline: source → grayscale → quantization → objects → object store.

Mirrors `visual_intensity_engine.pipeline.run_pipeline` for the Phase-1 core and
adds the object-extraction stage, so both stages share the same frame source,
config, vocabulary and provenance conventions. Extraction time is measured
separately from grayscale/quantization (EXP-0002), and the per-frame invariant
`Σ areas + dropped_pixels = H·W` is asserted at the boundary.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..config import PipelineConfig
from ..errors import VIEError
from ..intensity.vocabulary import IntensityVocabulary
from ..metrics import summarize
from ..objects.extraction import ExtractedFrame, extract_objects
from ..objects.objects_config import ObjectsConfig
from ..objects.store import ObjectStoreWriter
from ..provenance import capture_provenance
from .labeling import LabelMapResult  # noqa: F401  (re-exported for callers/tests)

logger = logging.getLogger("vie.objects.pipeline")


@dataclass
class ObjectPipelineMetrics:
    gray_ns: list[float] = field(default_factory=list)
    quantize_ns: list[float] = field(default_factory=list)
    extract_ns: list[float] = field(default_factory=list)
    end_to_end_ns: list[float] = field(default_factory=list)
    regions_kept: int = 0
    regions_dropped: int = 0
    dropped_pixels: int = 0
    source_warnings: int = 0

    def summary(self) -> dict:
        return {
            "frames": len(self.end_to_end_ns),
            "gray": summarize(self.gray_ns),
            "quantize": summarize(self.quantize_ns),
            "extract": summarize(self.extract_ns),
            "end_to_end": summarize(self.end_to_end_ns),
            "regions": {
                "kept": self.regions_kept,
                "dropped": self.regions_dropped,
                "dropped_pixels": self.dropped_pixels,
            },
            "source_warnings": self.source_warnings,
        }


@dataclass
class ObjectPipelineResult:
    outdir: Path
    manifest: dict
    metrics: dict
    warnings: list[str] = field(default_factory=list)


def run_objects(
    source,
    config: PipelineConfig,
    objects_config: ObjectsConfig,
    outdir: Path | str,
    *,
    previews: int = 0,
) -> ObjectPipelineResult:
    """Run the Phase-2 pipeline over a FrameSource and persist an object store."""
    from ..pipeline import process_frame

    started = time.perf_counter()
    outdir = Path(outdir)
    vocabulary = IntensityVocabulary.build_uniform(
        config.quantization.levels, luma_standard=config.input_domain.luma_standard
    )
    writer = ObjectStoreWriter(
        outdir,
        config=config,
        objects_config=objects_config,
        vocabulary=vocabulary,
        input_description=source.describe(),
        provenance=capture_provenance(seed=config.seed),
    )
    metrics = ObjectPipelineMetrics()
    warnings: list[str] = []
    preview_dir = outdir / "previews" if previews else None
    if preview_dir is not None:
        preview_dir.mkdir(parents=True, exist_ok=True)
    n_seen = 0
    for record in source.frames():
        t_start = time.perf_counter_ns()
        pf = process_frame(record, config, vocabulary)
        t_mid = time.perf_counter_ns()
        eframe: ExtractedFrame = extract_objects(pf.imap, vocabulary, objects_config)
        t_end = time.perf_counter_ns()
        if not eframe.labels.size or (
            sum(o.area for o in eframe.objects) + eframe.dropped_pixels
            != int(pf.imap.intensity.size)
        ):
            raise VIEError(
                f"frame {record.frame_index}: region invariant violated "
                f"(Σ areas + dropped_pixels != H·W)"
            )
        metrics.gray_ns.append(pf.gray_ns)
        metrics.quantize_ns.append(pf.quantize_ns)
        metrics.extract_ns.append(t_end - t_mid)
        metrics.end_to_end_ns.append(t_end - t_start)
        metrics.regions_kept += eframe.region_count
        metrics.regions_dropped += eframe.dropped_regions
        metrics.dropped_pixels += eframe.dropped_pixels
        if record.warnings:
            metrics.source_warnings += len(record.warnings)
            warnings.extend(record.warnings)
        writer.add(pf.imap, eframe)
        if preview_dir is not None and n_seen < previews:
            from ..visualization.render import render_object_overlay

            render_object_overlay(
                record.data,
                pf.y,
                pf.imap.intensity,
                eframe,
                vocabulary,
                title=f"frame {record.frame_index}",
                out_path=preview_dir / f"objects_{n_seen:06d}.png",
            )
        n_seen += 1

    manifest = writer.close(
        duration_s=time.perf_counter() - started, metrics=metrics.summary()
    )
    if metrics.regions_dropped:
        logger.info(
            "objects: %d region(s) below min_area discarded (%d pixel(s)) — counted, not hidden",
            metrics.regions_dropped,
            metrics.dropped_pixels,
        )
    logger.info(
        "objects pipeline done: %d frame(s), %d object(s) → %s",
        n_seen,
        metrics.regions_kept,
        outdir,
    )
    return ObjectPipelineResult(
        outdir=outdir, manifest=manifest, metrics=metrics.summary(), warnings=warnings
    )


def module_info() -> dict:
    return {
        "module": "visual_intensity_engine.objects.pipeline",
        "version": "1.0.0",
        "input_schema": "FrameSource + PipelineConfig + vie.objects-config/1",
        "output_schema": "vie-objectstore/1 bundle + ObjectPipelineResult.metrics",
        "config_schema": "vie.objects-config/1",
        "error_behavior": (
            "RegionExtractionError/VIEError on invariant violations or max_regions; "
            "source errors propagate"
        ),
        "logging_behavior": "INFO summaries on 'vie.objects.pipeline'",
        "performance_expectations": (
            "extraction cost measured in EXP-0002 (no target claimed); grayscale/quantization "
            "unchanged from EXP-0001"
        ),
        "test_coverage": "tests/integration/test_objects_pipeline.py, tests/unit/test_spec_example_phase2.py",
    }
