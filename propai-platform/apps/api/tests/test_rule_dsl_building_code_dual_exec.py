"""Rule DSL 소비 배선(opt-in) — BuildingCodeRuleEngine BL-001/BL-002 이중 실행 대조.

정답 기준선(baseline) = 기존 ``BuildingCodeRuleEngine._check_bcr``/``_check_far``
(app/services/permit/building_code_rules.py, 무회귀 — 이 파일에서도 변경하지 않는다).
동일 입력에 대해 신규 RuleDef 평가(app/services/rules/consumers/building_code_bl.py)가
같은 수치·같은 준수판정을 내는지 대조한다. 하나라도 불일치하면 배선을 보류해야 하므로
이 테스트가 그 게이트 역할을 한다(정직 보고 — 결과 불일치를 숨기지 않음).
"""
from __future__ import annotations

import pytest

from app.services.permit.building_code_rules import BuildingCodeRuleEngine, ComplianceStatus
from app.services.provenance.fact_status import FactStatus
from app.services.rules.consumers.building_code_bl import evaluate_bl001_bcr, evaluate_bl002_far

_ENGINE = BuildingCodeRuleEngine()


def _actual_pct(actual_value: str) -> float:
    return float(actual_value.rstrip("%"))


@pytest.mark.parametrize(
    ("building_area_sqm", "land_area_sqm", "max_bcr_pct"),
    [
        (120.0, 200.0, 60.0),   # 60% == 60% → 적합(경계값)
        (100.0, 200.0, 60.0),   # 50% < 60% → 적합
        (150.0, 200.0, 60.0),   # 75% > 60% → 부적합
        (48.0, 240.0, 20.0),    # 자연녹지 유형(건폐 20%) → 적합
        (60.0, 240.0, 20.0),    # 25% > 20% → 부적합
    ],
)
def test_bl001_bcr_dual_exec_matches_baseline(
    building_area_sqm: float, land_area_sqm: float, max_bcr_pct: float,
) -> None:
    design = {"building_area_sqm": building_area_sqm}
    site = {"land_area_sqm": land_area_sqm, "max_bcr": max_bcr_pct}

    baseline = _ENGINE._check_bcr(design, site)  # noqa: SLF001 — 정답 기준선 직접 호출(무회귀 대조)
    result = evaluate_bl001_bcr(design, site)

    assert result.status == FactStatus.DERIVED
    assert result.value == pytest.approx(_actual_pct(baseline.actual_value))
    assert result.compliant == (baseline.status == ComplianceStatus.PASS)


@pytest.mark.parametrize(
    ("total_gfa_sqm", "land_area_sqm", "max_far_pct"),
    [
        (400.0, 200.0, 200.0),   # 200% == 200% → 적합(경계값)
        (300.0, 200.0, 200.0),   # 150% < 200% → 적합
        (500.0, 200.0, 200.0),   # 250% > 200% → 부적합
        (200.0, 200.0, 100.0),   # 자연녹지 유형(용적 100%) → 적합
        (240.0, 200.0, 100.0),   # 120% > 100% → 부적합
    ],
)
def test_bl002_far_dual_exec_matches_baseline(
    total_gfa_sqm: float, land_area_sqm: float, max_far_pct: float,
) -> None:
    design = {"total_gfa_sqm": total_gfa_sqm}
    site = {"land_area_sqm": land_area_sqm, "max_far": max_far_pct}

    baseline = _ENGINE._check_far(design, site)  # noqa: SLF001 — 정답 기준선 직접 호출(무회귀 대조)
    result = evaluate_bl002_far(design, site)

    assert result.status == FactStatus.DERIVED
    assert result.value == pytest.approx(_actual_pct(baseline.actual_value))
    assert result.compliant == (baseline.status == ComplianceStatus.PASS)


def test_bl001_bcr_missing_input_is_unknown_baseline_unaffected() -> None:
    """신규 경로는 결손 입력을 UNKNOWN으로 정직 표면화(기존 경로는 변경하지 않음 — 무회귀)."""
    design: dict = {}  # building_area_sqm 결손
    site = {"land_area_sqm": 200.0, "max_bcr": 60.0}

    result = evaluate_bl001_bcr(design, site)
    assert result.status == FactStatus.UNKNOWN
    assert result.value is None

    # 기존 경로는 손대지 않았음을 재확인(design.get 기본값 0 — 여전히 동작).
    baseline = _ENGINE._check_bcr(design, site)  # noqa: SLF001
    assert baseline.status == ComplianceStatus.PASS
