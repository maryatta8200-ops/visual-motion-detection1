"""Unit tests: intensity vocabulary (plan §5, VIE-SPEC-REP §5)."""

from __future__ import annotations

import pytest

from visual_intensity_engine.errors import CompatibilityError
from visual_intensity_engine.intensity.vocabulary import (
    CANONICAL_LABELS_L16,
    IntensityVocabulary,
)

from ..conftest import SUPPORTED_LEVELS


@pytest.mark.parametrize("levels", SUPPORTED_LEVELS)
def test_intervals_partition_unit_interval(levels):
    vocab = IntensityVocabulary.build_uniform(levels)
    assert len(vocab.tokens) == levels
    assert vocab.tokens[0].lower_inclusive == 0.0
    for a, b in zip(vocab.tokens, vocab.tokens[1:]):
        assert b.lower_inclusive == pytest.approx(a.upper_exclusive, abs=1e-12)
    last = vocab.tokens[-1]
    assert last.upper_inclusive is True
    assert (last.upper_exclusive is None) or last.upper_exclusive == pytest.approx(1.0)
    assert last.lower_inclusive + 1.0 / levels == pytest.approx(1.0, abs=1e-12)


@pytest.mark.parametrize("levels", SUPPORTED_LEVELS)
def test_symbol_ids_and_representatives(levels):
    vocab = IntensityVocabulary.build_uniform(levels)
    for k, tok in enumerate(vocab.tokens):
        assert tok.token_id == k and tok.symbol == f"I{k}"
        assert tok.representative_value == pytest.approx((k + 0.5) / levels, abs=1e-12)
    assert vocab.vocabulary_version == f"uniform-l{levels}-v1"


def test_canonical_labels_l16():
    vocab = IntensityVocabulary.build_uniform(16)
    assert tuple(t.label for t in vocab.tokens) == CANONICAL_LABELS_L16
    # two distinct tokens share the label "Medium" — labels are human metadata only
    assert vocab.tokens[7].label == vocab.tokens[8].label == "Medium"
    assert vocab.tokens[7].token_id != vocab.tokens[8].token_id


def test_json_round_trip_and_schema_validation(tmp_path):
    import json

    vocab = IntensityVocabulary.build_uniform(16)
    text = vocab.to_json(tmp_path / "vocab.json")
    loaded = json.loads(text)
    # from_dict validates against schemas/intensity_vocabulary.schema.json
    vocab2 = IntensityVocabulary.from_dict(loaded)
    assert vocab2 == vocab
    # and the schema accepts the saved file standalone
    from visual_intensity_engine.config import schemas_dir, validate_against_schema

    validate_against_schema(loaded, schemas_dir() / "intensity_vocabulary.schema.json", what="vocab")


def test_compatibility_rules():
    v16a = IntensityVocabulary.build_uniform(16)
    v16b = IntensityVocabulary.build_uniform(16, luma_standard="bt601")
    assert v16a.compatible_with(v16b)
    v8 = IntensityVocabulary.build_uniform(8)
    assert not v16a.compatible_with(v8)
    v709 = IntensityVocabulary.build_uniform(16, luma_standard="bt709")
    assert not v16a.compatible_with(v709)
    with pytest.raises(CompatibilityError, match="vocabulary mismatch"):
        v16a.require_compatible(v8, context="unit-test")


def test_invariant_violations_rejected():
    tokens = list(IntensityVocabulary.build_uniform(8).tokens)
    broken = tokens[:-1]  # too few tokens
    with pytest.raises(CompatibilityError, match="tokens for levels"):
        IntensityVocabulary(
            strategy="uniform", levels=8, scope="global_fixed", boundary_rule="floor_right_open",
            source_domain={"kind": "normalized_luminance", "luma_standard": "bt601", "range": [0.0, 1.0]},
            tokens=tuple(broken), vocabulary_version="broken",
        )
    mislabeled = list(tokens)
    wrong = mislabeled[3]
    mislabeled[3] = type(wrong)(**{**wrong.__dict__, "symbol": "IX"})
    with pytest.raises(CompatibilityError, match="symbol"):
        IntensityVocabulary(
            strategy="uniform", levels=8, scope="global_fixed", boundary_rule="floor_right_open",
            source_domain={"kind": "normalized_luminance", "luma_standard": "bt601", "range": [0.0, 1.0]},
            tokens=tuple(mislabeled), vocabulary_version="broken",
        )


def test_token_lookup_bounds():
    vocab = IntensityVocabulary.build_uniform(16)
    with pytest.raises(IndexError):
        vocab.token(16)
    with pytest.raises(IndexError):
        vocab.token(-1)
