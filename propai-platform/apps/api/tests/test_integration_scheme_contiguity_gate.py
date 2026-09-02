"""인접성 게이트의 축 · 면적가중 우세 용도지역 · 제1종 아파트 불허 — 락.

★이 영역은 종전에 **완전 무잠금**이었다(볼트 실측 2026-08-28: `INTEGRATION_SCHEMES`
참조 테스트 0건 · `integration_feasible=False` 를 만드는 테스트 0건 → **분기를 지워도 초록**).
기존 `test_scenario_small_parcel_gate.py` 의 `_ctx` 도 `integration_feasible: True` 라
이 게이트를 한 번도 태우지 않는다.

사용자 신고(라이브 재현 2026-09-02): 제1종+제2종 다필지 부지에서
**지구단위계획이 「불가」** 로 떴다 — `notes: "⚠ 2개 그룹으로 분리 — 비인접 필지는
통합개발(합필/일단지) 불가"`.

법적 근거(법제처 DRF 원문 직독):
· 국토계획법 009294 §51·§52①3호 — 지구단위계획구역 지정에 **인접·연접 요건 없음**
· 도시개발법 002024 §3의2 — *"서로 떨어진 둘 이상의 지역을 결합"* 명문 허용
· 건축법 001823 §77의15① — *"대지간의 최단거리가 100미터 이내"* (제77조의4 는 **건축협정**)
· 국토계획법 시행령 009419 §71①3호 → **[별표 4]** 1호 나목
  *"공동주택(**아파트를 제외한다**)"* / §71①4호 → **[별표 5]** *"공동주택"*(제외 없음)
"""
import ast
import inspect
import pathlib

import pytest

from app.services.development import scenario_simulator as SS
from app.services.development.scenario_simulator import (
    ZONE_BASIS_AREA_WEIGHTED,
    ZONE_BASIS_NO_AREA,
    ZONE_BASIS_SINGLE,
    DevelopmentScenarioSimulator,
    dominant_zone_by_area,
)

_SRC = pathlib.Path(inspect.getsourcefile(SS)).read_text(encoding="utf-8")


def _ctx(*, integration_ok, area_sqm=5000.0, zone="제2종일반주거지역",
         multi=True, station=True, region="서울특별시"):
    """★기존 픽스처와 달리 `integration_feasible` 를 **실제로 False 로 만든다.**"""
    return {
        "total_area_sqm": area_sqm,
        "primary_zone": zone,
        "far_effective_blended": 200,
        "far_legal_blended": 250,
        "multi": multi,
        "near_station": {"name": "테스트역", "distance_m": 200} if station else None,
        "near_station_m": 200 if station else None,
        "region": region,
        "integration_feasible": integration_ok,
        "adjacency": {"contiguous": integration_ok, "components": 1 if integration_ok else 2,
                      "note": "단일 필지" if integration_ok else "2개 그룹으로 분리"},
        "buildings": {}, "block_aging": {},
    }


def _map(scenarios):
    return {s["scheme"]: s for s in scenarios}


# ─────────────────────────────────────────────────────────────────────────────
# 1) 게이트의 축 — 「불가」가 아니라 「조건부」. ★두 모집단을 가른다.
# ─────────────────────────────────────────────────────────────────────────────

def _adjacency_pair(**kw):
    """인접/비인접 두 실행을 같은 파라미터로 만든다 — 변수는 `integration_feasible` **하나뿐**."""
    sim = DevelopmentScenarioSimulator()
    return (_map(sim._scenarios(_ctx(integration_ok=True, **kw))),
            _map(sim._scenarios(_ctx(integration_ok=False, **kw))))


def _gated_and_eligible(ok, bad):
    """★모집단을 **파생**한다 — 손으로 나열하지 않는다.

    「인접이면 불가가 아닌」 게이트 대상 방식만 고른다. 나머지는 자기 사유(면적·노후도 등)로
    이미 불가라 이 게이트를 타지 않으므로 단언 대상이 아니다(그것까지 풀면 회귀).
    """
    gate = set().union(*_gate_set_literals().values())
    return sorted(k for k in gate if k in ok and ok[k]["applicable"] != "불가")


def test_gate_population_is_not_empty():
    """★공허 진리 가드 — 단언 대상이 실제로 존재하는지 **먼저** 확인한다.

    대상이 0개면 아래 단언들이 전부 공허하게 참이 된다.
    """
    ok, bad = _adjacency_pair()
    pop = _gated_and_eligible(ok, bad)
    assert len(pop) >= 3, f"게이트 대상이면서 인접 시 추진 가능한 방식이 너무 적다 — {pop}"


def test_no_gated_scheme_becomes_impossible_from_non_adjacency():
    """★핵심 계약(파생형) — **인접이면 가능한 것은 비인접이라고 불가가 되지 않는다.**

    사용자 신고의 정확한 형태다: 지구단위계획이 인접 시 「가능」이었는데 비인접이라고
    「불가」가 됐다. 법정 근거가 없다(국토계획법 §51·§52).
    """
    ok, bad = _adjacency_pair()
    pop = _gated_and_eligible(ok, bad)
    broken = [k for k in pop if bad[k]["applicable"] == "불가"]
    assert not broken, f"비인접만으로 「불가」가 된 방식: {broken}"


def test_non_adjacency_actually_changes_something():
    """★반대편 가드 — 게이트가 **아무 일도 안 하면** 위 단언은 「분기 삭제」도 통과시킨다.

    판정어가 그대로여도(이미 조건부였던 방식) **사유(notes)** 는 달라져야 한다.
    """
    ok, bad = _adjacency_pair()
    pop = _gated_and_eligible(ok, bad)
    touched = [k for k in pop if (ok[k]["notes"] or "") != (bad[k]["notes"] or "")]
    assert len(touched) >= 3, f"비인접이 사유를 바꾸지 않는다 — 게이트가 죽었다: {touched}"


@pytest.mark.parametrize("area_sqm", [1710.0, 5000.0, 12000.0])
def test_contract_holds_across_area_tiers(area_sqm):
    """면적대가 달라져도 같은 계약 — 티어마다 모집단이 달라지므로 함께 태운다."""
    ok, bad = _adjacency_pair(area_sqm=area_sqm)
    pop = _gated_and_eligible(ok, bad)
    assert pop, f"{area_sqm}㎡ 에서 대상이 0개 — 픽스처가 모집단을 못 만든다"
    assert not [k for k in pop if bad[k]["applicable"] == "불가"], (
        f"{area_sqm}㎡: 비인접만으로 불가가 된 것 {[k for k in pop if bad[k]['applicable']=='불가']}"
    )


def test_area_designation_states_the_real_axis():
    """강등 사유가 **법적 근거와 함께** 표면에 실려야 한다(침묵 강등 금지)."""
    sim = DevelopmentScenarioSimulator()
    s = _map(sim._scenarios(_ctx(integration_ok=False)))["지구단위계획 연계"]
    notes = s["notes"] or ""
    assert "§51" in notes or "§52" in notes, f"근거 조문이 사유에 없다: {notes!r}"
    assert "관할 확인" in notes, f"저장소 기준선 문구(관할 확인)가 없다: {notes!r}"
    # ★종전 문구가 남아 있으면 회귀
    assert "통합개발 불가" not in notes, f"종전 판정 문구가 남았다: {notes!r}"


def test_garo_guyeok_axis_is_road_not_distance():
    """가로구역형 — 축이 **도로 폭(4m/6m 관통)** 임을 사유가 말해야 한다."""
    sim = DevelopmentScenarioSimulator()
    s = _map(sim._scenarios(_ctx(integration_ok=False)))["가로주택정비사업"]
    assert s["applicable"] != "불가"
    assert "4m" in (s["notes"] or ""), f"가로구역 임계(4m)가 사유에 없다: {s['notes']!r}"


def test_legitimate_impossible_is_preserved():
    """★대조 모집단 — **정당한 「불가」는 그대로여야 한다**(처방이 그것까지 풀면 회귀).

    도시개발사업은 1만㎡ 미만이면 면적 미달로 불가다(라이브 실측: 1,710㎡ → 불가).
    이 단언이 없으면 "전부 조건부로 바꾸기"라는 틀린 구현도 통과한다.
    """
    sim = DevelopmentScenarioSimulator()
    m = _map(sim._scenarios(_ctx(integration_ok=False, area_sqm=1710.0)))
    assert m["도시개발사업(도시개발법)"]["applicable"] == "불가", "면적 미달은 여전히 불가여야 한다"
    assert "면적" in " ".join(m["도시개발사업(도시개발법)"]["cons"] or [])
    # 같은 실행에서 인접성 강등 대상은 조건부여야 한다(두 모집단이 갈린다)
    assert m["지구단위계획 연계"]["applicable"] != "불가"


# ─────────────────────────────────────────────────────────────────────────────
# 2) 집합 — ★죽은 원소 0(파생형: AST 로 실제 add() 이름을 뽑아 대조)
# ─────────────────────────────────────────────────────────────────────────────

def _add_scheme_names() -> set[str]:
    names = set()
    for n in ast.walk(ast.parse(_SRC)):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "add"
                and n.args and isinstance(n.args[0], ast.Constant)
                and isinstance(n.args[0].value, str)):
            names.add(n.args[0].value)
    return names


def _gate_set_literals() -> dict[str, set[str]]:
    """세 집합의 원소를 **AST 로** 뽑는다(정규식이 주석·문자열에 뚫리지 않도록)."""
    out: dict[str, set[str]] = {}
    for n in ast.walk(ast.parse(_SRC)):
        tgt = None
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            tgt = n.targets[0].id
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
            tgt = n.target.id
        if tgt and tgt.endswith("_SCHEMES") and isinstance(getattr(n, "value", None), ast.Set):
            out[tgt] = {e.value for e in n.value.elts
                        if isinstance(e, ast.Constant) and isinstance(e.value, str)}
    return out


def test_gate_sets_have_no_dead_members():
    """★집합의 이름이 실제 `add()` 이름과 어긋나면 **게이트가 조용히 발화를 멈춘다.**

    실제로 이 PR 작업 중 5종이 죽은 원소로 들어갔다가 이 대조로 적발됐다
    (집합만 고치고 `add()` 를 안 나눴다 = 「선언 ≠ 발화」).
    """
    sets = _gate_set_literals()
    assert sets, "집합을 하나도 못 찾았다 — 검사기가 죽었다(대상 오류)"
    real = _add_scheme_names()
    assert len(real) >= 15, f"add() 이름 수집이 비정상 — {len(real)}종"
    for name, members in sets.items():
        dead = sorted(members - real)
        assert not dead, f"{name} 의 죽은 원소: {dead}"


def test_combined_building_is_not_in_the_contiguity_gate():
    """결합건축은 **인접성 게이트에 없어야** 한다 — 제도의 전제가 「100m 이내 이격」이므로."""
    for name, members in _gate_set_literals().items():
        assert "결합건축" not in members, f"{name} 에 결합건축이 들어 있다(제도와 정면 모순)"


# ─────────────────────────────────────────────────────────────────────────────
# 3) 결합건축 — 축이 **인접성이 아니라 대상지역**
# ─────────────────────────────────────────────────────────────────────────────

def test_combined_building_ignores_adjacency():
    """인접/비인접에서 **같은 판정**이 나와야 한다(축이 인접성이 아니므로)."""
    sim = DevelopmentScenarioSimulator()
    ok = _map(sim._scenarios(_ctx(integration_ok=True)))["결합건축"]
    bad = _map(sim._scenarios(_ctx(integration_ok=False)))["결합건축"]
    assert ok["applicable"] == bad["applicable"], (
        f"인접 여부로 결합건축이 갈린다({ok['applicable']} vs {bad['applicable']}) — §77의15 는 이격이 전제"
    )


def test_combined_building_axis_is_eligible_zone():
    """★대상지역 축이 실제로 판정을 가르는가 — 두 모집단.

    §77의15① 각 호: 상업지역·역세권개발구역·주거환경개선 정비구역 등으로 **한정**된다.
    종전은 `if multi:` 만으로 「가능」을 줬다(대상지역 무관 = 과대허용).
    """
    sim = DevelopmentScenarioSimulator()
    eligible = _map(sim._scenarios(_ctx(integration_ok=False, station=True)))["결합건축"]
    not_eligible = _map(sim._scenarios(
        _ctx(integration_ok=False, station=False, zone="제2종일반주거지역")))["결합건축"]
    assert eligible["est_far"] is not None, "대상지역이면 용적 추정이 나와야 한다"
    assert not_eligible["est_far"] is None, (
        "상업·역세권이 아닌데 용적 추정이 나오면 대상지역 축이 안 걸린 것"
    )
    assert "관할 확인" in (not_eligible["notes"] or "")


def test_combined_building_cites_77_15_not_77_4():
    """조문 — §77의15(결합건축 대상지). §77의4 는 **건축협정의 체결**이다(원문 확인)."""
    s = _map(DevelopmentScenarioSimulator()._scenarios(_ctx(integration_ok=False)))["결합건축"]
    blob = " ".join(s["requirements"] or []) + " " + (s["notes"] or "")
    assert "77의15" in blob or "77조의15" in blob, f"정답 조문이 표면에 없다: {blob!r}"
    assert "77의4" not in blob and "77조의4" not in blob, f"오기 조문이 표면에 남았다: {blob!r}"


# ─────────────────────────────────────────────────────────────────────────────
# 4) 면적가중 우세 용도지역 — 순수함수(판단을 꺼내 따로 잠근다)
# ─────────────────────────────────────────────────────────────────────────────

def test_dominant_zone_is_area_weighted_not_first_parcel():
    """★작은 제1종이 **선두**여도 큰 제2종이 이겨야 한다.

    라이브 실측(2026-09-02): `zones=[제1종, 제2종]` 부지에서 `primary_zone=제1종` 이 나왔다.
    """
    rows = [{"zone": "제1종일반주거지역", "area": 100.0},
            {"zone": "제2종일반주거지역", "area": 900.0}]
    zone, basis = dominant_zone_by_area(rows)
    assert zone == "제2종일반주거지역", f"면적가중이면 제2종 — 실제 {zone}"
    assert basis == ZONE_BASIS_AREA_WEIGHTED


def test_dominant_zone_is_order_independent():
    """★순서를 뒤집어도 같은 답 — 「첫 필지 의존」이 남으면 여기서 갈린다."""
    a = [{"zone": "제1종일반주거지역", "area": 100.0}, {"zone": "제2종일반주거지역", "area": 900.0}]
    assert dominant_zone_by_area(a)[0] == dominant_zone_by_area(list(reversed(a)))[0]


def test_dominant_zone_reports_when_it_could_not_weight():
    """면적 미확보를 **조용히 첫 필지로** 떨어뜨리지 않고 말한다(모름은 유효값을 입지 않는다)."""
    rows = [{"zone": "제1종일반주거지역", "area": None}, {"zone": "제2종일반주거지역", "area": 900.0}]
    zone, basis = dominant_zone_by_area(rows)
    assert basis == ZONE_BASIS_NO_AREA, "면적 미확보인데 면적가중이라고 말하면 거짓이다"
    assert zone == "제1종일반주거지역"


def test_dominant_zone_single_and_empty():
    assert dominant_zone_by_area([{"zone": "제2종일반주거지역", "area": 5.0}]) == (
        "제2종일반주거지역", ZONE_BASIS_SINGLE)
    assert dominant_zone_by_area([])[0] == ""


def test_simulate_exposes_the_basis():
    """호출부가 근거를 구별할 수 있게 `primary_zone_basis` 가 응답에 실려야 한다."""
    assert '"primary_zone_basis": primary_zone_basis' in _SRC


# ─────────────────────────────────────────────────────────────────────────────
# 5) 제1종 아파트 불허 — ★파티션형(제2종에는 있어야 한다)
# ─────────────────────────────────────────────────────────────────────────────

def test_type1_residential_excludes_apartment():
    """[별표 4] 1호 나목 — 공동주택(**아파트를 제외한다**)."""
    types = DevelopmentScenarioSimulator._buildable_types("제1종일반주거지역", "단순 건축")
    assert "아파트" not in types, f"제1종에 아파트가 있으면 법정 불허를 허용하는 것 — {types}"
    assert any("연립" in t or "다세대" in t for t in types), f"공동주택(아파트 제외)은 가능 — {types}"
    assert any("4층" in t for t in types), f"4층 이하 제한이 표면에 없다 — {types}"


def test_type2_residential_includes_apartment():
    """★음성 대조군 — [별표 5] 1호 나목은 제외 문구가 **없다**.

    이 단언이 없으면 "주거는 전부 아파트 제거"라는 과잉 억제 구현도 통과한다.
    """
    types = DevelopmentScenarioSimulator._buildable_types("제2종일반주거지역", "단순 건축")
    assert "아파트" in types, f"제2종은 아파트 허용이어야 한다 — {types}"


def test_type3_residential_includes_apartment():
    types = DevelopmentScenarioSimulator._buildable_types("제3종일반주거지역", "단순 건축")
    assert "아파트" in types, f"제3종은 아파트 허용이어야 한다 — {types}"


def test_buildable_types_partition_is_actually_split():
    """★두 모집단이 **다른 값**을 내야 한다 — 같으면 분기를 지워도 초록이다."""
    t1 = DevelopmentScenarioSimulator._buildable_types("제1종일반주거지역", "단순 건축")
    t2 = DevelopmentScenarioSimulator._buildable_types("제2종일반주거지역", "단순 건축")
    assert t1 != t2, "제1종과 제2종이 같은 목록이면 1·2·3종이 여전히 뭉개진 것"
