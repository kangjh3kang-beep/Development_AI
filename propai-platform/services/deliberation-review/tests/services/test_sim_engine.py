"""AT-1..7 — 공학 시뮬: trace 동반, 파라미터화, trace 없으면 거부, 결손 UNAVAILABLE,
불확실 confidence 하향, 재현성, 주차 회전반경 위반."""
import pathlib

import pytest

from app.contracts.sim_metric import MetricStatus, SimMetric, emit
from app.core.errors import MethodTraceMissing
from app.services.sim.sim_engine import SimEngine
from tools.static_scan import scan_for_numeric_legal_constants

_SIM_DIR = pathlib.Path(__file__).resolve().parents[2] / "apps" / "api" / "app" / "services" / "sim"

SITE_WITH_ADJACENT = {
    "latitude": 37.5, "building_height": 30.0, "adjacent_distance": 12.0, "geom_confidence": 0.95,
}
SITE_LOW_CONF_GEOM = {**SITE_WITH_ADJACENT, "geom_confidence": 0.4}
PLAN_WITH_STAIR = {"travel_distance": 25.0, "elements": ["CORE_STAIR"], "geom_confidence": 0.9}
PLAN_WITHOUT_STAIR = {"travel_distance": 25.0, "elements": ["EXT_WALL"], "geom_confidence": 0.9}
PARKING_TIGHT_TURN = {"turn_radius": 5.0, "geom_confidence": 0.9}


def test_sunlight_metric_with_trace():
    m = SimEngine().run_sunlight(SITE_WITH_ADJACENT)
    assert m.value is not None
    assert m.method_trace.model == "solar_orbit_approx"


def test_sim_constants_parameterized():
    r1 = SimEngine(params={"egress_walk_speed_mps": 1.2}).run_egress(PLAN_WITH_STAIR)
    r2 = SimEngine(params={"egress_walk_speed_mps": 0.8}).run_egress(PLAN_WITH_STAIR)
    assert r1.value != r2.value
    offenders = {}
    # 측정치/지역변수(법정상수 아님) — static_scan이 법정명+benign값까지 잡으므로 명시 제외.
    allow = ("sunny_hours", "shaded_ratio", "area", "depth")
    for py in _SIM_DIR.rglob("*.py"):
        hits = scan_for_numeric_legal_constants(py.read_text(encoding="utf-8"), allowlist=allow)
        if hits:
            offenders[py.name] = hits
    assert offenders == {}


def test_no_metric_without_trace():
    with pytest.raises(MethodTraceMissing):
        emit(SimMetric(metric_id="x", value=1.0, method_trace=None))


def test_missing_input_unavailable():
    m = SimEngine().run_egress(PLAN_WITHOUT_STAIR)
    assert m.status == MetricStatus.UNAVAILABLE


def test_uncertain_input_lowers_confidence():
    m = SimEngine().run_sunlight(SITE_LOW_CONF_GEOM)
    assert m.confidence < 1.0


def test_sim_reproducible():
    assert SimEngine().run_sunlight(SITE_WITH_ADJACENT) == SimEngine().run_sunlight(SITE_WITH_ADJACENT)


def test_parking_turn_radius_flag():
    m = SimEngine().run_parking(PARKING_TIGHT_TURN)
    assert m.flags
    assert m.value < m.required


def test_egress_missing_distance_unavailable():
    # 보행거리 결손 → 크래시 없이 UNAVAILABLE(INV-21).
    plan = {"elements": ["CORE_STAIR"], "geom_confidence": 0.9}
    m = SimEngine().run_egress(plan)
    assert m.status == MetricStatus.UNAVAILABLE
    assert "missing_travel_distance" in m.flags


def test_egress_nonpositive_speed_unavailable():
    # 보행속도 0/음수 주입 → 0division(500)/음수시간 무음 오판 없이 UNAVAILABLE(INV-21 견고성).
    m0 = SimEngine(params={"egress_walk_speed_mps": 0}).run_egress(PLAN_WITH_STAIR)
    assert m0.status == MetricStatus.UNAVAILABLE
    assert "invalid_egress_params" in m0.flags
    assert m0.value is None
    mneg = SimEngine(params={"egress_flow_coefficient": -1.0}).run_egress(PLAN_WITH_STAIR)
    assert mneg.status == MetricStatus.UNAVAILABLE  # 음수 flow → 음수시간 차단


def test_sunlight_trace_surfaces_model_limitation():
    # 모델 한계(정오 단일 그림자 근사)가 method_trace로 표면화(감사 D절/INV-19).
    m = SimEngine().run_sunlight(SITE_WITH_ADJACENT)
    assert any("근사" in a for a in m.method_trace.assumptions)
