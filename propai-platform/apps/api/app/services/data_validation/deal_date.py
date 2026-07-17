"""실거래 거래일자 파싱 — 표기 형태가 다양한 deal_date 문자열에서 연/월/일을 추출한다.

MOLIT 실거래 deal_date는 소비처마다 표기가 다르다('2024년 3월 15일' 등, 일자 생략도 있음).
정렬(최신순 절단 방지)과 연월 라벨링('YYYY-MM') 모두 이 정규식 하나로 처리해, 같은 파싱 로직이
market_report_service(_deal_ym)·nearby_map_service(거래 최신순 정렬) 등 여러 곳에 따로
구현되어 표기가 갈라지지 않게 한다(프론트 MarketInsightsWorkspaceClient.parseDealDate와도
동일 산식).
"""
from __future__ import annotations

import re
from typing import Any

_DEAL_DATE_RE = re.compile(r"(\d{4})\D+(\d{1,2})(?:\D+(\d{1,2}))?")


def parse_deal_date(deal_date: Any) -> tuple[int, int, int] | None:
    """거래일 문자열 → (year, month, day) 정렬키.

    일자가 없는 표기('2024-03' 등)는 day=1로 채운다(같은 달 내 정렬은 안정 정렬에 맡김).
    파싱 실패·월/일 범위 이탈 시 None(무날조 — 임의 날짜로 채우지 않는다).
    """
    if not deal_date:
        return None
    m = _DEAL_DATE_RE.search(str(deal_date))
    if not m:
        return None
    y, mo = int(m.group(1)), int(m.group(2))
    if not (1 <= mo <= 12):
        return None
    d = int(m.group(3)) if m.group(3) else 1
    if not (1 <= d <= 31):
        d = 1
    return (y, mo, d)


def deal_ym(deal_date: Any) -> str | None:
    """거래일 문자열 → 'YYYY-MM'. 파싱 실패/월범위 이탈 시 None."""
    key = parse_deal_date(deal_date)
    if not key:
        return None
    y, mo, _d = key
    return f"{y}-{mo:02d}"
