"""Stage 2 동적 규칙/벤치마크 계약 테스트 (의존성 없는 소스 검증)."""

from __future__ import annotations

import json
from pathlib import Path


_BASE = Path(__file__).resolve().parents[2]
_SEUMTER_SOURCE = (
    _BASE / "apps" / "api" / "services" / "seumter_permit_service.py"
).read_text(encoding="utf-8")
_SEUMTER_RULES_PATH = (
    _BASE / "apps" / "api" / "config_data" / "seumter_permit_rules.default.json"
)
_GRESB_SOURCE = (
    _BASE / "apps" / "api" / "app" / "services" / "esg" / "gresb_scoring_service.py"
).read_text(encoding="utf-8")
_GRESB_BENCHMARK_PATH = (
    _BASE / "apps" / "api" / "config_data" / "gresb_benchmarks_2025.default.json"
)
_CARBON_SOURCE = (
    _BASE / "apps" / "api" / "services" / "carbon_calculation_service.py"
).read_text(encoding="utf-8")
_CARBON_FACTORS_PATH = (
    _BASE / "apps" / "api" / "config_data" / "carbon_factors_ifc.default.json"
)


def test_seumter_service_supports_external_rules_and_contextual_duration() -> None:
    assert "SEUMTER_PERMIT_RULES_PATH" in _SEUMTER_SOURCE
    assert "_load_dynamic_rules" in _SEUMTER_SOURCE
    assert "_estimate_duration_contextual" in _SEUMTER_SOURCE
    assert "applied_multiplier" in _SEUMTER_SOURCE
    assert "_resolve_region_key" in _SEUMTER_SOURCE


def test_seumter_default_rules_have_required_schema() -> None:
    payload = json.loads(_SEUMTER_RULES_PATH.read_text(encoding="utf-8"))
    assert "permit_types" in payload
    assert "building_permit" in payload["permit_types"]
    assert "durations" in payload["permit_types"]["building_permit"]
    assert payload["permit_types"]["building_permit"]["durations"]["seoul"] > 0
    assert "duration_multipliers" in payload
    assert payload["duration_multipliers"]["large_site_multiplier"] >= 1.0


def test_gresb_service_supports_external_benchmarks_and_metadata() -> None:
    assert "GRESB_BENCHMARKS_PATH" in _GRESB_SOURCE
    assert "_load_benchmark_payload" in _GRESB_SOURCE
    assert "BENCHMARK_META" in _GRESB_SOURCE
    assert "refresh_benchmark_cache" in _GRESB_SOURCE
    assert '"benchmark_meta": BENCHMARK_META' in _GRESB_SOURCE


def test_gresb_default_benchmark_file_has_required_building_types() -> None:
    payload = json.loads(_GRESB_BENCHMARK_PATH.read_text(encoding="utf-8"))
    assert "building_types" in payload
    assert "apartment" in payload["building_types"]
    assert payload["building_types"]["apartment"]["energy_kwh_sqm"] > 0
    assert "version" in payload


def test_carbon_service_supports_external_factor_file() -> None:
    assert "CARBON_FACTORS_PATH" in _CARBON_SOURCE
    assert "_load_carbon_factors" in _CARBON_SOURCE
    assert "_DEFAULT_CARBON_FACTORS_PATH" in _CARBON_SOURCE
    assert "self._carbon_factors" in _CARBON_SOURCE


def test_carbon_default_factor_file_has_ifc_schema() -> None:
    payload = json.loads(_CARBON_FACTORS_PATH.read_text(encoding="utf-8"))
    assert "factors" in payload
    assert "IfcWall" in payload["factors"]
    assert payload["factors"]["IfcWall"]["factor"] > 0
    assert payload["factors"]["IfcWall"]["unit"] in {"m³", "m2", "m²", "m3"}
