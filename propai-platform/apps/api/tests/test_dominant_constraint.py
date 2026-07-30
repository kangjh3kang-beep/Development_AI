"""지배 제약(무엇이 발목인가) 한 줄 + 높이 상한 — 단위 테스트(사통맵 v2 W1).

계약(SPEC_satong_map_v2_W1_implementation_2026-07-30.md §3-1):
  - 군사 통제보호구역 + 경사도 18% → headline은 **군사**(더 높은 severity)
  - 규제 0건 + 경사 5% → ranked 비어 있고 headline None
  - 정북거리 有 → governing_m 숫자 · governing_source="정북일조"
  - 고도지구만 있고 수치 없음 → governing_m is None · incomplete True
  - ★severity SSOT 재사용 확인(자체 등급 재정의 금지)

★정직 경계: 고도지구·비행안전구역은 수치 룩업 부재 → limit_m=None + "조례 확인 필요".
   이 테스트가 그 정직 표기를 잠근다(추정치 채워넣기 회귀 방지).
"""
from __future__ import annotations

import ast
import inspect

import pytest

from app.services.regulation import dominant_constraint as dc
from app.services.regulation import protection_zone_severity as pzs
from app.services.regulation.dominant_constraint import (
    build_for_parcel,
    north_distance_for_sunlight,
    resolve_dominant_constraint,
    slope_severity,
)


# ── ① severity 랭킹: 더 높은 쪽이 headline ───────────────────────────────────
def test_military_control_zone_outranks_slope():
    """군사 통제보호구역(높음) vs 경사도 18%(보통) → headline은 군사."""
    out = resolve_dominant_constraint(
        ["군사시설보호구역(통제보호구역)", "비행안전구역"],
        north_distance_m=None,
        slope_pct=18.0,
    )
    assert out["headline"] is not None
    assert "통제보호구역" in out["headline"], f"군사가 headline이어야 함: {out['headline']}"
    assert out["severity"] == "높음"
    # 그다음 항목에 경사도가 들어와야 한다(랭킹 자체가 작동하는지).
    names = [r["name"] for r in out["ranked"]]
    assert any(n == "경사도 18%" for n in names), f"경사도가 랭킹에 없음: {names}"
    # 상위 3개까지만(상세 목록은 종합 부지분석 담당).
    assert len(out["ranked"]) <= dc.RANKED_LIMIT


def test_ranked_is_sorted_by_severity_desc():
    """랭킹은 severity 내림차순 — 입력 순서와 무관(정렬이 실제로 걸리는지)."""
    out = resolve_dominant_constraint(
        ["경관지구", "개발제한구역", "고도지구"],  # 낮음 / 극히 높음 / 보통
        north_distance_m=None,
        slope_pct=None,
    )
    sevs = [r["severity"] for r in out["ranked"]]
    ranks = [pzs.severity_rank(s) for s in sevs]
    assert ranks == sorted(ranks, reverse=True), f"severity 내림차순 아님: {sevs}"
    assert out["severity"] == "극히 높음"
    # ★"낮음" 지정(경관지구)은 **남는다** — 경사도 "낮음"(임계 미달=제약 없음)과 달리 지정은
    #   실재하는 제약(경관 심의)이다. 성질이 달라 하한(SLOPE_RANKED_FLOOR)은 경사도에만 적용된다.
    assert out["ranked"][-1]["name"] == "경관지구", f"낮음 지정이 최하위로 남아야 함: {out['ranked']}"


def test_low_severity_designation_alone_still_produces_banner():
    """경관지구만 걸린 필지도 배너가 뜬다 — 지정 실재는 경사도 임계 미달과 다르다."""
    out = build_for_parcel(regulations=["경관지구"], zone_type="제2종일반주거지역")
    assert out is not None
    assert out["severity"] == "낮음"
    assert "경관" in out["headline"]


# ── ② 제약 0건: 빈 배너 금지 ─────────────────────────────────────────────────
def test_no_constraint_returns_empty_ranked_and_none_headline():
    """규제 0건 + 경사 5% → ranked 비어 있고 headline None(무날조·빈 배너 금지)."""
    out = resolve_dominant_constraint([], north_distance_m=None, slope_pct=5.0)
    assert out["headline"] is None
    assert out["severity"] is None
    assert out["ranked"] == []
    assert out["height"] is None


def test_build_for_parcel_returns_none_when_nothing_to_say():
    """소비처 진입점은 '말할 것이 없으면' None — 화면이 배너를 못 띄우게 계약으로 보장."""
    assert build_for_parcel(regulations=[], zone_type="보전관리지역", slope_pct=5.0) is None
    assert build_for_parcel(regulations=None, zone_type=None) is None
    # 알 수 없는 designation(SSOT 미등재)만 있으면 역시 None(가짜 severity 생성 금지).
    assert build_for_parcel(regulations=["존재하지않는구역명"], zone_type="보전관리지역") is None


# ── ★무음 낙관 차단: "조회 실패"와 "제약 없음"은 다른 것이다 ──────────────────
def test_lookup_failure_is_not_reported_as_no_constraint():
    """규제 조회 실패(designations_verified=False) + 제약 0건 → None이 아니라 unverified 블록.

    ★둘 다 배너 0건으로 뭉개면 사용자는 "규제를 확인했고 없다"고 착각한다. 이 저장소가
    반복해서 데인 결함 클래스(무음 낙관)라 계약 수준에서 구분한다.
    """
    failed = build_for_parcel(
        regulations=[], zone_type="보전관리지역", designations_verified=False,
    )
    assert failed is not None, "조회 실패를 '제약 없음'과 같이 숨기면 무음 낙관"
    assert failed["unverified"] is True
    assert failed["headline"] is None  # 없는 제약을 만들지도 않는다

    # 조회 성공 + 제약 0건은 그대로 None(빈 배너 금지) — 두 케이스가 갈린다.
    ok = build_for_parcel(regulations=[], zone_type="보전관리지역", designations_verified=True)
    assert ok is None


def test_verified_lookup_marks_unverified_false():
    """조회 성공 시 unverified=False가 명시된다(키 부재로 화면이 판단을 못 하는 상황 방지)."""
    out = build_for_parcel(regulations=["개발제한구역"], zone_type="보전관리지역")
    assert out["unverified"] is False


# ── ③ 정북일조: 수치가 있는 항목만 min()에 참여 ──────────────────────────────
def test_north_distance_yields_numeric_governing_height():
    """정북거리 有 → governing_m 숫자 · governing_source='정북일조' · 산식은 공용 SSOT."""
    from app.services.common.sunlight_setback import max_height_for_north_distance_m

    out = resolve_dominant_constraint([], north_distance_m=15.0, slope_pct=None)
    h = out["height"]
    assert h is not None
    assert h["governing_source"] == "정북일조"
    # 값은 공용 산식과 **동일**해야 한다(자체 산식 복제 금지 — 동어반복 아님: 왼쪽은 모듈 출력).
    assert h["governing_m"] == pytest.approx(round(max_height_for_north_distance_m(15.0), 1))
    assert h["governing_m"] == pytest.approx(30.0)  # max(10, 2×15) — 절대값 앵커
    assert h["incomplete"] is False, "수치 미보유 항목이 없으면 incomplete는 False"
    assert h["items"][0]["basis"], "정북일조 항목은 법적 근거를 명시해야 함"


def test_numeric_min_picks_lowest_and_ignores_unknown_items():
    """수치 보유 항목 중 **최소**가 governing — 미보유 항목은 min에 끼지 않는다."""
    out = resolve_dominant_constraint(
        ["고도지구", "비행안전구역"],  # 둘 다 수치 미보유
        north_distance_m=6.0,          # max(10, 12) = 12m
        slope_pct=None,
    )
    h = out["height"]
    assert h["governing_m"] == pytest.approx(12.0)
    assert h["governing_source"] == "정북일조"
    assert h["incomplete"] is True, "수치 미보유 항목이 있으면 최종값이 아님을 반드시 고지"
    unknown = [i for i in h["items"] if i["limit_m"] is None]
    assert len(unknown) == 2, f"고도지구·비행안전 2건이 미보유로 남아야 함: {h['items']}"


# ── ④ 정직 경계: 수치 미보유는 추정하지 않는다 ───────────────────────────────
def test_height_district_without_number_is_honest_not_estimated():
    """고도지구만 있고 수치 없음 → governing_m is None · incomplete True."""
    out = resolve_dominant_constraint(["고도지구"], north_distance_m=None, slope_pct=None)
    h = out["height"]
    assert h is not None
    assert h["governing_m"] is None, "★수치를 추정해 채우면 안 된다(플랫폼 미보유)"
    assert h["governing_source"] is None
    assert h["incomplete"] is True
    assert len(h["items"]) == 1
    item = h["items"][0]
    assert item["limit_m"] is None
    assert "조례" in item["note"], f"조례 확인 필요 문구가 있어야 함: {item['note']}"


def test_flight_safety_zone_is_height_constraining_without_number():
    """비행안전구역도 높이 제약 — 수치는 미보유(호미곶 라이브 케이스)."""
    out = resolve_dominant_constraint(
        ["군사시설보호구역(통제보호구역)", "비행안전구역(제6구역)"],
        north_distance_m=None,
        slope_pct=None,
    )
    h = out["height"]
    assert h is not None, "비행안전구역이 있으면 높이 블록이 생성돼야 함"
    assert h["governing_m"] is None
    assert h["incomplete"] is True
    assert any("비행안전" in i["source"] for i in h["items"])


def test_no_height_items_means_height_block_is_none():
    """높이를 제한하는 항목이 없으면 height는 None(빈 블록 금지)."""
    out = resolve_dominant_constraint(["개발제한구역"], north_distance_m=None, slope_pct=None)
    assert out["headline"] is not None       # 제약 자체는 있다
    assert out["height"] is None             # 다만 높이 제약은 아니다


# ── ⑤ 정북일조 적용 용도지역 게이트(없는 제약 만들지 않기) ───────────────────
_SQUARE_30M = {
    # 위도 37.3 기준 약 0.00027도 ≒ 30m 남북깊이(등거리 근사) — dims_from_polygon 실물 통과.
    "type": "Polygon",
    "coordinates": [[[127.1, 37.3], [127.1004, 37.3], [127.1004, 37.30027],
                     [127.1, 37.30027], [127.1, 37.3]]],
}


def test_sunlight_gate_applies_only_to_residential_zones():
    """정북일조는 전용/일반주거지역만 — 보전관리·임야에 일조 상한을 붙이면 날조다."""
    assert north_distance_for_sunlight("제2종일반주거지역", _SQUARE_30M) is not None
    assert north_distance_for_sunlight("제1종전용주거지역", _SQUARE_30M) is not None
    # 비적용 용도지역 — 호미곶(보전관리지역)이 여기 해당.
    assert north_distance_for_sunlight("보전관리지역", _SQUARE_30M) is None
    assert north_distance_for_sunlight("자연녹지지역", _SQUARE_30M) is None
    assert north_distance_for_sunlight("일반상업지역", _SQUARE_30M) is None
    # geometry·용도지역 결손은 미상(None) — 추정 금지.
    assert north_distance_for_sunlight("제2종일반주거지역", None) is None
    assert north_distance_for_sunlight(None, _SQUARE_30M) is None


def test_sunlight_gate_depth_matches_measured_geometry():
    """남북깊이는 실측 geometry에서 나온다(공용 dims_from_polygon 재사용 — 자체 기하 산식 0)."""
    from app.services.site_score.solar_envelope_service import dims_from_polygon

    depth = north_distance_for_sunlight("제2종일반주거지역", _SQUARE_30M)
    assert depth == pytest.approx(dims_from_polygon(_SQUARE_30M)["depth_m"])
    assert 25.0 < depth < 35.0, f"약 30m 남북깊이여야 함: {depth}"


def test_build_for_parcel_wires_zone_gate_into_height():
    """진입점이 용도지역 게이트를 실제로 통과시키는지(배선) — 주거는 숫자, 관리지역은 미생성."""
    residential = build_for_parcel(
        regulations=["고도지구"], zone_type="제2종일반주거지역", geometry=_SQUARE_30M,
    )
    assert residential["height"]["governing_source"] == "정북일조"
    assert residential["height"]["incomplete"] is True  # 고도지구 수치 미보유

    conservation = build_for_parcel(
        regulations=["고도지구"], zone_type="보전관리지역", geometry=_SQUARE_30M,
    )
    assert conservation["height"]["governing_m"] is None, (
        "보전관리지역에 정북일조 상한이 생기면 없는 제약을 만든 것(날조)"
    )


# ── ⑥ 경사도 severity 매핑 ───────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("pct", "expected"),
    [(25.0, "높음"), (20.0, "높음"), (19.9, "보통"), (10.0, "보통"), (9.9, "낮음"), (0.0, "낮음")],
)
def test_slope_severity_thresholds(pct, expected):
    assert slope_severity(pct) == expected


def test_slope_severity_unknown_is_none():
    """미상은 None — 0%로 단정하면 '경사 없음'이라는 없는 사실을 만든다."""
    assert slope_severity(None) is None
    assert slope_severity(True) is None  # bool은 수치가 아니다(int 서브클래스 함정)
    assert slope_severity("18") is None


def test_low_slope_is_not_a_constraint():
    """'낮음' 경사는 발목이 아니므로 랭킹에 넣지 않는다."""
    out = resolve_dominant_constraint([], north_distance_m=None, slope_pct=9.0)
    assert out["ranked"] == []
    assert out["headline"] is None


# ── ⑦ ★SSOT 재사용 확인(자체 등급 재정의 금지) ───────────────────────────────
def test_severity_grades_come_only_from_ssot():
    """이 모듈이 내는 모든 severity는 protection_zone_severity.SEVERITY_ORDER 안에 있어야 한다."""
    out = resolve_dominant_constraint(
        ["개발제한구역", "군사시설보호구역(통제보호구역)", "제한보호구역", "고도지구",
         "비행안전구역(제1구역)", "상수원보호구역", "대공방어협조구역"],
        north_distance_m=None,
        slope_pct=25.0,
    )
    grades = {out["severity"], *(r["severity"] for r in out["ranked"])}
    assert grades <= set(pzs.SEVERITY_ORDER), f"SSOT 밖 등급 발생: {grades - set(pzs.SEVERITY_ORDER)}"
    # 경사도 등급도 같은 사다리를 쓴다.
    assert slope_severity(25.0) in pzs.SEVERITY_ORDER
    assert slope_severity(15.0) in pzs.SEVERITY_ORDER


def test_module_imports_ssot_and_does_not_redefine_ladder():
    """★소스 수준 확인: SSOT를 import하고, 자체 등급 사다리를 만들지 않는다.

    값 비교만으로는 "우연히 같은 문자열을 하드코딩"한 경우를 잡지 못한다(SSOT 이중화의
    실제 발생 형태). 그래서 import 사실과 자체 사다리 부재를 함께 고정한다.
    """
    src = inspect.getsource(dc)
    assert "from app.services.regulation.protection_zone_severity import" in src
    # severity 비교는 SSOT의 severity_rank를 경유해야 한다(자체 index 비교 금지).
    assert "severity_rank(" in src
    # ★R1 LOW-8: 종전 단언은 문자열 치환 기반이라 (a) 이름만 다른 자체 사다리(_LADDER = ...)를
    #   통과시키고 (b) 정당한 SEVERITY_ORDER import에 오탐 실패했다. 코드 문자열 대신 **구조**로
    #   본다 — 등급 리터럴 2개 이상을 담은 시퀀스가 있으면 자체 사다리 의심(이름 무관).
    ladders = [
        node for node in ast.walk(ast.parse(src))
        if isinstance(node, (ast.Tuple, ast.List))
        and sum(
            1 for e in node.elts
            if isinstance(e, ast.Constant) and e.value in pzs.SEVERITY_ORDER
        ) >= 2
    ]
    assert not ladders, (
        "severity 등급 문자열 2개 이상을 담은 리터럴 시퀀스가 있다 — 자체 사다리(SSOT 이중화) 의심"
    )


def _reference_severity_oracle(name: str | None) -> str | None:
    """★독립 오라클 — classify() 리팩토링 **이전**의 누적 max 알고리즘을 여기서 재구현한다.

    R1 LOW-7: 종전 테스트는 `severity_for(x) == classify(x)["severity"]`였는데 severity_for가
    바로 그 값을 돌려주므로 동어반복이었다(classify의 severity를 상수로 파괴해도 통과 — 변이
    생존 실증). 여기서는 소비처가 의존하는 계약(부분일치·최댓값·비행안전 granular)을 **독립적으로**
    계산해 대조한다 — 구현을 고쳐도 이 오라클은 따라오지 않으므로 변이를 잡는다.
    """
    if not name:
        return None
    n = str(name).replace(" ", "")
    best: str | None = None
    if pzs._FLIGHT_SAFETY_KW in n:  # noqa: SLF001 — 오라클 전용 접근
        best = "높음" if ("제1구역" in n or "활주로" in n) else "보통"
    order = pzs.SEVERITY_ORDER
    for keyword, sev in pzs._ZONE_SEVERITY:  # noqa: SLF001 — 오라클 전용 접근
        if keyword in n and (best is None or order.index(sev) > order.index(best)):
            best = sev
    return best


def test_severity_for_matches_independent_oracle():
    """classify() 도입이 severity_for 값을 바꾸지 않았는지 — **독립 오라클** 대조(무회귀).

    3소비처(regulation_analysis·comprehensive risk_keywords·land_info)가 이 값을 소비한다.
    """
    samples = [
        "군사시설보호구역(통제보호구역)", "제한보호구역", "방공기지", "방공유도탄기지",
        "대공방어협조구역", "군사시설보호구역", "개발제한구역", "그린벨트",
        "상수원보호구역", "폐기물매립시설", "고도지구", "경관지구", "방화지구",
        "비행안전구역", "비행안전 제1구역", "비행안전제6구역", "활주로 비행안전구역",
        # 결합 명칭(실제 API 형태) — 최댓값 규칙이 오라클과 같아야 한다.
        "군사기지 및 군사시설 보호구역(비행안전제6구역)",
        "군사기지 및 군사시설 보호구역(대공방어협조구역)",
        "개발제한구역 및 상수원보호구역",
        "존재하지않는구역", "", None,
    ]
    for sample in samples:
        assert pzs.severity_for(sample) == _reference_severity_oracle(sample), (
            f"독립 오라클과 불일치: {sample!r}"
        )


# ── ⑧ ★R1 HIGH-1: 결합 designation(한 문자열에 복수 키워드) ─────────────────
#   실제 VWorld/NED는 개별법 명칭을 합쳐 한 문자열로 준다:
#     "군사기지 및 군사시설 보호구역(비행안전제6구역)"
#   최댓값 severity 키워드('군사시설보호'=높음) 하나만 남기면 낮은 쪽('비행안전'=보통)이 갖고
#   있던 height_constraining이 버려져 **높이 상한 블록 자체가 소실**된다(R1이 실측으로 적발).
@pytest.mark.parametrize(
    "designation",
    [
        "군사기지 및 군사시설 보호구역(비행안전제6구역)",
        "군사기지 및 군사시설 보호구역(대공방어협조구역)",
        "군사시설보호구역 비행안전 제1구역",
    ],
)
def test_combined_designation_preserves_height_constraint(designation):
    """결합 명칭에서 높이제약이 소실되지 않는다(합집합) — 정직 고지 무음 누락 방지."""
    hit = pzs.classify(designation)
    assert hit is not None
    assert hit["height_constraining"] is True, (
        f"결합 명칭에서 높이제약 소실: {designation} → matched={hit['matched']}"
    )
    out = resolve_dominant_constraint([designation], north_distance_m=None, slope_pct=None)
    assert out["height"] is not None, "높이 상한 블록이 통째로 사라졌다(핵심 산출물 무음 누락)"
    assert out["height"]["incomplete"] is True
    assert out["height"]["governing_m"] is None
    # 어떤 지정 때문에 걸렸는지 항목 문구에 남아야 한다(이름만으론 읽히지 않음).
    assert any(
        ("비행안전" in (i["note"] or "")) or ("대공방어협조구역" in (i["note"] or ""))
        for i in out["height"]["items"]
    ), f"높이제약 사유 미표기: {out['height']['items']}"


def test_combined_designation_keeps_max_severity_representative():
    """합집합은 height만 — severity·action/reason은 최댓값 키워드가 대표한다(과잉교정 회피)."""
    hit = pzs.classify("군사기지 및 군사시설 보호구역(비행안전제6구역)")
    assert hit["severity"] == "높음", "군사시설보호(높음)가 대표 severity"
    assert hit["keyword"] == "군사시설보호"
    assert set(hit["matched"]) == {"비행안전", "군사시설보호"}


def test_tie_break_prefers_first_matched_keyword():
    """★동순위(같은 severity) 복수 매치 → 표 순서상 먼저 오는 키워드가 대표(계약 고정).

    R1: 이 계약이 어떤 테스트로도 고정되지 않아, `if higher != best_sev` 가드를 제거하는
    변이(동순위 last-match-wins)가 85건 전부 생존했다.
    """
    # 개발제한구역·상수원보호구역 모두 "극히 높음"(동순위). 표에서 개발제한구역이 먼저 온다.
    hit = pzs.classify("개발제한구역 및 상수원보호구역")
    assert hit["severity"] == "극히 높음"
    assert hit["keyword"] == "개발제한구역", (
        f"동순위 tie-break가 첫 매치 우선이 아니다: {hit['keyword']}"
    )
    # 방공유도탄기지·방공기지도 동순위("높음") — 표 순서상 방공유도탄기지가 먼저.
    hit2 = pzs.classify("방공유도탄기지 방공기지")
    assert hit2["keyword"] == "방공유도탄기지", f"tie-break 위반: {hit2['keyword']}"


def test_zone_meta_covers_every_ssot_keyword():
    """★키워드 표 정합 — severity 표와 메타 표의 키 집합이 정확히 일치해야 한다.

    키워드 목록을 두 벌 두는 것이 이 저장소의 반복 결함(SSOT 이중화)이라, 새 규제를 한쪽에만
    추가하면 여기서 실패한다(action/reason 없는 규제가 조용히 배너에 '조치 미상'으로 뜨는 것 방지).
    """
    keywords = set(pzs.zone_keywords())
    meta_keys = set(pzs._ZONE_META)  # noqa: SLF001 — 표 정합 검사 전용
    assert meta_keys == keywords, (
        f"메타 누락: {keywords - meta_keys} / 유령 메타: {meta_keys - keywords}"
    )
    for kw, meta in pzs._ZONE_META.items():  # noqa: SLF001
        assert meta.get("action"), f"{kw}: action 누락"
        assert meta.get("reason"), f"{kw}: reason 누락"
        assert isinstance(meta.get("height"), bool), f"{kw}: height 플래그 누락"


def test_ranked_items_do_not_leak_internal_keys():
    """응답 계약 — ranked 항목은 name/severity/action만(내부 reason·플래그 비노출)."""
    out = resolve_dominant_constraint(["개발제한구역"], north_distance_m=None, slope_pct=None)
    for r in out["ranked"]:
        assert set(r) == {"name", "severity", "action"}, f"계약 밖 키: {set(r)}"


def test_duplicate_regulations_are_deduped():
    """VWorld가 같은 designation을 중복/공백변형으로 반환해도 랭킹·높이 항목이 1건이다.

    ★R1 LOW-10: 종전 dedup 키는 원문(strip만)이라 "고도지구"와 "고도 지구"가 서로 다른 항목으로
    남아 중복 표기됐다(classify는 공백을 제거하고 매칭하므로 같은 규제인데). 단언도 `<= 2`라
    그 중복을 통과시켰다 — dedup 키를 classify와 같은 정규화로 맞추고 `== 1`로 잠근다.
    """
    out = resolve_dominant_constraint(
        ["고도지구", "고도지구", " 고도지구 ", "고도 지구"], north_distance_m=None, slope_pct=None,
    )
    assert len(out["height"]["items"]) == 1, f"높이 항목 중복: {out['height']['items']}"
    assert len(out["ranked"]) == 1, f"랭킹 중복: {out['ranked']}"


# ── ⑨ ★R1 MEDIUM-5/6: 정직 고지(상시 커버리지·양방향 근사 오차) ──────────────
def test_height_block_always_discloses_coverage():
    """★incomplete=False라도 "이게 전부"가 아님을 **상시** 고지한다(거짓 완전성 차단).

    미반영 규정군(가로구역별 최고높이 §60·지구단위계획 지정높이·채광방향 이격 §86②·조례
    최고높이)은 애초에 items에 들어오지 않으므로 incomplete가 잡지 못한다.
    """
    # 정북일조 단독(incomplete=False) — 가장 위험한 케이스: "높이 상한 30m"이 확정처럼 읽힌다.
    solo = resolve_dominant_constraint([], north_distance_m=15.0, slope_pct=None)
    assert solo["height"]["incomplete"] is False
    note = solo["height"]["coverage_note"]
    assert note, "정북일조 단독일 때 커버리지 고지가 비면 거짓 완전성"
    for missing in ("가로구역", "지구단위계획", "채광방향", "조례"):
        assert missing in note, f"미반영 항목 누락: {missing}"
    # 미보유 항목이 있는 케이스에도 동일하게 붙는다(조건부 아님).
    mixed = resolve_dominant_constraint(["고도지구"], north_distance_m=15.0, slope_pct=None)
    assert mixed["height"]["coverage_note"] == note


def test_sunlight_note_discloses_error_in_both_directions():
    """근사 오차는 양방향 — 한쪽만 고지하면 반대 방향 오차를 숨긴다(R1 M-6)."""
    out = resolve_dominant_constraint([], north_distance_m=15.0, slope_pct=None)
    note = out["height"]["items"][0]["note"]
    assert "낮아질" in note, "부정형·실제 배치로 낮아질 수 있음(과대 방향) 고지 누락"
    assert "높아질" in note, "북측 도로·공지 완화로 높아질 수 있음(과소 방향) 고지 누락"


_IRREGULAR_L_SHAPE = {
    # L자형 — bbox는 30m×35m인데 실면적은 그 절반 남짓(불규칙도 약 0.5).
    "type": "Polygon",
    "coordinates": [[[127.1, 37.3], [127.1004, 37.3], [127.1004, 37.30013],
                     [127.1002, 37.30013], [127.1002, 37.30027],
                     [127.1, 37.30027], [127.1, 37.3]]],
}


def test_irregular_parcel_gets_overestimation_warning():
    """부정형 필지는 bbox 남북깊이가 실제 배치 정북거리를 과대평가 — 경고를 붙인다."""
    from app.services.site_score.solar_envelope_service import dims_from_polygon

    irr = dims_from_polygon(_IRREGULAR_L_SHAPE)["irregularity"]
    assert irr >= dc.IRREGULARITY_WARN, f"픽스처가 부정형이 아니다(불규칙도 {irr})"

    out = build_for_parcel(
        regulations=[], zone_type="제2종일반주거지역", geometry=_IRREGULAR_L_SHAPE,
    )
    note = out["height"]["items"][0]["note"]
    # 판별어는 "과대평가"/"불규칙도" — 기본 근사문구에 이미 "부정형"이 들어 있어 그 단어로는
    # 경고 유무를 구분할 수 없다(가드가 늘 통과하는 공허진리가 된다).
    assert "불규칙도" in note and "과대평가" in note, f"부정형 경고 누락: {note}"

    # 직사각 필지엔 그 경고가 붙지 않는다(과잉 고지도 정직이 아니다).
    rect = build_for_parcel(regulations=[], zone_type="제2종일반주거지역", geometry=_SQUARE_30M)
    rect_note = rect["height"]["items"][0]["note"]
    assert "불규칙도" not in rect_note and "과대평가" not in rect_note, rect_note
