"""공용 거래일 파싱 유틸(app.services.data_validation.deal_date) 단위테스트.

market_report_service._deal_ym(경쟁단지 최근거래월)과 nearby_map_service._finalize(거래
최신순 정렬)가 공유하는 단일 정규식/파싱 로직. 프론트 MarketInsightsWorkspaceClient의
parseDealDate와 동일 산식(연·월·일 3그룹, 일자 생략 허용)이어야 한다.
"""
from __future__ import annotations

from app.services.data_validation.deal_date import deal_ym, parse_deal_date


def test_parse_deal_date_full_ymd():
    assert parse_deal_date("2024년 3월 15일") == (2024, 3, 15)


def test_parse_deal_date_year_month_only_defaults_day_to_one():
    assert parse_deal_date("2024년 12월") == (2024, 12, 1)


def test_parse_deal_date_rejects_invalid_month():
    assert parse_deal_date("2024년 13월") is None


def test_parse_deal_date_rejects_garbage_and_empty():
    assert parse_deal_date("abc") is None
    assert parse_deal_date(None) is None
    assert parse_deal_date("") is None


def test_deal_ym_matches_legacy_market_report_behavior():
    """market_report_service의 구 _deal_ym과 동일 계약(_deal_ym 삭제 후 이 함수로 대체)."""
    assert deal_ym("2024년 3월 15일") == "2024-03"
    assert deal_ym("2024년 12월") == "2024-12"
    assert deal_ym("2024년 1월 5일") == "2024-01"
    assert deal_ym("abc") is None
    assert deal_ym(None) is None
    assert deal_ym("") is None
    assert deal_ym("2024년 13월") is None
