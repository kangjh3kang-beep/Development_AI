"""AT-1/AT-2/AT-3 — 면적 산정: 필로티 제외+trace, 용적률연면적 지하/주차 제외, 임계 파라미터화."""
import pathlib

from app.contracts.enums import RecordStatus
from app.contracts.legal_quantity import CalcElement, CalcTarget
from app.contracts.semantic_element import SemanticType
from app.services.legal_calc.calc_engine import CalcEngine
from tools.static_scan import scan_for_numeric_legal_constants

_LEGAL_CALC_DIR = (
    pathlib.Path(__file__).resolve().parents[2]
    / "apps" / "api" / "app" / "services" / "legal_calc"
)


def test_pilotis_excluded_from_building_area():
    q = CalcEngine().compute(
        target=CalcTarget.BUILDING_AREA,
        payload={"outer_area": 600.0},
        elements=[CalcElement(semantic_type=SemanticType.PILOTIS, area=100.0, confidence=0.95)],
    )
    assert q.value == 500.0  # 600 - 100(필로티)
    assert q.calc_trace.has(SemanticType.PILOTIS, art="119")


def test_far_floor_area_excludes_basement_and_underground_accessory_parking():
    # 지하층 + 지하·부속 주차(§119①4 제외 적격) → 둘 다 제외, 적격 확정이므로 AGREED.
    q = CalcEngine().compute(
        target=CalcTarget.FAR_FLOOR_AREA,
        payload={"gross_floor_area": 1000.0},
        elements=[
            CalcElement(semantic_type=SemanticType.BASEMENT, area=200.0, confidence=0.9),
            CalcElement(semantic_type=SemanticType.PARKING, area=150.0, confidence=0.9,
                        underground=True, accessory=True),
        ],
    )
    assert q.value == 1000.0 - 200.0 - 150.0
    assert q.status == RecordStatus.AGREED


def test_far_aboveground_parking_included_not_deducted():
    # 지상 주차는 §119①4 제외 대상 아님 → 산입(전량제외 거짓적합 방지).
    q = CalcEngine().compute(
        target=CalcTarget.FAR_FLOOR_AREA,
        payload={"gross_floor_area": 1000.0},
        elements=[CalcElement(semantic_type=SemanticType.PARKING, area=150.0, confidence=0.9,
                              underground=False, accessory=True)],
    )
    assert q.value == 1000.0  # 제외 안함
    assert q.status == RecordStatus.AGREED


def test_held_reason_recorded_in_trace():
    # UNKNOWN 요소 → HELD + 강등 사유가 calc_trace에 명시(무라벨 HELD 제거).
    q = CalcEngine().compute(
        target=CalcTarget.BUILDING_AREA, payload={"outer_area": 600.0},
        elements=[CalcElement(semantic_type=SemanticType.UNKNOWN, area=10.0, confidence=0.9)])
    assert q.status == RecordStatus.HELD
    held = next(e for e in q.calc_trace.entries if e.rule_id == "held_reason")
    assert "UNKNOWN" in (held.note or "")
    # 슬롯 혼선 제거: 비법령 내부근거(INV-12)는 법령 슬롯(basis_article) 아닌 note에(법령 해소 '미해소' 혼선 방지).
    assert held.basis_article == ""
    assert "INV-12" in (held.note or "")


def test_far_unknown_parking_held_and_not_excluded():
    # 주차 지하/부속 미상 → 무음 전량제외 금지(보수적 산입) + HELD(확인 필요).
    q = CalcEngine().compute(
        target=CalcTarget.FAR_FLOOR_AREA,
        payload={"gross_floor_area": 1000.0},
        elements=[CalcElement(semantic_type=SemanticType.PARKING, area=150.0, confidence=0.9)],
    )
    assert q.value == 1000.0  # 미상 → 제외 안함(거짓적합 방지)
    assert q.status == RecordStatus.HELD
    assert any(e.rule_id == "far_parking_held" for e in q.calc_trace.entries)


def test_exclusion_threshold_is_parameterized():
    balcony = [CalcElement(semantic_type=SemanticType.BALCONY, area=8.0, depth=1.4, confidence=0.9)]
    payload = {"outer_area": 600.0}
    # 발코니 제외 깊이 1.5 → depth 1.4 제외(value=592) vs 1.0 → 미제외(value=600).
    r1 = CalcEngine(params={"balcony_exclusion_depth": 1.5}).compute(
        target=CalcTarget.BUILDING_AREA, payload=payload, elements=balcony)
    r2 = CalcEngine(params={"balcony_exclusion_depth": 1.0}).compute(
        target=CalcTarget.BUILDING_AREA, payload=payload, elements=balcony)
    assert r1.value != r2.value
    # 법정 임계 하드코딩 부재(legal_calc 소스). rooftop_area는 면적 측정 입력(기본 0.0=부재) — 법정상수 아님.
    offenders = {}
    for py in _LEGAL_CALC_DIR.rglob("*.py"):
        hits = scan_for_numeric_legal_constants(py.read_text(encoding="utf-8"), allowlist=("rooftop_area",))
        if hits:
            offenders[py.name] = hits
    assert offenders == {}
