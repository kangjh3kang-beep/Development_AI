"""개발방식 시뮬레이터가 **전제 감시망 안에** 있는가 + 우세 용도지역이 **형제와 일치**하는가.

## 왜 필요한가 (실측 2026-09-04)

`premise_audit.audit()` 호출부가 **`routers/auto_zoning.py` 1곳뿐**이라
`/development-methods/scenarios` 경로는 **감시망 밖**이었다. 등록된 전제 6종 중
`dominant_argmax` 는 `#940` 의 RC-2(첫 필지를 우세 용도지역으로 씀)를 **정확히** 잡는다 —
신고 부지 형상으로 감사기를 직접 태워 확인했다(종전 발화 / 수정 후 침묵).

★그리고 `#940` 자신이 **같은 클래스의 약한 판본**을 만들었다: 형제
`special_parcel._aggregate_integrated_zoning` 은 **동률(±5%)·규제성격 상이**를
`mixed_review_required` 로 **거부**하는데, `dominant_zone_by_area` 는 **임의 단일화**했다.
4모집단 중 **3개가 갈렸다.** 볼트가 *"시뮬레이터만 자기 방식을 만들었다"* 고 적어 둔 그 자리다.
"""
import pytest

from app.services.development import scenario_simulator as SS
from app.services.development.scenario_simulator import (
    DevelopmentScenarioSimulator,
    dominant_zone_by_area,
)
from app.services.zoning import premise_audit
from app.services.zoning.special_parcel import _aggregate_integrated_zoning


def _rows(pairs):
    return [{"zone": z, "area": a} for z, a in pairs]


def _sibling(pairs):
    agg = _aggregate_integrated_zoning(
        [{"zone_type": z, "area_sqm": a, "areaSqm": a} for z, a in pairs])
    return agg.get("dominant_zone")


# ── ① 형제와의 일치 — ★4모집단(3개가 갈렸던 자리) ──────────────────────────

@pytest.mark.parametrize("label,pairs", [
    ("같은 성격·면적차 큼", [("제1종일반주거지역", 410.0), ("제2종일반주거지역", 1300.0)]),
    ("★규제성격 상이(상업+주거)", [("일반상업지역", 1200.0), ("제2종일반주거지역", 800.0)]),
    ("★동률(±5% 이내)", [("제2종일반주거지역", 1000.0), ("제3종일반주거지역", 1020.0)]),
    ("★녹지+주거", [("자연녹지지역", 900.0), ("제2종일반주거지역", 1100.0)]),
])
def test_dominant_zone_agrees_with_sibling(label, pairs):
    """두 구현이 **같은 답**을 내야 한다 — 갈리면 하나는 틀린 것이다."""
    mine, _basis = dominant_zone_by_area(_rows(pairs))
    sib = _sibling(pairs)
    assert mine == sib, f"{label}: 내 판정={mine!r} 형제={sib!r} — 갈렸다"


def test_the_four_populations_actually_split():
    """★공허 진리 가드 — 네 모집단이 **서로 다른 답**을 내는지 먼저 본다.

    전부 같은 답이면 위 파라미터 테스트는 «아무것도 구별하지 않는» 락이 된다.
    """
    answers = {
        _sibling([("제1종일반주거지역", 410.0), ("제2종일반주거지역", 1300.0)]),
        _sibling([("일반상업지역", 1200.0), ("제2종일반주거지역", 800.0)]),
    }
    assert len(answers) >= 2, f"모집단이 갈리지 않는다 — {answers}"


def test_mixed_review_sentinel_is_emitted_not_invented():
    """★단일화를 **거부**하는 경우 센티널을 낸다 — 첫 필지를 지어내지 않는다."""
    zone, basis = dominant_zone_by_area(_rows([("일반상업지역", 1200.0),
                                               ("제2종일반주거지역", 800.0)]))
    assert zone == SS.MIXED_REVIEW_SENTINEL, f"임의 단일화했다 — {zone!r}"
    assert basis == SS.ZONE_BASIS_MIXED_REVIEW
    # ★센티널 값을 **리터럴로 못 박는다** — 생태계(백엔드 6곳·프론트·withheld 어휘)가 이 문자열을 안다.
    assert SS.MIXED_REVIEW_SENTINEL == "mixed_review_required"


def test_sentinel_does_not_become_impossible_downstream():
    """★센티널이 «불가» 로 번역되면 안 된다 — 보류는 거부가 아니다.

    실측(2026-09-04): 단일화(일반상업) ↔ 센티널에서 **판정이 달라진 방식 0종 · 불가 집합 동일**.
    """
    sim = DevelopmentScenarioSimulator()

    def _run(z):
        return {x["scheme"]: x["applicable"] for x in sim._scenarios(_ctx(z))}

    a, b = _run("일반상업지역"), _run(SS.MIXED_REVIEW_SENTINEL)
    ba = {k for k, v in a.items() if v == "불가"}
    bb = {k for k, v in b.items() if v == "불가"}
    assert ba, "대조군이 비었다 — 불가가 0건이면 아래가 공허하다"
    assert ba == bb, f"센티널이 판정을 바꿨다 — 추가불가 {sorted(bb - ba)} / 해제 {sorted(ba - bb)}"
    # 대신 허용용도는 **정직한 보류**로 떨어져야 한다.
    bt = next(x for x in sim._scenarios(_ctx(SS.MIXED_REVIEW_SENTINEL))
              if x["scheme"] == "단순 건축")["buildable_types"]
    assert any("확인 필요" in t for t in bt), f"보류가 표면에 없다 — {bt}"


def _ctx(zone):
    return {
        "total_area_sqm": 12000.0, "primary_zone": zone,
        "zones": ["일반상업지역", "제2종일반주거지역"],
        "far_effective_blended": 200, "far_legal_blended": 250, "multi": True,
        "near_station": {"name": "t", "distance_m": 200}, "near_station_m": 200,
        "region": "서울특별시", "integration_feasible": True,
        "adjacency": {"contiguous": True, "components": 1, "note": "단일 필지",
                      "max_pair_distance_m_min": 10.0},
        "buildings": {"old_ratio": 0.8, "total_units": 200},
        "block_aging": {"old_ratio": 0.75, "meets_2_3": True, "total_units": 300,
                        "radius_m": 100, "buildings_found": 50},
        "apartment_restricted_zones": [],
    }


# ── ② 감사기가 이 경로에서 **실제로 돈다** ────────────────────────────────

def test_scenarios_path_is_inside_the_audit_net():
    """★배선 — `simulate()` 가 감사기를 호출하고 결과를 응답에 싣는가.

    소스 문자열이 아니라 **AST** 로 본다(주석·독스트링에 뚫리지 않게).
    """
    import ast
    import inspect
    import pathlib

    src = pathlib.Path(inspect.getsourcefile(SS)).read_text(encoding="utf-8")
    called = {
        n.func.attr
        for n in ast.walk(ast.parse(src))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    }
    assert "audit" in called, "`premise_audit.audit(` 호출이 없다 — 이 경로는 감시망 밖이다"
    # 응답에 실리는가(딕트 키를 AST 로)
    keys = {k.value for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Dict)
            for k in n.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    assert "premise_audit" in keys, "감사 결과를 응답에 싣지 않는다(만들어 놓고 버린다)"


def test_the_auditor_catches_the_rc2_defect():
    """★★결정적 — 그 감사기가 `#940` 의 RC-2 를 **실제로 잡는가**. 두 모집단.

    신고 부지 형상(zones=[제1종, 제2종] · 제2종 면적 우세)에서
      · `dominant_zone=제1종`(종전 RC-2 동작) → **위반**
      · `dominant_zone=제2종`(수정 후)        → **침묵**
    """
    zone_mix = [{"zone": "제2종일반주거지역", "area_sqm": 1300.0},
                {"zone": "제1종일반주거지역", "area_sqm": 410.0}]
    per_parcel = [{"zone": "제1종일반주거지역", "area_sqm": 410.0},
                  {"zone": "제2종일반주거지역", "area_sqm": 1300.0}]

    def _audit(dom):
        r = premise_audit.audit({
            "dominant_zone": dom, "zone_mix": zone_mix, "per_parcel": per_parcel,
            "integrated": {"total_area_sqm": 1710.0}, "scenario": {"top3": []},
            "_request_parcel_count": 2,
        })
        return {v.get("relation") or v.get("key") for v in (r.get("violations") or [])}

    broken = _audit("제1종일반주거지역")
    healed = _audit("제2종일반주거지역")
    assert "dominant_argmax" in broken, f"RC-2 를 못 잡는다 — {broken}"
    assert "dominant_argmax" not in healed, f"수정 후에도 발화한다(위양성) — {healed}"


def test_zone_mix_helper_matches_sibling_shape():
    """`zone_mix` 는 감사기가 읽는 두 키를 내고 **면적 내림차순**이어야 한다."""
    zm = SS._zone_mix_from([
        {"zone": "제1종일반주거지역", "area": 410.0},
        {"zone": "제2종일반주거지역", "area": 1300.0},
        {"zone": "제1종일반주거지역", "area": 90.0},   # 같은 zone 합산 확인
    ])
    assert [z["zone"] for z in zm] == ["제2종일반주거지역", "제1종일반주거지역"], zm
    assert zm[1]["area_sqm"] == 500.0, f"같은 용도지역이 합산되지 않았다 — {zm}"
    # ★결측은 지어내지 않고 **버린다**(0 으로 채우면 area_conservation 이 거짓 위반을 낸다)
    assert SS._zone_mix_from([{"zone": None, "area": 10.0}, {"zone": "A", "area": None}]) == []
