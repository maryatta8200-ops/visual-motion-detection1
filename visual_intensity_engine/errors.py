"""Typed error hierarchy (VIE-SPEC-REP §11).

Rule: modules fail explicitly on invalid input; no silent fallbacks, no silent
data loss. Every error message is actionable (says what was wrong and where).
"""

from __future__ import annotations


class VIEError(Exception):
    """Base class for all engine errors."""


class ConfigError(VIEError):
    """Configuration missing, unreadable, or invalid against its JSON Schema."""


class FrameValidationError(VIEError):
    """A frame violated the input-domain contract (shape, dtype, range, alpha)."""


class NonFinitePixelError(FrameValidationError):
    """NaN/±Inf pixels encountered under non_finite_policy='strict'."""


class SourceError(VIEError):
    """A frame source could not be opened/produced frames, or violated
    timestamp rules in strict mode."""


class SerializationError(VIEError):
    """Frame-store I/O failure, checksum mismatch, or malformed manifest."""


class CompatibilityError(VIEError):
    """Vocabulary/config incompatibility when reading a stored bundle."""
