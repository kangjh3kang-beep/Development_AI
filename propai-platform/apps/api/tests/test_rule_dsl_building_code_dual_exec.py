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


# ── 경계값 발산(R1 MEDIUM-2): baseline은 클램프/기본값으로 조용히 수치를 날조하지만,
# DSL 경로는 그 결손/비물리 상태를 UNKNOWN으로 정직 표면화한다. 이 발산은 의도된 개선이지
# 무음 회귀가 아니다 — 각 경계에서 두 경로를 나란히 대조해 명시한다.

def test_bl001_bcr_zero_land_area_diverges_from_baseline_by_design() -> None:
    """대지면적 0(비물리) — baseline은 0나눔을 피하려 ``max(land_area,1)=1``로 클램프해
    비물리적 수치라도 산출한다(발산=정직성 개선, 무음 아님). DSL은 0분모를 무날조 원칙으로
    UNKNOWN 거부한다."""
    design = {"building_area_sqm": 100.0}
    site = {"land_area_sqm": 0.0, "max_bcr": 60.0}

    baseline = _ENGINE._check_bcr(design, site)  # noqa: SLF001 — 정답 기준선(클램프 동작 재확인)
    assert baseline.actual_value == "10000.0%"  # 100/max(0,1)*100 — 클램프로 인한 비물리 수치(날조)

    result = evaluate_bl001_bcr(design, site)
    assert result.status == FactStatus.UNKNOWN  # DSL은 0분모를 UNKNOWN으로 정직 거부
    assert result.value is None


def test_bl001_bcr_negative_land_area_diverges_from_baseline_by_design() -> None:
    """대지면적 음수(비물리) — baseline은 여전히 ``max(neg,1)=1``로 클램프해 수치를 낸다
    (발산=정직성 개선, 무음 아님). DSL은 음수 분모를 UNKNOWN으로 거부한다(면적 도메인에서
    음수 분모=비물리, LOW-1 개선)."""
    design = {"building_area_sqm": 50.0}
    site = {"land_area_sqm": -20.0, "max_bcr": 60.0}

    baseline = _ENGINE._check_bcr(design, site)  # noqa: SLF001
    assert baseline.actual_value == "5000.0%"  # 50/max(-20,1)=1*100 — 클램프가 부호까지 왜곡

    result = evaluate_bl001_bcr(design, site)
    assert result.status == FactStatus.UNKNOWN
    assert result.value is None


def test_bl001_bcr_missing_max_bcr_diverges_from_baseline_by_design() -> None:
    """max_bcr 키 자체 부재 — baseline은 ``.get("max_bcr", 60)`` 기본값 60%로 조용히
    대체한다(법정 한도를 임의 가정 — 날조, 발산=정직성 개선). DSL은 한도 결손을 UNKNOWN으로
    거부한다."""
    design = {"building_area_sqm": 100.0}
    site = {"land_area_sqm": 200.0}  # max_bcr 키 자체 부재

    baseline = _ENGINE._check_bcr(design, site)  # noqa: SLF001
    assert baseline.required_value == "60% 이하"  # 기본값 60%로 조용히 대체(날조)

    result = evaluate_bl001_bcr(design, site)
    assert result.status == FactStatus.UNKNOWN  # DSL은 max_bcr_pct 결손을 UNKNOWN으로 거부
    assert result.value is None


def test_bl002_far_zero_land_area_diverges_from_baseline_by_design() -> None:
    """BL-002(용적률)도 동일 발산 패턴(대지면적 0). 발산=정직성 개선, 무음 아님."""
    design = {"total_gfa_sqm": 400.0}
    site = {"land_area_sqm": 0.0, "max_far": 200.0}

    baseline = _ENGINE._check_far(design, site)  # noqa: SLF001
    assert baseline.actual_value == "40000.0%"  # 400/max(0,1)*100 — 클램프로 인한 비물리 수치

    result = evaluate_bl002_far(design, site)
    assert result.status == FactStatus.UNKNOWN
    assert result.value is None


def test_bl002_far_negative_land_area_diverges_from_baseline_by_design() -> None:
    """BL-002(용적률) 대지면적 음수. 발산=정직성 개선, 무음 아님."""
    design = {"total_gfa_sqm": 150.0}
    site = {"land_area_sqm": -30.0, "max_far": 200.0}

    baseline = _ENGINE._check_far(design, site)  # noqa: SLF001
    assert baseline.actual_value == "15000.0%"  # 150/max(-30,1)=1*100

    result = evaluate_bl002_far(design, site)
    assert result.status == FactStatus.UNKNOWN
    assert result.value is None


def test_bl002_far_missing_max_far_diverges_from_baseline_by_design() -> None:
    """BL-002(용적률) max_far 키 자체 부재. 발산=정직성 개선, 무음 아님."""
    design = {"total_gfa_sqm": 300.0}
    site = {"land_area_sqm": 200.0}  # max_far 키 자체 부재

    baseline = _ENGINE._check_far(design, site)  # noqa: SLF001
    assert baseline.required_value == "200% 이하"  # 기본값 200%로 조용히 대체(날조)

    result = evaluate_bl002_far(design, site)
    assert result.status == FactStatus.UNKNOWN
    assert result.value is None
