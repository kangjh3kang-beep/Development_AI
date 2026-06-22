"""경공매 무목업 + 법원경매 스크래퍼 파서 단위 테스트.

검증 범위(★외부 실호출 없음 — JSON 픽스처/직접 호출만):
  1) 온비드 클라이언트: 키 없음 → data_source="unavailable" + 빈 items(가짜 0건).
  2) 온비드 _extract_items: 무자료/오류 응답 → 빈 리스트(가짜 생성 금지).
  3) 법원경매 parse_search_result: searchControllerMain.on JSON 응답 정규화
     (정상/무자료/보안차단 ipcheck=false).
  4) 법원경매 _normalize_row: 단행 필드 매핑(용도→kind, 금액/날짜 정규화).
  5) CourtAuctionScraper 지연(_sleep) 로직 + 차단(_request) 시 무목업 빈 결과.

★2026-06-07 모듈 재구현(HTML 스크래퍼 → JSON API)에 맞춰 테스트 정정.
구 parse_list_html/parse_detail_html 제거 → parse_search_result/_normalize_row로 검증.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.services.auction.court_scraper import (  # noqa: E402
    CourtAuctionScraper,
    _normalize_row,
    parse_search_result,
)
from app.services.auction.onbid_client import OnbidClient  # noqa: E402

# ── 픽스처: searchControllerMain.on JSON 응답(라이브 필드명 기준) ──

# 정상 응답: 부동산 2건(아파트/토지). totalCnt=전국 총건수.
SAMPLE_SEARCH_PAYLOAD = {
    "data": {
        "dma_pageInfo": {"totalCnt": "29032"},
        "dlt_srchResult": [
            {
                "docid": "DOC-2026-0001",
                "srnSaNo": "2026타경1234",
                "maemulSer": "1",
                "printSt": "서울 강남구 역삼동 100-1",
                "dspslUsgNm": "아파트",
                "hjguSido": "서울",
                "hjguSigu": "강남구",
                "srchHjguDongCd": "1168010100",
                "gamevalAmt": "1,200,000,000",
                "minmaePrice": "768,000,000",
                "yuchalCnt": "2",
                "mulStatcd": "01",
                "maeGiil": "20260715",
                "jiwonNm": "서울중앙지방법원",
            },
            {
                "srnSaNo": "2026타경5678",
                "maemulSer": "1",
                "convAddr": "경기 화성시 봉담읍 200",
                "dspslUsgNm": "토지",
                "rd1Nm": "경기",
                "gamevalAmt": "540,000,000",
                "minmaePrice": "540,000,000",
                "yuchalCnt": "0",
                "mulStatcd": "01",
            },
        ],
    }
}

# 보안정책 차단 응답(세션쿠키/헤더 누락) — ipcheck=false.
SAMPLE_BLOCKED_PAYLOAD = {
    "data": {"ipcheck": False},
    "message": "보안정책에 의하여 차단되었습니다.",
}

# 무자료 응답(해당 조건 물건 0건) — 가짜 없이 빈 items.
SAMPLE_EMPTY_PAYLOAD = {
    "data": {"dma_pageInfo": {"totalCnt": "0"}, "dlt_srchResult": []},
}


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


# ── 3) 법원경매 검색결과 파서(JSON 응답 정규화) ──

def test_court_parse_search_result_fixture():
    res = parse_search_result(SAMPLE_SEARCH_PAYLOAD)
    assert res["blocked"] is False
    assert res["reason"] is None
    assert res["total"] == 29_032  # 전국 총건수(totalCnt).
    items = res["items"]
    assert len(items) == 2

    first = items[0]
    assert first["source"] == "court"
    assert first["item_no"] == "DOC-2026-0001"  # docid 우선.
    assert first["kind"] == "apt"
    assert first["region_sido"] == "서울"
    assert first["appraisal_price"] == 1_200_000_000
    assert first["min_bid_price"] == 768_000_000
    assert first["fail_count"] == 2
    assert first["bid_end"] == "2026-07-15"  # maeGiil yyyyMMdd → ISO.
    assert first["court_name"] == "서울중앙지방법원"
    assert first["case_no"] == "2026타경1234"

    # 둘째 행: docid 없음 → 사건번호-물건순번 조합 item_no, 토지 kind.
    second = items[1]
    assert second["item_no"] == "2026타경5678-1"
    assert second["kind"] == "land"
    assert second["region_sido"] == "경기"
    assert second["address"] == "경기 화성시 봉담읍 200"  # convAddr 보조.


def test_court_parse_search_result_blocked_and_empty():
    # 보안차단(ipcheck=false): 가짜 없이 빈 items + blocked + reason.
    blocked = parse_search_result(SAMPLE_BLOCKED_PAYLOAD)
    assert blocked["items"] == []
    assert blocked["blocked"] is True
    assert "차단" in blocked["reason"]

    # 무자료: 빈 items, blocked=False(차단이 아니라 단순 0건).
    empty = parse_search_result(SAMPLE_EMPTY_PAYLOAD)
    assert empty["items"] == []
    assert empty["blocked"] is False
    assert empty["total"] == 0

    # 형식 오류(data 없음) → 빈 items + reason.
    bad = parse_search_result({"message": "형식오류"})
    assert bad["items"] == []
    assert bad["reason"]


# ── 4) 법원경매 단행 정규화(_normalize_row) ──

def test_court_normalize_row_fields():
    row = {
        "srnSaNo": "2025타경9999",
        "maemulSer": "2",
        "printSt": "부산 해운대구 우동 1500",
        "dspslUsgNm": "근린상가",
        "hjguSido": "부산",
        "gamevalAmt": "비공개",          # 비공개 → None(가짜 금지).
        "minmaePrice": "0",               # 0 → None.
        "yuchalCnt": "",                  # 빈값 → 0.
        "mulStatcd": "03",                # 종결 → closed.
        "maeGiil": "bad",                 # 형식불일치 → None.
    }
    d = _normalize_row(row)
    assert d["source"] == "court"
    assert d["item_no"] == "2025타경9999-2"
    assert d["kind"] == "building"       # 근린 → building.
    assert d["appraisal_price"] is None
    assert d["min_bid_price"] is None
    assert d["fail_count"] == 0
    assert d["status"] == "closed"
    assert d["bid_end"] is None
    assert d["raw"]["_source"] == "court_scrape"


# ── 5) 스크래퍼 지연(_sleep) 로직 + 차단 시 무목업 빈 결과 ──

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
    """차단/실패(_request=None) 시 가짜 없이 빈 결과 + reason(무목업)."""
    scraper = CourtAuctionScraper(delay_sec=0.0, delay_jitter=0.0)
    # 세션·검색 요청을 모두 무력화: _request가 None(HTTP오류/비-JSON) 반환.
    monkeypatch.setattr(scraper, "_request", lambda *a, **k: None)
    res = scraper.fetch_items(region="서울")
    assert res["data_source"] == "unavailable"
    assert res["items"] == []
    assert "reason" in res
