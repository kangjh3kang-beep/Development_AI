"""Stage 3 벤치 파이프라인 계약 테스트."""

from __future__ import annotations

import json
from pathlib import Path


_BASE = Path(__file__).resolve().parents[2]
_SCRIPT_PATH = _BASE / "scripts" / "perf" / "run_stage3_benchmarks.py"
_SCRIPT_SOURCE = _SCRIPT_PATH.read_text(encoding="utf-8")
_DATASET_PATH = _BASE / "tests" / "fixtures" / "ifc" / "golden_quantity_reference.v1.json"
_REAL_IFC_MANIFEST_PATH = _BASE / "tests" / "fixtures" / "ifc" / "real_ifc_manifest.v1.json"


def test_stage3_script_exists_and_contains_target_constants() -> None:
    assert _SCRIPT_PATH.exists()
    assert "IFC_MAE_TARGET = 0.02" in _SCRIPT_SOURCE
    assert "MONTE_CARLO_MAX_SECONDS = 30.0" in _SCRIPT_SOURCE
    assert "def _evaluate_ifc_accuracy" in _SCRIPT_SOURCE
    assert "def _evaluate_monte_carlo_performance" in _SCRIPT_SOURCE


def test_stage3_script_exports_markdown_and_json_report_outputs() -> None:
    assert "stage3_benchmark_report.json" in _SCRIPT_SOURCE
    assert "stage3_benchmark_report.md" in _SCRIPT_SOURCE
    assert "overall_pass" in _SCRIPT_SOURCE
    assert "--fail-on-target-miss" in _SCRIPT_SOURCE
    assert "--require-real-ifc-min" in _SCRIPT_SOURCE
    assert "_evaluate_real_ifc_manifest" in _SCRIPT_SOURCE


def test_ifc_golden_dataset_schema_is_valid() -> None:
    payload = json.loads(_DATASET_PATH.read_text(encoding="utf-8"))

    assert payload["dataset_version"]
    assert isinstance(payload["cases"], list)
    assert len(payload["cases"]) >= 5

    for case in payload["cases"]:
        assert case["expected_area_sqm"] > 0
        assert case["expected_volume_m3"] > 0
        assert case["actual_area_sqm"] > 0
        assert case["actual_volume_m3"] > 0


def test_ifc_golden_dataset_average_error_meets_target() -> None:
    payload = json.loads(_DATASET_PATH.read_text(encoding="utf-8"))
    errors: list[float] = []

    for case in payload["cases"]:
        errors.append(abs(case["actual_area_sqm"] - case["expected_area_sqm"]) / case["expected_area_sqm"])
        errors.append(abs(case["actual_volume_m3"] - case["expected_volume_m3"]) / case["expected_volume_m3"])

    mae = sum(errors) / len(errors)
    assert mae <= 0.02


def test_real_ifc_manifest_schema_is_valid() -> None:
    payload = json.loads(_REAL_IFC_MANIFEST_PATH.read_text(encoding="utf-8"))

    assert payload["manifest_version"]
    assert payload["generated_by"].endswith("onboard_real_ifc_fixtures.py")
    assert payload["scrub_owner_data"] is True
    assert isinstance(payload["fixtures"], list)
    assert len(payload["fixtures"]) >= 3

    for fixture in payload["fixtures"]:
        assert fixture["id"]
        assert fixture["local_path"].endswith(".ifc")
        assert fixture["expected_schema"]
        assert fixture["expected_area_sqm"] > 0
        assert fixture["expected_volume_m3"] > 0
        assert fixture["expected_element_count"] > 0
        assert fixture["scrub_owner_data"] is True
        assert isinstance(fixture["scrub_summary"], dict)
