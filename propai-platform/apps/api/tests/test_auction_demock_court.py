"""경공매 무목업 + 법원경매 스크래퍼 파서 단위 테스트.

검증 범위(★외부 실호출 없음 — 저장된 샘플 HTML 픽스처/직접 호출만):
  1) 온비드 클라이언트: 키 없음 → data_source="unavailable" + 빈 items(가짜 0건).
  2) 온비드 _extract_items: 무자료/오류 응답 → 빈 리스트(가짜 생성 금지).
  3) 법원경매 parse_list_html: 샘플 HTML 픽스처 파싱(정상/무자료/JS-only).
  4) 법원경매 parse_detail_html: 부분 dict 파싱.
  5) CourtAuctionScraper 지연(_sleep) 로직 호출 검증(실제 sleep은 0으로 단축).
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.services.auction.court_scraper import (  # noqa: E402
    CourtAuctionScraper,
    parse_detail_html,
    parse_list_html,
)
from app.services.auction.onbid_client import OnbidClient  # noqa: E402


# ── 픽스처: 저장된 샘플 HTML(목업데이터 생성이 아니라 파서 검증용) ──

SAMPLE_LIST_HTML = """
<html><body>
<table class="court-list">
  <tr class="court-auction-item" data-case-no="2026타경1234">
    <td data-field="kind">아파트</td>
    <td data-field="sido">서울</td>
    <td data-field="sigungu">강남구</td>
    <td data-field="address">서울 강남구 역삼동 100-1</td>
    <td data-field="appraisal">1,200,000,000</td>
    <td data-field="min_bid">768,000,000</td>
    <td data-field="fail_count">2</td>
    <td data-field="status">진행</td>
    <td data-field="bid_date">2026.07.15</td>
    <td data-field="court">서울중앙지방법원</td>
  </tr>
  <tr class="court-auction-item" data-case-no="2026타경5678">
    <td data-field="kind">토지</td>
    <td data-field="sido">경기</td>
    <td data-field="address">경기 화성시 봉담읍 200</td>
    <td data-field="appraisal">540,000,000</td>
    <td data-field="min_bid">540,000,000</td>
    <td data-field="fail_count">0</td>
  </tr>
</table>
</body></html>
"""

# JS/세션 의존 화면(데이터가 스크립트로만 채워짐) — 파서는 빈 결과 반환해야 함.
SAMPLE_JS_ONLY_HTML = """
<html><body>
<div id="root"></div>
<script>window.__DATA__ = {items: []};</script>
</body></html>
"""

SAMPLE_DETAIL_HTML = """
<html><body>
<div data-detail data-appraisal="1,200,000,000" data-min-bid="768,000,000"
     data-fail-count="2" data-address="서울 강남구 역삼동 100-1 상세"></div>
</body></html>
"""


# ── 1) 온비드: 키 없음 → unavailable(빈 결과, 가짜 0건) ──

@pytest.mark.asyncio
async def test_onbid_no_key_returns_unavailable():
    client = OnbidClient(service_key="")
    res = await client.fetch_items(region="서울", rows=50)
    assert res["data_source"] == "unavailable"
    assert res["items"] == []
    assert res["total"] == 0
    assert "미설정" in res["reason"]


# ── 2) 온비드 _extract_items: 무자료/오류 → 빈 리스트 ──

def test_onbid_extract_items_empty_and_error():
    assert OnbidClient._extract_items("") == []
    assert OnbidClient._extract_items("not-json-not-xml") == []
    # 에러 바디(JSON, items 없음) → 빈 리스트
    err = '{"response":{"header":{"resultCode":"99"},"body":{}}}'
    assert OnbidClient._extract_items(err) == []
    # 정상 단건(dict) → 1건 리스트화
    ok = '{"response":{"body":{"items":{"item":{"CLTR_NO":"1"}}}}}'
    parsed = OnbidClient._extract_items(ok)
    assert len(parsed) == 1 and parsed[0]["CLTR_NO"] == "1"


# ── 3) 법원경매 목록 파서 ──

def test_court_parse_list_fixture():
    items = parse_list_html(SAMPLE_LIST_HTML)
    assert len(items) == 2
    first = items[0]
    assert first["source"] == "court"
    assert first["item_no"] == "2026타경1234"
    assert first["kind"] == "apt"
    assert first["region_sido"] == "서울"
    assert first["appraisal_price"] == 1_200_000_000
    assert first["min_bid_price"] == 768_000_000
    assert first["fail_count"] == 2
    assert first["bid_end"] == "2026-07-15T00:00:00"
    assert first["court_name"] == "서울중앙지방법원"
    # 둘째 행: 토지 kind 매핑.
    assert items[1]["kind"] == "land"


def test_court_parse_list_empty_and_js_only():
    # 무목업: 빈/JS-only HTML이면 가짜 없이 빈 리스트.
    assert parse_list_html("") == []
    assert parse_list_html(SAMPLE_JS_ONLY_HTML) == []


# ── 4) 법원경매 상세 파서 ──

def test_court_parse_detail_fixture():
    d = parse_detail_html(SAMPLE_DETAIL_HTML)
    assert d["appraisal_price"] == 1_200_000_000
    assert d["min_bid_price"] == 768_000_000
    assert d["fail_count"] == 2
    assert "상세" in d["address"]
    assert parse_detail_html("") == {}


# ── 5) 스크래퍼 지연(_sleep) 로직 호출 검증 ──

def test_court_scraper_applies_delay(monkeypatch):
    scraper = CourtAuctionScraper(delay_sec=1.5, delay_jitter=0.8)
    calls = {"n": 0, "last": 0.0}

    def fake_sleep(sec):
        calls["n"] += 1
        calls["last"] = sec

    monkeypatch.setattr("app.services.auction.court_scraper.time.sleep", fake_sleep)
    scraper._sleep()
    assert calls["n"] == 1
    # delay_sec(1.5) <= 실제 지연 <= delay_sec + jitter(2.3)
    assert 1.5 <= calls["last"] <= 2.3


def test_court_scraper_fetch_blocked_returns_unavailable(monkeypatch):
    """차단/실패(_fetch=None) 시 가짜 없이 빈 결과 + reason."""
    scraper = CourtAuctionScraper()
    monkeypatch.setattr(scraper, "_fetch", lambda *a, **k: None)
    res = scraper.fetch_items(region="서울")
    assert res["data_source"] == "unavailable"
    assert res["items"] == []
    assert "reason" in res
