"""소규모 단일 필지 개발방식 게이트 — 사용자 지적("50~100평인데 지구단위/도시개발/역세권
등 부적합 대규모사업 제시")의 근본 차단 검증.

원칙: 단일 소규모 필지(약 300평 미만)는 가로구역/블록/구역을 단독으로 구성할 수 없어
통합·정비·지구단위·역세권형 사업의 단독 검토대상이 될 수 없다 → 단순건축만 가능.
"""
from app.services.development.scenario_simulator import DevelopmentScenarioSimulator


def _ctx(area_sqm, multi=False, zone="제2종일반주거지역", station=True):
    return {
        "total_area_sqm": area_sqm,
        "primary_zone": zone,
        "far_effective_blended": 200,
        "far_legal_blended": 250,
        "multi": multi,
        "near_station": {"name": "테스트역", "distance_m": 200} if station else None,
        "near_station_m": 200 if station else None,
        "region": "서울특별시",
        "integration_feasible": True,
        "adjacency": {},
        "buildings": {},
        "block_aging": {},
    }


def _by_scheme(scenarios):
    return {s["scheme"]: s["applicable"] for s in scenarios}


def test_small_single_parcel_only_simple_build():
    """100평(330㎡) 단일필지(서울 역세권 주거) — 단순건축 외 전부 '불가'."""
    sim = DevelopmentScenarioSimulator()
    scenarios = sim._scenarios(_ctx(330))
    m = _by_scheme(scenarios)
    assert m["단순 건축"] == "가능", "단순건축은 항상 가능"
    # 대표 통합·정비·지구단위·역세권형 사업은 단일 소규모라 전부 불가여야 함
    for scheme in ["지구단위계획 연계", "도시개발사업(도시개발법)", "역세권 활성화사업",
                   "가로주택정비사업", "역세권 장기전세주택(시프트)", "소규모재개발사업",
                   "주거환경개선사업"]:
        assert m.get(scheme) == "불가", f"{scheme}은 단일 소규모(330㎡)라 불가여야 함 (현재 {m.get(scheme)})"


def test_small_single_50pyeong():
    """50평(165㎡) 단일필지 — 단순건축만 가능."""
    sim = DevelopmentScenarioSimulator()
    m = _by_scheme(sim._scenarios(_ctx(165)))
    applicable = [k for k, v in m.items() if v in ("가능", "조건부")]
    assert applicable == ["단순 건축"], f"50평 단일은 단순건축만 추진 가능해야 함 — 현재: {applicable}"


def test_small_single_parcel_has_honest_note():
    """불가 강등 시 인접 통합/구역 편입 안내(정직 사유)가 담겨야 함."""
    sim = DevelopmentScenarioSimulator()
    scenarios = sim._scenarios(_ctx(330))
    jigudanwi = next(s for s in scenarios if s["scheme"] == "지구단위계획 연계")
    assert jigudanwi["applicable"] == "불가"
    assert "인접" in (jigudanwi["notes"] or ""), "인접 통합/편입 안내가 있어야 함"
    assert "평" in (jigudanwi["notes"] or ""), "평수 표기가 있어야 함"


def test_large_single_parcel_not_gated():
    """대형 단일필지(2만㎡)는 소규모 게이트 미적용 — 도시개발 등 정상 검토(무회귀)."""
    sim = DevelopmentScenarioSimulator()
    m = _by_scheme(sim._scenarios(_ctx(20000)))
    assert m["도시개발사업(도시개발법)"] == "가능", "2만㎡ 단일은 도시개발 가능(1만㎡ 이상)"
    assert m["지구단위계획 연계"] == "가능", "5천㎡ 이상이라 지구단위 가능"


def test_multi_parcel_not_gated_by_small_single():
    """다필지(통합)면 소규모 단일 게이트 미적용 — 통합개발 정책 검토 유지."""
    sim = DevelopmentScenarioSimulator()
    # 통합 합산 800㎡지만 multi=True → 단일 소규모 게이트는 적용 안 됨(다필지 통합 경로).
    m = _by_scheme(sim._scenarios(_ctx(800, multi=True)))
    assert m["지구단위계획 연계"] != "불가" or True  # 다필지는 지구단위 '가능'(area>=5000 or multi)
    assert m["지구단위계획 연계"] == "가능", "다필지 통합은 지구단위 가능"
