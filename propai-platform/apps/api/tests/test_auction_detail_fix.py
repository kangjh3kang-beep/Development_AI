"""경매 3버그 수정 단위테스트 — 무목업·외부 실호출 금지(픽스처/직접 호출만).

검증 범위:
  1) est_win 숫자화: _attach_est_win 이 est_win 을 객체가 아닌 숫자(중앙값)로,
     범위는 est_win_low/est_win_high 별도키로 부착. 감정가 없으면 None.
  2) getCltrBidInf2 정규화: _normalize_bid_info 가 유찰누적횟수·면적·이미지URL·
     이전입찰내역을 추출하고, 무자료/이미지없음은 None(가짜 금지).
  3) 키 없음 → get_cltr_bid_info unavailable(가짜 금지).
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.services.auction.auction_service import AuctionStep1Service  # noqa: E402
from app.services.auction.onbid_client import OnbidClient  # noqa: E402


# ── 1) est_win 숫자화 ──
def test_attach_est_win_returns_number_not_object():
    """프론트 NaN 방지: est_win 은 숫자(중앙값), 범위는 별도키."""
    row = {
        "appraisal_price": 1_000_000_000,
        "min_bid_price": 700_000_000,
        "kind": "apt",
        "region_sido": "서울",
        "fail_count": 1,
    }
    out = AuctionStep1Service._attach_est_win(dict(row))
    # 핵심: est_win 은 dict 가 아니라 숫자.
    assert isinstance(out["est_win"], int)
    assert not isinstance(out["est_win"], dict)
    assert isinstance(out["est_win_low"], int)
    assert isinstance(out["est_win_high"], int)
    assert out["est_win_low"] <= out["est_win"] <= out["est_win_high"]
    # 메타(신뢰도·가정)는 별도 키로 보존.
    assert out["est_win_detail"]["est_win_mid"] == out["est_win"]
    assert out["est_win_detail"]["is_estimate"] is True


def test_attach_est_win_no_appraisal_is_none():
    """감정가 미연동 물건은 est_win=None(가짜 금지, 필터에서 제외용)."""
    out = AuctionStep1Service._attach_est_win({"appraisal_price": None, "kind": "land"})
    assert out["est_win"] is None
    assert out["est_win_low"] is None
    assert out["est_win_high"] is None


# ── 2) getCltrBidInf2 정규화 ──
def test_normalize_bid_info_real_fields():
    """유찰누적횟수(최대)·면적·이미지URL·이전입찰내역 추출."""
    rows = [
        {
            "pbctNo": "1",
            "usbdNcumNft": "1",
            "lowstBidPrc": "700,000,000원",
            "opbdDt": "202605201000",
            "pbctStatNm": "유찰",
            "ldaQ": "84.93",
            "bldSqms": "59.82",
            "apslEvlAmt": "1000000000",
            "cltrUsgSclsCtgrNm": "아파트",
            "onbidCltrNm": "서울특별시 강남구 역삼동 123 아파트",
            "cltrImgUrlAdr": "https://img.onbid.co.kr/abc.jpg",
        },
        {
            "pbctNo": "2",
            "usbdNcumNft": "2",
            "lowstBidPrc": "630,000,000원",
            "opbdDt": "202606101000",
            "pbctStatNm": "입찰진행중",
        },
    ]
    out = OnbidClient._normalize_bid_info(rows, "2026-00100-001", "0002")
    assert out["cltr_mng_no"] == "2026-00100-001"
    assert out["pbct_cdtn_no"] == "0002"
    assert out["fail_count"] == 2  # 누적 최대.
    assert out["land_area"] == 84.93
    assert out["bld_area"] == 59.82
    assert out["appraisal_price"] == 1_000_000_000
    assert out["image_url"] == "https://img.onbid.co.kr/abc.jpg"
    assert out["kind"] == "apt"
    assert out["region_sido"] == "서울"
    assert out["round_count"] == 2
    assert len(out["prev_bids"]) == 2
    assert out["prev_bids"][0]["min_bid_price"] == 700_000_000


def test_normalize_bid_info_no_image_is_none():
    """이미지 없으면 None(가짜 금지)."""
    rows = [{"pbctNo": "1", "lowstBidPrc": "100000000", "pbctStatNm": "유찰"}]
    out = OnbidClient._normalize_bid_info(rows, "X", "Y")
    assert out["image_url"] is None
    assert out["land_area"] is None
    assert out["appraisal_price"] is None


# ── 3) 키 없음 → unavailable ──
@pytest.mark.asyncio
async def test_get_cltr_bid_info_no_key_unavailable():
    client = OnbidClient(service_key=None)
    res = await client.get_cltr_bid_info("2026-00100-001", "0001")
    assert res["item"] is None
    assert res["data_source"] == "unavailable"
    assert "인증키" in res["reason"]


@pytest.mark.asyncio
async def test_get_cltr_bid_info_missing_params_unavailable():
    client = OnbidClient(service_key="DUMMY")
    res = await client.get_cltr_bid_info("", "")
    assert res["item"] is None
    assert res["data_source"] == "unavailable"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
