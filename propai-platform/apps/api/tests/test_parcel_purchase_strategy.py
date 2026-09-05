"""토지필지 종합분석 **P2 — 매입전략 분류** 회귀망.

★규율(이 저장소가 반복해서 데인 것):
  1. **조립된 응답 표면을 태운다.** `build_strategy()` 반환 dict(rows→필드)와 실제 엔드포인트를
     본다. 헬퍼(`_judge_owner` 등)만 검사하면 조립부에서 배선을 끊는 변이가 생존한다 —
     실제로 P1 에서 그 변이가 살아남았다(CLAUDE.md 회귀망 규율 A-4).
  2. **픽스처가 두 모집단을 가른다.** 필드가 두 집합의 차를 말하면 그 둘이 실제로 **다른 값**을
     내야 한다(차가 0인 픽스처는 잠금이 아니다). 이 파일은 세 쌍을 강제한다 —
     주택법 계열 vs 동의율 계열 · 형상 확보 vs 미확보 · 피상속인 확인 vs 미확인.
  3. **"위반 0" 단언 앞에 개수 하한을 둔다.** 대상이 0개라 참이 되는 공허한 초록을 막는다.
  4. **대역이 아니라 계약 상수에 `==` 로 결속한다.**

★★이 파일의 핵심 회귀 케이스는 **4필지 고리(ring)** 다. 원래 설계는 "articulation point 면
  제척 불가, 아니면 제척 가능"이었는데, 안마당을 둘러싼 4필지에서는 `articulation_points` 가
  **빈 배열**인데도 LEFT+RIGHT 를 함께 빼면 부지가 **2조각**이 된다(실행 확인).
  4-사이클은 절단점 0개지만 크기 2의 **절단 집합**을 갖는다 — 필지별 소속 판정이 원리적으로
  틀렸다는 반증이며, 이 테스트가 그 설계로의 회귀를 막는다.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.services.registry.registry_analysis_service as ras
from app.services.land_intelligence import parcel_purchase_strategy_service as ps
from app.services.land_intelligence import parcel_rights_survey_service as prs
from app.services.zoning.parcel_graph import build_parcel_graph
from apps.api.app.utils.withheld import NOT_APPLICABLE

# 사업방식 — 두 모집단(보유기간 요건 있음/없음)을 가르는 축.
HOUSING_SCHEME = "지구단위계획 연계"          # 주택법 §22 — 보유기간 10년 요건 있음
CONSENT_SCHEME = "재개발·재건축(정비사업)"      # 도정법 §64 — 동의율 기준(보유기간 무관·트랙 모호성 없음)
EXPROPRIATION_SCHEME = "도시개발사업(도시개발법)"  # 도시개발법 §22 — 매도청구가 아니라 수용
# ★소규모정비특례법 §35 **본문 단서**(「§35의2 에 따라 수용·사용할 수 있는 경우는 제외」)로
#   시행자 유형·관리지역 여부에 따라 매도청구/수용이 갈리는 방식. `scheme` 만으로 갈리지 않는다.
TRACK_SCHEME = "가로주택정비사업"

# 행에 **숫자로** 들어와도 되는 필드의 전수. 시가·보상액이 숫자로 새면 이 집합을 벗어난다.
# ★목록형이 아니라 **파생형**이다 — 새 숫자 필드가 생기면 자동으로 이 가드에 걸린다.
ALLOWED_NUMERIC_ROW_KEYS = {"area_sqm", "holding_period_years"}


# ── 픽스처 ────────────────────────────────────────────────────────────────

def _poly(coords: list[list[float]]) -> dict[str, Any]:
    return {"type": "Polygon", "coordinates": [coords]}


def _ring_parcels() -> list[dict[str, Any]]:
    """안마당을 둘러싼 4필지 고리 + 형상 미확보 1필지.

    BOTTOM [0,3]×[0,1] · RIGHT [2,3]×[1,3] · TOP [0,3]×[3,4] · LEFT [0,1]×[1,3].
    LEFT 와 RIGHT 는 서로 닿지 않는다(x 1~2 간극) → 고리가 성립한다.
    """
    return [
        {"pnu": "BOTTOM", "geometry": _poly([[0, 0], [3, 0], [3, 1], [0, 1], [0, 0]]), "area_sqm": 300},
        {"pnu": "RIGHT", "geometry": _poly([[2, 1], [3, 1], [3, 3], [2, 3], [2, 1]]), "area_sqm": 200},
        {"pnu": "TOP", "geometry": _poly([[0, 3], [3, 3], [3, 4], [0, 4], [0, 3]]), "area_sqm": 300},
        {"pnu": "LEFT", "geometry": _poly([[0, 1], [1, 1], [1, 3], [0, 3], [0, 1]]), "area_sqm": 200},
        {"pnu": "NOGEOM", "area_sqm": 100},  # 형상 미확보 — 판정 불가 모집단
    ]


def _owner(name: str, share: str, acq_date: str | None, acq_cause: str | None) -> dict[str, Any]:
    return {
        "name": name, "share": share,
        "acquisition_date": acq_date, "acquisition_cause": acq_cause,
    }


def _ok_analysis(owners: list[dict[str, Any]], history: list[dict] | None = None) -> dict[str, Any]:
    ownership: dict[str, Any] = {
        "current_owner": ", ".join(o["name"] for o in owners),
        "owners": owners,
    }
    if history is not None:
        ownership["ownership_history"] = history
    return {
        "status": "ok", "origin": "hyphen", "land": {"pnu": "1111010100100010000"},
        "ai": {
            "generated": True, "ownership": ownership,
            "provisional_registration": {"exists": False},
            "seizure": [], "mortgage": [], "other_rights": [],
            "baseline_right": "해당 없음", "acquired_extinguished": "기재 없음",
            "right_to_demand_sale": {"possible": "판단보류", "reason": "테스트 픽스처"},
            "rights_analysis": "테스트 픽스처.", "risks": [],
            "safety_grade": "안전", "summary": "테스트 요약",
        },
    }


def _install_fake_registry(monkeypatch: pytest.MonkeyPatch, by_address: dict[str, Any]) -> None:
    class _Svc:
        async def analyze(self, **kw: Any) -> dict[str, Any]:
            result = by_address.get(kw.get("address"))
            if result is None:
                raise KeyError(f"픽스처에 없는 주소: {kw.get('address')}")
            if isinstance(result, Exception):
                raise result
            return result

    monkeypatch.setattr(ras, "RegistryAnalysisService", _Svc)


# ══ 1) ★★ring 반증 — 제척은 집합 판정이다 ══════════════════════════════

def test_고리형_4필지는_절단점이_없어도_두_필지를_빼면_분단된다() -> None:
    """★★원 설계("articulation 이 아니면 제척 가능")를 **원리적으로 무효화**한 반증.

    4-사이클은 절단점이 **0개**지만 크기 2의 절단 집합을 갖는다. 각자 '안전'해 보이는
    LEFT·RIGHT 를 함께 빼면 BOTTOM 과 TOP 이 갈라진다.
    """
    graph = build_parcel_graph(_ring_parcels())

    # ── 공허 진리 가드: 전제(고리가 실제로 성립)가 먼저 참이어야 아래 단언이 의미를 갖는다.
    assert graph["status"] == "ok"
    assert len(graph["adjacency"]) == 4, "형상 확보 필지가 4개가 아니다 — 고리 픽스처가 깨졌다"
    assert graph["component_count"] == 1, "고리가 하나로 이어져 있지 않다"
    assert len(graph["edges"]) == 4, f"고리는 간선 4개여야 한다: {graph['edges']}"

    # ★반증의 핵심: 절단점이 **없다**.
    assert graph["articulation_points"] == [], (
        "고리에 절단점이 잡혔다 — 이 픽스처는 반증 역할을 못 한다"
    )

    # 그런데 두 필지를 **함께** 빼면 분단된다.
    out = ps.severability(graph, ["LEFT", "RIGHT"])
    assert out["severable"] is False, f"집합 절단을 놓쳤다(개별 판정으로 회귀했다): {out}"
    assert out["topology_severable"] is False
    assert out["component_count_before"] == 1
    assert out["component_count_after"] == 2, (
        f"분단 개수를 세지 않았다 — 집합 제거 후 재계산이 실제로 돌지 않았을 수 있다: {out}"
    )


def test_개별로는_빼도_되는_필지가_집합으로는_안_된다() -> None:
    """★대조군 — 위 테스트가 '항상 False'인 결함이 아님을 확인한다.
    LEFT 하나만 빼면 나머지 3필지는 여전히 한 덩어리다(차가 0이면 잠금이 아니다)."""
    graph = build_parcel_graph(_ring_parcels())
    single = ps.severability(graph, ["LEFT"])
    pair = ps.severability(graph, ["LEFT", "RIGHT"])

    assert single["severable"] is True
    assert single["component_count_after"] == 1
    assert single["severable"] != pair["severable"], (
        "단일 제외와 집합 제외가 같은 결과다 — 집합 판정이 아니라 필지별 판정으로 퇴화했다"
    )


def test_형상_미확보_필지는_가능이_아니라_판정_불가다() -> None:
    """★두 모집단을 가른다 — 형상 확보 필지(가능)와 미확보 필지(판정 불가)는
    **다른 버킷**에 떨어져야 한다. 미확보를 '가능'으로 접으면 없는 근거로 제척을 권고한다."""
    graph = build_parcel_graph(_ring_parcels())
    assert graph["geometry_unknown_pnus"] == ["NOGEOM"], "형상 미확보 모집단이 비었다"

    known = ps.severability(graph, ["LEFT"])       # 형상 확보 · 비-절단점
    unknown = ps.severability(graph, ["NOGEOM"])   # 형상 미확보

    assert known["severable"] is True
    assert unknown["severable"] is None, f"형상 미확보를 확정 판정했다: {unknown}"
    assert unknown["undecidable_pnus"] == ["NOGEOM"]
    assert known["severable"] != unknown["severable"], "두 모집단이 같은 값을 낸다"


@pytest.mark.parametrize(
    "graph",
    [
        None,
        {"status": "skipped_large_set", "parcel_count": 500, "note": "…"},  # ★articulation_points 키 자체가 없다
        {"status": "empty", "parcel_count": 0},
        {"status": "duplicate_parcel_id"},
    ],
)
def test_그래프_전제가_깨지면_다른_키를_읽기_전에_거부한다(graph: Any) -> None:
    """★`skipped_large_set` 응답에는 `articulation_points` 키가 **아예 없다**.
    다른 키를 먼저 읽으면 KeyError 로 죽거나 None 을 '없음'으로 오독한다."""
    out = ps.severability(graph, ["A", "B"])
    assert out["severable"] is None
    assert out["reason"], "거부 사유가 비어 있다 — 조용히 비운 것과 같다"
    # ★status 게이트가 **가장 먼저** 걸렸음을 사유로 확인한다 — 뒤에서 걸리면 사유가
    #   "형상 확보 필지가 0개"처럼 엉뚱해져, 왜 판정을 못 했는지 오독하게 된다.
    if isinstance(graph, dict):
        assert str(graph["status"]) in out["reason"], out["reason"]


def test_이미_분리된_집합이나_단일_필지는_판정하지_않는다() -> None:
    """★'유일 필지 제외'를 '가능'이라 하면 사업 자체가 사라지는 제안이 초록으로 나간다."""
    single = build_parcel_graph([
        {"pnu": "ONLY", "geometry": _poly([[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]), "area_sqm": 100},
    ])
    assert single["component_count"] == 1
    assert ps.severability(single, ["ONLY"])["severable"] is None

    split = build_parcel_graph([
        {"pnu": "A", "geometry": _poly([[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]), "area_sqm": 100},
        {"pnu": "B", "geometry": _poly([[9, 9], [10, 9], [10, 10], [9, 10], [9, 9]]), "area_sqm": 100},
    ])
    assert split["component_count"] == 2, "대조 픽스처가 실제로 분리돼 있지 않다"
    assert ps.severability(split, ["A"])["severable"] is None


def test_제척_가능이라는_말을_쓰지_않고_절차를_항상_붙인다() -> None:
    """★위상은 구역 지정요건(면적·접도율·노후도)을 증명하지 못한다.
    '제척 가능'이라 단정하면 사용자가 그 문장으로 구역계를 바꾼다."""
    graph = build_parcel_graph(_ring_parcels())
    outs = [ps.severability(graph, e) for e in (["LEFT"], ["LEFT", "RIGHT"], ["NOGEOM"])]
    assert len(outs) == 3  # ★개수 하한 — 대상 0개로 참이 되는 것을 막는다

    for out in outs:
        assert out["procedure_required"] == ps.PROCEDURE_REQUIRED
        blob = " ".join(str(v) for v in out.values())
        assert "제척 가능" not in blob, f"위상 판정이 제척 가능을 단정했다: {out['reason']}"


# ══ 2) ★실제 build_parcel_graph 계약 ═════════════════════════════════════

def test_실제_그래프_모듈은_articulation_points_키를_낸다() -> None:
    """★기존 백엔드 테스트 하나가 `{"articulation": [...], "components": 1}` 이라는
    **실제 모듈이 절대 내지 않는 키**로 스텁을 심었다. 스텁이 계약에서 갈라지면 그 테스트는
    아무것도 잠그지 않는다 — 여기서는 **진짜** 모듈을 태워 키 이름을 못박는다."""
    graph = build_parcel_graph(_ring_parcels())
    assert "articulation_points" in graph, "실제 모듈의 키 이름이 바뀌었다"
    assert "articulation" not in graph, "스텁이 쓰던 가공의 키가 실제 모듈에 생겼다"
    assert "component_count" in graph and "components" not in graph
    assert "n_minus_1" in graph and "adjacency" in graph


# ══ 3) 확보율 — 모르면 숫자를 내지 않는다 ════════════════════════════════

def _secured_parcel(pnu: str, area: float | None, secured: bool, share: str = "전부") -> dict[str, Any]:
    row: dict[str, Any] = {
        "pnu": pnu,
        "use_right_secured": secured,
        "owners": [{"name": f"{pnu}소유자", "share": share, "use_right_secured": secured}],
    }
    if area is not None:
        row["area_sqm"] = area
    return row


def test_면적_미상이_하나라도_있으면_확보율을_내지_않는다() -> None:
    """★★실증된 결함: 아는 면적만 합하면 **실제 64% 부지가 100% 로 보고**되어 95% 게이트를
    통과했다(`_area_sqm` 은 미상에 0 이 아니라 None 을 낸다)."""
    rows = [_secured_parcel("확보", 6400, True), _secured_parcel("미상", None, False)]
    out = ps.secured_ratio(rows, 10000)

    assert out["status"] == ps.STATUS_UNDECIDABLE
    assert "secured_ratio_pct" not in out, f"거부해 놓고 숫자를 냈다: {out}"
    assert out["missing_area_pnus"] == ["미상"]


def test_면적이_다_있으면_실제_비율을_낸다() -> None:
    """★대조군 — 위 테스트가 '항상 판정 불가'가 아님을 확인하고, 64% 가 100% 로 부풀지
    않았음을 **값으로** 잠근다(차가 0이면 잠금이 아니다)."""
    rows = [_secured_parcel("확보", 6400, True), _secured_parcel("미확보", 3600, False)]
    out = ps.secured_ratio(rows, 10000)

    assert out["status"] == ps.STATUS_OK
    assert out["secured_ratio_pct"] == 64.0, f"확보율이 부풀었다: {out}"
    assert out["meets_threshold"] is False
    assert out["threshold_pct"] == ps.SECURED_RATIO_THRESHOLD_PCT


def test_분모_미입력이면_행_합계로_대체하지_않는다() -> None:
    """★사용자는 보통 **미확보 필지만** 등록한다 — 행 합계를 분모로 쓰면 0%/100% 가 나온다."""
    rows = [_secured_parcel("미확보1", 3000, False), _secured_parcel("미확보2", 2000, False)]
    out = ps.secured_ratio(rows, None)
    assert out["status"] == ps.STATUS_UNDECIDABLE
    assert "secured_ratio_pct" not in out
    assert "주택건설대지면적" in out["reason"]


def test_확보_소유자의_지분을_못_읽으면_거부한다() -> None:
    """★인식 못 한 지분을 1.0 으로 접으면 미확보 지분이 확보로 둔갑한다."""
    rows = [_secured_parcel("확보", 6400, True, share="기재 없음")]
    out = ps.secured_ratio(rows, 10000)
    assert out["status"] == ps.STATUS_UNDECIDABLE
    assert out["unparsed_share_pnus"] == ["확보"]
    assert "secured_ratio_pct" not in out


@pytest.mark.parametrize(
    "share,expected",
    [
        ("1/2", 50.0),
        ("1388분의 1387.08", 99.9337),    # ★A분의B = B/A (1387.08/1388, 순서 주의)
        ("99.934%", 99.934),
        ("전부", 100.0),
        ("단독", 100.0),
    ],
)
def test_지분_표기별_확보율이_조립_표면에서_그대로_나온다(share: str, expected: float) -> None:
    """★헬퍼가 아니라 `secured_ratio()` 표면으로 태운다 — 파서만 맞고 조립부에서
    지분을 무시하는 변이가 생존하지 않도록."""
    out = ps.secured_ratio([_secured_parcel("P", 1000, True, share=share)], 1000)
    assert out["status"] == ps.STATUS_OK
    assert round(out["secured_ratio_pct"], 3) == round(expected, 3), out


def test_분의_표기의_분자분모_순서를_뒤집지_않는다() -> None:
    """★"1388분의 1387.08" 을 1388/1387.08 로 읽으면 1 을 넘는다 — 그 오류는
    `_share_ratio` 가 None 을 내며 **거부**로 드러나야지, 조용히 1.0 이 되면 안 된다."""
    assert ps._share_ratio("1388분의 1387.08") == pytest.approx(1387.08 / 1388)
    assert ps._share_ratio("1387.08분의 1388") is None, "1을 넘는 지분을 받아들였다"
    assert ps._share_ratio("알 수 없는 표기") is None
    assert ps._share_ratio(None) is None


# ══ 4) 95% 도달 최소 **건수** 조합 ═══════════════════════════════════════

def _cand(pnu: str, area: float | None) -> dict[str, Any]:
    row: dict[str, Any] = {"pnu": pnu}
    if area is not None:
        row["area_sqm"] = area
    return row


def test_최소_건수_조합은_면적_상위부터_고른다() -> None:
    """★목적함수는 **하나**(최소 건수)다. 정확성 근거를 매 결과가 실어 나른다.

    ★픽스처 정합(2026-08-15): 종전 픽스처는 확보 6400 + 후보 5500 = 11,900㎡ 로 대지
      10,000㎡ 를 넘는 **모순 입력**이었다(그래서 결과가 114% 였는데 아무도 안 봤다).
      100% 초과 가드를 넣으면서 합이 대지를 넘지 않도록 고쳤다.
    """
    out = ps.min_count_combination(
        [_cand("A", 3000), _cand("B", 500), _cand("C", 100)],
        housing_site_area_sqm=10000,
        current_secured_sqm=6400,   # 목표 9500 → 부족분 3100
    )
    assert out["status"] == ps.STATUS_OK
    assert out["combination_pnus"] == ["A", "B"], f"최소 건수 조합이 아니다: {out}"
    assert out["count"] == 2
    assert out["optimality"] == ps.OPTIMALITY_MIN_COUNT
    assert out["resulting_ratio_pct"] >= ps.SECURED_RATIO_THRESHOLD_PCT
    assert out["resulting_ratio_pct"] <= 100.0, (
        f"확보율이 100% 를 넘었다 — 불가능한 숫자다: {out['resulting_ratio_pct']}"
    )


def test_전부_확보해도_모자라면_빈_배열이_아니라_달성_불가를_낸다() -> None:
    """★빈 배열은 '쉽다'로 오독된다 — 사업 성립 자체가 걸린 신호를 침묵시키면 안 된다."""
    out = ps.min_count_combination(
        [_cand("A", 500), _cand("B", 300)],
        housing_site_area_sqm=10000, current_secured_sqm=6400,
    )
    assert out["status"] == ps.STATUS_UNREACHABLE
    assert out["combination_pnus"] is None, "달성 불가인데 조합을 냈다"
    assert out["optimality"] == ps.OPTIMALITY_MIN_COUNT


def test_면적_미상_후보가_있으면_조합을_내지_않는다() -> None:
    out = ps.min_count_combination(
        [_cand("A", 3000), _cand("B", None)],
        housing_site_area_sqm=10000, current_secured_sqm=6400,
    )
    assert out["status"] == ps.STATUS_UNDECIDABLE
    assert out["combination_pnus"] is None
    assert out["missing_area_pnus"] == ["B"]


def test_이미_충족이면_추가_확보를_요구하지_않는다() -> None:
    out = ps.min_count_combination(
        [_cand("A", 3000)], housing_site_area_sqm=10000, current_secured_sqm=9600
    )
    assert out["status"] == ps.STATUS_ALREADY_MET
    assert out["combination_pnus"] == []
    assert out["count"] == 0
    assert out["needed_area_sqm"] == 0.0, "이미 충족인데 부족분이 남아 있다"


def test_모든_결과가_최적성_근거와_비용_미산출_사실을_싣는다() -> None:
    """★단가 데이터가 저장소에 없다 — '최소 비용'을 흉내 내면 그 숫자가 매입 결정에 쓰인다."""
    outs = [
        ps.min_count_combination([_cand("A", 3000), _cand("B", 500)], 10000, 6400),
        ps.min_count_combination([_cand("A", 100)], 10000, 6400),
        ps.min_count_combination([_cand("A", None)], 10000, 6400),
        ps.min_count_combination([_cand("A", 100)], None, None),
        ps.min_count_combination([_cand("A", 100)], 10000, 9600),
    ]
    assert len(outs) == 5  # ★개수 하한
    for out in outs:
        assert out["optimality"] == ps.OPTIMALITY_MIN_COUNT, out
        assert out["price_basis"] == ps.PRICE_BASIS
        assert "단가" in out["cost_note"]


# ══ 4-b) ★★이중계상 — 이미 확보한 면적을 후보 기여분에서 빼야 한다 ═════════
# ★2026-08-15 실증: `secured_ratio` 의 분자는 **소유자 지분 단위**로 확보분을 셌는데
#   후보 필터는 **필지 단위 플래그**만 봤다. 소유자 단위로만 확보된 필지가 **전체 면적**으로
#   후보에 들어가 확보분이 두 번 세어졌고, 사용자가 **이미 100% 보유한 필지를 사라**고
#   권고하면서 `resulting_ratio_pct = 160.0` 이라는 불가능한 숫자가 나왔다.
#   ★기존 `_cand` 픽스처(`{pnu, area_sqm}` 뿐)는 소유자도 플래그도 없어 두 모집단을 가르지
#     못했다 — 아래 세 픽스처가 그 구멍을 메운다.

def _fully_unsecured(pnu: str, area: float) -> dict[str, Any]:
    """(a) 전량 미확보 — 기여분 = 면적 전부."""
    return {"pnu": pnu, "area_sqm": area, "use_right_secured": False,
            "owners": [{"name": "남", "share": "전부", "use_right_secured": False}]}


def _partly_secured(pnu: str, area: float) -> dict[str, Any]:
    """(b) **부분 확보**(90%) — 기여분 = 면적의 10% 뿐이다."""
    return {"pnu": pnu, "area_sqm": area, "owners": [
        {"name": "우리", "share": "90%", "use_right_secured": True},
        {"name": "남", "share": "10%", "use_right_secured": False},
    ]}


def _owner_level_secured(pnu: str, area: float) -> dict[str, Any]:
    """(c) 전량 확보인데 **필지 단위 플래그가 없다**(소유자 단위로만 확보).

    ★이 모집단이 결함의 진원지다 — 종전 필터 `use_right_secured is not True` 는 필지 키가
      아예 없는 이 행을 **미확보 후보**로 통과시켰다.
    """
    return {"pnu": pnu, "area_sqm": area,
            "owners": [{"name": "우리", "share": "전부", "use_right_secured": True}]}


def test_세_모집단의_후보_기여분이_실제로_다르다() -> None:
    """★★확보 상태 세 모집단이 **다른 기여분**을 내야 한다(차가 0이면 잠금이 아니다).

    대지 10,000㎡ · 확보 9,400㎡ → 부족분 100㎡.
    ★(b) 와 (c) 는 **면적이 1,000㎡ 로 같다** — 그래서 둘의 차이는 오직 '이미 확보된 지분'
      에서만 나온다(면적으로는 구별되지 않는다는 것이 요점이다).
    """
    unsecured = ps.min_count_combination([_fully_unsecured("A", 500)], 10000, 9400)
    partial = ps.min_count_combination([_partly_secured("B", 1000)], 10000, 9400)
    secured = ps.min_count_combination([_owner_level_secured("C", 1000)], 10000, 9400)

    # (a) 전량 미확보 → 면적 전부(500㎡)가 기여분
    assert unsecured["status"] == ps.STATUS_OK
    assert unsecured["combination_pnus"] == ["A"]
    assert unsecured["added_area_sqm"] == 500.0
    assert unsecured["already_secured_pnus"] == []

    # (b) 90% 확보 → 기여분은 **100㎡ 뿐**(원면적 1,000 이 아니다)
    assert partial["status"] == ps.STATUS_OK
    assert partial["combination_pnus"] == ["B"]
    assert partial["added_area_sqm"] == 100.0, (
        f"부분 확보 필지를 **원면적**으로 셌다(이중계상): {partial}"
    )
    assert partial["already_secured_pnus"] == []

    # (c) 전량 확보(소유자 단위만) → 후보가 아니다. 살 것이 없으니 부족분을 못 메운다.
    assert secured["status"] == ps.STATUS_UNREACHABLE, (
        f"이미 100% 보유한 필지를 매입 후보로 셌다: {secured}"
    )
    assert secured["combination_pnus"] is None
    assert secured["already_secured_pnus"] == ["C"], secured

    # ★면적이 같은 (b)·(c) 가 실제로 다른 결과를 낸다 — 확보 지분이 결과를 가른다.
    assert partial["added_area_sqm"] != secured.get("added_area_sqm")
    assert len({unsecured["status"], partial["status"], secured["status"]}) == 2

    # ★셋을 **함께** 넣어도 같다: 기여분 상위(A 500)가 부족분 100 을 먼저 넘긴다.
    together = ps.min_count_combination(
        [_fully_unsecured("A", 500), _partly_secured("B", 1000), _owner_level_secured("C", 1000)],
        10000, 9400,
    )
    assert together["status"] == ps.STATUS_OK
    assert together["combination_pnus"] == ["A"], together
    assert together["already_secured_pnus"] == ["C"]


def test_이미_확보한_필지를_사라고_권고하지_않는다() -> None:
    """★★재현된 결함 그대로 — 소유자 단위로만 확보된 8,000㎡ 가 **전체 면적**으로 후보에
    들어가면, 이미 100% 보유한 필지가 1순위 추천이 되고 확보율이 **160%** 로 찍혔다."""
    parcels = [_owner_level_secured("이미확보8000", 8000), _fully_unsecured("진짜필요2000", 2000)]

    ratio = ps.secured_ratio(parcels, 10000)
    assert ratio["secured_ratio_pct"] == 80.0  # ★전제(분자는 처음부터 옳았다)
    assert ratio["secured_area_sqm"] == 8000.0

    out = ps.min_count_combination(parcels, 10000, ratio["secured_area_sqm"])
    assert out["status"] == ps.STATUS_OK
    assert out["combination_pnus"] == ["진짜필요2000"], (
        f"이미 확보한 필지를 매입 대상으로 권고했다: {out['combination_pnus']}"
    )
    assert out["already_secured_pnus"] == ["이미확보8000"]
    assert out["resulting_ratio_pct"] == 100.0
    assert out["resulting_ratio_pct"] <= 100.0


def test_확보율_100퍼센트_초과는_숫자로_내지_않고_모순으로_거부한다() -> None:
    """★`secured_ratio` 가 `확보면적 > 대지면적` 을 '모순'으로 거부하는 것과 **같은 규율**이다.
    분자가 분모를 넘을 수 없다 — 넘으면 입력이 틀린 것이지 결과가 아니다."""
    # 확보 6,000 + 후보 기여 6,000 = 12,000 > 대지 10,000 → 모순
    out = ps.min_count_combination([_fully_unsecured("A", 6000)], 10000, 6000)
    assert out["status"] == ps.STATUS_UNDECIDABLE, out
    assert "resulting_ratio_pct" not in out, f"모순인데 숫자를 냈다: {out}"
    assert out["combination_pnus"] is None
    assert "모순" in out["reason"] and "100%" in out["reason"], out["reason"]

    # ★대조군 — 합이 대지를 넘지 않으면 정상 산정된다(차가 0이면 잠금이 아니다).
    ok = ps.min_count_combination([_fully_unsecured("A", 4000)], 10000, 6000)
    assert ok["status"] == ps.STATUS_OK
    assert ok["resulting_ratio_pct"] == 100.0
    assert ok["status"] != out["status"]


def test_최소조합_응답이_어느_경로에서도_계약키를_갖춘다() -> None:
    """★거부 경로에서 키가 빠지면 UI 가 `undefined` 를 그린다(성공 경로만 보면 못 잡는다).

    ★변이 감사 잔존 봉합(2026-08-15): `common` 의 `"already_secured_pnus": []` 초기화를
      지워도 아무 테스트가 몰랐다 — **분모 미입력 조기 반환**은 후보 루프에 닿기 전에
      나가므로 그 경로에서만 키가 사라진다. 전 경로를 파생형으로 태운다.
    ★같은 이유로 전제 가드(`denom <= 0 or secured < 0`)도 함께 잠근다 — 무력화하면 부족분이
      엉뚱한 기준으로 계산돼 근거 없는 조합이 나간다.
    """
    outs = {
        "분모미입력": ps.min_count_combination([_fully_unsecured("A", 100)], None, 0),
        "확보면적미입력": ps.min_count_combination([_fully_unsecured("A", 100)], 10000, None),
        "면적미상": ps.min_count_combination([_cand("A", None)], 10000, 6400),
        "달성불가": ps.min_count_combination([_fully_unsecured("A", 100)], 10000, 6400),
        "이미충족": ps.min_count_combination([_fully_unsecured("A", 100)], 10000, 9600),
        "산정": ps.min_count_combination([_fully_unsecured("A", 4000)], 10000, 6000),
        "모순": ps.min_count_combination([_fully_unsecured("A", 6000)], 10000, 6000),
    }
    assert len(outs) == 7  # ★개수 하한 — 대상이 0개면 아래 루프는 공허하다

    for label, out in outs.items():
        for key in ("already_secured_pnus", "optimality", "price_basis",
                    "threshold_pct", "cost_note", "disclaimer", "status", "reason"):
            assert key in out, f"{label} 응답에 계약키 {key} 가 없다: {sorted(out)}"
        assert isinstance(out["already_secured_pnus"], list), label

    # ★전제 가드가 실제로 거부한다(무력화하면 아래 네 줄이 죽는다).
    assert outs["분모미입력"]["status"] == ps.STATUS_UNDECIDABLE
    assert outs["확보면적미입력"]["status"] == ps.STATUS_UNDECIDABLE
    assert outs["분모미입력"]["combination_pnus"] is None
    assert outs["확보면적미입력"]["combination_pnus"] is None
    # ★대조군 — 둘 다 있으면 산정된다(차가 0이면 잠금이 아니다).
    assert outs["산정"]["status"] == ps.STATUS_OK
    assert outs["산정"]["status"] != outs["분모미입력"]["status"]


@pytest.mark.asyncio
async def test_조립부가_확보분을_후보에서_빼고_넘긴다(monkeypatch: pytest.MonkeyPatch) -> None:
    """★★배선 락 — `build_strategy` 가 후보를 **필지 플래그로 거르면** 부분·소유자단위 확보가
    새어 들어온다. 조립 표면에서 이중계상이 없는지 잠근다(순수함수만 고쳐도 여기서 샜다)."""
    owners = [_owner("소유자", "전부", "2005-03-02", "매매")]
    fixtures = {"이미확보8000": _ok_analysis(owners), "진짜필요2000": _ok_analysis(owners)}
    parcels = [_owner_level_secured("이미확보8000", 8000), _fully_unsecured("진짜필요2000", 2000)]
    for p in parcels:
        p["address"] = p["pnu"]

    out = ps.build_strategy(
        await _survey(monkeypatch, fixtures, HOUSING_SCHEME), parcels,
        scheme=HOUSING_SCHEME, housing_site_area_sqm=10000,
    )
    combo = out["min_count_combination"]
    assert out["secured_ratio"]["secured_ratio_pct"] == 80.0
    assert combo["status"] == ps.STATUS_OK, combo
    assert combo["combination_pnus"] == ["진짜필요2000"], (
        f"조립부가 이미 확보한 필지를 후보로 넘겼다: {combo['combination_pnus']}"
    )
    assert combo["already_secured_pnus"] == ["이미확보8000"]
    assert combo["resulting_ratio_pct"] == 100.0


@pytest.mark.asyncio
async def test_필지플래그_필터는_필요한_필지를_빠뜨린다(monkeypatch: pytest.MonkeyPatch) -> None:
    """★★같은 결함의 **반대 방향** — 필지 단위 플래그로 후보를 거르면 부분확보 필지의
    **미확보 잔여 지분**이 후보에서 통째로 사라진다.

    필지 플래그가 `True` 여도 소유자 지분은 60%만 확보된 필지(잔여 40% = 2,000㎡)가 있다.
    종전 필터(`use_right_secured is not True`)는 이 필지를 **빼 버려** 도달 가능한 사업을
    '달성 불가'로 오판했다. 후보 판정을 `_parcel_secured_area` 로 일원화하면 잔여만 들어온다.
    """
    owners = [_owner("소유자", "전부", "2005-03-02", "매매")]
    parcels = [
        {"pnu": "부분확보5000", "address": "부분확보5000", "area_sqm": 5000,
         "use_right_secured": True,   # ★필지 플래그는 True 인데 지분은 60%만 확보다
         "owners": [
             {"name": "우리", "share": "60%", "use_right_secured": True},
             {"name": "남", "share": "40%", "use_right_secured": False},
         ]},
        {"pnu": "미확보5000", "address": "미확보5000", "area_sqm": 5000,
         "use_right_secured": False,
         "owners": [{"name": "남", "share": "전부", "use_right_secured": False}]},
    ]
    fixtures: dict[str, Any] = {str(p["address"]): _ok_analysis(owners) for p in parcels}

    out = ps.build_strategy(
        await _survey(monkeypatch, fixtures, HOUSING_SCHEME), parcels,
        scheme=HOUSING_SCHEME, housing_site_area_sqm=10000,
    )
    assert out["secured_ratio"]["secured_area_sqm"] == 3000.0  # ★전제: 5000×60%

    combo = out["min_count_combination"]
    assert combo["status"] == ps.STATUS_OK, (
        f"도달 가능한데 조합을 내지 못했다 — 후보에서 부분확보 잔여가 빠졌다: {combo}"
    )
    # 부족분 9500−3000 = 6500. 잔여 기여분 5000(미확보) + 2000(부분확보 잔여) = 7000.
    assert combo["needed_area_sqm"] == 6500.0
    assert combo["combination_pnus"] == ["미확보5000", "부분확보5000"], combo
    assert combo["added_area_sqm"] == 7000.0, f"부분확보 잔여 2,000㎡ 가 빠졌다: {combo}"
    assert combo["already_secured_pnus"] == []
    assert combo["resulting_ratio_pct"] == 100.0


# ══ 5) 조립 표면 — build_strategy ════════════════════════════════════════

async def _survey(
    monkeypatch: pytest.MonkeyPatch,
    addresses: dict[str, Any],
    scheme: str | None,
    decision_date: str | None = "2024-01-01",
) -> dict[str, Any]:
    _install_fake_registry(monkeypatch, addresses)
    return await prs.survey_selected_parcels(
        [{"address": a, "pnu": a} for a in addresses],
        district_plan_decision_date=decision_date,
        scheme=scheme,
    )


def _strategy_parcels() -> list[dict[str, Any]]:
    """확보율이 **산정 가능한** 제원(면적·확보여부·지분 전부 존재) — 64%."""
    return [
        {"pnu": "장기필지", "address": "장기필지", "area_sqm": 3600,
         "use_right_secured": False,
         "owners": [{"name": "장기보유자", "share": "전부", "use_right_secured": False}]},
        {"pnu": "확보필지", "address": "확보필지", "area_sqm": 6400,
         "use_right_secured": True,
         "owners": [{"name": "우리", "share": "전부", "use_right_secured": True}]},
    ]


@pytest.mark.asyncio
async def test_같은_필지가_사업방식에_따라_다른_행을_낸다(monkeypatch: pytest.MonkeyPatch) -> None:
    """★★두 모집단을 가른다 — **같은 픽스처**에 사업방식만 바꾼다.
    두 결과가 같다면 `scheme` 은 장식이고, 게이트를 지워도 아무도 모른다."""
    owners = [_owner("장기보유자", "전부", "2005-03-02", "매매")]  # 결정고시일 기준 ~18.8년
    fixtures = {"장기필지": _ok_analysis(owners), "확보필지": _ok_analysis(owners)}
    parcels = _strategy_parcels()

    housing = ps.build_strategy(
        await _survey(monkeypatch, fixtures, HOUSING_SCHEME), parcels,
        scheme=HOUSING_SCHEME, housing_site_area_sqm=10000,
    )
    consent = ps.build_strategy(
        await _survey(monkeypatch, fixtures, CONSENT_SCHEME), parcels,
        scheme=CONSENT_SCHEME, housing_site_area_sqm=10000,
    )
    # ★★세 번째 모집단 — 트랙(시행자 유형·관리지역)이 수단을 뒤집는 방식은 **판정보류**다.
    #   `scheme` 만으로 "매도청구"라 단정하면 §35의2 수용 대상을 잘못 분류한다.
    track = ps.build_strategy(
        await _survey(monkeypatch, fixtures, TRACK_SCHEME), parcels,
        scheme=TRACK_SCHEME, housing_site_area_sqm=10000,
    )

    assert housing["summary"]["row_count"] == 2  # ★개수 하한
    assert consent["summary"]["row_count"] == 2

    h = housing["rows"][0]
    c = consent["rows"][0]

    # ① 판정이 다르다 — 보유기간 요건은 주택법 계열에만 있다.
    assert h["sell_claim_judgment"] == "불가(장기보유 추정)"
    assert c["sell_claim_judgment"] is None
    assert c["sell_claim_judgment_absent"] == NOT_APPLICABLE
    assert h["sell_claim_judgment"] != c["sell_claim_judgment"]

    # ② 액션도 다르다 — 확보율 95% 미만 + 장기보유면 강제수단이 없다(협의매수).
    assert h["action"] == ps.ACTION_NEGOTIATE
    assert c["action"] == ps.ACTION_SELL_CLAIM
    assert h["action"] != c["action"], "사업방식이 액션을 가르지 않는다"

    # ③ 1순위(A) 라벨은 주택법 계열에서만 붙는다.
    assert h["priority_label"] == ps.PRIORITY_A_LABEL
    assert c["priority_label"] is None
    assert housing["summary"]["priority_a_count"] == 2
    assert consent["summary"]["priority_a_count"] == 0

    assert housing["governing_act"] == "주택법"
    assert consent["governing_act"] == "도정법"

    # ④ ★★소규모정비특례법 §35 본문 단서 — 트랙이 수단을 뒤집는 방식은 **판정보류**다.
    #    같은 법령 계열인데도 `scheme` 만으로 갈리지 않는다는 사실을 액션이 반영해야 한다.
    t = track["rows"][0]
    assert track["governing_act"] == "소규모정비특례법"
    assert track["legal"]["requires_track_input"] is True, (
        "트랙 입력 필요 표시가 판정표 표면까지 전달되지 않았다"
    )
    assert t["action"] == ps.ACTION_UNDECIDED, (
        f"§35의2 수용 대상이 될 수 있는 방식을 매도청구로 단정했다: {t['action_reason']}"
    )
    assert "§35의2" in t["action_reason"], t["action_reason"]
    # ★세 모집단이 실제로 **다른 액션**을 낸다(차가 0이면 잠금이 아니다).
    assert len({h["action"], c["action"], t["action"]}) == 3, (
        f"주택법·동의율·트랙모호 세 방식이 같은 액션을 낸다: "
        f"{h['action']}·{c['action']}·{t['action']}"
    )


@pytest.mark.asyncio
async def test_도시개발사업은_수용_액션을_낸다(monkeypatch: pytest.MonkeyPatch) -> None:
    """★액션이 셋뿐이면 이 행을 표현할 수 없다 — 수용은 매도청구와 절차가 다르다."""
    owners = [_owner("소유자", "전부", "2005-03-02", "매매")]
    fixtures = {"장기필지": _ok_analysis(owners), "확보필지": _ok_analysis(owners)}
    out = ps.build_strategy(
        await _survey(monkeypatch, fixtures, EXPROPRIATION_SCHEME), _strategy_parcels(),
        scheme=EXPROPRIATION_SCHEME, housing_site_area_sqm=10000,
    )
    assert out["instrument"] == "수용"
    assert out["summary"]["row_count"] == 2
    assert {r["action"] for r in out["rows"]} == {ps.ACTION_EXPROPRIATION}


@pytest.mark.asyncio
async def test_확보율이_95를_넘으면_장기보유자도_매도청구_대상이_된다(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """★1순위는 정적 목록이 아니라 **확보율의 함수**다 — 95% 를 넘는 순간 지위가 해제된다."""
    owners = [_owner("장기보유자", "전부", "2005-03-02", "매매")]
    fixtures = {"장기필지": _ok_analysis(owners), "확보필지": _ok_analysis(owners)}
    parcels = _strategy_parcels()
    parcels[1]["area_sqm"] = 9600  # 확보 9600 / 10000 = 96%

    out = ps.build_strategy(
        await _survey(monkeypatch, fixtures, HOUSING_SCHEME), parcels,
        scheme=HOUSING_SCHEME, housing_site_area_sqm=10000,
    )
    assert out["secured_ratio"]["meets_threshold"] is True
    assert {r["action"] for r in out["rows"]} == {ps.ACTION_SELL_CLAIM}
    assert out["summary"]["priority_a_count"] == 0, "95% 를 넘겼는데 1순위 지위가 남아 있다"
    # ★매도청구 전 3개월 협의는 **법정 선행요건**이다(전략이 아니다).
    assert all("3개월" in r["prerequisite"] for r in out["rows"])


@pytest.mark.asyncio
async def test_확보율을_모르면_A라벨도_판정보류다(monkeypatch: pytest.MonkeyPatch) -> None:
    """★확보율이 '판정 불가'인데 1순위 라벨을 붙이면, 없는 근거로 매입 우선순위가 결정된다."""
    owners = [_owner("장기보유자", "전부", "2005-03-02", "매매")]
    fixtures = {"장기필지": _ok_analysis(owners), "확보필지": _ok_analysis(owners)}
    parcels = _strategy_parcels()
    del parcels[0]["area_sqm"]  # 면적 미상 → 확보율 판정 불가

    out = ps.build_strategy(
        await _survey(monkeypatch, fixtures, HOUSING_SCHEME), parcels,
        scheme=HOUSING_SCHEME, housing_site_area_sqm=10000,
    )
    assert out["secured_ratio"]["status"] == ps.STATUS_UNDECIDABLE
    assert out["summary"]["row_count"] == 2
    assert out["summary"]["priority_a_count"] == 0
    assert out["summary"]["priority_undecided_count"] == 2
    assert {r["action"] for r in out["rows"]} == {ps.ACTION_UNDECIDED}


@pytest.mark.asyncio
async def test_상속_합산_여부가_행_결과를_가른다(monkeypatch: pytest.MonkeyPatch) -> None:
    """★두 모집단 — 피상속인 **확인**(합산 → 장기보유 → 협의매수) vs **미확인**(단기 → 매도청구).
    두 행이 같은 값을 내면 이력 전달 배선을 끊어도 아무도 모른다."""
    heir = [_owner("김상속", "전부", "2023-01-01", "상속")]
    history = [
        {"date": "2003-01-01", "cause": "매매", "owner": "김부친"},
        {"date": "2023-01-01", "cause": "상속", "owner": "김상속"},
    ]
    fixtures = {
        "합산확인": _ok_analysis(heir, history),
        "합산미확인": _ok_analysis(heir),  # 이력 없음
    }
    parcels = [
        {"pnu": "합산확인", "address": "합산확인", "area_sqm": 1800, "use_right_secured": False,
         "owners": [{"name": "김상속", "share": "전부", "use_right_secured": False}]},
        {"pnu": "합산미확인", "address": "합산미확인", "area_sqm": 1800, "use_right_secured": False,
         "owners": [{"name": "김상속", "share": "전부", "use_right_secured": False}]},
        {"pnu": "확보분", "address": "확보분", "area_sqm": 6400, "use_right_secured": True,
         "owners": [{"name": "우리", "share": "전부", "use_right_secured": True}]},
    ]
    survey = await _survey(monkeypatch, fixtures, HOUSING_SCHEME, decision_date="2026-01-01")
    out = ps.build_strategy(survey, parcels, scheme=HOUSING_SCHEME, housing_site_area_sqm=10000)

    rows = {r["pnu"]: r for r in out["rows"]}
    assert len(rows) == 2  # ★개수 하한(확보분은 등기 조사 대상이 아니다)

    aggregated = rows["합산확인"]
    not_aggregated = rows["합산미확인"]

    assert aggregated["inheritance_aggregated"] is True
    assert not_aggregated["inheritance_aggregated"] is False
    assert aggregated["holding_period_years"] > 20
    assert not_aggregated["holding_period_years"] < 10
    assert aggregated["action"] == ps.ACTION_NEGOTIATE
    assert not_aggregated["action"] == ps.ACTION_SELL_CLAIM
    assert aggregated["action"] != not_aggregated["action"], (
        "상속 합산 여부가 액션을 가르지 않는다 — 이력 전달이 조립 경로에서 끊겼을 수 있다"
    )


@pytest.mark.asyncio
async def test_제척은_집합_판정이_통과할_때만_제안된다(monkeypatch: pytest.MonkeyPatch) -> None:
    """★조립 표면에서도 '집합 판정' 이어야 한다 — 개별 절단점 판정으로 퇴화하면
    LEFT+RIGHT 를 동시에 제척검토로 권고해 부지를 분단시킨다."""
    owners = [_owner("소유자", "전부", "2005-03-02", "매매")]
    ring = _ring_parcels()
    for row in ring:
        row["address"] = row["pnu"]
        row["use_right_secured"] = False
        row["owners"] = [{"name": "소유자", "share": "전부", "use_right_secured": False}]
    fixtures = {r["pnu"]: _ok_analysis(owners) for r in ring}
    graph = build_parcel_graph(ring)
    survey = await _survey(monkeypatch, fixtures, HOUSING_SCHEME)

    single = ps.build_strategy(
        survey, ring, scheme=HOUSING_SCHEME, housing_site_area_sqm=10000,
        graph=graph, exclusion_candidates=["LEFT"],
    )
    pair = ps.build_strategy(
        survey, ring, scheme=HOUSING_SCHEME, housing_site_area_sqm=10000,
        graph=graph, exclusion_candidates=["LEFT", "RIGHT"],
    )

    single_actions = {r["pnu"]: r["action"] for r in single["rows"]}
    pair_actions = {r["pnu"]: r["action"] for r in pair["rows"]}
    assert len(single_actions) == 5  # ★개수 하한(고리 4 + 형상 미확보 1)

    assert single_actions["LEFT"] == ps.ACTION_EXCLUSION_REVIEW
    assert pair_actions["LEFT"] != ps.ACTION_EXCLUSION_REVIEW, (
        "집합으로 빼면 부지가 분단되는데 제척검토를 권고했다"
    )
    assert pair["severability"]["component_count_after"] == 2


@pytest.mark.asyncio
async def test_모든_행이_구조화_면책과_감정평가_표기를_갖는다(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """★면책은 사유 문자열에 파묻지 않는다 — 배지로 렌더돼도 살아남는 **형제 필드**여야 한다.
    ★시가는 **숫자로 내지 않는다**(감정평가 영역)."""
    owners = [_owner("소유자", "전부", "2005-03-02", "매매")]
    fixtures = {"장기필지": _ok_analysis(owners), "확보필지": _ok_analysis(owners)}
    out = ps.build_strategy(
        await _survey(monkeypatch, fixtures, HOUSING_SCHEME), _strategy_parcels(),
        scheme=HOUSING_SCHEME, housing_site_area_sqm=10000,
    )

    rows = out["rows"]
    assert len(rows) >= 2, "★개수 하한 — 대상이 0개면 아래 '위반 0'은 공허하다"

    for row in rows:
        d = row["disclaimer"]
        assert d["advisory"] is False
        assert d["disclaimer"], "면책 문구가 비었다"
        assert d["requires_professional"] == ["법무사", "변호사"]
        assert row["price_basis"] == ps.PRICE_BASIS
        assert row["procedure_required"] == ps.PROCEDURE_REQUIRED

        numeric = {
            k for k, v in row.items()
            if isinstance(v, (int, float)) and not isinstance(v, bool)
        }
        assert numeric <= ALLOWED_NUMERIC_ROW_KEYS, (
            f"허용되지 않은 숫자 필드가 행에 실렸다(시가·보상액 유출 의심): {numeric}"
        )

    # 최상위 산출물도 같은 계약을 따른다.
    for block in (out["secured_ratio"], out["min_count_combination"]):
        assert block["disclaimer"]["advisory"] is False


def test_액션_열거는_다섯이며_계약_상수와_일치한다() -> None:
    """★셋으로는 도시개발 **수용**도, 판정 불가 행도 표현하지 못한다."""
    assert len(ps.ACTIONS) == 5
    assert ps.ACTIONS == (
        ps.ACTION_NEGOTIATE, ps.ACTION_SELL_CLAIM, ps.ACTION_EXPROPRIATION,
        ps.ACTION_EXCLUSION_REVIEW, ps.ACTION_UNDECIDED,
    )
    assert ps.SECURED_RATIO_THRESHOLD_PCT == 95.0
    # ★계약 **문자열 값**을 못박는다. 다른 테스트들은 필드를 상수와 비교하는데(자기참조),
    #   그러면 값 자체는 자유라 문자열 변이가 전부 생존한다 — 값의 잠금은 여기 한 곳이다.
    assert ps.PRICE_BASIS == "시가 = 감정평가 필요"
    assert ps.PROCEDURE_REQUIRED == "구역계 변경 — 주민공람·도시계획위원회 심의"
    assert ps.OPTIMALITY_MIN_COUNT == "exact(k-largest 증명)"
    assert ps.ACTION_UNDECIDED == "판정보류"
    assert ps.PRIORITY_A_LABEL == "A(1순위 핵심관리필지)"


# ══ 6) 엔드포인트 — P1 을 **실제로** 태우는가(소비처 0 봉합) ═══════════════

class _User:
    user_id = "user-1"
    id = "user-1"
    tenant_id = "tenant-1"
    role = "user"


def _client(monkeypatch: pytest.MonkeyPatch, charged: list[str]) -> TestClient:
    import routers.registry as reg
    from apps.api.auth.jwt_handler import get_current_user

    async def _fake_issue(user_id: Any, result: Any, times: int | None = None) -> None:
        if reg.issued_count(result):
            charged.append("issue")

    async def _fake_analysis(user_id: Any, result: Any) -> Any:
        if reg.analysis_charged(result):
            charged.append("analysis")
        return None

    monkeypatch.setattr(reg, "_charge_registry_issue", _fake_issue)
    monkeypatch.setattr(reg, "_charge_registry_analysis", _fake_analysis)

    app = FastAPI()
    app.include_router(reg.router)
    app.dependency_overrides[get_current_user] = lambda: _User()
    return TestClient(app)


def test_엔드포인트가_P1_권리분석을_실제로_태운다(monkeypatch: pytest.MonkeyPatch) -> None:
    """★★이 엔드포인트의 존재 이유 하나가 **'소비처 0' 결함 봉합**이다.
    P1 을 우회하고 자체 판정을 만들면 rows 에 P1 산출 필드(evidence·inheritance·
    holding_period_years)가 사라진다 — 그것으로 우회를 적발한다."""
    charged: list[str] = []
    owners = [_owner("장기보유자", "전부", "2005-03-02", "매매")]
    _install_fake_registry(monkeypatch, {
        "장기필지": _ok_analysis(owners), "확보필지": _ok_analysis(owners),
    })

    with _client(monkeypatch, charged) as client:
        resp = client.post("/registry/survey/strategy", json={
            "parcels": _strategy_parcels(),
            "scheme": HOUSING_SCHEME,
            "district_plan_decision_date": "2024-01-01",
            "housing_site_area_sqm": 10000,
        })

    assert resp.status_code == 200, resp.text
    body = resp.json()

    # ① P1 응답이 그대로 실린다(우회하지 않았다).
    assert body["survey"]["parcel_count"] == 2
    assert body["survey"]["summary"]["parcels_ok"] == 2
    rows = body["strategy"]["rows"]
    assert len(rows) == 2, "★개수 하한 — 행이 0개면 아래 단언이 공허하다"

    for row in rows:
        assert row["evidence"], "P1 의 근거 스니펫이 없다 — P1 을 우회했을 가능성"
        assert row["inheritance"]["status"] == "비상속"
        assert row["holding_period_years"] is not None
        assert row["action"] == ps.ACTION_NEGOTIATE

    # ② 발급·분석은 성공한 건수만 과금된다(P1 이 원본 analysis 를 실어 보낸 덕분).
    assert charged.count("issue") == 2
    assert charged.count("analysis") == 2

    # ③ 확보율·조합·면책이 응답 표면에 있다.
    assert body["strategy"]["secured_ratio"]["secured_ratio_pct"] == 64.0
    assert body["strategy"]["min_count_combination"]["optimality"] == ps.OPTIMALITY_MIN_COUNT
    assert body["strategy"]["action_enum"] == list(ps.ACTIONS)


def test_엔드포인트는_사업방식_없이는_판정하지_않는다(monkeypatch: pytest.MonkeyPatch) -> None:
    """★기본값을 몰래 넣지 않는다 — 방식이 없으면 어느 법령 요건인지 알 수 없다."""
    charged: list[str] = []
    owners = [_owner("장기보유자", "전부", "2005-03-02", "매매")]
    _install_fake_registry(monkeypatch, {
        "장기필지": _ok_analysis(owners), "확보필지": _ok_analysis(owners),
    })

    with _client(monkeypatch, charged) as client:
        resp = client.post("/registry/survey/strategy", json={
            "parcels": _strategy_parcels(),
            "district_plan_decision_date": "2024-01-01",
            "housing_site_area_sqm": 10000,
        })

    assert resp.status_code == 200, resp.text
    rows = resp.json()["strategy"]["rows"]
    assert len(rows) == 2
    assert {r["action"] for r in rows} == {ps.ACTION_UNDECIDED}
    # ★보류값 계약 — 판정 자리엔 **판정만**. 사유는 코드로 온다.
    assert all(r["sell_claim_judgment"] is None for r in rows), (
        "판정 자리에 판정이 아닌 문자열이 들어 있다"
    )
    assert all(r["sell_claim_judgment_absent"] == NOT_APPLICABLE for r in rows)


# ══ 6-b) ★★라우터 배선 락 — 변이 감사에서 41개 중 22개가 생존한 자리 ═══════
# ★2026-08-15 `scripts/mutate_changed.py --only routers/registry.py` 실행에서 아래가 **생존**했다:
#     줄삭제 `graph = build_parcel_graph(parcels)` · `graph=graph,`
#     줄삭제 `exclusion_candidates=req.exclusion_candidates or None,`
#     줄삭제/문자열변경 성장루프 payload 6줄 전부
#   근본은 **어떤 엔드포인트 테스트도 `exclusion_candidates` 를 보내지 않았다**는 것이다
#   (`build_strategy` 가 그 인자에 게이트를 걸어 `severability()` 가 라우터를 통해서는 한 번도
#   실행되지 않았다). 그래서 프로덕션에서 `parcel_graph` 가 던지기 시작하면 :822 의
#   `except` 가 삼키고 **모든 제척 요청이 `severable: null` · `geometry_unknown_count: 0`** 이
#   되어, 성장루프에 "형상 문제 없음"이라는 **거짓 신호**가 무기한 흘러든다.

def _ring_endpoint_parcels(include_nogeom: bool = True) -> list[dict[str, Any]]:
    """엔드포인트로 보낼 고리 픽스처(주소·소유자·확보여부 포함). JSON 직렬화 가능해야 한다."""
    rows = _ring_parcels() if include_nogeom else _ring_parcels()[:4]
    out: list[dict[str, Any]] = []
    for row in rows:
        row = dict(row)
        row["address"] = row["pnu"]
        row["use_right_secured"] = False
        row["owners"] = [{"name": "소유자", "share": "전부", "use_right_secured": False}]
        out.append(row)
    return out


def _post_strategy(
    monkeypatch: pytest.MonkeyPatch,
    parcels: list[dict[str, Any]],
    **body: Any,
) -> dict[str, Any]:
    owners = [_owner("소유자", "전부", "2005-03-02", "매매")]
    _install_fake_registry(monkeypatch, {p["address"]: _ok_analysis(owners) for p in parcels})
    with _client(monkeypatch, []) as client:
        resp = client.post("/registry/survey/strategy", json={"parcels": parcels, **body})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_엔드포인트가_제척_집합_위상판정을_실제로_돌린다(monkeypatch: pytest.MonkeyPatch) -> None:
    """★★`severability()` 를 **라우터를 통해** 태운다(직접 호출이 아니라).

    이 테스트가 죽이는 변이: `graph = build_parcel_graph(parcels)` 줄삭제 ·
    `graph=graph,` 줄삭제 · `exclusion_candidates=req.exclusion_candidates or None,` 줄삭제.
    셋 중 무엇이 끊겨도 `severability` 는 `None` 이 되거나 아예 없어진다.
    """
    parcels = _ring_endpoint_parcels()
    common = {"scheme": HOUSING_SCHEME, "district_plan_decision_date": "2024-01-01",
              "housing_site_area_sqm": 1100}

    pair = _post_strategy(monkeypatch, parcels, exclusion_candidates=["LEFT", "RIGHT"], **common)
    single = _post_strategy(monkeypatch, parcels, exclusion_candidates=["LEFT"], **common)

    sev_pair = pair["strategy"]["severability"]
    sev_single = single["strategy"]["severability"]
    assert sev_pair is not None, "제척 후보를 보냈는데 위상 판정이 응답에 없다(배선 절단)"
    assert sev_single is not None

    # ★★고리 반증이 **엔드포인트를 통해** 재현된다 — LEFT+RIGHT 를 함께 빼면 2조각이다.
    assert sev_pair["component_count_before"] == 1
    assert sev_pair["component_count_after"] == 2, (
        f"집합 제거 후 재계산이 라우터 경로에서 돌지 않았다: {sev_pair}"
    )
    assert sev_pair["severable"] is False

    # ★대조군(두 모집단) — LEFT 하나만 빼면 한 덩어리 그대로다.
    assert sev_single["component_count_after"] == 1
    assert sev_single["severable"] is True
    assert sev_pair["severable"] != sev_single["severable"], "집합 판정이 필지별 판정으로 퇴화했다"

    # 조립 표면까지: 분단되는 집합에는 제척검토를 권고하지 않는다.
    pair_actions = {r["pnu"]: r["action"] for r in pair["strategy"]["rows"]}
    single_actions = {r["pnu"]: r["action"] for r in single["strategy"]["rows"]}
    assert len(pair_actions) == 5  # ★개수 하한
    assert single_actions["LEFT"] == ps.ACTION_EXCLUSION_REVIEW
    assert pair_actions["LEFT"] != ps.ACTION_EXCLUSION_REVIEW


def test_엔드포인트가_형상_미확보_건수를_실제로_센다(monkeypatch: pytest.MonkeyPatch) -> None:
    """★두 모집단 — 형상 미확보 필지가 섞이면 1, 전부 형상이 있으면 0.

    이 값이 항상 0 이면 성장루프는 "형상 문제 없음"으로 읽는다(고칠 우선순위가 사라진다).
    `graph = build_parcel_graph(parcels)` 가 끊기면 여기서 죽는다.
    """
    common = {"scheme": HOUSING_SCHEME, "district_plan_decision_date": "2024-01-01"}
    with_unknown = _post_strategy(
        monkeypatch, _ring_endpoint_parcels(True), housing_site_area_sqm=1100, **common
    )
    all_known = _post_strategy(
        monkeypatch, _ring_endpoint_parcels(False), housing_site_area_sqm=1000, **common
    )

    a = with_unknown["strategy"]["summary"]["geometry_unknown_count"]
    b = all_known["strategy"]["summary"]["geometry_unknown_count"]
    assert a == 1, f"형상 미확보 1건을 세지 못했다: {a}"
    assert b == 0, f"전부 형상이 있는데 미확보로 셌다: {b}"
    assert a != b, "두 모집단이 같은 값을 낸다 — 그래프 배선이 끊겨도 통과한다"


def test_그래프_계산이_던져도_분류는_살고_제척은_판정불가로_남는다(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """★★리뷰가 지목한 **프로덕션 실패 시나리오** 그 자체다.

    `parcel_graph` 가 던지기 시작하면 :841 의 `except` 가 삼킨다. 그때 본기능(분류)은 살아야
    하지만, 제척은 **'가능'이 아니라 '판정 불가'** 여야 하고 형상 미확보 수는 0 이어야 한다.
    ★`graph: ... | None = None` 초기화가 사라지면 여기서 NameError 로 500 이 난다
    (변이 감사 생존 1건을 이 테스트가 죽인다).
    """
    import app.services.zoning.parcel_graph as pg

    def _boom(*_a: Any, **_kw: Any) -> dict[str, Any]:
        raise RuntimeError("shapely 실패(프로덕션 재현)")

    monkeypatch.setattr(pg, "build_parcel_graph", _boom)
    events = _capture_growth(monkeypatch)

    body = _post_strategy(
        monkeypatch, _ring_endpoint_parcels(True),
        scheme=HOUSING_SCHEME, district_plan_decision_date="2024-01-01",
        housing_site_area_sqm=1100, exclusion_candidates=["LEFT", "RIGHT"],
    )

    strategy = body["strategy"]
    assert strategy["summary"]["row_count"] == 5, "그래프 실패가 본기능(분류)까지 죽였다"
    sev = strategy["severability"]
    assert sev["severable"] is None, f"그래프가 없는데 제척을 확정 판정했다: {sev}"
    assert "인접 그래프" in sev["reason"], sev["reason"]
    # ★제척검토를 권고하면 안 된다 — 근거가 없다.
    actions = {r["action"] for r in strategy["rows"]}
    assert ps.ACTION_EXCLUSION_REVIEW not in actions, actions
    # ★성장루프는 계속 돈다(0 이라는 값 자체는 그래프 실패의 결과다 — 위 sev 가 그 사실을 말한다).
    assert len(events) == 1 and events[0][1]["geometry_unknown"] == 0


class _GrowthEvents:
    """실제 적재된 이벤트 큐를 `(event_type, payload)` 로 보여주는 **지연 뷰**.

    큐를 접근 시점에 읽으므로 요청 **전에** 만들어 두고 요청 **후에** 단언하면 된다.
    """

    def __init__(self, queue: Any) -> None:
        self._q = queue

    def _rows(self) -> list[dict[str, Any]]:
        return list(self._q)

    def __len__(self) -> int:
        return len(self._rows())

    def __getitem__(self, i: int) -> tuple[Any, dict[str, Any]]:
        row = self._rows()[i]
        # ★`payload` 를 돌려준다 — 화이트리스트를 **통과해 실제로 저장된** 도메인 필드만 보인다.
        return row.get("event_type"), dict(row.get("payload") or {})

    def __repr__(self) -> str:  # 실패 메시지 가독성
        return repr([(r.get("event_type"), r.get("payload")) for r in self._rows()])


def _capture_growth(monkeypatch: pytest.MonkeyPatch) -> _GrowthEvents:
    """성장루프를 **실제 적재 경로로** 태운다 — `record_event` 를 스텁하지 않는다.

    ★★이전 구현은 `record_event` **자체를** monkeypatch 로 갈아 끼웠다. 그러면 단언이
      "호출부가 넘긴 dict" 를 볼 뿐이라, `record_event` **안에서** 화이트리스트
      (`capture_service._EVENT_COLS`)가 **평면 키를 통째로 버리는** 사실을 원리적으로 볼 수 없다.
      실측: 그 상태에서 도메인 필드 6개가 **전량 소실**되는데도 이 테스트는 초록이었다
      — 단언 6줄이 전부 **공허한 참**이었다(검증이 실제 대상을 태우지 않는 그 형태).
    → 큐를 비우고 **실제 적재된 row 의 `payload`** 를 단언한다. emitter 가 평면 키로 되돌아가는
      변이가 즉시 빨갛게 뜬다.
    ★`monkeypatch` 인자는 호출부 시그니처 호환으로 남긴다(더는 아무것도 패치하지 않는다).
    """
    import app.services.growth.capture_service as cap

    cap._QUEUE.clear()
    return _GrowthEvents(cap._QUEUE)


def test_성장루프_payload가_실제_판정값을_싣는다(monkeypatch: pytest.MonkeyPatch) -> None:
    """★★payload 6줄이 전부 무잠금이었다 — 줄삭제·문자열변경 변이가 모두 생존했다.

    ★식별자(pnu·주소)는 보내지 않는다. 보낼 가치가 있는 것은 **플랫폼이 고쳐야 할 신호**다.
    """
    events = _capture_growth(monkeypatch)
    body = _post_strategy(
        monkeypatch, _ring_endpoint_parcels(True),
        scheme=HOUSING_SCHEME, district_plan_decision_date="2024-01-01",
        housing_site_area_sqm=1100, exclusion_candidates=["LEFT"],
    )

    assert len(events) == 1, f"성장루프 이벤트가 정확히 1건이 아니다: {events}"
    name, props = events[0]
    assert name == "parcel_purchase_strategy", name

    summary = body["strategy"]["summary"]
    assert props["parcel_count"] == 5
    assert props["row_count"] == summary["row_count"] == 5
    assert props["geometry_unknown"] == summary["geometry_unknown_count"] == 1
    assert props["secured_ratio_available"] is True
    assert props["scheme_provided"] is True
    # ★★2026-09-05 — `scheme_resolved` 는 **단언 0건**이었고 원리적으로 늘 False 였다
    #   (`strategy["legal"]` 에는 `governing_act` 가 없다 — 최상위에 있다).
    #   그 계기가 죽어 있으면 성장루프가 판정보류 원인을 「사용자 미입력」으로 **오귀속**한다.
    #   여기는 **등록 방식**(HOUSING_SCHEME)이므로 True 여야 한다 — 아래 음성 짝과 대조.
    assert props["scheme_resolved"] is True, props
    assert props["undecided_rows"] == 0

    # ★식별자 유출 금지 — 필지 식별자·주소는 payload 에 들어가면 안 된다.
    blob = " ".join(f"{k}={v}" for k, v in props.items())
    for pnu in ("LEFT", "RIGHT", "TOP", "BOTTOM", "NOGEOM"):
        assert pnu not in blob, f"성장루프 payload 에 식별자가 실렸다: {blob}"


def test_성장루프_판정보류_집계가_계약_상수에_결속된다(monkeypatch: pytest.MonkeyPatch) -> None:
    """★`by_action.get("판정보류")` 처럼 라벨을 **다시 적으면** 계약 상수와 갈라진다 —
    상수가 바뀌어도 이 줄은 조용히 0 을 세고 성장루프는 '판정보류 없음'으로 오독한다.

    두 모집단: 사업방식 있음(판정보류 0) vs 없음(전 행 판정보류).
    """
    events = _capture_growth(monkeypatch)
    parcels = _strategy_parcels()

    # (A) 사업방식 없음 → 전 행이 판정보류다.
    no_scheme = _post_strategy(
        monkeypatch, parcels,
        district_plan_decision_date="2024-01-01", housing_site_area_sqm=10000,
    )
    # (B) 사업방식 있음 → 판정보류 0.
    with_scheme = _post_strategy(
        monkeypatch, parcels, scheme=HOUSING_SCHEME,
        district_plan_decision_date="2024-01-01", housing_site_area_sqm=10000,
    )

    assert len(events) == 2, events
    props_a, props_b = events[0][1], events[1][1]

    by_action_a = no_scheme["strategy"]["summary"]["by_action"]
    assert by_action_a[ps.ACTION_UNDECIDED] == 2, by_action_a
    assert props_a["undecided_rows"] == by_action_a[ps.ACTION_UNDECIDED] == 2, (
        f"판정보류 집계가 계약 상수와 갈라졌다: {props_a}"
    )
    assert props_a["scheme_provided"] is False
    assert props_a["secured_ratio_available"] is True

    assert with_scheme["strategy"]["summary"]["by_action"][ps.ACTION_UNDECIDED] == 0
    assert props_b["undecided_rows"] == 0
    assert props_b["scheme_provided"] is True
    # ★차가 0이면 잠금이 아니다.
    assert props_a["undecided_rows"] != props_b["undecided_rows"]
    assert props_a["scheme_provided"] != props_b["scheme_provided"]


def test_엔드포인트는_인증을_요구한다() -> None:
    """★요율·정책은 계정 컨텍스트에 딸린 정보다(무인증 발급 금지)."""
    import routers.registry as reg

    app = FastAPI()
    app.include_router(reg.router)
    with TestClient(app) as client:
        resp = client.post("/registry/survey/strategy", json={"parcels": []})
    assert resp.status_code in (401, 403), resp.text


# ══ 7) 정책표(MAGDO_RULES) 계약 — 변이 감사로 드러난 무잠금 구멍 봉합 ═══════
# ★2026-08-15 `scripts/mutate_changed.py` 실행에서 아래 줄들이 **생존**했다:
#   `governing_act: "도정법"` · 도시개발 note · `HOLDING_PERIOD_ACT` · `requires_track_input`
#   · out-of-scope 사유 문구. 전부 "커밋이 선언했는데 아무도 안 보는" 값이었다.

def test_정책표가_사업방식별_근거법령과_수단을_명시한다() -> None:
    """★전수 파생형 — 정책표에 방식이 추가되면 자동으로 이 검사에 들어온다(목록형 아님)."""
    from app.services.development.scenario_simulator import (
        HOLDING_PERIOD_ACT,
        MAGDO_RULES,
        scheme_legal_profile,
    )

    assert HOLDING_PERIOD_ACT == "주택법"
    assert len(MAGDO_RULES) >= 7  # ★개수 하한 — 표가 비면 아래 루프가 공허해진다

    for name, rule in MAGDO_RULES.items():
        assert "governing_act" in rule, f"{name}: 근거법령이 명시 필드로 없다(basis 추론 금지)"
        assert rule["instrument"] in ("매도청구", "수용"), f"{name}: {rule.get('instrument')}"
        act = rule["governing_act"]
        assert act in (None, "주택법", "도정법", "소규모정비특례법", "도시개발법"), f"{name}: {act}"
        if act is None:
            assert rule.get("requires_track_input") is True, (
                f"{name}: 근거법령을 확정 못 하면서 트랙 입력 요구 표시가 없다"
            )
        prof = scheme_legal_profile(name)
        assert prof is not None and prof["governing_act"] == act
        assert prof["instrument"] == rule["instrument"]

    # 명시적 매핑(전수 루프가 '전부 None' 같은 퇴화로 참이 되지 않도록 값을 못박는다).
    assert MAGDO_RULES["재개발·재건축(정비사업)"]["governing_act"] == "도정법"
    assert MAGDO_RULES["가로주택정비사업"]["governing_act"] == "소규모정비특례법"
    assert MAGDO_RULES["모아주택/모아타운"]["governing_act"] == "소규모정비특례법"
    assert MAGDO_RULES["지구단위계획 연계"]["governing_act"] == "주택법"
    assert MAGDO_RULES["역세권 장기전세주택(시프트)"]["governing_act"] == "주택법"


def test_도시개발사업_note에서_매도청구에_준함을_걷어냈다() -> None:
    """★법령 대조로 **부정확**이 확인된 문구다 — 수용은 토지보상법 준용이라 절차가 다르다.
    선언만 하고 잠그지 않으면 다음 사람이 되돌려 놓아도 초록이다."""
    from app.services.development.scenario_simulator import MAGDO_RULES

    rule = MAGDO_RULES["도시개발사업(도시개발법)"]
    assert rule["instrument"] == "수용"
    assert "매도청구에 준함" not in rule["note"], rule["note"]
    assert "토지보상법" in rule["note"], "수용의 준용 법률이 사라졌다"


def test_out_of_scope_사유가_주택법_전용_요건임을_밝힌다() -> None:
    """★사유 문구가 **법적 설명**이다 — 사용자는 이 문장을 보고 왜 판정이 없는지 이해한다."""
    consent = prs._judge_owner(
        _owner("소유자", "전부", "2005-03-02", "매매"), None, None, CONSENT_SCHEME
    )
    # ★상수 리터럴 대신 **계약**을 본다 — 문구는 다듬어도 계약은 안 바뀐다.
    assert consent["sell_claim_judgment"] is None
    assert consent["sell_claim_judgment_absent"] == NOT_APPLICABLE, (
        "해당 사업방식에 기준이 없는 것은 **자료 부족이 아니라 not_applicable** 이다"
    )
    reason = consent["sell_claim_reason"]
    assert "도정법" in reason, reason
    assert "주택법" in reason, "보유기간 요건이 어느 법 소관인지 밝히지 않았다"
    assert "보유기간" in reason and "10년" in reason, reason

    track = prs._judge_owner(
        _owner("소유자", "전부", "2005-03-02", "매매"), None, None, "역세권 활성화사업"
    )
    assert "트랙" in track["sell_claim_reason"], (
        f"근거법령이 트랙에 따라 갈린다는 사실이 사유에 없다: {track['sell_claim_reason']}"
    )
    assert track["sell_claim_reason"] != reason, "모호 방식과 동의율 방식이 같은 사유를 낸다"

    # ★소규모정비 트랙 — 근거법령은 **확정**이고 갈리는 것은 **수단**이다. 아는 법령 이름까지
    #   지워 버리면 사용자가 무엇을 보완해야 하는지 알 수 없다(세 사유가 전부 달라야 한다).
    small = prs._judge_owner(
        _owner("소유자", "전부", "2005-03-02", "매매"), None, None, TRACK_SCHEME
    )
    small_reason = small["sell_claim_reason"]
    assert "소규모정비특례법" in small_reason, small_reason
    assert "트랙" in small_reason and "시행자" in small_reason, small_reason
    assert len({reason, track["sell_claim_reason"], small_reason}) == 3, (
        "동의율·법령모호·수단모호 세 사유가 구별되지 않는다"
    )


@pytest.mark.asyncio
async def test_도정법_정비사업도_동의율_기준으로_분류된다(monkeypatch: pytest.MonkeyPatch) -> None:
    """★변이 감사에서 `governing_act: "도정법"` 줄삭제가 **생존**했다 — 어느 테스트도
    도정법 계열을 태우지 않았다. 동의율 기반이므로 장기보유자도 매도청구 대상이다."""
    owners = [_owner("장기보유자", "전부", "2005-03-02", "매매")]
    fixtures = {"장기필지": _ok_analysis(owners), "확보필지": _ok_analysis(owners)}
    scheme = "재개발·재건축(정비사업)"

    out = ps.build_strategy(
        await _survey(monkeypatch, fixtures, scheme), _strategy_parcels(),
        scheme=scheme, housing_site_area_sqm=10000,
    )
    assert out["governing_act"] == "도정법"
    assert out["instrument"] == "매도청구"
    assert out["summary"]["row_count"] == 2
    assert {r["action"] for r in out["rows"]} == {ps.ACTION_SELL_CLAIM}
    assert out["summary"]["priority_a_count"] == 0, "보유기간 요건이 없는데 1순위를 붙였다"
    # ★동의요건이 판정 근거로 실린다 — 없으면 사용자가 무엇을 충족해야 할지 모른다.
    assert out["legal"]["consent_threshold_pct"] == 75
    assert "3/4" in out["legal"]["consent_required"]
    assert "제64조" in out["legal"]["basis"]


# ══ 8) 변이 감사(2026-08-15)로 드러난 무잠금 분기 봉합 ═════════════════════
# ★`scripts/mutate_changed.py --only parcel_purchase_strategy_service.py` 실행에서
#   아래 분기들이 **생존**했다 — 어느 테스트도 태우지 않는 경로였다.

def test_확보_여부가_불리언이_아니면_확보로_접지_않는다() -> None:
    """★`"Y"`·`1` 같은 값을 참으로 읽으면 미확보 지분이 확보로 둔갑한다 — 미상은 미상이다."""
    rows = [
        {"pnu": "애매", "area_sqm": 6400, "use_right_secured": "Y",
         "owners": [{"name": "소유자", "share": "전부"}]},
    ]
    out = ps.secured_ratio(rows, 10000)
    assert out["status"] == ps.STATUS_UNDECIDABLE
    assert out["undetermined_secured_pnus"] == ["애매"]
    assert "secured_ratio_pct" not in out


def test_소유자_구조가_없는_필지도_확보여부를_추측하지_않는다() -> None:
    """★소유자 배열이 없으면 필지 단위 플래그가 곧 전 지분이다 — 미상이면 거부한다."""
    unknown = ps.secured_ratio([{"pnu": "무소유자", "area_sqm": 1000}], 1000)
    assert unknown["status"] == ps.STATUS_UNDECIDABLE
    assert unknown["undetermined_secured_pnus"] == ["무소유자"]

    # ★대조군 — 명시적 True/False 면 소유자 배열 없이도 산정된다(차가 0이면 잠금이 아니다).
    yes = ps.secured_ratio([{"pnu": "확보", "area_sqm": 1000, "use_right_secured": True}], 1000)
    no = ps.secured_ratio([{"pnu": "미확보", "area_sqm": 1000, "use_right_secured": False}], 1000)
    assert yes["secured_ratio_pct"] == 100.0
    assert no["secured_ratio_pct"] == 0.0


def test_확보면적이_대지면적을_넘으면_모순으로_거부한다() -> None:
    """★입력이 서로 모순인데 100% 를 넘는 확보율을 내면 95% 게이트가 무의미해진다."""
    rows = [{"pnu": "과대", "area_sqm": 20000, "use_right_secured": True}]
    out = ps.secured_ratio(rows, 10000)
    assert out["status"] == ps.STATUS_UNDECIDABLE
    assert "모순" in out["reason"]
    assert "secured_ratio_pct" not in out
    # ★거부 경로에서도 계약 키가 살아 있어야 UI 가 undefined 를 그리지 않는다.
    for key in ("missing_area_pnus", "unparsed_share_pnus", "undetermined_secured_pnus"):
        assert out[key] == [], f"{key} 가 모순-거부 응답에서 빠졌다"


def test_확보율_응답이_분자분모와_커버리지를_드러낸다() -> None:
    """★비율만 내고 분자·분모를 감추면 사후 검증이 불가능하다.
    ★입력 행이 대지를 덮지 않으면 분자가 **과소**다 — 그 사실을 표면에 드러낸다."""
    partial = ps.secured_ratio(
        [{"pnu": "일부", "area_sqm": 1000, "use_right_secured": True}], 10000
    )
    assert partial["secured_area_sqm"] == 1000.0
    assert partial["housing_site_area_sqm"] == 10000.0
    assert partial["coverage"]["row_area_sum_sqm"] == 1000.0
    assert partial["coverage"]["covers_site"] is False
    assert "과소" in partial["coverage"]["note"]

    full = ps.secured_ratio(
        [{"pnu": "전부", "area_sqm": 10000, "use_right_secured": True}], 10000
    )
    assert full["coverage"]["covers_site"] is True
    assert full["coverage"]["covers_site"] != partial["coverage"]["covers_site"]


def test_제외_집합이_비었거나_전량이면_가능이라_하지_않는다() -> None:
    """★둘 다 '아무것도 안 뺐다'/'전부 뺐다'라서 연결성분 수가 줄지 않는다 —
    성분 수만 보면 **가능**으로 읽힌다. 그 함정을 전제 가드가 막는지 잠근다."""
    graph = build_parcel_graph(_ring_parcels())
    assert graph["component_count"] == 1  # ★전제

    empty = ps.severability(graph, [])
    assert empty["severable"] is None, "제외 대상이 없는데 '가능'을 냈다"
    assert "지정되지" in empty["reason"]

    everything = ps.severability(graph, ["BOTTOM", "RIGHT", "TOP", "LEFT"])
    assert everything["severable"] is None, "전량 제척을 '가능'으로 냈다"
    assert "남는 필지가 없" in everything["reason"]


@pytest.mark.parametrize(
    "graph,exclusions",
    [
        (None, ["A"]),
        ({"status": "skipped_large_set"}, ["A"]),
        (build_parcel_graph(_ring_parcels()), []),
        (build_parcel_graph(_ring_parcels()), ["NOGEOM"]),
    ],
)
def test_판정_불가_응답도_계약_필드를_전부_갖춘다(graph: Any, exclusions: list[str]) -> None:
    """★거부 경로에서 필드가 빠지면 UI 가 `undefined` 를 그린다(성공 경로만 검사하면 못 잡는다)."""
    out = ps.severability(graph, exclusions)
    for key in (
        "severable", "topology_severable", "component_count_before",
        "component_count_after", "undecidable_pnus", "excluded_pnus",
        "procedure_required", "basis", "reason", "disclaimer",
    ):
        assert key in out, f"거부 응답에 {key} 가 없다: {sorted(out)}"
    assert out["severable"] is None
    assert out["procedure_required"] == ps.PROCEDURE_REQUIRED


@pytest.mark.asyncio
async def test_조립부가_확보면적을_최소조합_탐색에_실제로_넘긴다(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """★★배선 락 — `secured_ratio` 의 확보면적이 `min_count_combination` 의 기준선이다.
    전달이 끊기면 부족분이 틀려 "이 필지들만 사면 된다"는 **틀린 실행 지시**가 나간다."""
    owners = [_owner("소유자", "전부", "2005-03-02", "매매")]
    fixtures = {"장기필지": _ok_analysis(owners), "확보필지": _ok_analysis(owners)}

    out = ps.build_strategy(
        await _survey(monkeypatch, fixtures, HOUSING_SCHEME), _strategy_parcels(),
        scheme=HOUSING_SCHEME, housing_site_area_sqm=10000,
    )
    combo = out["min_count_combination"]
    assert out["secured_ratio"]["secured_area_sqm"] == 6400.0
    # 목표 9500 − 확보 6400 = 3100. 미확보(장기필지 3600) 하나로 넘긴다.
    assert combo["status"] == ps.STATUS_OK, f"확보면적이 전달되지 않았다: {combo}"
    assert combo["needed_area_sqm"] == 3100.0
    assert combo["combination_pnus"] == ["장기필지"]
    assert combo["count"] == 1


def test_소유자에_확보표시가_없으면_필지_단위_값을_승계한다() -> None:
    """★변이 감사 잔존 — 소유자 행에 플래그가 없을 때 **필지 단위 값을 물려받는** 경로가
    어느 테스트도 태우지 않았다. 승계가 끊기면 확보 필지가 통째로 '미상'이 되어 거부된다."""
    inherit_yes = ps.secured_ratio(
        [{"pnu": "확보", "area_sqm": 1000, "use_right_secured": True,
          "owners": [{"name": "소유자", "share": "전부"}]}],  # 소유자에 플래그 없음
        1000,
    )
    inherit_no = ps.secured_ratio(
        [{"pnu": "미확보", "area_sqm": 1000, "use_right_secured": False,
          "owners": [{"name": "소유자", "share": "전부"}]}],
        1000,
    )
    inherit_unknown = ps.secured_ratio(
        [{"pnu": "미상", "area_sqm": 1000,
          "owners": [{"name": "소유자", "share": "전부"}]}],  # 양쪽 다 없음
        1000,
    )

    assert inherit_yes["secured_ratio_pct"] == 100.0, "필지 단위 확보가 소유자에게 승계되지 않았다"
    assert inherit_no["secured_ratio_pct"] == 0.0
    assert inherit_unknown["status"] == ps.STATUS_UNDECIDABLE
    assert inherit_unknown["undetermined_secured_pnus"] == ["미상"]
    # ★세 모집단이 실제로 다른 값을 낸다(차가 0이면 승계 배선이 잠기지 않는다).
    assert inherit_yes["secured_ratio_pct"] != inherit_no["secured_ratio_pct"]


# ── 유료 경로의 지출 경계 ─────────────────────────────────────────────
# ★★이 락이 없어서 변이(`max_length=…` 줄 삭제)가 **생존**했다. 상수를 만들었으면 테스트는
#   같은 커밋에 — 손으로 재고 커밋에 안 넣으면 그 상한은 다음 리팩토링에서 조용히 사라진다.
#   (실제로 최초 커밋이 그 상태였고 독립 리뷰가 잡았다.)
# ★대역이 아니라 **계약 상수에 `==` 로 결속**한다 — 매직넘버 100 을 쓰면 상수가 장식이 된다.

def _boundary_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """경계 검사 전용 클라이언트 — 본문 처리 전에 422 가 나는지만 본다."""
    return _client(monkeypatch, [])


def test_필지수_상한을_넘으면_거부한다(monkeypatch: pytest.MonkeyPatch) -> None:
    """★유료 경로라 **입력 길이가 곧 청구액**이다. 상한이 없으면 요청 하나로 임의 금액이 빠진다.

    조용히 잘라내지 않고 **422 로 거부**한다 — 잘라내면 사용자가 빠진 필지를 모른 채 결과를
    신뢰한다(=조용한 오답). 두 모집단을 갈라 잠근다: 상한 = 통과 / 상한+1 = 거부.
    """
    import routers.registry as reg

    at_limit = [{"pnu": f"P{i}", "area_sqm": 100} for i in range(reg.MAX_STRATEGY_PARCELS)]
    over_limit = at_limit + [{"pnu": "OVER", "area_sqm": 100}]

    with _boundary_client(monkeypatch) as client:
        ok = client.post("/registry/survey/strategy", json={"parcels": at_limit})
        over = client.post("/registry/survey/strategy", json={"parcels": over_limit})

    # ★공허 진리 가드 — 두 모집단이 실제로 다른 응답을 내야 잠금이다(차가 0이면 잠금이 아니다).
    assert ok.status_code != 422, f"상한 이내인데 거부됐다: {ok.text[:200]}"
    assert over.status_code == 422, f"상한을 넘겼는데 통과했다 — 지출 상한이 없다: {over.text[:200]}"
    assert len(over_limit) == reg.MAX_STRATEGY_PARCELS + 1  # 계약 상수 결속


def test_빈_필지목록도_거부한다_경계는_양방향(monkeypatch: pytest.MonkeyPatch) -> None:
    """★상한만 걸고 하한을 안 걸면 반대쪽이 무제한이 된다(CLAUDE.md D19).

    ★자기적발 회귀: 최초 커밋은 주석에 `(min_length=1)` 이라 **적어 놓고 실제로는 안 걸어**
      `parcels=[] → HTTP 200` 이었다. 없는 면역을 주장한 형태라 이 락으로 고정한다.
    """
    import routers.registry as reg

    assert reg.MIN_STRATEGY_PARCELS == 1  # 계약 상수 결속(대역 금지)
    with _boundary_client(monkeypatch) as client:
        empty = client.post("/registry/survey/strategy", json={"parcels": []})
    assert empty.status_code == 422, f"빈 요청이 조용히 통과했다: {empty.text[:200]}"


# ── 응답 표면의 데이터 노출 경계 ──────────────────────────────────────
# ★★P1 카드는 `analysis`(RegistryAnalysisService 원본)를 통째로 싣는데 그 안에 `pdf_url` 이
#   있다 — `upload_registry_pdf(ttl_days=30)` 가 만든 **30일짜리 무인증 서명 URL**이다.
#   그대로 응답에 나가면 JSON 을 가진 사람이 30일간 등기부등본 전문(소유자 실명·지분·거래가액·
#   근저당 채권최고액)을 인증 없이 받는다. 라우터는 이 블롭을 **과금에만** 쓰므로 응답에서 뺀다.

def test_응답에_등기부_원본블롭과_서명URL이_실리지_않는다(monkeypatch: pytest.MonkeyPatch) -> None:
    """★과금 뒤 `analysis` 를 걷어냈는지 — **조립된 응답 표면 전체**를 훑어 확인한다.

    키 하나만 보지 않고 응답을 직렬화해 `pdf_url` 문자열 자체를 찾는다(중첩 어디에 있어도 잡힌다).
    """
    import json

    body = _post_strategy(
        monkeypatch, _ring_endpoint_parcels(True),
        scheme=HOUSING_SCHEME, district_plan_decision_date="2024-01-01",
        housing_site_area_sqm=1100,
    )
    cards = body["survey"]["cards"]
    # ★공허 진리 가드 — 카드가 0개면 "노출 없음"이 무의미하다.
    assert len(cards) == 5, f"카드 수가 예상과 다르다: {len(cards)}"

    for c in cards:
        assert "analysis" not in c, f"원본 분석 블롭이 응답에 남았다: {c.get('parcel')}"

    blob = json.dumps(body, ensure_ascii=False, default=str)
    assert "pdf_url" not in blob, "응답에 등기부 PDF 서명 URL 이 실렸다(30일 무인증 다운로드)"

    # ★반대 방향도 건다 — 필요한 표면까지 같이 사라지면 그것도 결함이다.
    ok = [c for c in cards if c.get("status") == "ok"]
    assert ok, "정상 카드가 하나도 없다 — 픽스처가 이 락을 공허하게 만든다"
    assert all(c.get("registry") is not None for c in ok), "권리분석 요약(registry)까지 사라졌다"


def test_성장루프는_payload_아래로_실어야_적재된다(monkeypatch: pytest.MonkeyPatch) -> None:
    """★★`capture_service` 는 화이트리스트라 **평면 키를 버린다**.

    이 테스트는 **실제 적재된 row** 를 본다(`record_event` 를 스텁하지 않는다) — emitter 가
    평면 키로 되돌아가면 payload 가 비어 빨갛게 뜬다. 두 모집단을 가른다:
    평면 전송(버려짐) vs payload 전송(보존).
    """
    import app.services.growth.capture_service as cap

    cap._QUEUE.clear()
    cap.record_event("__t_flat__", {"parcel_count": 5, "undecided_rows": 3})
    cap.record_event("__t_wrapped__", {"service": "x", "payload": {"parcel_count": 5}})
    rows = {r["event_type"]: r for r in cap._QUEUE}
    cap._QUEUE.clear()

    # 두 모집단이 **다른 결과**를 내야 잠금이다(차가 0이면 잠금이 아니다).
    assert rows["__t_flat__"].get("payload") is None, "평면 키가 보존됐다 — 화이트리스트 전제가 바뀌었다"
    assert rows["__t_wrapped__"]["payload"]["parcel_count"] == 5, "payload 가 보존되지 않는다"


# ── 형제 스윕: 다필지 요청 모델은 **전부** 상한을 가져야 한다 ──────────────
# ★★최초 구현은 `/survey/strategy` 에만 상한을 걸었다. `/registry/bulk` 는 **더 오래됐고
#   더 많이 쓰이며 똑같이 유료**(`times=len(items)`)인데 무제한이었다 — D20(처방 범위 ≠
#   결함 범위). 다른 세션이 원장 실측으로 잡아 줬다.
# ★목록형이 아니라 **파생형**으로 쓴다: 모듈에서 요청 모델을 긁어오므로 새 엔드포인트가
#   상한 없이 추가되면 **자동으로** 이 락에 걸린다(사람이 센 목록이 상한이 되지 않게).

def test_다필지_요청모델은_전부_길이상한을_가진다() -> None:
    """유료·다필지 경로에서 길이는 곧 청구액/부하다. 하나라도 무제한이면 실패한다."""
    import inspect

    from pydantic import BaseModel

    import routers.registry as reg

    def _list_fields_without_cap(model: type[BaseModel]) -> list[str]:
        bad = []
        for name, f in model.model_fields.items():
            ann = str(f.annotation)
            if "list[" not in ann.lower():
                continue
            caps = [m for m in (f.metadata or []) if type(m).__name__ == "MaxLen"]
            if not caps:
                bad.append(f"{model.__name__}.{name}")
        return bad

    models = [
        obj for _n, obj in inspect.getmembers(reg, inspect.isclass)
        if issubclass(obj, BaseModel) and obj is not BaseModel
        and obj.__module__ == reg.__name__
        and any("list[" in str(f.annotation).lower() for f in obj.model_fields.values())
    ]
    # ★공허 진리 가드 — 대상이 0개면 "위반 0"이 무의미하다.
    assert len(models) >= 3, f"다필지 요청모델을 못 찾았다(파생이 깨졌다): {models}"

    violations = [v for m in models for v in _list_fields_without_cap(m)]
    assert not violations, f"길이 상한이 없는 다필지 필드: {violations}"


def test_형제_상한이_같은_상수를_공유한다() -> None:
    """★값을 따로 적어 두면 한쪽만 바뀌었을 때 '어느 게 진짜 상한인가'가 갈린다."""
    import routers.registry as reg

    assert reg.MAX_STRATEGY_PARCELS == reg.MAX_BULK_ITEMS
    assert reg.MIN_STRATEGY_PARCELS == reg.MIN_BULK_ITEMS


def test_scheme_resolved_gates_registered_vs_unregistered(monkeypatch):
    """★두 모집단 — 계기가 **등록/미등록을 실제로 가르는가**.

    한쪽만 보면 «항상 True» 도 «항상 False» 도 통과한다. 실제로 이 필드는
    **원리적으로 늘 False** 였는데(정본이 아닌 블록을 봤다) 단언이 0건이라 조용했다.

    ★사유가 다른 두 축을 섞지 않는다 — 여기서 재는 것은 ①정책표 미등록(개발자가 고칠 것)이고,
      ②트랙 미입력(사용자가 채울 것)은 `requires_track_input` 축이라 별개다.
    """
    # ★형제 헬퍼를 쓴다 — `record_event` 를 **스텁하지 않는다.**
    #   스텁하면 «호출부가 넘긴 dict» 만 보게 되어, `capture_service._EVENT_COLS` 화이트리스트가
    #   키를 버리는 사실을 **원리적으로 못 본다**(그 파일이 실측으로 적어 둔 함정이고,
    #   내 초판이 정확히 그것을 밟아 KeyError 로 죽었다). 실제 적재된 row 의 payload 를 본다.
    events = _capture_growth(monkeypatch)

    # ① 양성 — 정책표에 **등록된** 방식
    _post_strategy(monkeypatch, _ring_endpoint_parcels(True), scheme=HOUSING_SCHEME,
                   district_plan_decision_date="2024-01-01", housing_site_area_sqm=1100)
    # ② 음성 — 정책표에 **없는** 방식(문자열은 있으므로 scheme_provided 는 True)
    _post_strategy(monkeypatch, _ring_endpoint_parcels(True), scheme="존재하지않는사업방식XYZ",
                   district_plan_decision_date="2024-01-01", housing_site_area_sqm=1100)

    # ★공허 진리 가드 — 두 이벤트가 실제로 적재됐는가(대상 부재면 아래 대조가 공허하다).
    got = [p for n, p in events if n == "parcel_purchase_strategy"]
    assert len(got) == 2, f"성장루프 이벤트 2건이 아니다: {list(events)}"

    registered, unregistered = got[0], got[1]
    # ★핵심 — 두 모집단이 **실제로 갈린다**. 늘 True/늘 False 면 여기서 죽는다.
    assert registered["scheme_resolved"] is True, registered
    assert unregistered["scheme_resolved"] is False, unregistered
    # ★그리고 `scheme_provided` 와 **다른 것을 잰다** — 둘 다 True 면 구별이 없다.
    assert unregistered["scheme_provided"] is True, unregistered
