"""Visualization: deterministic palette, frame panels, palette legend.

Deterministic (plan §21/§36): the palette is a pure function of
(levels, palette_seed) recorded in the vocabulary, so published figures can
be regenerated exactly. These renderers serve inspection; the live server
separately marks its output as exploratory-only (plan §21).
"""

from __future__ import annotations

import colorsys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from ..intensity.intensity_map import validate_intensity_map
from ..intensity.vocabulary import IntensityVocabulary
from ..preprocessing.grayscale import to_uint8_gray


def deterministic_palette(levels: int, seed: int = 0) -> list[tuple[int, int, int]]:
    """Perceptually spread colors; pure function of (levels, seed).

    Golden-angle hue walk in HSV with fixed s/v, rotated by the seed. I0 maps
    to near-black and I(L-1) to near-white so grayscale structure reads
    through; middle tokens get distinct hues.
    """
    colors: list[tuple[int, int, int]] = []
    if levels <= 2:
        return [(10, 10, 10), (245, 245, 245)][:levels]
    golden = 137.508 * (1 + (seed % 7) / 11.0)
    for k in range(levels):
        t = k / (levels - 1)
        if k == 0:
            colors.append((8, 8, 8))
            continue
        if k == levels - 1:
            colors.append((248, 248, 248))
            continue
        hue = ((k * golden + seed * 47.0) % 360.0) / 360.0
        sat = 0.62 - 0.25 * abs(t - 0.5) * 2 * 0.5
        val = 0.35 + 0.55 * t
        r, g, b = colorsys.hsv_to_rgb(hue, max(0.25, sat), val)
        colors.append((int(r * 255), int(g * 255), int(b * 255)))
    return colors


def colorize(map_: np.ndarray, palette: list[tuple[int, int, int]]) -> np.ndarray:
    validate_intensity_map(map_, len(palette))
    lut = np.array(palette, dtype=np.uint8)
    return lut[map_]


def render_frame_panel(
    raw: np.ndarray,
    y: np.ndarray,
    qmap: np.ndarray,
    vocabulary: IntensityVocabulary,
    *,
    title: str,
    out_path,
) -> Image.Image:
    """Side-by-side ORIGINAL | GRAYSCALE | QUANTIZED with labels (plan §20)."""
    palette = deterministic_palette(vocabulary.levels, vocabulary.palette_seed)
    panels = [
        Image.fromarray(_as_uint8_rgb(raw)),
        Image.fromarray(np.stack([to_uint8_gray(y)] * 3, axis=-1)),
        Image.fromarray(colorize(qmap, palette)),
    ]
    h = max(p.height for p in panels)
    w = sum(p.width for p in panels)
    header = 26
    canvas = Image.new("RGB", (w, h + header), (24, 24, 24))
    draw = ImageDraw.Draw(canvas)
    labels = ["ORIGINAL", "GRAYSCALE", f"QUANTIZED L={vocabulary.levels}"]
    x = 0
    for panel, label in zip(panels, labels):
        canvas.paste(panel, (x, header))
        draw.text((x + 6, 6), f"{label}  {title}", fill=(230, 230, 230))
        x += panel.width
    out = ImageDraw.Draw(canvas)
    out.text((6, canvas.height - 16), f"vocab={vocabulary.vocabulary_version}", fill=(160, 160, 160))
    _save_png(canvas, out_path)
    return canvas


def _save_png(img: Image.Image, out_path) -> None:
    """Accepts a filesystem path or a writable buffer (e.g. BytesIO)."""
    if hasattr(out_path, "write"):
        img.save(out_path, format="PNG")
    else:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        img.save(str(out_path), format="PNG")


def render_palette_legend(vocabulary: IntensityVocabulary, *, out_path) -> Image.Image:
    """Token → color → [lower, upper) → representative value chart."""
    palette = deterministic_palette(vocabulary.levels, vocabulary.palette_seed)
    cell_h, cell_w = 22, 340
    img = Image.new("RGB", (cell_w, cell_h * vocabulary.levels + 8), (24, 24, 24))
    draw = ImageDraw.Draw(img)
    for k, tok in enumerate(vocabulary.tokens):
        y0 = k * cell_h + 4
        draw.rectangle([6, y0, 30, y0 + cell_h - 6], fill=palette[k], outline=(80, 80, 80))
        hi = 1.0 if tok.upper_inclusive and tok.upper_exclusive is None else tok.upper_exclusive
        draw.text(
            (40, y0 + 2),
            f"{tok.symbol:<5} {tok.label:<18} [{tok.lower_inclusive:.4f}, {hi:.4f}) rep={tok.representative_value:.4f}",
            fill=(225, 225, 225),
        )
    _save_png(img, out_path)
    return img


def _as_uint8_rgb(arr: np.ndarray) -> np.ndarray:
    a = np.asarray(arr)
    if a.ndim == 2:
        a = np.stack([a] * 3, axis=-1)
    if a.dtype != np.uint8:
        if np.issubdtype(a.dtype, np.floating):
            a = np.clip(a * (255.0 if float(a.max(initial=0.0)) <= 1.0 else 1.0), 0, 255)
        a = a.astype(np.uint8)
    if a.shape[2] == 4:
        a = a[..., :3]
    return np.ascontiguousarray(a)


def module_info() -> dict:
    return {
        "module": "visual_intensity_engine.visualization.render",
        "version": "1.0.0",
        "input_schema": "raw frame + luminance + intensity map + vocabulary",
        "output_schema": "PNG panel / legend images",
        "config_schema": "palette from vocabulary (levels, palette_seed)",
        "error_behavior": "propagates validation errors for malformed maps",
        "logging_behavior": "silent",
        "performance_expectations": "~10-30 ms per 1080p panel",
        "test_coverage": "tests/unit/test_render.py",
    }
