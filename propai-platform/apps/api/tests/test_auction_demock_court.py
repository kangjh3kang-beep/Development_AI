"""경공매 무목업 + 법원경매 스크래퍼 파서 단위 테스트.

검증 범위(★외부 실호출 없음 — 저장된 샘플 JSON 픽스처/직접 호출만):
  1) 온비드 클라이언트: 키 없음 → data_source="unavailable" + 빈 items(가짜 0건).
  2) 온비드 _extract_items: 무자료/오류 응답 → 빈 리스트(가짜 생성 금지).
  3) 법원경매 parse_search_result: 라이브 JSON 응답(searchControllerMain) 파싱(정상/무자료/보안차단).
     ※ 과거 BeautifulSoup HTML 파서(parse_list_html/parse_detail_html)는 ed2c5bd2에서 JSON API로
       대체됨 → 현 정본 parse_search_result(+_normalize_row)로 검증 갱신(필드추출 의도 통합 보존).
  4) CourtAuctionScraper 지연(_sleep) 로직 호출 검증(실제 sleep은 0으로 단축).
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.services.auction.court_scraper import (  # noqa: E402
    CourtAuctionScraper,
    parse_search_result,
)
from app.services.auction.onbid_client import OnbidClient  # noqa: E402

# ── 픽스처: 저장된 샘플 JSON(라이브 searchControllerMain 응답 형태 — 파서 검증용) ──

SAMPLE_SEARCH_PAYLOAD = {
    "data": {
        "dma_pageInfo": {"totalCnt": "29032"},
        "dlt_srchResult": [
            {"srnSaNo": "2021타경105850", "maemulSer": "1", "dspslUsgNm": "아파트",
             "hjguSido": "서울", "hjguSigu": "강남구", "printSt": "서울 강남구 역삼동 100-1",
             "gamevalAmt": "1,200,000,000", "minmaePrice": "768,000,000", "yuchalCnt": "2",
             "maeGiil": "20260715", "jiwonNm": "서울중앙지방법원", "mulStatcd": "01"},
            {"srnSaNo": "2026타경5678", "maemulSer": "1", "dspslUsgNm": "토지",
             "hjguSido": "경기", "printSt": "경기 화성시 봉담읍 200",
             "gamevalAmt": "540,000,000", "minmaePrice": "540,000,000", "yuchalCnt": "0"},
        ],
    }
}

# 보안정책 차단(ipcheck=false) — 무목업: 빈 결과 + blocked + 차단 사유 정직 노출.
SAMPLE_BLOCKED_PAYLOAD = {"data": {"ipcheck": False}, "message": "보안정책에 의하여 차단"}


# ── 1) 온비드: 키 없음 → unavailable(빈 결과, 가짜 0건) ──

@pytest.mark.asyncio
async def test_onbid_no_key_returns_unavailable():
    client = OnbidClient(service_key="")
    res = await client.fetch_items(region="서울", rows=50)
    assert res["data_source"] == "unavailable"
    assert res["items"] == []
    assert res["total"] == 0
    assert "미설정" in res["reason"]


# ── 2) 온비드 _extract_items: 무자료/오류 → 빈 리스트 + (err) ──

def test_onbid_extract_items_empty_and_error():
    # 반환은 (items, error_reason) 튜플.
    assert OnbidClient._extract_items("") == ([], None)
    assert OnbidClient._extract_items("not-json-not-xml") == ([], None)
    # 에러 바디(JSON, resultCode!=00) → 빈 리스트 + error_reason.
    err = '{"response":{"header":{"resultCode":"99","resultMsg":"ERR"},"body":{}}}'
    items, reason = OnbidClient._extract_items(err)
    assert items == [] and reason and "99" in reason
    # 정상 단건(dict) → 1건 리스트화.
    ok = '{"response":{"header":{"resultCode":"00"},"body":{"items":{"item":{"pbancMngNo":"1"}}}}}'
    items, reason = OnbidClient._extract_items(ok)
    assert reason is None and len(items) == 1 and items[0]["pbancMngNo"] == "1"


# ── 3) 법원경매 JSON 응답 파서(parse_search_result) ──

def test_court_parse_search_fixture():
    parsed = parse_search_result(SAMPLE_SEARCH_PAYLOAD)
    assert parsed["blocked"] is False and parsed["reason"] is None
    assert parsed["total"] == 29032
    items = parsed["items"]
    assert len(items) == 2
    first = items[0]
    assert first["source"] == "court"
    assert first["item_no"] == "2021타경105850-1"   # docid 없으면 사건번호-물건순번
    assert first["kind"] == "apt"
    assert first["region_sido"] == "서울"
    assert first["appraisal_price"] == 1_200_000_000
    assert first["min_bid_price"] == 768_000_000
    assert first["fail_count"] == 2
    assert first["bid_end"] == "2026-07-15"          # 신 파서는 date.isoformat()
    assert first["court_name"] == "서울중앙지방법원"
    # 둘째 행: 토지 kind 매핑.
    assert items[1]["kind"] == "land"


def test_court_parse_empty_and_blocked():
    # 무목업: 형식오류/무자료 → 가짜 없이 빈 결과 + reason.
    empty = parse_search_result({})
    assert empty["items"] == [] and empty["reason"]
    # 보안정책 차단(ipcheck=false) → 빈 결과 + blocked + 차단 사유 정직 노출.
    blocked = parse_search_result(SAMPLE_BLOCKED_PAYLOAD)
    assert blocked["items"] == [] and blocked["blocked"] is True and "차단" in blocked["reason"]


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
    """수집 실패(_request=None) 시 가짜 없이 빈 결과 + reason(JSON 재구현 후 _fetch→_request)."""
    scraper = CourtAuctionScraper()
    # _request가 None이면(HTTP오류/비JSON) 무자료 → unavailable. 세션GET 실패·httpx 미설치도 동일 경로.
    monkeypatch.setattr(scraper, "_request", lambda *a, **k: None)
    res = scraper.fetch_items(region="서울")
    assert res["data_source"] == "unavailable"
    assert res["items"] == []
    assert "reason" in res
