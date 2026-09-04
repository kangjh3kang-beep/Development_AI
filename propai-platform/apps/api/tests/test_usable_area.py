"""S3-B 실사용가능용지(usable_area) 3계층 정산 + S3-C 제외 what-if 재정산 — TDD.

계약(MULTI_PARCEL_ATTRIBUTES_PLAN_2026-07-03 §S3-B/§S3-C):
  · gross / usable_confirmed(POSSIBLE·CAUTION) / usable_conditional(PRECONDITION·CONDITIONAL·
    NEEDS_OFFICIAL_SURVEY — 조건 목록 동반) / excluded(BLOCKED + 도로·구거·하천 지목 — 사유 명세).
  · 임의 감보 계수 금지(무날조) — 도로·구거·하천은 전액 제외 + 합필 가능성 honest 고지.
  · simulate_exclusion: 순수 재정산 비교표(면적 3계층까지만 — 통합한도 재산정은 호출부 소관).
  · 게이트 문자열 계약은 special_parcel.py SSOT와 일치해야 한다(계약 테스트로 고정).
"""
import copy

import pytest

from app.services.zoning.usable_area import (
    EXCLUDED_LAND_CATEGORIES,
    GATE_BLOCK_DEVELOPABILITY,
    GATE_BLOCK_RESOLVABLE,
    GATE_TENTATIVE_DEVELOPABILITY,
    GATE_TENTATIVE_RESOLVABLE,
    compute_usable_area,
    simulate_exclusion,
)


def _p(pnu: str, area: float | None, cat: str = "대",
       dev: str | None = None, res: str | None = None, **kw) -> dict:
    """필지 dict 빌더 — detect_multi_parcel per_parcel 유사 형상(special 중첩)."""
    p: dict = {"pnu": pnu, "land_category": cat}
    if area is not None:
        p["area_sqm"] = area
    if dev is not None or res is not None:
        p["special"] = {"developability": dev or "POSSIBLE",
                        "resolvable": res or "YES", "factors": []}
    p.update(kw)
    return p


def _mixed_set() -> list[dict]:
    """계획서 TDD 시나리오: 정상2 + 도로1 + 임야1 + 농지1."""
    return [
        _p("1111010100100010000", 100.0, "대"),                                # 정상(특이 없음)
        _p("1111010100100020000", 200.0, "대", dev="CAUTION", res="YES"),      # 정상(경미)
        _p("1111010100100030000", 50.0, "도로", dev="BLOCKED", res="NO"),      # 도로 지목
        _p("1111010100100040000", 300.0, "임야", dev="NEEDS_OFFICIAL_SURVEY"), # 임야
        _p("1111010100100050000", 150.0, "전", dev="CONDITIONAL", res="YES"),  # 농지
    ]


# ── 게이트 문자열 계약: special_parcel.py SSOT와 일치(문자 단위) ──────────────

def test_gate_contract_matches_special_parcel_ssot():
    from app.services.zoning import special_parcel as sp

    assert GATE_BLOCK_DEVELOPABILITY == sp.GATE_BLOCK_DEVELOPABILITY
    assert GATE_BLOCK_RESOLVABLE == sp.GATE_BLOCK_RESOLVABLE
    assert GATE_TENTATIVE_DEVELOPABILITY == sp.GATE_TENTATIVE_DEVELOPABILITY
    assert GATE_TENTATIVE_RESOLVABLE == sp.GATE_TENTATIVE_RESOLVABLE


# ── S3-B 3계층 정산 ──────────────────────────────────────────────────────────

def test_mixed_set_three_tier_settlement():
    out = compute_usable_area(_mixed_set())
    assert out["parcel_count"] == 5
    assert out["gross_sqm"] == pytest.approx(800.0)
    assert out["usable_confirmed_sqm"] == pytest.approx(300.0)   # 대100 + 대(CAUTION)200
    assert out["usable_conditional_sqm"] == pytest.approx(450.0)  # 임야300 + 전150
    assert out["excluded_sqm"] == pytest.approx(50.0)             # 도로50
    # 3계층 합 == gross (면적 보존 불변식)
    assert (out["usable_confirmed_sqm"] + out["usable_conditional_sqm"]
            + out["excluded_sqm"]) == pytest.approx(out["gross_sqm"])
    # 조건부 필지는 조건 목록 동반(비어있으면 설명가능성 위반)
    assert len(out["conditional_parcels"]) == 2
    for cp in out["conditional_parcels"]:
        assert cp["conditions"], "조건부 필지는 조건 목록이 비어있으면 안 됨"
    # 제외 필지는 사유 명세 동반
    assert len(out["excluded_parcels"]) == 1
    exc = out["excluded_parcels"][0]
    assert exc["pnu"] == "1111010100100030000"
    assert exc["reasons"] and all(r.get("code") and r.get("detail") for r in exc["reasons"])


def test_all_blocked():
    parcels = [
        _p("A", 100.0, "학교용지", dev="BLOCKED", res="NO"),
        _p("B", 200.0, "대", dev="BLOCKED", res="NO"),
    ]
    out = compute_usable_area(parcels)
    assert out["usable_confirmed_sqm"] == pytest.approx(0.0)
    assert out["usable_conditional_sqm"] == pytest.approx(0.0)
    assert out["excluded_sqm"] == pytest.approx(300.0)
    assert len(out["excluded_parcels"]) == 2


def test_all_normal():
    parcels = [_p("A", 120.5, "대"), _p("B", 79.5, "대")]
    out = compute_usable_area(parcels)
    assert out["gross_sqm"] == pytest.approx(200.0)
    assert out["usable_confirmed_sqm"] == pytest.approx(200.0)
    assert out["usable_conditional_sqm"] == pytest.approx(0.0)
    assert out["excluded_sqm"] == pytest.approx(0.0)
    assert out["conditional_parcels"] == []
    assert out["excluded_parcels"] == []


def test_non_buildable_land_categories_and_codes_excluded():
    # 지목 전명칭 + 공부 지목부호(도로→도, 구거→구, 하천→천) 모두 전액 제외.
    for cat in ("도로", "구거", "하천", "도", "구", "천"):
        out = compute_usable_area([_p("X", 100.0, cat)])
        assert out["excluded_sqm"] == pytest.approx(100.0), cat
        assert out["usable_confirmed_sqm"] == pytest.approx(0.0), cat
    # '대'는 제외 아님(부호 오탐 방어).
    out = compute_usable_area([_p("X", 100.0, "대")])
    assert out["excluded_sqm"] == pytest.approx(0.0)
    assert {"도로", "구거", "하천"} <= EXCLUDED_LAND_CATEGORIES


def test_resolvable_no_is_excluded_even_without_blocked():
    # gate_decision 의미 보존: developability가 잠정이어도 resolvable=NO면 BLOCK.
    out = compute_usable_area([_p("A", 100.0, "대", dev="CONDITIONAL", res="NO")])
    assert out["excluded_sqm"] == pytest.approx(100.0)
    assert out["usable_conditional_sqm"] == pytest.approx(0.0)


def test_conditions_are_grade_specific():
    out = compute_usable_area([
        _p("P1", 100.0, "학교용지", dev="PRECONDITION"),
        _p("P2", 100.0, "임야", dev="NEEDS_OFFICIAL_SURVEY"),
        _p("P3", 100.0, "전", dev="CONDITIONAL"),
    ])
    conds = {cp["pnu"]: " ".join(cp["conditions"]) for cp in out["conditional_parcels"]}
    assert "도시계획" in conds["P1"] or "시설폐지" in conds["P1"]
    assert "산림" in conds["P2"] or "산지" in conds["P2"]
    assert "인허가" in conds["P3"] or "전용" in conds["P3"]


def test_missing_area_is_honest_not_fabricated():
    parcels = [_p("A", 100.0, "대"), _p("B", None, "대")]
    out = compute_usable_area(parcels)
    # 미확보 면적은 0으로 날조하지 않고 별도 명세 + 경고.
    assert out["gross_sqm"] == pytest.approx(100.0)
    assert [x["pnu"] for x in out["area_unknown_parcels"]] == ["B"]
    assert any("면적" in w for w in out["warnings"])


def test_no_arbitrary_reduction_coefficient_and_honest_notes():
    out = compute_usable_area(_mixed_set())
    # 도로는 전액(50.0 그대로) 제외 — 부분 차감 계수 없음.
    assert out["excluded_parcels"][0]["area_sqm"] == pytest.approx(50.0)
    notes = " ".join(out["honest_notes"])
    assert "감보" in notes            # 정밀 감보율 미산정 사유
    assert "합필" in notes or "합병" in notes  # 도로·구거 합필 시 포함 가능성 고지
    assert "확정 아님" in notes or "잠정" in notes  # 조건부 면적 정직 라벨


def test_accepts_per_parcel_shape_and_camel_area():
    # detect_multi_parcel per_parcel 형상(special=None=일상) + areaSqm 키 호환.
    parcels = [
        {"index": 0, "pnu": "A", "address": "x", "land_category": "대",
         "special": None, "areaSqm": 100.0},
        {"index": 1, "pnu": "B", "address": "y", "land_category": "대",
         "special": {"developability": "PRECONDITION", "resolvable": "CONDITIONAL",
                     "factors": [{"category": "도시계획시설(학교) 부지"}]},
         "areaSqm": 200.0},
    ]
    out = compute_usable_area(parcels)
    assert out["usable_confirmed_sqm"] == pytest.approx(100.0)
    assert out["usable_conditional_sqm"] == pytest.approx(200.0)
    # factor category가 조건 상세에 반영(설명가능성).
    joined = " ".join(out["conditional_parcels"][0]["conditions"])
    assert "학교" in joined


def test_empty_input():
    out = compute_usable_area([])
    assert out["parcel_count"] == 0
    assert out["gross_sqm"] == pytest.approx(0.0)
    assert out["usable_confirmed_sqm"] == pytest.approx(0.0)


# ── S3-C 제외 시나리오 what-if ───────────────────────────────────────────────

def test_simulate_exclusion_recompute():
    parcels = _mixed_set()
    sim = simulate_exclusion(parcels, ["1111010100100030000"])  # 도로 제외
    assert sim["applied_exclude_pnus"] == ["1111010100100030000"]
    assert sim["not_found_pnus"] == []
    assert sim["lost_area_sqm"] == pytest.approx(50.0)
    assert sim["before"]["gross_sqm"] == pytest.approx(800.0)
    assert sim["after"]["gross_sqm"] == pytest.approx(750.0)
    assert sim["after"]["excluded_sqm"] == pytest.approx(0.0)
    # usable(확정+조건부)은 도로 제외로 변하지 않음(재정산 일치).
    assert sim["after"]["usable_confirmed_sqm"] == pytest.approx(300.0)
    assert sim["after"]["usable_conditional_sqm"] == pytest.approx(450.0)
    assert sim["delta"]["gross_sqm"] == pytest.approx(-50.0)
    assert sim["delta"]["excluded_sqm"] == pytest.approx(-50.0)
    assert sim["remaining_parcel_count"] == 4
    # before는 원본 전체 재정산과 일치.
    assert sim["before"] == compute_usable_area(parcels)


def test_simulate_exclusion_empty_and_all():
    parcels = _mixed_set()
    empty = simulate_exclusion(parcels, [])
    assert empty["applied_exclude_pnus"] == []
    assert empty["after"] == empty["before"]
    assert all(v == pytest.approx(0.0) for v in empty["delta"].values())

    everything = simulate_exclusion(parcels, [p["pnu"] for p in parcels])
    assert everything["remaining_parcel_count"] == 0
    assert everything["after"]["gross_sqm"] == pytest.approx(0.0)
    assert everything["lost_area_sqm"] == pytest.approx(800.0)


def test_simulate_exclusion_not_found_pnu_is_honest():
    sim = simulate_exclusion(_mixed_set(), ["9999999999999999999"])
    assert sim["not_found_pnus"] == ["9999999999999999999"]
    assert sim["applied_exclude_pnus"] == []
    assert sim["after"] == sim["before"]


def test_purity_inputs_not_mutated():
    parcels = _mixed_set()
    snapshot = copy.deepcopy(parcels)
    compute_usable_area(parcels)
    simulate_exclusion(parcels, [parcels[0]["pnu"]])
    assert parcels == snapshot


# ── 2026-08-02: '모르는 것'을 '가능'으로 세지 않는다 ──────────────────────────
#
# 배경: 다필지 detect 경로는 지목·용도지구 미확인 필지를 만나면 상위 집계를 UNKNOWN으로
# **정직하게** 강등하고 per_parcel에 analysis_status="unanalyzed"를 심는다. 그런데 면적
# 정산은 그 신호를 하나도 읽지 않아, 미분석 필지가 usable_confirmed(통상 개발가능 면적)에
# 그대로 합산됐다. 게이트 기본값이 POSSIBLE이라 '신호 부재'와 '가능'이 구분되지 않은 것이 근원.

def test_unknown_developability_is_not_counted_as_confirmed():
    """UNKNOWN(판정 불가)은 확정이 아니라 조건부로 센다.

    ★변이-kill: GATE_TENTATIVE_DEVELOPABILITY에서 "UNKNOWN"을 빼면 else 분기로 떨어져
      confirmed에 합산되므로 이 단언이 깨진다.
    """
    # ★res는 일부러 정상값(YES)으로 둔다. res="UNKNOWN"으로 두면 resolvable 게이트가 대신
    #   조건부로 내려줘서, developability 게이트를 지워도 테스트가 통과한다(변이로 확인).
    out = compute_usable_area([_p("1111010100100010000", 500.0, "대", dev="UNKNOWN", res="YES")])

    assert out["usable_confirmed_sqm"] == pytest.approx(0.0), (
        "판정 불가(UNKNOWN) 필지가 확정 개발가능 면적에 합산됐다 — '모르는 것'을 '가능'으로 단정."
    )
    assert out["usable_conditional_sqm"] == pytest.approx(500.0)
    conds = out["conditional_parcels"][0]["conditions"]
    assert any("판정하지 못했습니다" in c for c in conds), f"사유 문구 부재: {conds}"


def test_unanalyzed_parcel_is_not_counted_as_confirmed():
    """analysis_status='unanalyzed'는 게이트 값과 무관하게 확정으로 올리지 않는다.

    ★이 필지는 게이트가 기본값(POSSIBLE/YES)이라 종전에는 confirmed로 셌다. 상위 집계만
      정직하고 면적은 낙관이던 비대칭을 잠근다.
    """
    out = compute_usable_area([
        _p("1111010100100010000", 400.0, "대"),                                  # 정상
        _p("1111010100100020000", 600.0, "대", analysis_status="unanalyzed"),    # 미분석
    ])

    assert out["usable_confirmed_sqm"] == pytest.approx(400.0), (
        "미분석 필지가 확정 면적에 합산됐다 — 상위 집계는 UNKNOWN으로 정직 고지하는데 "
        "면적 정산만 그 신호를 무시하는 상태."
    )
    assert out["usable_conditional_sqm"] == pytest.approx(600.0)
    conds = out["conditional_parcels"][0]["conditions"]
    assert any("분석되지 않았습니다" in c for c in conds), f"사유 문구 부재: {conds}"
    # 면적 보존 불변식은 그대로 성립해야 한다.
    assert out["gross_sqm"] == pytest.approx(1000.0)


def test_gate_decision_downgrades_unknown_to_tentative():
    """공유 SSOT gate_decision도 UNKNOWN을 PASS로 보지 않는다(근원 봉합 확인).

    ★usable_area만 고치면 auto_recommend_top3·integrated_recommender 등 다른 소비처는
      여전히 확신 %를 낸다. 근원은 special_parcel의 게이트 집합이므로 거기서 잠근다.
    """
    from app.services.zoning.special_parcel import gate_decision

    assert gate_decision("UNKNOWN", "UNKNOWN") == "TENTATIVE"
    assert gate_decision("UNKNOWN", "YES") == "TENTATIVE"
    # 무회귀: 기존 계약은 그대로.
    assert gate_decision("POSSIBLE", "YES") == "PASS"
    assert gate_decision("BLOCKED", "YES") == "BLOCK"
    assert gate_decision("NEEDS_OFFICIAL_SURVEY", "YES") == "TENTATIVE"


def test_unknown_resolvable_is_not_counted_as_confirmed():
    """해결가능성 UNKNOWN도 확정으로 세지 않는다(developability 축과 별개로 잠금)."""
    out = compute_usable_area([_p("1111010100100010000", 300.0, "대", dev="POSSIBLE", res="UNKNOWN")])
    assert out["usable_confirmed_sqm"] == pytest.approx(0.0)
    assert out["usable_conditional_sqm"] == pytest.approx(300.0)


def test_rank_treats_unknown_as_tentative_grade():
    """다요인 필지에서 '판정 불가'가 '문제 없음'에 밀리지 않는다.

    ★_RANK에 UNKNOWN이 없으면 `.get(dev, 0)`이 0(POSSIBLE 동급)이라, POSSIBLE 요인과
      UNKNOWN 요인이 함께 있을 때 max()가 POSSIBLE을 골라 종합 게이트가 낙관으로 굳는다.
    """
    from app.services.zoning.special_parcel import _RANK

    assert _RANK.get("UNKNOWN", 0) == 2, "UNKNOWN이 미등재라 POSSIBLE과 동급으로 취급된다"
    assert _RANK["UNKNOWN"] > _RANK["POSSIBLE"]
    assert _RANK["UNKNOWN"] < _RANK["BLOCKED"]


# ── 2026-08-02 R1 봉합: 순서 역전 — 표식이 소비처보다 늦게 붙던 문제 ──────────
#
# 종전에는 `/special-parcels` 라우터가 detect_multi_parcel() **반환 후**에
# analysis_status="unanalyzed" 를 심었다. 그런데 면적 3계층 정산(compute_usable_area)은
# 그 함수 **안에서** 이미 끝난 뒤였다 — 소비처가 표식을 영원히 못 봤고, 미분석 필지 면적이
# 그대로 '확정 개발가능'에 합산됐다.
#
# ★아래 테스트는 compute_usable_area를 직접 부르지 않는다. detect_multi_parcel을 통과시켜
#   **실제 파이프라인 순서**로 검증한다. 합성 픽스처로 compute_usable_area만 부르면 죽은
#   경로를 잠그게 되고(가짜 골든), 순서 역전을 영원히 못 잡는다.

def test_detect_multi_parcel_excludes_unanalyzed_from_confirmed():
    """파이프라인 통합 오라클 — 미분석 필지가 usable_confirmed에 합산되지 않는다."""
    from app.services.zoning.special_parcel import detect_multi_parcel

    out = detect_multi_parcel([
        {"pnu": "a", "land_category": "대", "zone_type": "제2종일반주거지역", "area_sqm": 400.0},
        {"pnu": "b", "area_sqm": 600.0},  # 지목·용도지구·용도지역 전무 = 미분석
    ])
    u = out["usable_area"]

    assert u["usable_confirmed_sqm"] == pytest.approx(400.0), (
        "미분석 필지(600㎡)가 확정 개발가능 면적에 합산됐다 — 표식이 정산보다 늦게 붙는 "
        "순서 역전이 재발했다."
    )
    assert u["usable_conditional_sqm"] == pytest.approx(600.0)
    assert out["per_parcel"][1].get("analysis_status") == "unanalyzed"
    conds = u["conditional_parcels"][0]["conditions"]
    assert any("분석되지 않았습니다" in c for c in conds), f"사유 문구 부재: {conds}"


def test_unanalyzed_judgement_is_ssot():
    """미분석 판정이 SSOT 함수로 노출돼 라우터 우회 호출부도 같은 기준을 쓴다."""
    from app.services.zoning.special_parcel import is_unanalyzed_parcel

    assert is_unanalyzed_parcel({"pnu": "x"}) is True
    # 신호가 하나라도 있으면 미분석이 아니다(과잉 강등 방지).
    assert is_unanalyzed_parcel({"land_category": "대"}) is False
    assert is_unanalyzed_parcel({"zone_type": "제2종일반주거지역"}) is False
    assert is_unanalyzed_parcel({"special_districts": ["개발제한구역"]}) is False


def test_normal_parcels_are_not_downgraded():
    """★오탐 0 — 정상 필지만 있으면 종전대로 전부 확정으로 센다(과잉 강등 회귀 방지)."""
    from app.services.zoning.special_parcel import detect_multi_parcel

    out = detect_multi_parcel([
        {"pnu": "a", "land_category": "대", "zone_type": "제2종일반주거지역", "area_sqm": 400.0},
        {"pnu": "b", "land_category": "대", "zone_type": "제2종일반주거지역", "area_sqm": 600.0},
    ])
    assert out["usable_area"]["usable_confirmed_sqm"] == pytest.approx(1000.0)
    assert out["usable_area"]["usable_conditional_sqm"] == pytest.approx(0.0)


def test_unanalyzed_parcel_degrades_top_level_gate():
    """★R1 HIGH — 미분석 필지가 있으면 SSOT가 '특이 없음(PASS)'으로 단정하지 않는다.

    종전에는 이 판정이 라우터에만 있어서, detect_multi_parcel()을 직접 부르는 경로
    (integrated_recommender·persona runner·design_ingest·decision_brief)에서는 무정보 필지에도
    POSSIBLE/PASS가 그대로 나왔다 — 게이트 집합에 UNKNOWN을 넣어도 **그 값을 만드는 곳이
    없으면** 전파되지 않는다.
    """
    from app.services.zoning.special_parcel import detect_multi_parcel, gate_decision

    out = detect_multi_parcel([
        {"pnu": "a", "land_category": "대", "zone_type": "제2종일반주거지역", "area_sqm": 400.0},
        {"pnu": "b", "area_sqm": 600.0},  # 미분석
    ])
    assert out["developability"] == "UNKNOWN", "미분석이 섞였는데 개발가능으로 단정했다"
    assert gate_decision(out["developability"], out["resolvable"]) == "TENTATIVE", (
        "게이트가 PASS(일상 개발부지)로 나와 확신 %가 그대로 산출된다"
    )
    assert "제약이 없다는 뜻이" in out["honest_disclosure"]


def test_unanalyzed_does_not_downgrade_normal_only_set():
    """★오탐 0 — 정상 필지만이면 종전 계약(POSSIBLE/PASS) 그대로."""
    from app.services.zoning.special_parcel import detect_multi_parcel, gate_decision

    out = detect_multi_parcel([
        {"pnu": "a", "land_category": "대", "zone_type": "제2종일반주거지역", "area_sqm": 400.0},
    ])
    assert out["developability"] == "POSSIBLE"
    assert out["resolvable"] == "YES"
    assert gate_decision(out["developability"], out["resolvable"]) == "PASS"


def test_unanalyzed_does_not_weaken_stronger_gate():
    """미분석 강등이 더 무거운 게이트(BLOCKED 등)를 **약화시키지 않는다**."""
    from app.services.zoning.special_parcel import detect_multi_parcel

    out = detect_multi_parcel([
        {"pnu": "a", "land_category": "도로", "zone_type": "제2종일반주거지역", "area_sqm": 100.0},
        {"pnu": "b", "area_sqm": 600.0},  # 미분석
    ])
    # 도로 지목 등으로 산출된 게이트가 UNKNOWN(2)보다 무거우면 그대로 유지돼야 한다.
    from app.services.zoning.special_parcel import _RANK
    assert _RANK.get(out["developability"], 0) >= _RANK["UNKNOWN"], (
        f"미분석 강등이 더 무거운 게이트를 약화시켰다: {out['developability']}"
    )
    # ★이 픽스처는 상향 분기(_RANK < UNKNOWN)에 **도달하지 않는다** — 도로 지목이
    #   PRECONDITION(rank 3)을 내기 때문이다. 즉 이 단언은 '약화 금지' 한 방향만 본다.
    #   반대 방향(가벼운 게이트를 UNKNOWN까지 **올리는지**)은 아래 테스트가 따로 잠근다.
    assert _RANK.get(out["developability"], 0) > _RANK["UNKNOWN"], (
        "픽스처가 상향 분기에 도달해버렸다 — 이 테스트의 전제(더 무거운 게이트)가 깨졌다"
    )


def test_unanalyzed_lifts_lighter_gate_to_unknown():
    """★가벼운 게이트는 '판정 불가'까지 **올린다** — 못 본 필지가 있는데 CAUTION으로 단정 금지.

    2026-08-05 R2 적대검증 MEDIUM: 이 상향 라인을 지워도 저장소의 어떤 테스트도 깨지지
    않았다(변이 생존). 종전 회귀락의 픽스처가 PRECONDITION(rank 3)을 내서 분기에 아예
    도달하지 못했기 때문이다 — **통과는 '옳아서'가 아니라 '그 경로를 안 타서'였다.**
    도달하는 픽스처(성장관리계획구역 = CAUTION, rank 1)로 반대 방향을 잠근다.
    """
    from app.services.zoning.special_parcel import _RANK, detect_multi_parcel, gate_decision

    light_only = detect_multi_parcel([
        {"pnu": "a", "land_category": "대", "zone_type": "제2종일반주거지역",
         "special_districts": ["성장관리계획구역"], "area_sqm": 100.0},
    ])
    # 전제 확인 — 이 픽스처가 정말 UNKNOWN보다 가벼운 게이트를 낸다(공허 방지).
    assert _RANK.get(light_only["developability"], 0) < _RANK["UNKNOWN"], light_only["developability"]

    with_unanalyzed = detect_multi_parcel([
        {"pnu": "a", "land_category": "대", "zone_type": "제2종일반주거지역",
         "special_districts": ["성장관리계획구역"], "area_sqm": 100.0},
        {"pnu": "b", "area_sqm": 600.0},  # 미분석
    ])
    assert with_unanalyzed["developability"] == "UNKNOWN"
    assert gate_decision(with_unanalyzed["developability"], with_unanalyzed["resolvable"]) != "PASS"
