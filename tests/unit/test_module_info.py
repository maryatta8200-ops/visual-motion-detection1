"""Module-contract tests (plan §34): every component publishes its contract.

The plan requires each module to declare input/output/config schemas, error and
logging behavior, performance expectations, test coverage, and version. It also
requires claims to be measured (plan §39). An audit (2026-09-18) found
`performance_expectations` strings carrying unmeasured marketing numbers
(">60 fps at 1080p") that contradicted the recorded EXP-0001 measurements, so
these tests now enforce the honesty rule: a rate may appear only together with
its measurement reference or an explicit non-claim.
"""

from __future__ import annotations

import importlib
import re

import pytest

MODULES = [
    "visual_intensity_engine.config",
    "visual_intensity_engine.pipeline",
    "visual_intensity_engine.input.synthetic",
    "visual_intensity_engine.input.video",
    "visual_intensity_engine.intensity.vocabulary",
    "visual_intensity_engine.preprocessing.grayscale",
    "visual_intensity_engine.preprocessing.quantization",
    "visual_intensity_engine.serialization.store",
    "visual_intensity_engine.visualization.render",
    "visual_intensity_engine.visualization.server",
]

REQUIRED_KEYS = {
    "module",
    "version",
    "input_schema",
    "output_schema",
    "config_schema",
    "error_behavior",
    "logging_behavior",
    "performance_expectations",
    "test_coverage",
}

# A bare aspiration like ">60 fps at 1080p" or "~30 fps" is forbidden; a rate is
# allowed only when the same string says how it was obtained / that none is claimed.
UNMEASURED_RATE = re.compile(r"(?<![\w.])[<>≈~≥≤]?\s*\d+(?:\.\d+)?\s*fps", re.IGNORECASE)
MEASUREMENT_MARKERS = ("measured", "no rate claimed", "no target claimed", "excluded from")


def module_infos():
    return [(name, importlib.import_module(name).module_info()) for name in MODULES]


def test_all_components_publish_a_complete_contract():
    for name, info in module_infos():
        missing = REQUIRED_KEYS - set(info)
        assert not missing, f"{name}.module_info() is missing {sorted(missing)}"
        assert info["module"] == name, f"{name}.module_info() declares module={info['module']!r}"
        for key in REQUIRED_KEYS - {"module"}:
            assert isinstance(info[key], str) and info[key].strip(), f"{name}.module_info()[{key!r}] empty"


def test_performance_expectations_are_measured_or_explicitly_disclaimed():
    for name, info in module_infos():
        text = info["performance_expectations"]
        if UNMEASURED_RATE.search(text):
            assert any(marker in text for marker in MEASUREMENT_MARKERS), (
                f"{name}.module_info()['performance_expectations'] states a rate without a "
                f"measurement reference or an explicit non-claim: {text!r} (plan §39)"
            )


def test_module_info_records_stage_and_version():
    import visual_intensity_engine as vie

    assert vie.__version__
    for name, info in module_infos():
        assert info["version"], name


def test_unknown_module_access_fails():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("visual_intensity_engine.no_such_module")
