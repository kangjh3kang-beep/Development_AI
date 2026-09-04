"""경쟁 단지 비교표 집계(_build_competitor_complexes) 단위테스트.

검증 축:
  A. 단지명(building_name)별 집계 — 거래건수·거래액가중 평당가·최근 거래월·준공연도.
  B. 평당가 = 거래액가중(Σ가격/(Σ전용면적/평)) — 단순 행평균과 다름을 명시 검증.
  C. price_basis='전용'(molit excluUseAr = 전용면적) 계약.
  D. 상위 N(거래건수 desc, 동률이면 평당가 desc) + top_n 캡.
  E. 유효성 필터 — 빈 단지명·가격<=0·면적<=0 행 드롭(무목업).
  F. 빈/None 입력 → [](정직).
  G. 거래일 파싱(_deal_ym) — 'YYYY년 M월 …' → 'YYYY-MM', 이상값 None.

순수 함수(네트워크·LLM 없음)라 실제로 호출해 결정론 검증한다.
"""
from __future__ import annotations

from app.services.market.market_report_service import (
    PYEONG_SQM,
    _build_competitor_complexes,
    _deal_ym,
)


def _rows() -> list[dict]:
    """molit 아파트 매매 원자료 형태 픽스처(building_name·price_10k_won·area_m2·deal_date·build_year)."""
    return [
        # 래미안: 3건(전용 84/100/84) — 최근 2024-05, 준공 2015
        {"building_name": "래미안", "price_10k_won": 100000, "area_m2": 84.0, "deal_date": "2024년 3월 15일", "build_year": 2015},
        {"building_name": "래미안", "price_10k_won": 120000, "area_m2": 100.0, "deal_date": "2024년 5월 2일", "build_year": 2015},
        {"building_name": "래미안", "price_10k_won": 90000, "area_m2": 84.0, "deal_date": "2024년 4월 10일", "build_year": 2015},
        # 힐스테이트: 2건 — 최근 2024-06, 준공 2020
        {"building_name": "힐스테이트", "price_10k_won": 60000, "area_m2": 59.0, "deal_date": "2024년 2월 1일", "build_year": 2020},
        {"building_name": "힐스테이트", "price_10k_won": 65000, "area_m2": 59.0, "deal_date": "2024년 6월 20일", "build_year": 2020},
        # 자이: 1건 — 준공 2008
        {"building_name": "자이", "price_10k_won": 200000, "area_m2": 120.0, "deal_date": "2024년 1월 5일", "build_year": 2008},
        # ↓ 유효성 필터로 드롭돼야 하는 행들(무목업 — 가짜 단지 금지)
        {"building_name": "", "price_10k_won": 50000, "area_m2": 84.0, "deal_date": "2024년 3월 1일", "build_year": 2000},
        {"building_name": "제로가격", "price_10k_won": 0, "area_m2": 84.0, "deal_date": "2024년 3월 1일", "build_year": 2000},
        {"building_name": "무면적", "price_10k_won": 50000, "area_m2": 0, "deal_date": "2024년 3월 1일", "build_year": 2000},
    ]


def test_aggregates_by_complex_name_with_count_recent_month_and_build_year():
    out = _build_competitor_complexes(_rows())
    # 유효 단지 3개만(빈명·0가격·0면적 드롭)
    assert [c["name"] for c in out] == ["래미안", "힐스테이트", "자이"]  # 거래건수 desc
    a = out[0]
    assert a["deal_count"] == 3
    assert a["recent_deal_ym"] == "2024-05"  # 최근 거래월
    assert a["build_year"] == 2015
    assert a["price_basis"] == "전용"  # 전용면적 기준 계약
    # 힐스테이트 최근월/준공
    assert out[1]["recent_deal_ym"] == "2024-06"
    assert out[1]["build_year"] == 2020


def test_per_pyeong_is_transaction_value_weighted_not_row_mean():
    """평당가는 거래액가중(Σ가격/(Σ면적/평)) — 단순 행평균과 다르다."""
    out = _build_competitor_complexes(_rows())
    a = out[0]
    sum_price = 100000 + 120000 + 90000
    sum_area = 84.0 + 100.0 + 84.0
    expected_weighted = round(sum_price / (sum_area / PYEONG_SQM))
    assert a["avg_per_pyeong_manwon"] == expected_weighted
    # 단순 행평균과는 달라야 함(가중 semantics 증명)
    row_ppgs = [
        100000 / (84.0 / PYEONG_SQM),
        120000 / (100.0 / PYEONG_SQM),
        90000 / (84.0 / PYEONG_SQM),
    ]
    naive_mean = round(sum(row_ppgs) / len(row_ppgs))
    assert expected_weighted != naive_mean


def test_ordering_count_desc_then_per_pyeong_desc():
    """거래건수 동률이면 평당가 높은 단지가 앞선다."""
    rows = [
        # X: 2건, 낮은 평당가
        {"building_name": "X", "price_10k_won": 60000, "area_m2": 84.0, "deal_date": "2024년 1월 1일", "build_year": 2000},
        {"building_name": "X", "price_10k_won": 60000, "area_m2": 84.0, "deal_date": "2024년 2월 1일", "build_year": 2000},
        # Y: 2건, 높은 평당가
        {"building_name": "Y", "price_10k_won": 120000, "area_m2": 84.0, "deal_date": "2024년 1월 1일", "build_year": 2010},
        {"building_name": "Y", "price_10k_won": 120000, "area_m2": 84.0, "deal_date": "2024년 2월 1일", "build_year": 2010},
    ]
    out = _build_competitor_complexes(rows)
    assert [c["name"] for c in out] == ["Y", "X"]  # 동률 → 평당가 desc


def test_top_n_cap():
    out = _build_competitor_complexes(_rows(), top_n=2)
    assert [c["name"] for c in out] == ["래미안", "힐스테이트"]
    # 기본 top_n=8 이하 데이터는 전부 반환
    assert len(_build_competitor_complexes(_rows())) == 3


def test_empty_and_none_return_empty_list():
    assert _build_competitor_complexes([]) == []
    assert _build_competitor_complexes(None) == []
    # 유효행이 하나도 없으면 [](무목업)
    only_invalid = [
        {"building_name": "", "price_10k_won": 100000, "area_m2": 84.0, "deal_date": "2024년 3월 1일", "build_year": 2015},
        {"building_name": "제로", "price_10k_won": 0, "area_m2": 84.0, "deal_date": "2024년 3월 1일", "build_year": 2015},
    ]
    assert _build_competitor_complexes(only_invalid) == []


def test_build_year_uses_most_common_nonzero_and_none_when_absent():
    rows = [
        {"building_name": "Z", "price_10k_won": 100000, "area_m2": 84.0, "deal_date": "2024년 1월 1일", "build_year": 2011},
        {"building_name": "Z", "price_10k_won": 100000, "area_m2": 84.0, "deal_date": "2024년 2월 1일", "build_year": 2011},
        {"building_name": "Z", "price_10k_won": 100000, "area_m2": 84.0, "deal_date": "2024년 3월 1일", "build_year": 0},  # 결측
        {"building_name": "W", "price_10k_won": 100000, "area_m2": 84.0, "deal_date": "2024년 1월 1일", "build_year": 0},  # 전부 결측
    ]
    out = {c["name"]: c for c in _build_competitor_complexes(rows)}
    assert out["Z"]["build_year"] == 2011  # 최빈 non-zero
    assert out["W"]["build_year"] is None  # 준공연도 결측 → None(정직)


def test_deal_ym_parsing():
    assert _deal_ym("2024년 3월 15일") == "2024-03"
    assert _deal_ym("2024년 12월") == "2024-12"
    assert _deal_ym("2024년 1월 5일") == "2024-01"
    assert _deal_ym("abc") is None
    assert _deal_ym(None) is None
    assert _deal_ym("") is None
    assert _deal_ym("2024년 13월") is None  # 월 범위 이탈
