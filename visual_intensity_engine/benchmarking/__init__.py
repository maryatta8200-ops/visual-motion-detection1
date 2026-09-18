"""Benchmarking package: recorded experiment runners (EXP-0001, EXP-0002).

Experiment outputs are *records*: `experiments/registry.json` is append-only and
`process` / `objects` refuse to reuse an output directory. The benchmark runners
enforce the same rule (audit AUD-03): an existing non-empty output directory is a
hard error unless the caller explicitly opts in with ``overwrite=True`` (the
``--overwrite`` flag), and even then only the runner's own files are replaced —
nothing is deleted.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ..errors import ConfigError

logger = logging.getLogger("vie.benchmarking")

# Files a benchmark run owns inside its output directory. `--overwrite` replaces
# these and nothing else.
BENCHMARK_OUTPUT_FILES = ("result.json", "report.md")


def prepare_experiment_outdir(
    outdir: Path | str, *, experiment_id: str, overwrite: bool = False
) -> Path:
    """Validate an experiment output directory before a benchmark writes to it.

    Refuses an existing non-empty directory unless `overwrite=True`. With
    `overwrite=True`, logs a WARNING naming the files that will be replaced.
    Never deletes anything: the run is additive apart from its own artifacts.
    """
    outdir = Path(outdir)
    existing = sorted(p.name for p in outdir.iterdir()) if outdir.is_dir() else []
    if existing and not overwrite:
        raise ConfigError(
            f"experiment output directory {outdir} already exists and is not empty "
            f"({len(existing)} entr{'y' if len(existing) == 1 else 'ies'}, "
            f"e.g. {', '.join(existing[:3])}); recorded experiments are never overwritten "
            f"(plan §38). Choose a new --output, or pass --overwrite to replace "
            f"{' and '.join(BENCHMARK_OUTPUT_FILES)} for {experiment_id}."
        )
    if existing:
        logger.warning(
            "OVERWRITING recorded benchmark artifacts in %s: %s for %s "
            "(any other files in that directory are left untouched)",
            outdir,
            " and ".join(BENCHMARK_OUTPUT_FILES),
            experiment_id,
        )
    outdir.mkdir(parents=True, exist_ok=True)
    return outdir


__all__ = ["BENCHMARK_OUTPUT_FILES", "prepare_experiment_outdir"]
