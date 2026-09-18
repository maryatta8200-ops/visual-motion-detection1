"""Object extraction stage: intensity map in, regions + label map out.

Thin, *measurement-visible* wrapper around the labeling core: this is the module
EXP-0002 times, and the module the pipeline calls. It owns the conversion from
the label field to `vie.intensity-object/1` records (ids, symbols, fingerprints)
so that identity rules live in exactly one place (§R3, §R4).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..config import canonical_json
from ..errors import RegionExtractionError
from ..intensity.intensity_map import IntensityMap
from ..intensity.vocabulary import IntensityVocabulary
from ..provenance import sha256_bytes
from .labeling import LabelMapResult, label_level_uniform_regions
from .objects_config import ObjectsConfig

OBJECT_SCHEMA = "vie.intensity-object/1"


@dataclass(frozen=True)
class ExtractedObject:
    """One `vie.intensity-object/1` record plus its pixel mask rows."""

    frame_index: int
    region_id: int
    level: int
    symbol: str
    area: int
    bbox: tuple[int, int, int, int]
    centroid: tuple[float, float]
    fingerprint: str

    def to_dict(self) -> dict:
        return {
            "schema": OBJECT_SCHEMA,
            "frame_index": self.frame_index,
            "region_id": self.region_id,
            "level": self.level,
            "symbol": self.symbol,
            "area": self.area,
            "bbox": list(self.bbox),
            "centroid": [self.centroid[0], self.centroid[1]],
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True)
class ExtractedFrame:
    frame_index: int
    objects: tuple[ExtractedObject, ...]
    labels: np.ndarray
    dropped_regions: int
    dropped_pixels: int

    @property
    def region_count(self) -> int:
        return len(self.objects)


def object_fingerprint(*, level: int, area: int, bbox: tuple[int, int, int, int],
                       centroid: tuple[float, float]) -> str:
    """Content signature of a region — *not* a cross-frame identity (§R3).

    sha256 over the canonical JSON of exactly {area, bbox, centroid, level}; two
    regions in different frames with the same signature are content-identical,
    which is checkable and cheap, but says nothing about tracking identity.
    """
    payload = {
        "area": int(area),
        "bbox": [int(v) for v in bbox],
        "centroid": [float(centroid[0]), float(centroid[1])],
        "level": int(level),
    }
    return sha256_bytes(canonical_json(payload).encode("utf-8"))


def extract_objects(
    imap: IntensityMap,
    vocabulary: IntensityVocabulary,
    config: ObjectsConfig,
) -> ExtractedFrame:
    """Label one quantized frame and build its deterministic object records."""
    result = label_level_uniform_regions(imap.intensity, vocabulary.levels, config)
    return _to_extracted_frame(imap.frame.frame_index, result, vocabulary)


def extract_label_map(
    intensity: np.ndarray,
    levels: int,
    config: ObjectsConfig,
) -> LabelMapResult:
    """Label-map-only entry point (used by the cost experiment to separate stages)."""
    return label_level_uniform_regions(intensity, levels, config)


def _to_extracted_frame(
    frame_index: int, result: LabelMapResult, vocabulary: IntensityVocabulary
) -> ExtractedFrame:
    symbols = {tok.token_id: tok.symbol for tok in vocabulary.tokens}
    objects: list[ExtractedObject] = []
    for region_id, region in enumerate(result.regions):
        if region.level not in symbols:
            raise RegionExtractionError(
                f"intensity level {region.level} has no token in vocabulary "
                f"{vocabulary.vocabulary_version} (levels={vocabulary.levels})"
            )
        bbox = (region.x0, region.y0, region.x1, region.y1)
        centroid = (region.centroid_x, region.centroid_y)
        objects.append(
            ExtractedObject(
                frame_index=frame_index,
                region_id=region_id,
                level=region.level,
                symbol=symbols[region.level],
                area=region.area,
                bbox=bbox,
                centroid=centroid,
                fingerprint=object_fingerprint(
                    level=region.level, area=region.area, bbox=bbox, centroid=centroid
                ),
            )
        )
    return ExtractedFrame(
        frame_index=frame_index,
        objects=tuple(objects),
        labels=result.labels,
        dropped_regions=result.dropped_regions,
        dropped_pixels=result.dropped_pixels,
    )


def module_info() -> dict:
    return {
        "module": "visual_intensity_engine.objects.extraction",
        "version": "1.0.0",
        "input_schema": "IntensityMap + vie.vocabulary/1 + vie.objects-config/1",
        "output_schema": "ExtractedFrame (vie.intensity-object/1 records + int32 label map)",
        "config_schema": "vie.objects-config/1",
        "error_behavior": "propagates RegionExtractionError from the labeling core",
        "logging_behavior": "silent",
        "performance_expectations": "dominated by O(H*W) labeling; measured in EXP-0002",
        "test_coverage": "tests/unit/test_object_extraction.py",
    }
