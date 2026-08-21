"""온비드 공고목록(getPbancList2) 실연동 파서 단위 테스트 — 무목업·외부 실호출 금지.

검증 범위(★저장된 실제 JSON 형태 픽스처/직접 호출만 — 외부 호출 없음):
  1) _normalize: 공고관리번호·주소(onbidPbancNm)·처분방식·입찰기간·개찰일시·기관 추출.
  2) 취소공고(pbancKindNm "취소") 필터링 → None.
  3) _extract_items: 단건 dict 방어적 리스트화 / resultCode!=00 에러 / 무자료.
  4) 기본 날짜범위(_default_date_window) 실시간 생성(공고일 과거~오늘, 개찰 오늘~미래).
  5) 미연동 필드(감정가·최저입찰가·유찰횟수) → None(가짜 금지).
  6) 키 없음 → unavailable.
"""

import os
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.services.auction.onbid_client import OnbidClient  # noqa: E402

# ── 픽스처: getPbancList2 실응답 형태(resultType=json) ──
# header.resultCode "00", body.items.item[] (단건이면 dict).
SAMPLE_LIST_JSON = """
{
  "response": {
    "header": {"resultCode": "00", "resultMsg": "NORMAL_CODE"},
    "body": {
      "items": {
        "item": [
          {
            "pbancMngNo": "2026-01000-001",
            "onbidPbancNo": "202600001",
            "pbctNo": "0001",
            "pbancKindCd": "0001",
            "pbancKindNm": "일반공고",
            "prptDivCd": "0007",
            "prptDivNm": "아파트",
            "dspsMthodCd": "0001",
            "dspsMthodNm": "매각",
            "bidDivCd": "0001",
            "bidDivNm": "전자입찰",
            "onbidPbancNm": "서울특별시 강남구 역삼동 100-1 아파트",
            "orgNm": "한국자산관리공사",
            "pbancYmd": "20260520",
            "cltrBidBgngDt": "202606101000",
            "cltrBidEndDt": "202606121700",
            "cltrOpbdDt": "202606130200"
          },
          {
            "pbancMngNo": "2026-01000-002",
            "pbctNo": "0001",
            "pbancKindNm": "취소공고",
            "prptDivNm": "토지",
            "dspsMthodNm": "매각",
            "onbidPbancNm": "경기도 화성시 봉담읍 200 토지(취소)",
            "orgNm": "한국자산관리공사",
            "pbancYmd": "20260521",
            "cltrBidBgngDt": "202606101000",
            "cltrBidEndDt": "202606121700"
          }
        ]
      }
    }
  }
}
"""

# 단건(dict) 응답 — 방어적 리스트화 검증.
SAMPLE_SINGLE_JSON = """
{
  "response": {
    "header": {"resultCode": "00", "resultMsg": "NORMAL_CODE"},
    "body": {
      "items": {
        "item": {
          "pbancMngNo": "2026-09000-009",
          "pbctNo": "0002",
          "pbancKindNm": "일반공고",
          "prptDivNm": "근린생활시설",
          "dspsMthodNm": "매각",
          "onbidPbancNm": "부산광역시 해운대구 우동 50 상가",
          "orgNm": "부산광역시",
          "pbancYmd": "20260601",
          "cltrBidBgngDt": "202606200900",
          "cltrBidEndDt": "202606221700",
          "cltrOpbdDt": "202606230200"
        }
      }
    }
  }
}
"""


# ── 1) _normalize: 공고 필드 추출 ──

def test_normalize_extracts_pbanc_fields():
    items, reason = OnbidClient._extract_items(SAMPLE_LIST_JSON)
    assert reason is None
    norm = [OnbidClient._normalize(it) for it in items]
    norm = [n for n in norm if n is not None]
    # 취소공고 1건 필터 → 1건만 남음.
    assert len(norm) == 1
    a = norm[0]
    assert a["source"] == "onbid"
    assert a["item_no"] == "2026-01000-001-0001"        # 공고관리번호-공매재산번호.
    assert a["pbanc_mng_no"] == "2026-01000-001"
    assert a["kind"] == "apt"                            # 아파트 → apt.
    assert a["kind_name"] == "아파트"
    assert a["address"] == "서울특별시 강남구 역삼동 100-1 아파트"
    assert a["status"] == "매각"                          # 처분방식명.
    assert a["org"] == "한국자산관리공사"
    assert a["bid_start"] == datetime(2026, 6, 10, 10, 0).isoformat()
    assert a["bid_end"] == datetime(2026, 6, 12, 17, 0).isoformat()
    assert a["opbd_dt"] == datetime(2026, 6, 13, 2, 0).isoformat()
    assert a["pbanc_ymd"] == datetime(2026, 5, 20).isoformat()


# ── 2) 취소공고 필터 ──

def test_normalize_filters_cancelled():
    cancelled = {
        "pbancMngNo": "X", "pbancKindNm": "취소공고",
        "prptDivNm": "토지", "onbidPbancNm": "취소건",
    }
    assert OnbidClient._normalize(cancelled) is None


# ── 3) _extract_items: 단건 dict 방어 / 에러 / 무자료 ──

def test_extract_single_dict_defensive():
    items, reason = OnbidClient._extract_items(SAMPLE_SINGLE_JSON)
    assert reason is None
    assert isinstance(items, list) and len(items) == 1
    assert items[0]["pbancMngNo"] == "2026-09000-009"


def test_extract_error_and_empty():
    err = '{"response":{"header":{"resultCode":"30","resultMsg":"SERVICE_KEY_IS_NOT_REGISTERED_ERROR"}}}'
    items, reason = OnbidClient._extract_items(err)
    assert items == [] and reason and "30" in reason
    # 무자료(items 비어있음).
    empty = '{"response":{"header":{"resultCode":"00"},"body":{"items":""}}}'
    items, reason = OnbidClient._extract_items(empty)
    assert items == [] and reason is None


# ── 4) 기본 날짜범위 실시간 생성 ──

def test_default_date_window_is_realtime():
    w = OnbidClient._default_date_window()
    today = datetime.now().strftime("%Y%m%d")
    assert w["pbancYmdEnd"] == today
    assert w["opbdDtStart"] == today
    assert w["bidPrdYmdStart"] == today
    # 공고일 시작은 과거, 개찰/입찰 종료는 미래.
    assert w["pbancYmdStart"] < today
    assert w["opbdDtEnd"] > today
    assert w["bidPrdYmdEnd"] > today
    # 8자리 yyyyMMdd 형식.
    for v in w.values():
        assert len(v) == 8 and v.isdigit()


# ── 5) 미연동 필드는 None(가짜 금지) ──

def test_unlinked_price_fields_are_none():
    items, _ = OnbidClient._extract_items(SAMPLE_SINGLE_JSON)
    a = OnbidClient._normalize(items[0])
    assert a["appraisal_price"] is None
    assert a["min_bid_price"] is None
    assert a["fail_count"] is None


# ── 6) 키 없음 → unavailable ──

@pytest.mark.asyncio
async def test_fetch_items_no_key_unavailable():
    client = OnbidClient(service_key="")
    res = await client.fetch_items(region="서울", rows=50)
    assert res["data_source"] == "unavailable"
    assert res["items"] == []
    assert res["total"] == 0
    assert "미설정" in res["reason"]


# ──────────────────────────────────────────────────────────────────
# XML 파서 강화 (2026-08-20 · Bandit B314)
# ──────────────────────────────────────────────────────────────────


# ★엔티티가 **마크업으로** 확장되는지를 결과로 드러내는 페이로드.
#   확장되면 응답에 **없던 item 이 목록에 생긴다** — 단순 DoS 가 아니라 **데이터 위조**다.
_엔티티_주입 = (
    '<?xml version="1.0"?>'
    '<!DOCTYPE response [<!ENTITY inj "<item><PLNM_NO>BOOM</PLNM_NO></item>">]>'
    "<response><header><resultCode>00</resultCode></header>"
    "<body><items>&inj;</items></body></response>"
)

_정상_XML = (
    "<response><header><resultCode>00</resultCode></header>"
    "<body><items>"
    "<item><PLNM_NO>1</PLNM_NO></item>"
    "<item><PLNM_NO>2</PLNM_NO></item>"
    "</items></body></response>"
)


def test_외부_XML응답_파서가_엔티티_주입을_거부한다() -> None:
    """★온비드 응답은 **외부 입력**이다. 표준 `xml.etree` 로 파싱하면 위험하다.

    실측(CPython 3.10)으로 표준 파서의 **실제 면역 범위**를 확인했다 —
    *"면역을 거짓 주장하지 마라"* 는 규율대로 추측하지 않고 재 봤다.

    | 공격 | 표준 `xml.etree` | `defusedxml` |
    |---|---|---|
    | XXE(파일 읽기) | `undefined entity` 로 **거부** | 거부 |
    | SSRF(외부 URL) | **거부** | 거부 |
    | billion laughs(엔티티 폭탄) | **확장됨**(3단계 1000자) | `EntitiesForbidden` |
    | **엔티티 → 마크업 주입** | **확장됨 — 없던 item 이 생긴다** | `EntitiesForbidden` |

    표준 파서는 XXE 는 막아도 **엔티티 확장은 막지 않는다**. 마지막 줄이 특히 나쁘다:
    응답에 **없던 매물이 목록에 들어온다**(DoS 가 아니라 **데이터 위조**).

    ★이 락의 첫 판은 `items == []` 만 봤는데 **변이가 통과했다** — 폭탄이든 아니든
      `items` 는 어차피 비어서 단언이 **원리적으로 위반 불가**였다(공허한 참).
      그래서 **확장 여부가 결과에 드러나는** 페이로드로 바꿨다: 확장되면 `BOOM` 이
      목록에 나타나므로, 표준 파서로 되돌리는 순간 이 락이 깨진다.
    """
    items, _reason = OnbidClient._extract_items(_엔티티_주입)
    주입된 = [str(it) for it in items if "BOOM" in str(it)]
    assert not 주입된, (
        "엔티티가 확장되어 **응답에 없던 항목이 생겼다** — 파서가 defused 가 아니다: "
        f"{주입된!r}"
    )


def test_정상_XML응답은_그대로_파싱된다_대조군() -> None:
    """★위 락은 *무엇이든 거부하는 파서*라도 초록이 된다 — 그러면 **기능이 죽은 것을
    보안이라고 부르게 된다**. 그래서 정상 응답이 실제로 파싱되는지 함께 본다.

    이 대조군이 깨지면 위 락의 초록은 아무 의미가 없다.
    """
    items, reason = OnbidClient._extract_items(_정상_XML)
    assert reason is None, f"정상 응답인데 오류로 판정했다: {reason}"
    assert len(items) == 2, f"항목 2개가 나와야 한다 — 실제 {len(items)}개: {items!r}"
