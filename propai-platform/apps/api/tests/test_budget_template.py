"""수지 예산 표준 템플릿(설계도 §12 FeasibilityTemplate) 회귀가드.

무목업(금액 0)·개발방식별 부담금 포함/제외·그룹 정렬·미등록 폴백을 고정한다.
순수 함수(DB·fastapi 무의존) → 로컬 py3.10 실행 가능.
"""
from __future__ import annotations

from app.services.feasibility.budget_template import (
    METHOD_LABELS,
    get_budget_template,
)

_GROUPS = ["토지비", "공사비", "설계감리비", "각종부담금", "판매관리비",
           "보존등기비", "일반관리비", "제세금", "금융비", "예비비"]


def test_apartment_includes_school_and_metro_charges():
    """공동주택 계열(M06 일반분양) → 학교용지·광역교통 부담금 포함."""
    t = get_budget_template("M06")
    assert t["is_apartment"] is True
    assert t["method_label"] == "일반분양"
    labels = {it["label"] for it in t["items"]}
    assert "학교용지부담금" in labels
    assert "광역교통시설부담금" in labels


def test_non_apartment_excludes_school_and_metro():
    """비주거(M09 지식산업센터) → 학교용지·광역교통 부담금 제외(대상 아님).

    ★재기준(R1 교정): 종전 이 테스트는 M08 오피스텔을 '대상 아님'으로 고정했으나,
    분양형 오피스텔은 준주택 포함 부과 대상(학교용지법 §2 3호·2021.6.23~) — 틀린
    기준선이었다. 비주거 검증은 M09(office)로 대체."""
    t = get_budget_template("M09")
    assert t["is_apartment"] is False
    labels = {it["label"] for it in t["items"]}
    assert "학교용지부담금" not in labels
    assert "광역교통시설부담금" not in labels
    # 공통 부담금(원인자·기반시설)은 유지.
    assert "상수도 원인자부담금" in labels
    assert "기반시설부담금" in labels


def test_officetel_includes_school_site_line():
    """★R1 교정: M08 분양형 오피스텔=준주택 포함 — 학교용지부담금 라인 편입."""
    t = get_budget_template("M08")
    labels = {it["label"] for it in t["items"]}
    assert "학교용지부담금" in labels


def test_no_mockup_all_amounts_zero():
    """★무목업: 모든 라인아이템 금액=0(구조만·금액은 사용자/분석이 채움)."""
    for m in ("M06", "M08", None, "ZZZ"):
        t = get_budget_template(m)
        assert t["items"], f"{m}: 빈 템플릿"
        assert all(it["budget_won"] == 0 for it in t["items"]), f"{m}: 0 아닌 금액 존재"


def test_unknown_method_graceful_fallback():
    """미등록/None method → 비-공동주택 공통 세트 폴백(임의 합성 금지)."""
    t = get_budget_template("ZZZ")
    assert t["is_apartment"] is False
    assert t["method_label"] is None
    assert t["items"]  # 공통 세트는 존재


def test_groups_sorted_and_within_known_set():
    """그룹은 프론트 GROUPS 순서로 정렬되고 알려진 그룹만 사용."""
    t = get_budget_template("M06")
    groups_seq = [it["group"] for it in t["items"]]
    assert set(groups_seq) <= set(_GROUPS)
    idx = [_GROUPS.index(g) for g in groups_seq]
    assert idx == sorted(idx), "그룹 정렬 위반"


def test_method_labels_cover_m01_to_m15():
    """개발방식 라벨은 M01~M15 전수(unit_standards 정합)."""
    assert {f"M{n:02d}" for n in range(1, 16)} <= set(METHOD_LABELS)
