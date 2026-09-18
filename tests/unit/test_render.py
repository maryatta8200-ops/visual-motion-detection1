"""Unit tests: deterministic visualization (plan §21/§36)."""

from __future__ import annotations

import numpy as np
import pytest

from visual_intensity_engine.intensity.vocabulary import IntensityVocabulary
from visual_intensity_engine.visualization.render import (
    colorize,
    deterministic_palette,
    render_frame_panel,
    render_palette_legend,
)


def test_palette_deterministic_and_distinct():
    p1 = deterministic_palette(16, 0)
    p2 = deterministic_palette(16, 0)
    p3 = deterministic_palette(16, 1)
    assert p1 == p2
    assert p1 != p3
    assert len(set(p1)) == 16  # all 16 colors distinct
    assert p1[0] == (8, 8, 8) and p1[-1] == (248, 248, 248)


@pytest.mark.parametrize("levels", (8, 16, 64))
def test_colorize_exact_lookup(levels):
    vocab = IntensityVocabulary.build_uniform(levels)
    palette = deterministic_palette(levels, vocab.palette_seed)
    q = np.array([[0, levels - 1], [levels // 2, 1]], np.uint8)
    img = colorize(q, palette)
    assert img.shape == (2, 2, 3)
    assert img[0, 0].tolist() == list(palette[0])
    assert img[0, 1].tolist() == list(palette[levels - 1])
    from visual_intensity_engine.errors import FrameValidationError

    with pytest.raises(FrameValidationError):
        colorize(np.array([[levels]], np.uint8), palette)  # id out of range


def test_render_frame_panel_is_byte_deterministic(tmp_path, small_rgb):
    vocab = IntensityVocabulary.build_uniform(16)
    from visual_intensity_engine.config import InputDomainSettings
    from visual_intensity_engine.preprocessing.grayscale import to_grayscale
    from visual_intensity_engine.preprocessing.quantization import quantize_uniform

    y, _, _ = to_grayscale(small_rgb, InputDomainSettings())
    q = quantize_uniform(y, 16)
    outs = []
    for i in (1, 2):
        p = tmp_path / f"panel{i}.png"
        render_frame_panel(small_rgb, y, q, vocab, title="t", out_path=p)
        outs.append(p.read_bytes())
    assert outs[0] == outs[1]


def test_render_palette_legend(tmp_path):
    vocab = IntensityVocabulary.build_uniform(16)
    out = tmp_path / "legend.png"
    img = render_palette_legend(vocab, out_path=out)
    assert out.is_file() and img.height >= 16 * 22
