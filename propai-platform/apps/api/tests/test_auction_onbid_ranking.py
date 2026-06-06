"""온비드 순위(getInqRnkClg)·물건입찰결과목록(getCltrBidRsltList2)·낙찰가능가 단위테스트.

★무목업·외부 실호출 금지 — 저장된 실응답 형태(resultType=json) 픽스처/직접 호출만.

검증 범위:
  1) _normalize_ranking: 순위(sn)·감정가(apslEvlAmt)·할인율(feeRate)·용도(대/중/소)·
     주소(onbidCltrNm)·상태(pbctStatNm)·썸네일 추출, "비공개" 최저입찰가 → None.
  2) _normalize_bid_result: 유찰횟수(usbdNft)·감정가·최저입찰가·낙찰가율·낙찰가·면적·
     개찰일·입찰결과 파싱.
  3) win_estimator: 감정가+유찰횟수 → est_win 범위(저~고).
  4) _parse_amount: "비공개"·콤마/통화 → 정수|None.
  5) 키 없음 / 무자료 → unavailable(가짜 금지).
  6) _sido_from_address: 주소 선두 시도 정규화.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.services.auction.onbid_client import (  # noqa: E402
    OnbidClient,
    _parse_amount,
    _parse_int,
    _parse_rate,
    _sido_from_address,
)
from app.services.auction.win_estimator import estimate_win_price  # noqa: E402


# ── 픽스처: getInqRnkClg 실응답 형태(resultType=json) ──
SAMPLE_RANK_JSON = """
{
  "response": {
    "header": {"resultCode": "00", "resultMsg": "NORMAL_CODE"},
    "body": {
      "items": {
        "item": [
          {
            "sn": "1",
            "cltrMngNo": "2026-00100-001",
            "pbctCdtnNo": "0001",
            "cltrBidBgngDt": "202606101000",
            "cltrBidEndDt": "202606121700",
            "prptDivNm": "압류재산",
            "dspsMthodNm": "매각",
            "cltrUsgLclsCtgrNm": "부동산",
            "cltrUsgMclsCtgrNm": "토지",
            "cltrUsgSclsCtgrNm": "대지",
            "onbidCltrNm": "인천광역시 서구 마전동 1126-10 대지",
            "apslEvlAmt": "350000000",
            "lowstBidPrcIndctCont": "245,000,000원",
            "feeRate": "30",
            "thnlImgUrlAdr": "https://img.onbid.co.kr/x.jpg",
            "pbctStatNm": "입찰진행중"
          },
          {
            "sn": "2",
            "cltrMngNo": "2026-00100-002",
            "pbctCdtnNo": "0001",
            "cltrUsgLclsCtgrNm": "부동산",
            "cltrUsgMclsCtgrNm": "건물",
            "cltrUsgSclsCtgrNm": "아파트",
            "onbidCltrNm": "서울특별시 강남구 역삼동 100-1 아파트",
            "apslEvlAmt": "1200000000",
            "lowstBidPrcIndctCont": "비공개",
            "feeRate": "0",
            "pbctStatNm": "입찰진행중"
          }
        ]
      }
    }
  }
}
"""

# ── 픽스처: getCltrBidRsltList2 실응답 형태(유찰/낙찰가율) ──
SAMPLE_BIDRSLT_JSON = """
{
  "response": {
    "header": {"resultCode": "00", "resultMsg": "NORMAL_CODE"},
    "body": {
      "items": {
        "item": [
          {
            "cltrMngNo": "2025-09000-007",
            "pbctNo": "0003",
            "prptDivNm": "압류재산",
            "dspsMthodNm": "매각",
            "cltrUsgLclsCtgrNm": "부동산",
            "cltrUsgMclsCtgrNm": "토지",
            "cltrUsgSclsCtgrNm": "전",
            "onbidCltrNm": "경기도 화성시 봉담읍 200 전",
            "usbdNft": "2",
            "ldaQ": "660.5",
            "bldSqms": "0",
            "apslEvlAmt": "500000000",
            "lowstBidPrc": "320000000",
            "opbdDt": "202605201000",
            "pbctStatNm": "낙찰",
            "scsbidRate": "88.4",
            "scsbidAmt": "442000000",
            "vldBidrCnt": "5"
          }
        ]
      }
    }
  }
}
"""


# ── 1) 순위 정규화 ──

def test_normalize_ranking_real_fields():
    items, reason = OnbidClient._extract_items(SAMPLE_RANK_JSON)
    assert reason is None
    norm = [OnbidClient._normalize_ranking(it) for it in items]
    assert all(n is not None for n in norm)
    a = norm[0]
    assert a["source"] == "onbid"
    assert a["item_no"] == "2026-00100-001-0001"
    assert a["rank"] == 1
    assert a["appraisal_price"] == 350000000          # 감정가 실값.
    assert a["min_bid_price"] == 245000000            # "245,000,000원" → 정수.
    assert a["usage"] == "대지"                        # 소분류 우선.
    assert a["kind"] == "land"                        # 대지 → land.
    assert a["region_sido"] == "인천"                  # 주소 선두 정규화.
    assert a["address"] == "인천광역시 서구 마전동 1126-10 대지"
    assert a["status"] == "입찰진행중"
    assert a["discount_rate"] == 30.0
    assert a["thumbnail"] == "https://img.onbid.co.kr/x.jpg"
    assert a["fail_count"] is None                    # 순위 응답엔 유찰횟수 없음.


def test_normalize_ranking_undisclosed_minbid_is_none():
    items, _ = OnbidClient._extract_items(SAMPLE_RANK_JSON)
    b = OnbidClient._normalize_ranking(items[1])
    assert b["min_bid_price"] is None                 # "비공개" → None(가짜 금지).
    assert b["appraisal_price"] == 1200000000
    assert b["kind"] == "apt"                          # 아파트 → apt.
    assert b["region_sido"] == "서울"


# ── 2) 입찰결과목록 정규화(유찰·낙찰가율) ──

def test_normalize_bid_result_real_fields():
    items, reason = OnbidClient._extract_items(SAMPLE_BIDRSLT_JSON)
    assert reason is None
    a = OnbidClient._normalize_bid_result(items[0])
    assert a["item_no"] == "2025-09000-007-0003"
    assert a["fail_count"] == 2                        # usbdNft 유찰횟수.
    assert a["appraisal_price"] == 500000000
    assert a["min_bid_price"] == 320000000
    assert a["win_rate"] == 88.4                       # 낙찰가율(%).
    assert a["win_price"] == 442000000                 # 낙찰가격.
    assert a["valid_bidder_count"] == 5
    assert a["land_area"] == 660.5
    assert a["status"] == "낙찰"
    assert a["kind"] == "land"                          # 전 → land.
    assert a["region_sido"] == "경기"
    assert a["opbd_dt"] is not None


# ── 3) win_estimator: 감정가 + 유찰횟수 → 범위 ──

def test_win_estimator_with_real_appraisal_and_fail():
    # 입찰결과 픽스처의 실값으로 추정.
    est = estimate_win_price(
        appraisal_price=500000000, min_bid_price=320000000,
        kind="land", region_sido="경기", fail_count=2,
    )
    assert est["is_estimate"] is True
    assert est["est_win_low"] is not None
    assert est["est_win_low"] <= est["est_win_mid"] <= est["est_win_high"]
    # 최저입찰가 이상에서만 낙찰 성립 → 하한 보정.
    assert est["est_win_low"] >= 320000000
    assert est["win_rate_mid"] is not None


def test_win_estimator_no_appraisal_unavailable():
    est = estimate_win_price(appraisal_price=None, kind="land")
    assert est["est_win_mid"] is None
    assert "추정 불가" in est["basis"]


# ── 4) 금액 파서 ──

def test_parse_amount_variants():
    assert _parse_amount("245,000,000원") == 245000000
    assert _parse_amount("비공개") is None
    assert _parse_amount("") is None
    assert _parse_amount(0) is None
    assert _parse_amount(350000000) == 350000000
    assert _parse_int("2") == 2
    assert _parse_int("") is None
    assert _parse_rate("88.4") == 88.4
    assert _parse_rate("30%") == 30.0
    assert _parse_rate("") is None


# ── 5) 키 없음 / 무자료 → unavailable ──

@pytest.mark.asyncio
async def test_fetch_ranking_no_key_unavailable():
    client = OnbidClient(service_key="")
    res = await client.fetch_ranking()
    assert res["data_source"] == "unavailable"
    assert res["items"] == []
    assert "미설정" in res["reason"]


@pytest.mark.asyncio
async def test_fetch_bid_result_list_no_key_unavailable():
    client = OnbidClient(service_key="")
    res = await client.fetch_bid_result_list(filters={"sido": "서울"})
    assert res["data_source"] == "unavailable"
    assert res["items"] == []
    assert "미설정" in res["reason"]


# ── 6) 시도 정규화 ──

def test_sido_from_address():
    assert _sido_from_address("서울특별시 강남구 역삼동") == "서울"
    assert _sido_from_address("경기도 화성시 봉담읍") == "경기"
    assert _sido_from_address("강원특별자치도 춘천시") == "강원"
    assert _sido_from_address("") == ""
