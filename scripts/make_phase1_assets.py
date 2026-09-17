#!/usr/bin/env python
"""Regenerate Phase 1 documentation assets (deterministic panels + legends)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from visual_intensity_engine.config import PipelineConfig
from visual_intensity_engine.input.synthetic import SyntheticSource
from visual_intensity_engine.intensity.vocabulary import IntensityVocabulary
from visual_intensity_engine.pipeline import process_frame
from visual_intensity_engine.visualization.render import render_frame_panel, render_palette_legend


def main() -> int:
    out = ROOT / "docs" / "phase-1" / "assets"
    out.mkdir(parents=True, exist_ok=True)
    src = SyntheticSource("moving_square", (192, 144), 3, seed=42, levels=16)
    rec = list(src.frames())[2]
    for levels in (8, 16, 64):
        config = PipelineConfig.default(levels=levels)
        vocab = IntensityVocabulary.build_uniform(levels)
        pf = process_frame(rec, config, vocab)
        render_frame_panel(
            rec.data, pf.y, pf.imap.intensity, vocab,
            title=f"idx={rec.frame_index} ts={rec.timestamp_us}us",
            out_path=out / f"panel_moving_square_l{levels}.png",
        )
        render_palette_legend(vocab, out_path=out / f"palette_legend_l{levels}.png")
    print(f"assets written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
