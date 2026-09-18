"""Visual Intensity Engine — Discrete Visual Intensity & Motion Representation.

Stage-gated research platform. Current implemented stage: **Phase 2**
(Phase 1: grayscale + discrete intensity quantization + frame store + visualization;
Phase 2: level-uniform 4-connected intensity objects + deterministic object store).

Every public module exposes `module_info()` describing inputs, outputs, config,
error behavior, logging, performance expectations, coverage and version
(MASTER_PLAN §34). Schema validation happens at module boundaries.
"""

__version__ = "0.1.0"
STAGE = "phase2"

from .errors import (  # noqa: F401
    CompatibilityError,
    ConfigError,
    FrameValidationError,
    NonFinitePixelError,
    SerializationError,
    SourceError,
    VIEError,
)
