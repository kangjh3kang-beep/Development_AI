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
         multi=True, station=True, region="서울특별시", max_pair_m=30.0, zones=None):
    """★기존 픽스처와 달리 `integration_feasible` 를 **실제로 False 로 만든다.**"""
    return {
        "total_area_sqm": area_sqm,
        "primary_zone": zone,
        # ★부지에 실재하는 용도지역 전부 — 우세만 보면 혼재 부지에서 제약이 꺼진다(M-5).
        "zones": list(zones) if zones is not None else [zone],
        # ★§84① 흡수를 반영한 불허 목록은 `simulate()` 가 **면적을 보고** 판정해 넘긴다.
        #   픽스처는 그 결과를 흉내 낸다 — 판정 자체는 `apartment_restricted_zones()` 락이 태운다.
        "apartment_restricted_zones": [z for z in (list(zones) if zones is not None else [zone])
                                       if SS.zone_prohibits_apartment(z)],
        "far_effective_blended": 200,
        "far_legal_blended": 250,
        "multi": multi,
        "near_station": {"name": "테스트역", "distance_m": 200} if station else None,
        "near_station_m": 200 if station else None,
        "region": region,
        "integration_feasible": integration_ok,
        "adjacency": {"contiguous": integration_ok, "components": 1 if integration_ok else 2,
                      "note": "단일 필지" if integration_ok else "2개 그룹으로 분리",
                      "max_pair_distance_m_min": max_pair_m},
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
    assert "§51" in notes, f"근거 조문이 사유에 없다: {notes!r}"
    # ★MINOR 3 — §52 를 근거로 끌어오면 안 된다. §52①3호는 오히려 *"일단의 지역"* 이라
    #   이 논지(인접 요건 없음)와 **반대로** 읽힐 수 있다. 근거는 §51(부재)과 §3의2(명문)뿐.
    assert "§52" not in notes, f"§52 는 이 논지의 근거가 아니다: {notes!r}"
    assert "§3의2" in notes, f"명문 허용 근거(도시개발법 §3의2)가 없다: {notes!r}"
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
    """게이트를 구성하는 집합만 **AST 로** 뽑는다.

    ★축을 «이름이 `_SCHEMES` 로 끝나는 것» 으로 잡았다가 `SELF_STANDING_SCHEMES`(= 단순 건축)
      까지 빨아들여 **틀린 모집단**을 만들었다. 게이트의 정의는 이름이 아니라
      `INTEGRATION_SCHEMES = A | B | C` **그 식**이므로, 거기서 피연산자 이름을 파생한다.
      (새 축을 추가해도 그 식에 넣기만 하면 이 수집기가 자동으로 따라온다.)
    """
    tree = ast.parse(_SRC)
    assigns: dict[str, ast.AST] = {}
    for n in ast.walk(tree):
        tgt = None
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            tgt = n.targets[0].id
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
            tgt = n.target.id
        if tgt and getattr(n, "value", None) is not None:
            assigns[tgt] = n.value

    union = assigns.get("INTEGRATION_SCHEMES")
    assert union is not None, "INTEGRATION_SCHEMES 대입을 못 찾았다 — 수집기가 죽었다"
    members: list[str] = []

    def _walk(node):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            _walk(node.left); _walk(node.right)
        elif isinstance(node, ast.Name):
            members.append(node.id)

    _walk(union)
    assert len(members) >= 2, f"게이트가 합집합으로 구성돼 있지 않다 — {members}"

    out: dict[str, set[str]] = {}
    for name in members:
        v = assigns.get(name)
        if isinstance(v, ast.Set):
            out[name] = {e.value for e in v.elts
                         if isinstance(e, ast.Constant) and isinstance(e.value, str)}
        elif isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id == "set" and not v.args:
            out[name] = set()   # 의도적 빈 축(근거 미확인이라 비워 둔 것)
    assert set(out) == set(members), f"피연산자 중 해석 못 한 것: {set(members) - set(out)}"
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
    # ★적격 축은 §77의15①**1호 상업지역**이다 — `station`(지하철 500m)은 2호「지정된
    #   역세권개발구역」과 다른 모집단이라 적대 리뷰 J-1 로 축에서 뺐다.
    eligible = _map(sim._scenarios(_ctx(integration_ok=False, zone="일반상업지역")))["결합건축"]
    not_eligible = _map(sim._scenarios(
        _ctx(integration_ok=False, station=True, zone="제2종일반주거지역")))["결합건축"]
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


# ─────────────────────────────────────────────────────────────────────────────
# 6) ★기계 변이(`scripts/mutate_changed.py`)가 드러낸 구멍 봉합
#    손으로 고른 변이 8종은 전부 CAUGHT 였는데, 기계는 아래를 생존시켰다.
# ─────────────────────────────────────────────────────────────────────────────

def test_downgrade_lands_on_conditional_not_merely_not_impossible():
    """★`applicable = "조건부"` **줄을 지워도** 종전 락이 초록이었다.

    *"불가가 아니다"* 는 **강등이 아예 일어나지 않는 경우**에도 참이다(「가능」이 그대로 남음).
    계약은 «불가가 아님» 이 아니라 **«조건부로 내려간다»** 이므로 값을 못 박는다.
    """
    ok, bad = _adjacency_pair()
    # 인접 시 「가능」이던 게이트 대상만 고른다(파생) — 이미 조건부인 것은 변화가 안 보인다.
    gate = set().union(*_gate_set_literals().values())
    was_possible = sorted(k for k in gate if k in ok and ok[k]["applicable"] == "가능")
    assert was_possible, "「가능」이던 게이트 대상이 0개 — 픽스처가 모집단을 못 만든다"
    for k in was_possible:
        assert bad[k]["applicable"] == "조건부", (
            f"{k}: 비인접이면 **조건부**여야 한다 — 실제 {bad[k]['applicable']!r} "
            "(강등 자체가 사라지면 사용자는 근거 없는 「가능」을 본다)"
        )


def test_downgrade_reason_reaches_cons_not_only_notes():
    """사유는 `notes` 뿐 아니라 **`cons`** 에도 실려야 한다(화면이 둘을 다르게 쓴다)."""
    _, bad = _adjacency_pair()
    s = bad["지구단위계획 연계"]
    joined = " ".join(s["cons"] or [])
    assert "비인접" in joined, f"cons 에 비인접 사유가 없다: {s['cons']!r}"
    assert "관할 확인" in joined, f"cons 에 후속 안내가 없다: {s['cons']!r}"


def test_zone_basis_constants_are_pinned_literals():
    """★상수를 **리터럴로 못 박는다**.

    종전 락은 `basis == ZONE_BASIS_AREA_WEIGHTED` 처럼 **상수를 임포트해 비교**해서,
    상수 값을 바꾸면 양변이 같이 바뀌어 **통과했다**(자기 상수를 단언하는 락).
    값은 응답 계약이므로 소비처가 문자열로 분기할 수 있다 — 바뀌면 깨져야 한다.
    """
    assert ZONE_BASIS_AREA_WEIGHTED == "area_weighted"
    assert ZONE_BASIS_SINGLE == "single_zone"
    assert ZONE_BASIS_NO_AREA == "first_parcel_no_area"
    # 닫힌 집합 — 새 값을 조용히 늘리면 소비처가 모른다.
    assert {ZONE_BASIS_AREA_WEIGHTED, ZONE_BASIS_SINGLE,
            ZONE_BASIS_NO_AREA, SS.ZONE_BASIS_NONE} == {
        "area_weighted", "single_zone", "first_parcel_no_area", "none"}


def test_every_site_payload_carrying_primary_zone_also_carries_basis():
    """★소스 문자열 검사가 아니라 **AST 로 전수** 대조한다.

    종전 락은 `'"primary_zone_basis": …' in _SRC` 였다 — 페이로드가 **두 군데**인데
    한 곳만 지워도 통과했다(기계 변이가 `:507` 줄삭제로 정확히 그것을 생존시켰다).
    """
    with_zone = with_basis = 0
    for n in ast.walk(ast.parse(_SRC)):
        if not isinstance(n, ast.Dict):
            continue
        keys = {k.value for k in n.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)}
        if "primary_zone" in keys:
            with_zone += 1
            if "primary_zone_basis" in keys:
                with_basis += 1
    assert with_zone >= 2, f"primary_zone 을 싣는 딕트가 {with_zone}개 — 수집기가 죽었다"
    assert with_basis == with_zone, (
        f"primary_zone 을 싣는 {with_zone}곳 중 basis 를 함께 싣는 곳은 {with_basis}곳뿐 — "
        "근거 없이 용도지역만 실으면 「면적가중」과 「첫 필지 폴백」이 구별되지 않는다"
    )


def test_zone_fallback_paths_are_wired():
    """폴백 경로 — 실측 용도지역이 **없을 때** 전체 목록으로 떨어지는가."""
    # 실측이 하나도 없으면 전체(추론 포함) 행으로 판단해야 한다.
    rows = [{"zone": "제1종일반주거지역", "area": 100.0},
            {"zone": "제2종일반주거지역", "area": 900.0}]
    assert dominant_zone_by_area(rows)[0] == "제2종일반주거지역"
    # 전부 비어 있으면 빈 문자열 + none — 조용히 첫 값을 지어내지 않는다.
    assert dominant_zone_by_area([{"zone": None, "area": 5.0}]) == ("", SS.ZONE_BASIS_NONE)


# ─────────────────────────────────────────────────────────────────────────────
# 7) 용도지역 **배선** — 판단이 아니라 «어느 모집단을 주는가»
#    ★기계 변이가 `simulate()` 인라인 두 줄을 생존시켜, 순수함수로 꺼내 잠근다.
# ─────────────────────────────────────────────────────────────────────────────

def test_measured_zones_win_over_inferred():
    """실측이 있으면 **추론은 모집단에서 빠진다** — 지어낸 값이 실측을 이기지 않는다."""
    enriched = [
        {"zone": "보전녹지지역", "area": 9000.0, "zone_source": "keyword_inference"},
        {"zone": "제2종일반주거지역", "area": 100.0, "zone_source": "vworld"},
    ]
    zone, basis = SS.select_primary_zone(enriched)
    assert zone == "제2종일반주거지역", f"추론(9,000㎡)이 실측(100㎡)을 이겼다 — {zone}"
    assert basis == "single_zone"


def test_falls_back_to_all_rows_when_nothing_measured():
    """실측이 하나도 없으면 **추론 포함 전체**로 판단한다(그 줄을 지우면 여기서 깨진다)."""
    enriched = [
        {"zone": "제1종일반주거지역", "area": 100.0, "zone_source": "keyword_inference"},
        {"zone": "제2종일반주거지역", "area": 900.0, "zone_source": "keyword_inference"},
    ]
    zone, basis = SS.select_primary_zone(enriched)
    assert zone == "제2종일반주거지역", f"전체 폴백이 끊겼다 — {zone}"
    assert basis == "area_weighted"


def test_falls_back_to_site_zone_type_when_no_parcel_zone():
    """필지에 용도지역이 하나도 없으면 호출자가 준 값 — 그때 근거는 `none`."""
    assert SS.select_primary_zone([], "제3종일반주거지역") == ("제3종일반주거지역", "none")
    assert SS.select_primary_zone([{"zone": None, "area": 1.0}], "준주거지역") == ("준주거지역", "none")
    assert SS.select_primary_zone([], "") == ("", "none")


def test_simulate_uses_the_extracted_wiring():
    """배선이 `simulate()` 안에서 **실제로 호출**되는지(꺼내 놓고 안 쓰면 무의미)."""
    assert "select_primary_zone(enriched" in _SRC
    # ★인라인 복제본이 남으면 두 경로가 갈린다 — 종전 인라인 표식이 사라졌는지 확인.
    assert "dominant_zone_by_area(_measured_rows or _all_rows)" not in _SRC


# ─────────────────────────────────────────────────────────────────────────────
# 8) ★적대 리뷰(2026-09-02)가 뚫은 두 층 — CRITICAL 봉합
# ─────────────────────────────────────────────────────────────────────────────

#: 게이트에 **의도적으로 넣지 않은** 방식과 그 사유. ★이 표가 없으면 아래 파티션 단언이
#  성립하지 않으므로, 새 방식을 추가하면 **여기서 판단을 강제**당한다(조용한 누락 방지).
#  ★사유 없는 원소는 금지 — 「부채」도 사유로 적어 둔다(§36 죽은 면제도 실패시킬 것).
NON_GATED_WITH_REASON: dict[str, str] = {
    "단순 건축": "자립방식 — 현 용도지역 한도 내 건축이라 구역·가로구역과 무관",
    "결합건축": "제도의 전제가 **100m 이내 이격**(건축법 §77의15①) — 인접성 축 자체가 역적용",
    "공동주택 리모델링": "기존 건축물 증축 — 신규 구역 지정과 무관",
    "도시재생사업": "★부채 — 인접 요건 조문 미확인(지어내지 않는다)",
    "자율주택정비사업": "★부채 — 인접 요건 조문 미확인",
    "소규모재건축사업": "★부채 — 인접 요건 조문 미확인(주택단지 축일 가능성)",
    "역세권 청년안심주택": "★부채 — 서울시 조례 발원, 인접 요건 미확인",
    "공공지원민간임대(뉴스테이)": "★부채 — 촉진지구 요건 미확인",
}


def test_gate_membership_is_a_partition_of_all_schemes():
    """★★기대값을 **변이 대상 밖**에서 만든다.

    적대 리뷰 실측: 종전 락은 모집단을 `_gate_set_literals()` — **자기가 잠그려는 그 집합** —
    에서 파생시켰다. 그래서 원소를 지우면 **기대값이 함께 깎여** 단언이 빨개지지 않고
    **사라졌다**: 13종 중 **10종을 지워도 32건 전부 초록**(M17).

    여기서는 원천을 **`add()` 전수**(게이트와 무관한 축)로 두고, 게이트와 명시적 비게이트 표가
    **정확히 그것을 분할**하는지 본다. 어느 쪽에서 원소가 사라지면 **양변이 갈린다.**
    """
    every = _add_scheme_names()
    gate = set().union(*_gate_set_literals().values())
    declared_out = set(NON_GATED_WITH_REASON)

    assert len(every) >= 20, f"add() 수집이 비정상 — {len(every)}종(수집기 사망)"
    assert not (gate & declared_out), f"게이트와 비게이트가 겹친다: {sorted(gate & declared_out)}"

    missing = sorted(every - gate - declared_out)
    assert not missing, (
        f"게이트에도 비게이트 표에도 없는 방식: {missing} — "
        "새 방식을 추가하면 인접성 판정을 **의도적으로** 정하고 여기 적어라"
    )
    ghost = sorted((gate | declared_out) - every)
    assert not ghost, f"실재하지 않는 방식이 선언돼 있다(죽은 원소): {ghost}"
    # ★양쪽 크기를 못 박는다 — 한쪽에서 지우면 다른 쪽 합이 어긋난다.
    assert len(gate) + len(declared_out) == len(every), (
        f"분할이 성립하지 않는다: 게이트 {len(gate)} + 비게이트 {len(declared_out)} != 전체 {len(every)}"
    )


def test_every_non_gated_entry_carries_a_reason():
    """비게이트 표의 **사유가 비어 있으면 실패** — 조용한 면제를 금지한다."""
    for k, v in NON_GATED_WITH_REASON.items():
        assert v and len(v) >= 10, f"{k}: 비게이트 사유가 비었거나 너무 짧다 — {v!r}"


def test_self_standing_never_enters_the_gate():
    """★처음 뚫린 그 성질 자체를 잠근다 — 자립방식이 게이트에 **침투하지 않는다**.

    적대 리뷰 M22: `GARO_GUYEOK_SCHEMES` 에 `"단순 건축"` 을 넣어도 **생존**했다.
    수집기의 «어떻게 파생하는가» 는 고쳤지만 이 성질은 아무도 단언하지 않았다.
    """
    self_standing = _named_set_literal("SELF_STANDING_SCHEMES")
    assert self_standing, "SELF_STANDING_SCHEMES 를 못 찾았다 — 수집기 사망"
    gate = set().union(*_gate_set_literals().values())
    overlap = sorted(gate & self_standing)
    assert not overlap, f"자립방식이 인접성 게이트에 들어왔다: {overlap}"


def _named_set_literal(name: str) -> set[str]:
    for n in ast.walk(ast.parse(_SRC)):
        tgt = None
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            tgt = n.targets[0].id
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
            tgt = n.target.id
        if tgt == name and isinstance(getattr(n, "value", None), ast.Set):
            return {e.value for e in n.value.elts
                    if isinstance(e, ast.Constant) and isinstance(e.value, str)}
    return set()


def _constraint_map(**kw):
    """★`_scenarios()` 를 **통과시켜** 얻는다 — `_buildable_types` 직접 호출이 아니다.

    적대 리뷰 M-2: C-1 락 전부가 정적 메서드를 직접 불러 **배선을 안 태웠다.**
    그래서 `_zone = c.get("primary_zone")` 를 고정값으로 바꾸는 변이가 **통과**했다 —
    즉 «제1종 부지에서 아파트 제안» 이라는 **바로 그 사용자 결함을 되살려도 초록**이었다.
    """
    sim = DevelopmentScenarioSimulator()
    return _map(sim._scenarios(_ctx(integration_ok=True, **kw)))


def test_wiring_marks_every_apartment_proposal_on_type1_site():
    """★★C-1(배선) — 제1종 부지에서 **아파트를 제안하는 모든 방식**이 제약을 달아야 한다.

    모집단은 `add()` 전수에서 파생하고, 판정은 **`_scenarios()` 결과**로 한다.
    """
    got = _constraint_map(zone="제1종일반주거지역", area_sqm=12000.0)
    assert len(got) >= 20, f"시나리오가 {len(got)}종 — 픽스처가 모집단을 못 만든다"
    proposing = [k for k, v in got.items() if SS.proposes_apartment(v.get("buildable_types") or [])]
    assert proposing, "제1종 부지인데 아파트를 제안하는 방식이 0개 — 검사기가 죽었다"
    missing = [k for k in proposing if not v_ok(got[k])]
    assert not missing, (
        f"아파트를 제안하면서 용도 제약을 안 단 방식 {len(missing)}/{len(proposing)}: {missing}"
    )


def v_ok(scn: dict) -> bool:
    c = scn.get("zone_use_constraint")
    return bool(c) and "아파트" in (c.get("prohibited") or []) and bool(c.get("message"))


def test_wiring_survives_mixed_zone_where_type1_is_not_dominant():
    """★★M-5 — 제2종이 **면적 우세**여도 제1종이 부지에 있으면 제약이 살아 있어야 한다.

    사용자가 신고한 부지가 정확히 `zones=[제1종, 제2종]` 이다. RC-2(면적가중)를 고치자
    `primary_zone=제2종` 이 되어 RC-3(제1종 제약)의 발화 조건이 **지워졌다** —
    둘이 서로를 가린다고 적어 놓고, 같이 고쳤더니 한쪽이 다른 쪽을 껐다.
    """
    got = _constraint_map(zone="제2종일반주거지역",
                          zones=["제1종일반주거지역", "제2종일반주거지역"], area_sqm=12000.0)
    proposing = [k for k, v in got.items() if SS.proposes_apartment(v.get("buildable_types") or [])]
    assert proposing, "혼재 부지에서 아파트 제안이 0개 — 픽스처 이상"
    missing = [k for k in proposing if not v_ok(got[k])]
    assert not missing, f"혼재 부지에서 제1종 제약이 꺼졌다: {missing}"
    # ★음성 대조군 — 제1종이 **없는** 부지에서는 붙으면 안 된다.
    clean = _constraint_map(zone="제2종일반주거지역",
                            zones=["제2종일반주거지역", "제3종일반주거지역"], area_sqm=12000.0)
    stuck = [k for k, v in clean.items() if v.get("zone_use_constraint")]
    assert not stuck, f"제1종이 없는 부지에 제약이 붙었다: {stuck}"


def test_constraint_is_not_pasted_into_buildable_types():
    """★M-4 — 경고를 **「건축 가능」 칩 목록에 섞지 않는다.**

    프론트(`DevelopmentScenarioCard.tsx`)는 `buildable_types` 의 **모든 원소를 같은 악센트
    색 칩**으로 그린다. 거기에 경고를 넣으면 *"아파트"* 와 *"아파트 불허"* 가 나란히 서고,
    그건 고친 것이 아니라 **문구로 덮은 것**이다. 전용 필드 + `cons` 로 낸다.
    """
    got = _constraint_map(zone="제1종일반주거지역", area_sqm=12000.0)
    for k, v in got.items():
        for t in (v.get("buildable_types") or []):
            assert SS.APARTMENT_PROHIBITED_MARK not in t, f"{k}: 경고가 칩 목록에 섞였다 — {t!r}"
        if v.get("zone_use_constraint"):
            joined = " ".join(v.get("cons") or [])
            assert SS.APARTMENT_PROHIBITED_MARK in joined, f"{k}: cons 에 제약이 없다"


def test_apartment_detector_ignores_its_own_negative_label():
    """★M-3 — 검출기가 **자기가 심은 부정 라벨**을 「아파트 제안」으로 세면 안 된다.

    적대 리뷰 실측: `any("아파트" in t …)` 가 `"(4층 이하 — 아파트 불가)"` 에 걸려
    21종 중 **9종이 위양성**이었다. 파티션형으로 잠근다.
    """
    assert SS.proposes_apartment(["아파트", "단독주택"]) is True
    assert SS.proposes_apartment(["저층 아파트"]) is True
    assert SS.proposes_apartment(["연립/다세대(빌라)", "(4층 이하 — 아파트 불가)"]) is False
    assert SS.proposes_apartment([SS.APARTMENT_PROHIBITED_MARK]) is False
    assert SS.proposes_apartment([]) is False
    # 전수 — 제1종에서 검출기가 세는 수가 실제 아파트 제안 수와 같아야 한다.
    D = DevelopmentScenarioSimulator
    schemes = sorted(_add_scheme_names())
    flagged = [x for x in schemes if SS.proposes_apartment(D._buildable_types("제1종일반주거지역", x))]
    naive = [x for x in schemes
             if any("아파트" in t for t in D._buildable_types("제1종일반주거지역", x))]
    assert len(flagged) < len(naive), (
        f"부정 라벨 배제가 아무것도 걸러내지 못했다(검출기={len(flagged)} 순진={len(naive)})"
    )


def test_apartment_mark_is_not_pasted_where_it_does_not_belong():
    """★음성 대조군 — 제2·3종에는 **붙으면 안 된다**([별표 5]에 제외 문구 없음).

    이 단언이 없으면 *"전부 고지 붙이기"* 라는 과잉 구현도 통과한다.
    """
    D = DevelopmentScenarioSimulator
    for zone in ("제2종일반주거지역", "제3종일반주거지역"):
        marked = [s for s in sorted(_add_scheme_names())
                  if SS.APARTMENT_PROHIBITED_MARK in D._buildable_types(zone, s)]
        assert not marked, f"{zone} 에 불허 고지가 붙었다: {marked}"


def test_zone_prohibits_apartment_partitions():
    """순수함수 — 두 모집단이 **다른 답**을 내야 한다."""
    assert SS.zone_prohibits_apartment("제1종일반주거지역") is True
    assert SS.zone_prohibits_apartment("제1종전용주거지역") is True
    assert SS.zone_prohibits_apartment("제2종일반주거지역") is False
    assert SS.zone_prohibits_apartment("제3종일반주거지역") is False
    assert SS.zone_prohibits_apartment("일반상업지역") is False
    assert SS.zone_prohibits_apartment(None) is False


# ─────────────────────────────────────────────────────────────────────────────
# 9) 적대 리뷰 MAJOR 봉합 락
# ─────────────────────────────────────────────────────────────────────────────

def test_station_is_not_an_eligibility_axis_for_combined_building():
    """★J-1 — `station`(지하철 500m)은 §77의15①2호 **「지정된 역세권개발구역」**이 아니다.

    적격 축은 **1호 상업지역**만 측정된 것으로 둔다. 이 단언이 없으면 `com or station` 으로
    되돌려도 초록이고, 그러면 서울 다필지 대부분에 `est_far = far×1.2` 가 붙는다
    (그 값은 화면 표시이자 **추천 정렬 키**다).
    """
    sim = DevelopmentScenarioSimulator()
    res = _map(sim._scenarios(_ctx(integration_ok=False, station=True,
                                   zone="제2종일반주거지역")))["결합건축"]
    assert res["est_far"] is None, (
        f"역세권(500m)만으로 결합건축 용적 추정이 나왔다 — est_far={res['est_far']} "
        "(§77의15①2호는 「지정된 역세권개발구역」이지 지하철 반경이 아니다)"
    )
    com = _map(sim._scenarios(_ctx(integration_ok=False, station=False,
                                    zone="일반상업지역")))["결합건축"]
    assert com["est_far"] is not None, "상업지역(1호)은 측정된 적격 축이어야 한다"


def test_distance_is_not_used_as_a_verdict():
    """★축이 틀렸으므로 **거리로 판정하지 않는다**(시행령 §111 원문 확인 2026-09-02).

    종전 이 자리의 락은 `assert far["applicable"] == "불가"`(450m) 였다 —
    **결함을 계약으로 못 박은 것**이다. 실제 법:

    · 건축법 §77의15① 의 「100미터」는 **외곽 한계**이고, 조작적 기준은 시행령 **§111①**:
      ①동일 지역 + ②**너비 12m 이상 도로로 둘러싸인 하나의 구역** 안. **거리 요건이 아니다.**
    · **3개 이상 대지는 §111③ 이 「500미터」** 다 — 100m 를 적용하면 **거짓 「불가」**가 난다.

    현 분석은 두 축(12m 도로 구역 · 대지 수별 상한) 어느 것도 측정하지 못하므로,
    **거리로 「불가」를 만들지 않는다.**
    """
    sim = DevelopmentScenarioSimulator()
    verdicts = {
        m: _map(sim._scenarios(_ctx(integration_ok=False, zone="일반상업지역",
                                     max_pair_m=m)))["결합건축"]["applicable"]
        for m in (5.0, 30.0, 450.0, 5000.0, None)
    }
    assert len(set(verdicts.values())) == 1, (
        f"거리가 판정을 가르고 있다 — {verdicts}. 시행령 §111 의 축은 거리가 아니다"
    )
    assert set(verdicts.values()) == {"조건부"}, f"판정은 조건부여야 한다 — {verdicts}"


def test_real_decree_axes_are_disclosed_not_invented():
    """측정 못 하는 축은 **요건으로 고지**한다 — 지어내지도, 침묵하지도 않는다."""
    s = _map(DevelopmentScenarioSimulator()._scenarios(
        _ctx(integration_ok=False, zone="일반상업지역")))["결합건축"]
    blob = " ".join(s["requirements"] or [])
    assert "12m" in blob or "12미터" in blob, f"§111① 의 12m 도로 구역 축이 없다: {blob!r}"
    assert "500" in blob, f"§111③ 의 3개 이상 500m 축이 없다: {blob!r}"
    assert "§111" in blob, f"시행령 근거가 없다: {blob!r}"
    # ★거리로 판정한다는 주장이 표면에 남으면 안 된다(종전 문구 회귀 방지)
    assert "100m 이내" not in blob, f"틀린 축(100m 판정)이 요건에 남았다: {blob!r}"


def test_distance_helper_exists_but_is_not_wired():
    """`combined_building_distance_verdict` 는 **판정에서 뺐다** — 죽은 채로 두되 사실을 잠근다.

    ★§36 「죽은 면제도 실패시켜라」의 형태: 값·헬퍼를 남기면서 **왜 안 쓰는지**를 코드에 적었고,
    여기서는 **실제로 안 쓰이는지**를 확인한다. 되살리려면 12m 도로 구역·대지 수별 상한을
    먼저 측정할 수 있어야 한다.
    """
    assert SS.COMBINED_BUILDING_MAX_DISTANCE_M == 100.0
    assert SS.COMBINED_BUILDING_MAX_DISTANCE_M_3PLUS == 500.0
    # 순수함수 자체는 정상 동작(향후 배선용)
    assert SS.combined_building_distance_verdict({"max_pair_distance_m_min": 30.0}) == (True, 30.0)
    assert SS.combined_building_distance_verdict({}) == (None, None)
    # ★그러나 시나리오 판정 경로에서는 호출되지 않는다(AST)
    called_in = set()
    tree = ast.parse(_SRC)
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for n in ast.walk(fn):
                if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                        and n.func.id == "combined_building_distance_verdict"):
                    called_in.add(fn.name)
    assert not called_in, (
        f"거리 판정이 다시 배선됐다: {sorted(called_in)} — 12m 도로 구역(§111①)과 "
        "대지 수별 상한(§111③ 500m)을 측정할 수 있게 된 뒤에만 되살려라"
    )


def test_measured_zone_predicate_has_no_duplicate():
    """★J-2 — 실측 판정 술어가 **한 곳에만** 있다(복제본이 남으면 드리프트한다)."""
    assert SS.measured_zone_count([
        {"zone": "제2종일반주거지역", "zone_source": "vworld"},
        {"zone": "보전녹지지역", "zone_source": "keyword_inference"},
        {"zone": None, "zone_source": "vworld"},
    ]) == 1
    assert SS.measured_zone_count([]) == 0
    # 소스에 인라인 복제본이 남아 있으면 실패 — 술어 문자열을 세어 본다.
    dup = _SRC.count('p.get("zone_source") != "keyword_inference"')
    assert dup <= 2, (
        f"실측 술어가 {dup}곳에 복제돼 있다 — `measured_zone_count`/`select_primary_zone` "
        "두 곳(같은 함수 계열)을 넘으면 드리프트가 가능해진다"
    )
    # ★소스 문자열이 아니라 **AST** 로 본다 — 변수명은 그대로 두고 계산만 바꾸는 변이가
    #   문자열 검사를 통과했다(실측 SURVIVED). 「이름이 있다」가 아니라 「그 함수가 쓰인다」를 본다.
    assigned_from = []
    for n in ast.walk(ast.parse(_SRC)):
        if (isinstance(n, ast.Assign) and len(n.targets) == 1
                and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "measured_zone_n"):
            v = n.value
            assigned_from.append(
                v.func.id if isinstance(v, ast.Call) and isinstance(v.func, ast.Name) else type(v).__name__
            )
    assert assigned_from, "`measured_zone_n` 대입을 못 찾았다 — 수집기 사망"
    assert set(assigned_from) == {"measured_zone_count"}, (
        f"`measured_zone_n` 이 단일 술어가 아닌 것에서 나온다: {assigned_from} — "
        "인라인 계산을 다시 넣으면 `primary_zone_is_inferred` 가 조용히 드리프트한다"
    )
    # 소비처가 실제로 그 변수를 쓰는지(꺼내 놓고 안 쓰면 무의미)
    assert _SRC.count("measured_zone_n == 0") >= 2, "두 페이로드 모두 단일 술어를 소비해야 한다"


def test_gate_has_no_unreachable_reason_branch():
    """★J-3 — 사유 없는 축이 들어오면 **시끄럽게 죽는다**(조용히 틀린 사유가 나가지 않는다)."""
    assert "raise AssertionError(f\"인접성 게이트에 사유 없는 축" in _SRC, (
        "도달 불가 else 가 조용한 폴백으로 남아 있다"
    )
    # 세 축이 모두 명시 분기를 갖는다(else 폴백에 기대지 않는다).
    for name in _gate_set_literals():
        assert f"scheme in {name}" in _SRC, f"{name} 에 대응하는 명시 분기가 없다"


def test_small_site_asymmetry_is_declared_not_accidental():
    """★J-4 — 같은 면적인데 **단일 1필지는 불가 · 비인접 2필지는 조건부**.

    이 PR 이 만든 차이다(종전에는 인접성 게이트가 양쪽을 「불가」로 만들어 같았다).
    `single_small = (not multi) and …` 이라 다필지는 이 하한을 **원리적으로 통과**한다.

    ★**의도로 선언하고 잠근다** — 두 분기는 다른 것을 인코딩한다:
      `single_small` 은 **규모**(단독으로 구역을 구성할 수 없음), 이 PR 의 게이트는 **인접성**
      (법정 요건 아님). 규모 하한을 다필지로 확장하는 것은 **사용자가 신고하지 않은 모집단**의
      동작을 바꾸고 기존 락 3건과 충돌하므로 **이 PR 범위 밖**이다.
      이 단언은 그 비대칭이 **조용히 생기지 않게** 붙잡아 둔다 — 없어지면 여기서 빨개진다.
    """
    sim = DevelopmentScenarioSimulator()
    single = _map(sim._scenarios(_ctx(integration_ok=True, multi=False, area_sqm=800.0)))
    multi_np = _map(sim._scenarios(_ctx(integration_ok=False, multi=True, area_sqm=800.0)))
    assert single["지구단위계획 연계"]["applicable"] == "불가", "단일 소규모 규모 하한은 유지"
    assert multi_np["지구단위계획 연계"]["applicable"] == "조건부", "다필지는 규모 하한을 안 탄다"
    assert single["단순 건축"]["applicable"] == "가능"


# ─────────────────────────────────────────────────────────────────────────────
# 10) ★M-1 — 게이트 멤버십을 **행동**으로 잠근다(분류만으로 통과하지 않게)
# ─────────────────────────────────────────────────────────────────────────────

def test_gate_membership_is_locked_by_behavior_not_by_classification():
    """★★파티션 단언만으로는 **이관 우회로**가 열린다.

    적대 리뷰 실측: `도심복합개발사업` 을 게이트에서 지우고 `NON_GATED_WITH_REASON` 에
    **상용구 사유**로 옮기면 44건 전부 초록이었다(2종을 옮겨도 초록).
    파티션은 「겹침·누락·유령·크기합」만 보고 **어느 쪽에 있느냐**는 안 봤다.

    실전 위험이 정확히 이것이다 — 다음 사람이 빨간 테스트를
    **`NON_GATED_WITH_REASON` 에 「★부채」로 옮겨서 고친다.** 테스트가 그 행동을 보상한다.

    → **행동으로** 판정한다: 게이트 원소는 비인접에서 **사유가 달라지고**,
      비게이트 원소는 두 실행이 **동일**해야 한다. 이관하면 반대편에서 빨개진다.
    """
    ok, bad = _adjacency_pair(area_sqm=12000.0)
    gate = set().union(*_gate_set_literals().values())
    declared_out = set(NON_GATED_WITH_REASON)

    def _touched(k: str) -> bool:
        """비인접 실행에서 판정 또는 사유가 달라졌는가."""
        a, b = ok.get(k), bad.get(k)
        if a is None or b is None:
            return False
        return (a["applicable"] != b["applicable"]
                or (a["notes"] or "") != (b["notes"] or "")
                or (a["cons"] or []) != (b["cons"] or []))

    # ① 게이트 원소 중 **인접 시 추진 가능**한 것은 반드시 영향을 받아야 한다.
    eligible_gate = [k for k in gate if k in ok and ok[k]["applicable"] != "불가"]
    assert len(eligible_gate) >= 3, f"판정 대상이 너무 적다 — {eligible_gate}"
    inert = [k for k in eligible_gate if not _touched(k)]
    assert not inert, (
        f"게이트에 있는데 인접성이 **아무것도 바꾸지 않는** 방식: {inert} — "
        "선언만 되고 발화하지 않으면 게이트에 있을 이유가 없다"
    )

    # ② ★반대 방향 — 비게이트 원소는 인접성으로 **한 글자도** 달라지면 안 된다.
    #    이관 우회로가 여기서 죽는다: 게이트에서 빼서 옮기면 이 단언이 빨개진다.
    leaked = [k for k in declared_out if _touched(k)]
    assert not leaked, (
        f"비게이트로 선언해 놓고 인접성이 판정/사유를 바꾸는 방식: {leaked} — "
        "게이트에서 지우고 표로 옮기는 것만으로는 계약이 성립하지 않는다"
    )


def test_buildable_types_derive_from_the_site_zone_not_a_constant():
    """★MUT-16 — `_zone = c.get("primary_zone")` 를 **고정값으로 바꿔도** 종전 락은 초록이었다.

    제약 부착만 보고 **목록 내용이 부지 용도지역에서 나오는지**를 안 봤기 때문이다.
    두 모집단이 **다른 목록**을 내야 한다.
    """
    t1 = _constraint_map(zone="제1종일반주거지역", area_sqm=12000.0)["단순 건축"]["buildable_types"]
    t2 = _constraint_map(zone="제2종일반주거지역", area_sqm=12000.0)["단순 건축"]["buildable_types"]
    assert t1 != t2, f"제1종과 제2종이 같은 목록 — 용도지역이 배선에서 끊겼다: {t1}"
    assert not SS.proposes_apartment(t1), f"제1종 단순건축에 아파트가 있다 — [별표 4] 위반: {t1}"
    assert SS.proposes_apartment(t2), f"제2종 단순건축에 아파트가 없다 — [별표 5]는 허용: {t2}"
    # 상업지역도 갈려야 한다(분기가 통째로 죽는 변이 차단)
    tc = _constraint_map(zone="일반상업지역", area_sqm=12000.0)["단순 건축"]["buildable_types"]
    assert tc != t1 and tc != t2, f"상업지역이 주거와 같은 목록 — 분기가 죽었다: {tc}"


#: 각 축의 **원소 수**를 리터럴로 못 박는다. ★행동 락은 「그 픽스처에서 발화하는 방식」만 볼 수
#  있어, 발화하지 않는 방식을 게이트 밖으로 옮기면 **행동이 안 바뀌어 통과**한다(MUT-11 실측).
#  크기를 못 박으면 이관이 **양쪽에서** 걸린다. 값을 바꾸려면 사유를 함께 고치게 된다.
_AXIS_SIZES = {
    "AREA_DESIGNATION_SCHEMES": 11,   # 구역지정형 — 인접성으로 「불가」를 만들지 않는다
    "GARO_GUYEOK_SCHEMES": 2,         # 가로구역형 — 축은 폭 4m/6m 초과 도로 관통
    "HOUSING_COMPLEX_SCHEMES": 0,     # 주택단지형 — ★의도적 공집합(근거 조문 미확인)
}


def test_axis_sizes_are_pinned():
    """★MUT-11 — 게이트에서 지우고 비게이트 표에 상용구 사유로 옮기면 44건 전부 초록이었다.

    행동 락의 사각(발화하지 않는 방식)을 **크기 고정**으로 덮는다.
    """
    sets = _gate_set_literals()
    assert set(sets) == set(_AXIS_SIZES), (
        f"축 구성이 바뀌었다 — 코드 {sorted(sets)} vs 선언 {sorted(_AXIS_SIZES)}. "
        "축을 더하거나 빼면 사유와 크기를 여기 함께 적어라"
    )
    for name, want in _AXIS_SIZES.items():
        assert len(sets[name]) == want, (
            f"{name} 원소 수 {len(sets[name])} ≠ 선언 {want} — "
            f"현재 {sorted(sets[name])}. 이관·삭제는 사유와 함께 여기도 고쳐라"
        )
    assert len(NON_GATED_WITH_REASON) == len(_add_scheme_names()) - sum(_AXIS_SIZES.values())


def test_adjacency_producer_reports_real_pair_distance():
    """★C-A — `max_pair_distance_m_min` 의 **생산자**(`_adjacency`)를 실 geometry 로 태운다.

    적대 리뷰 실측: `max_pair_deg = max(…)` → `min(…)` 으로 바꾸면 시드가 0.0 이라
    **모든 부지가 영원히 0.0m** 를 보고하는데 락 전부 초록이었다. 픽스처가 그 값을
    **손으로 넣어 줘서** 생산자가 한 번도 안 탔기 때문이다(«순수함수는 잠갔는데 생산자는 무잠금»).

    ★이 값은 현재 **판정에 쓰이지 않는다**(축이 틀려 철회 — 시행령 §111). 그래도 응답에 실려
    나가므로, 다음 사람이 §111③(3개 이상 500m)을 구현할 때 **틀린 값을 믿지 않도록** 잠근다.
    """
    pytest.importorskip("shapely")

    def _sq(lon, lat, d=0.00002):
        return {"type": "Polygon", "coordinates": [[
            [lon, lat], [lon + d, lat], [lon + d, lat + d], [lon, lat + d], [lon, lat]]]}

    # 서울 도심 부근. 세 번째 필지를 **멀리** 둬서 최댓값이 그것으로 정해지게 한다.
    near = [{"geometry": _sq(127.0, 37.5)}, {"geometry": _sq(127.00005, 37.5)}]
    far = [*near, {"geometry": _sq(127.005, 37.5)}]

    a_near = DevelopmentScenarioSimulator._adjacency(near)
    a_far = DevelopmentScenarioSimulator._adjacency(far)
    d_near = a_near.get("max_pair_distance_m_min")
    d_far = a_far.get("max_pair_distance_m_min")

    assert d_near is not None and d_far is not None, (
        f"생산자가 쌍거리를 방출하지 않는다 — near={a_near} far={a_far}"
    )
    # ★두 모집단이 **갈려야** 한다(0.0 붕괴·상수화가 여기서 죽는다)
    assert d_far > d_near, f"먼 필지를 더해도 최댓값이 안 커진다 — near={d_near} far={d_far}"
    assert d_far > 100.0, f"약 440m 떨어진 쌍인데 {d_far}m 로 보고 — max 가 아니라 min/0 붕괴 의심"
    assert d_near < 50.0, f"맞닿은 두 필지가 {d_near}m — 과대보고"
    # ★상수 변경 탐지 — 0.005도(경도)는 88,800 기준 약 444m 다.
    assert 380.0 < d_far < 520.0, f"도→미터 변환이 바뀌었다 — {d_far}m (기대 약 444m)"


def test_absorption_rule_prevents_over_restriction():
    """★국토계획법 **§84①** — 가장 작은 부분이 **330㎡ 이하**면 그 부분의 **건축 제한은
    적용되지 않고** 가장 넓은 용도지역 규정을 따른다.

    원문: *"…가장 작은 부분의 규모가 대통령령으로 정하는 규모 이하인 경우에는 …
    **그 밖의 건축 제한 등에 관한 사항은 그 대지 중 가장 넓은 면적이 속하는 용도지역등에 관한
    규정을 적용**한다."*

    ★전수 판정(이름만 보기)은 **과잉 억제**다 — 1㎡ 짜리 제1종 자투리가 8만㎡ 부지 전체에
    아파트 불허를 붙인다. 두 모집단이 **갈려야** 한다.
    """
    # ① 흡수됨(300㎡ ≤ 330㎡) → 제약 **없음**
    absorbed = SS.apartment_restricted_zones([
        {"zone": "제1종일반주거지역", "area": 300.0},
        {"zone": "제2종일반주거지역", "area": 80_000.0},
    ])
    assert absorbed == [], f"330㎡ 이하 자투리는 흡수돼 제약이 없어야 한다 — {absorbed}"

    # ② 흡수 안 됨(400㎡ > 330㎡) → 제약 **있음**
    kept = SS.apartment_restricted_zones([
        {"zone": "제1종일반주거지역", "area": 400.0},
        {"zone": "제2종일반주거지역", "area": 80_000.0},
    ])
    assert kept == ["제1종일반주거지역"], f"330㎡ 초과면 각 부분에 각 규정 — {kept}"

    # ★②-b **두 모집단을 가른다** — 흡수가 일어나도 **남는 제한**은 살아야 한다.
    #   이 케이스가 없으면 `restricted = []`(흡수 시 통째로 비우기)가 통과한다(실측 SURVIVED):
    #   흡수 대상이 유일한 제한 지역이면 두 구현의 답이 같기 때문이다.
    #   → **흡수되는 쪽이 제한 대상이 아닌** 조합으로 가른다.
    kept2 = SS.apartment_restricted_zones([
        {"zone": "제1종일반주거지역", "area": 80_000.0},   # 최대 · 제한 대상 → **남아야 한다**
        {"zone": "제2종일반주거지역", "area": 300.0},      # 최소 ≤330㎡ → 흡수되지만 제한 대상 아님
    ])
    assert kept2 == ["제1종일반주거지역"], (
        f"흡수와 무관한 제한까지 사라졌다 — {kept2} (흡수는 **가장 작은 부분 하나**만이다)"
    )

    # ★②-c **분기 안까지 태운다** — 위 kept2 는 흡수 대상이 `restricted` 에 **없어서**
    #   필터 분기가 실행조차 되지 않는다(그래서 `restricted = []` 변이가 생존했다).
    #   흡수 대상이 **제한 대상이면서** 다른 제한이 남는 조합이 그 분기를 태운다.
    both = SS.apartment_restricted_zones([
        {"zone": "제1종전용주거지역", "area": 300.0},      # 최소 ≤330㎡ → 흡수 · **제한 대상**
        {"zone": "제1종일반주거지역", "area": 80_000.0},   # 최대 · 제한 대상 → **남아야 한다**
    ])
    assert both == ["제1종일반주거지역"], (
        f"흡수된 것만 빠지고 나머지는 남아야 한다 — {both}"
    )

    # ★기존 헬퍼의 한계를 사실로 적어 둔다(지어내지 않는다).
    #   `mixed_zone_limits` 는 흡수를 **2개 용도지역에서만** 적용한다(그 파일이 명시).
    #   따라서 3개 이상이면 흡수가 일어나지 않고 제한이 그대로 남는다 — **과잉 억제 방향**이다.
    three = SS.apartment_restricted_zones([
        {"zone": "제1종전용주거지역", "area": 300.0},
        {"zone": "제1종일반주거지역", "area": 5_000.0},
        {"zone": "제2종일반주거지역", "area": 80_000.0},
    ])
    assert "제1종일반주거지역" in three
    assert "제1종전용주거지역" in three, (
        "3개 이상에서도 흡수가 일어났다면 `mixed_zone_limits` 의 계약이 바뀐 것 — "
        "이 단언과 위 주석을 함께 갱신하라(★미측정: 3개 이상 흡수의 법적 근거는 확인하지 않았다)"
    )

    # ③ 단일 용도지역이면 흡수 여지가 없다
    assert SS.apartment_restricted_zones([{"zone": "제1종일반주거지역", "area": 50.0}]) == [
        "제1종일반주거지역"]
    # ④ 제한 대상이 없으면 빈 목록
    assert SS.apartment_restricted_zones([
        {"zone": "제2종일반주거지역", "area": 100.0},
        {"zone": "제3종일반주거지역", "area": 900.0}]) == []
    # ⑤ ★면적 미확보 — 흡수를 판정할 수 없으면 **불허 쪽으로 남긴다**(고지가 사라지는 것보다 낫다)
    assert SS.apartment_restricted_zones([
        {"zone": "제1종일반주거지역", "area": None},
        {"zone": "제2종일반주거지역", "area": 900.0}]) == ["제1종일반주거지역"]
    assert SS.apartment_restricted_zones([]) == []


def test_simulate_computes_restriction_from_areas_not_names():
    """배선 — `simulate()` 가 **면적을 보고** 판정해 ctx 로 넘기는가(이름 전수가 아니라)."""
    assert "apartment_restricted_zones(enriched)" in _SRC, (
        "`simulate()` 가 면적 기반 판정을 호출하지 않는다"
    )
    # `_scenarios` 는 소비만 한다 — 거기서 이름으로 다시 판정하면 §84① 흡수가 무시된다.
    i = _SRC.index("def _scenarios(")
    body = _SRC[i:]
    assert "zone_prohibits_apartment(z) for z in" not in body, (
        "`_scenarios` 가 이름으로 재판정하고 있다 — §84① 흡수가 무시된다"
    )
