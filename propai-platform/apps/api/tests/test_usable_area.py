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
