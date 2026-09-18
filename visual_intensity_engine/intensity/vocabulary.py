"""Intensity vocabulary (plan §5, VIE-SPEC-REP §5).

Machine-readable identity for each discrete intensity level: token id, symbol
(I<k>), half-open interval, deterministic representative value, human label,
quantization identity, compatibility rules, deterministic palette seed.

Token IDs are identifiers, not features: models must not consume raw IDs as
ordered numerics unless a documented ordering decision exists; use
`representative_values` (ordered by construction) or one-hot encodings instead.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..config import schemas_dir, validate_against_schema
from ..errors import CompatibilityError

SCHEMA_NAME = "intensity_vocabulary.schema.json"
SCHEMA_ID = "vie.vocabulary/1"

# Canonical human labels for L=16 exactly as given in MASTER_PLAN §4.
CANONICAL_LABELS_L16 = (
    "Black", "Very Dark", "Dark", "Dark-Low", "Low", "Low-Medium", "Medium-Low",
    "Medium", "Medium", "Medium-High", "High", "Bright-Low", "Bright",
    "Very Bright", "Extremely Bright", "White",
)


@dataclass(frozen=True)
class IntensityToken:
    token_id: int
    symbol: str
    label: str
    lower_inclusive: float
    upper_exclusive: float | None
    upper_inclusive: bool
    representative_value: float
    semantic_metadata: dict | None = None


def _label(k: int, levels: int) -> str:
    if levels == 16:
        return CANONICAL_LABELS_L16[k]
    if k == 0:
        return "Black"
    if k == levels - 1:
        return "White"
    return f"Level {k}"


class IntensityVocabulary:
    """Immutable vocabulary for one quantization configuration."""

    def __init__(
        self,
        *,
        strategy: str,
        levels: int,
        scope: str,
        boundary_rule: str,
        source_domain: dict,
        palette_seed: int = 0,
        tokens: tuple[IntensityToken, ...],
        vocabulary_version: str,
    ):
        self.strategy = strategy
        self.levels = int(levels)
        self.scope = scope
        self.boundary_rule = boundary_rule
        self.source_domain = dict(source_domain)
        self.palette_seed = int(palette_seed)
        self.tokens = tokens
        self.vocabulary_version = vocabulary_version
        self._validate_invariants()

    # ------------------------------------------------------------------
    @classmethod
    def build_uniform(cls, levels: int, *, luma_standard: str = "bt601", palette_seed: int = 0) -> IntensityVocabulary:
        if levels < 2 or levels > 256:
            raise ValueError(f"levels must be in [2,256], got {levels}")
        width = 1.0 / levels
        tokens = []
        for k in range(levels):
            lower = k * width
            upper = (k + 1) * width
            tokens.append(
                IntensityToken(
                    token_id=k,
                    symbol=f"I{k}",
                    label=_label(k, levels),
                    lower_inclusive=lower,
                    upper_exclusive=None if k == levels - 1 else upper,
                    upper_inclusive=(k == levels - 1),
                    representative_value=lower + width / 2.0,
                    semantic_metadata=None,
                )
            )
        return cls(
            strategy="uniform",
            levels=levels,
            scope="global_fixed",
            boundary_rule="floor_right_open",
            source_domain={"kind": "normalized_luminance", "luma_standard": luma_standard, "range": [0.0, 1.0]},
            palette_seed=palette_seed,
            tokens=tuple(tokens),
            vocabulary_version=f"uniform-l{levels}-v1",
        )

    # ------------------------------------------------------------------
    def _validate_invariants(self) -> None:
        width = 1.0 / self.levels
        if len(self.tokens) != self.levels:
            raise CompatibilityError(f"vocabulary has {len(self.tokens)} tokens for levels={self.levels}")
        prev_upper: float | None = None
        for i, tok in enumerate(self.tokens):
            if tok.token_id != i:
                raise CompatibilityError(f"token ids must be 0..L-1 in order; token {i} has id {tok.token_id}")
            if tok.symbol != f"I{i}":
                raise CompatibilityError(f"token {i} symbol must be I{i}, got {tok.symbol}")
            expected_lower = i * width
            if abs(tok.lower_inclusive - expected_lower) > 1e-12:
                raise CompatibilityError(
                    f"token {i} lower bound {tok.lower_inclusive} != expected {expected_lower}"
                )
            if prev_upper is not None and abs(tok.lower_inclusive - prev_upper) > 1e-12:
                raise CompatibilityError(f"token {i} interval does not continue the previous interval")
            prev_upper = tok.upper_exclusive
            expected_repr = expected_lower + width / 2.0
            if abs(tok.representative_value - expected_repr) > 1e-12:
                raise CompatibilityError(
                    f"token {i} representative_value {tok.representative_value} != midpoint {expected_repr}"
                )
        last = self.tokens[-1]
        if not last.upper_inclusive:
            raise CompatibilityError("last token interval must be closed at 1.0")
        if last.upper_exclusive is not None and abs(last.upper_exclusive - 1.0) > 1e-12:
            raise CompatibilityError(f"last token upper bound {last.upper_exclusive} != 1.0")

    # ------------------------------------------------------------------
    @property
    def representative_values(self) -> tuple[float, ...]:
        return tuple(t.representative_value for t in self.tokens)

    def token(self, level: int) -> IntensityToken:
        if not 0 <= level < self.levels:
            raise IndexError(f"level {level} outside [0, {self.levels - 1}]")
        return self.tokens[level]

    def compatible_with(self, other: IntensityVocabulary) -> bool:
        return (
            self.strategy == other.strategy
            and self.levels == other.levels
            and self.scope == other.scope
            and self.boundary_rule == other.boundary_rule
            and self.source_domain == other.source_domain
        )

    def require_compatible(self, other: IntensityVocabulary, *, context: str) -> None:
        if not self.compatible_with(other):
            raise CompatibilityError(
                f"{context}: vocabulary mismatch — stored={other.vocabulary_version} "
                f"({other.strategy}/L={other.levels}/{other.boundary_rule}/{other.scope}/"
                f"{other.source_domain.get('luma_standard')}) vs requested="
                f"{self.vocabulary_version}"
            )

    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "schema": SCHEMA_ID,
            "vocabulary_version": self.vocabulary_version,
            "quantization": {
                "strategy": self.strategy,
                "levels": self.levels,
                "scope": self.scope,
                "boundary_rule": self.boundary_rule,
            },
            "source_domain": self.source_domain,
            "palette_seed": self.palette_seed,
            "tokens": [
                {
                    "token_id": t.token_id,
                    "symbol": t.symbol,
                    "label": t.label,
                    "lower_inclusive": t.lower_inclusive,
                    "upper_exclusive": t.upper_exclusive,
                    "upper_inclusive": t.upper_inclusive,
                    "representative_value": t.representative_value,
                    "semantic_metadata": t.semantic_metadata,
                }
                for t in self.tokens
            ],
        }

    def to_json(self, path: Path | None = None) -> str:
        text = json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"
        if path is not None:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(text, encoding="utf-8")
        return text

    @classmethod
    def from_dict(cls, d: dict, *, validate: bool = True) -> IntensityVocabulary:
        if validate:
            validate_against_schema(d, schemas_dir() / SCHEMA_NAME, what="intensity vocabulary")
        tokens = tuple(IntensityToken(**t) for t in d["tokens"])
        return cls(
            strategy=d["quantization"]["strategy"],
            levels=d["quantization"]["levels"],
            scope=d["quantization"]["scope"],
            boundary_rule=d["quantization"]["boundary_rule"],
            source_domain=d["source_domain"],
            palette_seed=d["palette_seed"],
            tokens=tokens,
            vocabulary_version=d["vocabulary_version"],
        )

    def __eq__(self, other: object) -> bool:
        return isinstance(other, IntensityVocabulary) and self.to_dict() == other.to_dict()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<IntensityVocabulary {self.vocabulary_version}>"


def module_info() -> dict:
    return {
        "module": "visual_intensity_engine.intensity.vocabulary",
        "version": "1.0.0",
        "input_schema": "constructor or vie.vocabulary/1 JSON",
        "output_schema": "IntensityVocabulary (validated invariants)",
        "config_schema": "levels 2..256, strategy uniform, scope global_fixed, boundary floor_right_open",
        "error_behavior": "CompatibilityError on invariant violation; ValueError on bad levels",
        "logging_behavior": "silent",
        "performance_expectations": "build O(L); to_dict O(L)",
        "test_coverage": "tests/unit/test_vocabulary.py",
    }
