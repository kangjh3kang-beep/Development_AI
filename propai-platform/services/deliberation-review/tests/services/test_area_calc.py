"""AT-1/AT-2/AT-3 — 면적 산정: 필로티 제외+trace, 용적률연면적 지하/주차 제외, 임계 파라미터화."""
import pathlib

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


def test_far_floor_area_excludes_basement_parking():
    q = CalcEngine().compute(
        target=CalcTarget.FAR_FLOOR_AREA,
        payload={"gross_floor_area": 1000.0},
        elements=[
            CalcElement(semantic_type=SemanticType.BASEMENT, area=200.0, confidence=0.9),
            CalcElement(semantic_type=SemanticType.PARKING, area=150.0, confidence=0.9),
        ],
    )
    assert q.value == 1000.0 - 200.0 - 150.0


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
