"""온비드(KAMCO 공매) OpenAPI 커넥터 — 실연동 전용(무목업).

차세대 온비드 OpenAPI(공공데이터포털 apis.data.go.kr / B010003)의 ★라이브 검증으로
확정된 공고목록 엔드포인트(getPbancList2)를 호출해 전국 공매 부동산 공고를 수집한다.
본 모듈은 ★목업(mock)을 생성하지 않는다:

- 인증키 미설정 → 빈 결과 + data_source="unavailable" + reason(활용신청 필요).
- 호출 실패/무자료 → 빈 결과 + data_source="unavailable" + reason(실패 사유).
- 키가 있고 호출 성공 → 실데이터 정규화 + data_source="onbid_live".

★라이브 검증으로 확정된 사실(컨테이너 실호출로 resultCode "00" NORMAL_CODE 실데이터 확인):
  - 포맷 파라미터는 반드시 `resultType=json`(기존 `type`은 틀림).
  - 공고목록(확정): B010003/OnbidPbancListSrvc2/getPbancList2.
    필수 날짜범위(공고일/개찰일/입찰기간 중 일부)를 비우면
    NO_MANDATORY_REQUEST_PARAMETERS_ERROR → 기본 날짜범위를 datetime.now() 기준 자동 설정.
  - 공고상세(보조): B010003/OnbidPbancDtlInfSrvc2/getPbancDtlInf2 (필수 pbancMngNo).
  - 물건입찰결과상세(보조): B010003/OnbidCltrBidRsltDtlSrvc2/getCltrBidRsltDtl2
    (필수 cltrMngNo + pbctCdtnNo).

★미연동(후속): 부동산 물건목록(감정가·최저입찰가·유찰횟수·낙찰가율)의 엔드포인트는
미확정이라 이번엔 제외한다 → appraisal_price/min_bid_price/fail_count는 None(가짜 금지).

★취소공고(pbancKindNm 에 "취소" 포함)는 정규화 단계에서 필터링한다.

경매(법원)는 court_scraper.py(스크래핑)로 별도 수집하며, 본 모듈은 공매(온비드)만
담당한다(source="onbid").
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

# ── 차세대 온비드 OpenAPI(공공데이터포털 apis.data.go.kr / B010003) ──
ONBID_BASE_URL = "https://apis.data.go.kr/B010003"
# ★라이브 확정 엔드포인트(공고목록).
ONBID_LIST_OP = "OnbidPbancListSrvc2/getPbancList2"
# ★라이브 확정 엔드포인트(순위: 조회수/관심).
ONBID_INQ_RANK_OP = "OnbidInqRnkClgSrvc/getInqRnkClg"          # 조회수 순위.
ONBID_ITRS_RANK_OP = "OnbidItrsCltrRnkClgSrvc/getItrsCltrRnkClg"  # 관심 순위.
# ★라이브 확정 엔드포인트(물건 입찰결과목록: 유찰·낙찰가율·조건검색).
ONBID_BID_RESULT_LIST_OP = "OnbidCltrBidRsltListSrvc2/getCltrBidRsltList2"
# 보조 엔드포인트.
ONBID_PBANC_DETAIL_OP = "OnbidPbancDtlInfSrvc2/getPbancDtlInf2"
ONBID_BID_RESULT_OP = "OnbidCltrBidRsltDtlSrvc2/getCltrBidRsltDtl2"
ONBID_BID_INF_OP = "OnbidCltrBidDtlSrvc2/getCltrBidInf2"

# 순위 조회 물건구분(라이브 확정: cltrDivNm="부동산"만 필요).
CLTR_DIV_REAL_ESTATE = "부동산"

# 입찰결과목록 코드(라이브 확정).
BID_DIV_GENERAL = "0001"  # 입찰구분=일반경쟁.
PBCT_STAT_WIN = "0010"    # 낙찰.
PBCT_STAT_FAIL = "0011"   # 유찰.

# 기본 조회 코드(라이브 확정).
CLTR_TYPE_REAL_ESTATE = "0001"   # 물건종류=부동산.
DSPS_MTHOD_SALE = "0001"         # 처분방식=매각.
BID_DIV_ELECTRONIC = "0001"      # 입찰방식=전자입찰.

# 기본 날짜범위(필수 파라미터 누락 방지 — datetime.now() 기준 실시간).
LOOKBACK_PBANC_DAYS = 90   # 공고일: 최근 90일.
LOOKAHEAD_OPBD_DAYS = 60   # 개찰일/입찰기간: 오늘 ~ +60일.

# 온비드 재산유형명(prptDivNm) → 내부 kind 코드.
KIND_MAP: dict[str, str] = {
    "아파트": "apt",
    "오피스텔": "officetel",
    "토지": "land",
    "대지": "land",
    "임야": "land",
    "전": "land",
    "답": "land",
    "주택": "building",
    "주거용건물": "building",
    "건물": "building",
    "근린생활시설": "building",
    "상가": "building",
    "공장": "factory",
}

# 내부 kind → 온비드 prptDivCd 후보(요청 필터용, 라이브로 확장 가능).
KIND_TO_PRPT_DIV: dict[str, str] = {
    "apt": "0007",
    "officetel": "0005",
}


def normalize_kind(raw: Any) -> str:
    """온비드 재산유형명을 내부 kind 코드로 정규화한다."""
    s = str(raw or "").strip()
    for key, code in KIND_MAP.items():
        if key in s:
            return code
    return "etc"


def _parse_dt(raw: Any) -> Optional[str]:
    """온비드 날짜 문자열을 ISO8601(naive)로 변환한다(실패 시 None).

    입찰기간/개찰일시는 yyyyMMddHHmm, 공고일은 yyyyMMdd 형태가 확정.
    """
    if not raw:
        return None
    s = str(raw).strip()
    if not s or s in {"0", "00000000", "000000000000"}:
        return None
    for fmt in ("%Y%m%d%H%M", "%Y%m%d%H%M%S", "%Y%m%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).isoformat()
        except ValueError:
            continue
    return None


def _parse_amount(raw: Any) -> Optional[int]:
    """금액 문자열을 정수(원)로 파싱한다.

    "비공개"·빈값·숫자 없음 → None(가짜 금지). "1,200,000원" 등 통화/콤마 제거.
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        v = int(raw)
        return v if v > 0 else None
    s = str(raw).strip()
    if not s or "비공개" in s or "미정" in s:
        return None
    digits = "".join(ch for ch in s if ch.isdigit())
    if not digits:
        return None
    v = int(digits)
    return v if v > 0 else None


def _parse_int(raw: Any) -> Optional[int]:
    """정수 파싱(유찰횟수·회차·입찰자수 등). 숫자 없으면 None."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return int(raw)
    s = str(raw).strip()
    if not s:
        return None
    neg = s.startswith("-")
    digits = "".join(ch for ch in s if ch.isdigit())
    if not digits:
        return None
    return -int(digits) if neg else int(digits)


def _parse_rate(raw: Any) -> Optional[float]:
    """낙찰가율/할인율 등 퍼센트 실수 파싱. 숫자 없으면 None."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).strip().replace("%", "").replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _sido_from_address(address: str) -> str:
    """주소 문자열 선두에서 시/도(region_sido)를 추출한다(매칭 실패 시 빈 문자열)."""
    s = (address or "").strip()
    if not s:
        return ""
    first = s.split()[0] if s.split() else ""
    # 광역시/특별시/도 표기 정규화(예: "서울특별시"→"서울", "경기도"→"경기").
    for full, short in (
        ("서울특별시", "서울"), ("부산광역시", "부산"), ("대구광역시", "대구"),
        ("인천광역시", "인천"), ("광주광역시", "광주"), ("대전광역시", "대전"),
        ("울산광역시", "울산"), ("세종특별자치시", "세종"), ("경기도", "경기"),
        ("강원특별자치도", "강원"), ("강원도", "강원"), ("충청북도", "충북"),
        ("충청남도", "충남"), ("전라북도", "전북"), ("전북특별자치도", "전북"),
        ("전라남도", "전남"), ("경상북도", "경북"), ("경상남도", "경남"),
        ("제주특별자치도", "제주"), ("제주도", "제주"),
    ):
        if first.startswith(full):
            return short
    return first[:2] if first else ""


class OnbidClient:
    """온비드 공매 OpenAPI REST 클라이언트 — 실호출 전용(무목업).

    키가 없거나 호출이 실패하면 가짜데이터 대신 빈 결과 + data_source="unavailable"
    + reason 을 반환한다.
    """

    def __init__(self, service_key: Optional[str], timeout: float = 20.0):
        self._service_key = service_key or ""
        self._timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def has_key(self) -> bool:
        return bool(self._service_key)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    @staticmethod
    def _unavailable(reason: str) -> dict[str, Any]:
        """무목업: 가짜데이터 없이 빈 결과 + 사유를 반환한다."""
        return {"items": [], "data_source": "unavailable", "total": 0, "reason": reason}

    @staticmethod
    def _default_date_window() -> dict[str, str]:
        """필수 날짜범위 자동 설정(실시간 datetime.now() 기준).

        - 공고일(pbancYmd): 최근 LOOKBACK_PBANC_DAYS일 ~ 오늘.
        - 개찰일(opbdDt) / 입찰기간(bidPrdYmd): 오늘 ~ +LOOKAHEAD_OPBD_DAYS일
          (현재/임박 공매가 나오도록).
        """
        now = datetime.now()
        pbanc_start = (now - timedelta(days=LOOKBACK_PBANC_DAYS)).strftime("%Y%m%d")
        today = now.strftime("%Y%m%d")
        ahead = (now + timedelta(days=LOOKAHEAD_OPBD_DAYS)).strftime("%Y%m%d")
        return {
            "pbancYmdStart": pbanc_start,
            "pbancYmdEnd": today,
            "opbdDtStart": today,
            "opbdDtEnd": ahead,
            "bidPrdYmdStart": today,
            "bidPrdYmdEnd": ahead,
        }

    # ──────────────────────────────────────────
    # 공매 공고 목록 (실호출 전용 — getPbancList2)
    # ──────────────────────────────────────────

    async def fetch_items(
        self,
        *,
        region: Optional[str] = None,
        kind: Optional[str] = None,
        page: int = 1,
        rows: int = 50,
    ) -> dict[str, Any]:
        """공매 공고 목록을 getPbancList2로 실 API 조회한다(resultType=json).

        반환: {"items": [정규화 dict...], "data_source": "onbid_live"|"unavailable",
               "total": int, "note"|"reason": str}
        키 미설정/호출실패/무자료는 ★가짜데이터 없이 빈 결과 + reason 으로 반환한다.

        - region: 시도/시군구 키워드. getPbancList2엔 지역 전용 파라미터가 없으므로
          물건명(onbidPbancNm) 텍스트 클라이언트 필터로 처리한다.
        - kind: 내부 kind 코드. 매핑 가능하면 prptDivCd 요청 파라미터로,
          그 외엔 정규화 결과 클라이언트 필터로 처리한다.
        - 필수 날짜범위는 _default_date_window()로 실시간 자동 설정한다.
        """
        if not self._service_key:
            return self._unavailable("온비드 인증키 미설정(공공데이터포털 활용신청 필요)")

        params: dict[str, Any] = {
            "serviceKey": self._service_key,
            "pageNo": page,
            "numOfRows": rows,
            "resultType": "json",
            "cltrTypeCd": CLTR_TYPE_REAL_ESTATE,
            "dspsMthodCd": DSPS_MTHOD_SALE,
            "bidDivCd": BID_DIV_ELECTRONIC,
        }
        params.update(self._default_date_window())

        prpt_div = KIND_TO_PRPT_DIV.get(kind or "")
        if prpt_div:
            params["prptDivCd"] = prpt_div
        if region:
            params["onbidPbancNm"] = region

        url = f"{ONBID_BASE_URL}/{ONBID_LIST_OP}"
        try:
            client = await self._get_client()
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            raw_items, err = self._extract_items(resp.text)
            if err:
                return self._unavailable(f"온비드 응답 오류: {err}")
            items = [self._normalize(it) for it in raw_items]
            # 취소공고 제외(정규화에서 None 반환) + 종류 클라필터.
            items = [it for it in items if it is not None]
            if kind:
                items = [it for it in items if it.get("kind") == kind]
            if not items:
                return self._unavailable("온비드 응답 무자료(해당 조건의 공고 없음)")
            return {
                "items": items,
                "data_source": "onbid_live",
                "total": len(items),
                "note": "온비드 OpenAPI getPbancList2 실연동(resultType=json)",
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("온비드 호출 실패(무목업, 빈 결과 반환): %s", str(e)[:160])
            return self._unavailable(f"온비드 호출 실패: {str(e)[:120]}")

    # ──────────────────────────────────────────
    # 순위 (실호출 전용 — getInqRnkClg / getItrsCltrRnkClg)
    # ──────────────────────────────────────────

    async def fetch_ranking(
        self, *, kind: str = CLTR_DIV_REAL_ESTATE, interest: bool = False,
        page: int = 1, rows: int = 50,
    ) -> dict[str, Any]:
        """온비드 부동산 순위를 실 API 조회한다(resultType=json, 무목업).

        - interest=False → 조회수 순위(getInqRnkClg).
        - interest=True  → 관심 순위(getItrsCltrRnkClg).
        파라미터는 매우 단순: cltrDivNm="부동산"만 필요(날짜 불필요·라이브 확정).
        키 미설정/호출실패/무자료 → 빈 결과 + data_source="unavailable" + reason.
        """
        if not self._service_key:
            return self._unavailable("온비드 인증키 미설정(공공데이터포털 활용신청 필요)")

        op = ONBID_ITRS_RANK_OP if interest else ONBID_INQ_RANK_OP
        params: dict[str, Any] = {
            "serviceKey": self._service_key,
            "pageNo": page,
            "numOfRows": rows,
            "resultType": "json",
            "cltrDivNm": kind or CLTR_DIV_REAL_ESTATE,
        }
        url = f"{ONBID_BASE_URL}/{op}"
        try:
            client = await self._get_client()
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            raw_items, err = self._extract_items(resp.text)
            if err:
                return self._unavailable(f"온비드 응답 오류: {err}")
            items = [self._normalize_ranking(it) for it in raw_items]
            items = [it for it in items if it is not None]
            if not items:
                return self._unavailable("온비드 순위 응답 무자료")
            return {
                "items": items,
                "data_source": "onbid_live",
                "total": len(items),
                "by": "interest" if interest else "views",
                "note": (
                    "온비드 OpenAPI "
                    + ("getItrsCltrRnkClg(관심순위)" if interest else "getInqRnkClg(조회수순위)")
                    + " 실연동(resultType=json)"
                ),
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("온비드 순위 호출 실패(무목업, 빈 결과): %s", str(e)[:160])
            return self._unavailable(f"온비드 순위 호출 실패: {str(e)[:120]}")

    # ──────────────────────────────────────────
    # 물건 입찰결과목록 (실호출 전용 — getCltrBidRsltList2)
    # ──────────────────────────────────────────

    async def fetch_bid_result_list(
        self, *, filters: Optional[dict[str, Any]] = None, page: int = 1, rows: int = 50,
    ) -> dict[str, Any]:
        """물건 입찰결과목록을 getCltrBidRsltList2로 실 API 조회한다(resultType=json).

        지역·용도·유찰횟수·감정가·최저입찰가·면적·개찰일·낙찰/유찰 상태 필터를
        파라미터로 매핑한다. getPbancList2처럼 필수 조합(cltrTypeCd=부동산 +
        dspsMthodCd=매각 + 최근 개찰일범위)을 채워 NO_MANDATORY_* 오류를 회피한다.

        키 미설정/호출실패/무자료 → 빈 결과 + data_source="unavailable" + reason.
        """
        if not self._service_key:
            return self._unavailable("온비드 인증키 미설정(공공데이터포털 활용신청 필요)")

        f = dict(filters or {})
        params: dict[str, Any] = {
            "serviceKey": self._service_key,
            "pageNo": page,
            "numOfRows": rows,
            "resultType": "json",
            # mandatory 충족용 기본 조합(부동산·매각·일반경쟁).
            "cltrTypeCd": CLTR_TYPE_REAL_ESTATE,
            "dspsMthodCd": DSPS_MTHOD_SALE,
            "bidDivCd": BID_DIV_GENERAL,
        }
        # 개찰일 범위(없으면 mandatory 충족용 기본 최근범위).
        opbd_start = f.get("opbd_start")
        opbd_end = f.get("opbd_end")
        if not opbd_start or not opbd_end:
            win = self._default_date_window()
            now = datetime.now()
            opbd_start = opbd_start or (now - timedelta(days=LOOKBACK_PBANC_DAYS)).strftime("%Y%m%d")
            opbd_end = opbd_end or win["pbancYmdEnd"]
        params["opbdDtStart"] = opbd_start
        params["opbdDtEnd"] = opbd_end

        # 지역(시도/시군구/읍면동).
        if f.get("sido"):
            params["lctnSdnm"] = f["sido"]
        if f.get("sigungu"):
            params["lctnSggnm"] = f["sigungu"]
        if f.get("emd"):
            params["lctnEmdNm"] = f["emd"]
        # 용도(대/중/소 분류 ID).
        if f.get("usg_lcls_id"):
            params["cltrUsgLclsCtgrId"] = f["usg_lcls_id"]
        if f.get("usg_mcls_id"):
            params["cltrUsgMclsCtgrId"] = f["usg_mcls_id"]
        if f.get("usg_scls_id"):
            params["cltrUsgSclsCtgrId"] = f["usg_scls_id"]
        # 재산구분.
        if f.get("prpt_div_cd"):
            params["prptDivCd"] = f["prpt_div_cd"]
        # 처분방식 명시 override.
        if f.get("dsps_mthod_cd"):
            params["dspsMthodCd"] = f["dsps_mthod_cd"]
        # 낙찰/유찰 상태.
        if f.get("pbct_stat_cd"):
            params["pbctStatCd"] = f["pbct_stat_cd"]
        # 유찰횟수 범위.
        if f.get("fail_min") is not None:
            params["usbdNftStart"] = f["fail_min"]
        if f.get("fail_max") is not None:
            params["usbdNftEnd"] = f["fail_max"]
        # 감정가 범위.
        if f.get("apsl_min") is not None:
            params["apslEvlAmtStart"] = f["apsl_min"]
        if f.get("apsl_max") is not None:
            params["apslEvlAmtEnd"] = f["apsl_max"]
        # 최저입찰가 범위.
        if f.get("minbid_min") is not None:
            params["lowstBidPrcStart"] = f["minbid_min"]
        if f.get("minbid_max") is not None:
            params["lowstBidPrcEnd"] = f["minbid_max"]
        # 면적 범위.
        if f.get("land_min") is not None:
            params["landSqmsStart"] = f["land_min"]
        if f.get("land_max") is not None:
            params["landSqmsEnd"] = f["land_max"]
        if f.get("bld_min") is not None:
            params["bldSqmsStart"] = f["bld_min"]
        if f.get("bld_max") is not None:
            params["bldSqmsEnd"] = f["bld_max"]
        # 물건명/관리번호/기관.
        if f.get("cltr_nm"):
            params["onbidCltrNm"] = f["cltr_nm"]
        if f.get("cltr_mng_no"):
            params["cltrMngNo"] = f["cltr_mng_no"]
        if f.get("org_nm"):
            params["orgNm"] = f["org_nm"]

        url = f"{ONBID_BASE_URL}/{ONBID_BID_RESULT_LIST_OP}"
        try:
            client = await self._get_client()
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            raw_items, err = self._extract_items(resp.text)
            if err:
                return self._unavailable(f"온비드 응답 오류: {err}")
            items = [self._normalize_bid_result(it) for it in raw_items]
            items = [it for it in items if it is not None]
            if not items:
                return self._unavailable("온비드 입찰결과목록 무자료(해당 조건의 물건 없음)")
            return {
                "items": items,
                "data_source": "onbid_live",
                "total": len(items),
                "note": "온비드 OpenAPI getCltrBidRsltList2 실연동(resultType=json)",
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("온비드 입찰결과목록 호출 실패(무목업, 빈 결과): %s", str(e)[:160])
            return self._unavailable(f"온비드 입찰결과목록 호출 실패: {str(e)[:120]}")

    # ──────────────────────────────────────────
    # 보조 상세 (실호출 전용 — 실패 시 정직 빈값)
    # ──────────────────────────────────────────

    async def get_pbanc_detail(self, pbanc_mng_no: str) -> dict[str, Any]:
        """공고 상세(getPbancDtlInf2). 필수 pbancMngNo.

        실패/무자료 시 {"item": None, "data_source": "unavailable", "reason": ...}.
        """
        if not self._service_key:
            return {"item": None, "data_source": "unavailable", "reason": "온비드 인증키 미설정"}
        if not pbanc_mng_no:
            return {"item": None, "data_source": "unavailable", "reason": "pbancMngNo 누락"}
        params = {
            "serviceKey": self._service_key,
            "resultType": "json",
            "pbancMngNo": pbanc_mng_no,
        }
        url = f"{ONBID_BASE_URL}/{ONBID_PBANC_DETAIL_OP}"
        return await self._fetch_single(url, params)

    async def get_bid_result_detail(
        self, cltr_mng_no: str, pbct_cdtn_no: str,
    ) -> dict[str, Any]:
        """물건 입찰결과 상세(getCltrBidRsltDtl2). 필수 cltrMngNo + pbctCdtnNo.

        실패/무자료 시 {"item": None, "data_source": "unavailable", "reason": ...}.
        """
        if not self._service_key:
            return {"item": None, "data_source": "unavailable", "reason": "온비드 인증키 미설정"}
        if not cltr_mng_no or not pbct_cdtn_no:
            return {"item": None, "data_source": "unavailable",
                    "reason": "cltrMngNo/pbctCdtnNo 누락"}
        params = {
            "serviceKey": self._service_key,
            "resultType": "json",
            "cltrMngNo": cltr_mng_no,
            "pbctCdtnNo": pbct_cdtn_no,
        }
        url = f"{ONBID_BASE_URL}/{ONBID_BID_RESULT_OP}"
        return await self._fetch_single(url, params)

    async def _fetch_single(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        """단건 상세 응답을 정직하게 반환한다(가짜 생성 금지)."""
        try:
            client = await self._get_client()
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            raw_items, err = self._extract_items(resp.text)
            if err:
                return {"item": None, "data_source": "unavailable",
                        "reason": f"온비드 응답 오류: {err}"}
            if not raw_items:
                return {"item": None, "data_source": "unavailable",
                        "reason": "온비드 응답 무자료"}
            return {"item": raw_items[0], "data_source": "onbid_live"}
        except Exception as e:  # noqa: BLE001
            logger.warning("온비드 상세 호출 실패(무목업): %s", str(e)[:160])
            return {"item": None, "data_source": "unavailable",
                    "reason": f"온비드 상세 호출 실패: {str(e)[:120]}"}

    @staticmethod
    def _extract_items(text: str) -> tuple[list[dict[str, Any]], Optional[str]]:
        """온비드 JSON/XML 응답에서 item 리스트를 추출한다(방어적).

        반환: (items, error_reason). resultCode != "00" 이면 error_reason 채움.
        무자료/파싱불가도 (빈 리스트, None|reason) — ★가짜데이터 생성 금지.
        단건(dict)일 수 있으므로 방어적으로 리스트화한다.
        """
        import json as _json
        import xml.etree.ElementTree as ET

        text = (text or "").strip()
        if not text:
            return [], None

        # JSON 시도.
        if text.startswith("{") or text.startswith("["):
            try:
                root = _json.loads(text)
            except Exception:  # noqa: BLE001
                return [], None
            resp = root.get("response", root) if isinstance(root, dict) else {}
            header = resp.get("header", {}) if isinstance(resp, dict) else {}
            result_code = str(header.get("resultCode", "")).strip()
            if result_code and result_code != "00":
                msg = str(header.get("resultMsg", "")).strip()
                return [], f"resultCode={result_code} {msg}".strip()
            body = resp.get("body", {}) if isinstance(resp, dict) else {}
            items = body.get("items", {}) if isinstance(body, dict) else {}
            if isinstance(items, dict):
                items = items.get("item", [])
            if isinstance(items, dict):
                items = [items]
            if not isinstance(items, list):
                return [], None
            return [it for it in items if isinstance(it, dict)], None

        # XML 시도(에러 응답은 보통 XML로 옴).
        try:
            root = ET.fromstring(text)
        except Exception:  # noqa: BLE001
            return [], None
        code_el = root.find(".//resultCode")
        if code_el is not None and (code_el.text or "").strip() not in {"", "00"}:
            msg_el = root.find(".//resultMsg")
            msg = (msg_el.text or "").strip() if msg_el is not None else ""
            return [], f"resultCode={(code_el.text or '').strip()} {msg}".strip()
        out: list[dict[str, Any]] = []
        for item in root.iter("item"):
            out.append({child.tag: (child.text or "") for child in item})
        return out, None

    @staticmethod
    def _normalize(it: dict[str, Any]) -> Optional[dict[str, Any]]:
        """온비드 공고(getPbancList2 item)를 내부 auction_items 스키마로 정규화한다.

        ★취소공고(pbancKindNm 에 "취소" 포함)는 None 반환(필터링).
        ★미연동 필드(감정가·최저입찰가·유찰횟수)는 None(가짜 금지).
        """
        pbanc_kind_nm = str(it.get("pbancKindNm") or "")
        if "취소" in pbanc_kind_nm:
            return None

        # 공고관리번호(+공매재산번호)로 안정 item_no 구성.
        pbanc_mng_no = str(it.get("pbancMngNo") or "").strip()
        pbct_no = str(it.get("pbctNo") or "").strip()
        item_no = pbanc_mng_no
        if pbct_no:
            item_no = f"{pbanc_mng_no}-{pbct_no}" if pbanc_mng_no else pbct_no

        address = str(it.get("onbidPbancNm") or it.get("address") or "").strip()
        prpt_div_nm = str(it.get("prptDivNm") or "").strip()

        return {
            "source": "onbid",
            "item_no": item_no,
            "pbanc_mng_no": pbanc_mng_no or None,
            "kind": normalize_kind(prpt_div_nm),
            "kind_name": prpt_div_nm or None,
            "region_sido": "",
            "region_sigungu": "",
            "bjd_code": "",
            "pnu": "",
            "address": address,
            # ★물건목록 미연동 → 감정가/최저입찰가/유찰횟수 가짜 금지(None).
            "appraisal_price": None,
            "min_bid_price": None,
            "fail_count": None,
            "status": str(it.get("dspsMthodNm") or "매각"),
            "bid_start": _parse_dt(it.get("cltrBidBgngDt") or it.get("bid_start")),
            "bid_end": _parse_dt(it.get("cltrBidEndDt") or it.get("bid_end")),
            "opbd_dt": _parse_dt(it.get("cltrOpbdDt")),
            "org": str(it.get("orgNm") or "").strip() or None,
            "pbanc_ymd": _parse_dt(it.get("pbancYmd")),
            "raw": it,
        }

    @staticmethod
    def _normalize_ranking(it: dict[str, Any]) -> Optional[dict[str, Any]]:
        """온비드 순위(getInqRnkClg/getItrsCltrRnkClg item)를 내부 스키마로 정규화.

        ★실데이터 채움: 감정가(apslEvlAmt)·순위(sn)·할인율(feeRate)·상태(pbctStatNm)·
        용도(cltrUsgLclsCtgrNm)·주소(onbidCltrNm). 최저입찰가는 "비공개"면 None(정직).
        취소/무효 상태는 필터링하지 않고 상태 그대로 노출(순위 자체가 진행물건 위주).
        """
        cltr_mng_no = str(it.get("cltrMngNo") or "").strip()
        pbct_cdtn_no = str(it.get("pbctCdtnNo") or "").strip()
        item_no = cltr_mng_no
        if pbct_cdtn_no:
            item_no = f"{cltr_mng_no}-{pbct_cdtn_no}" if cltr_mng_no else pbct_cdtn_no
        if not item_no:
            return None

        address = str(it.get("onbidCltrNm") or "").strip()
        # 용도: 대>중>소 중 가장 구체적인 명칭 우선.
        usage = (
            str(it.get("cltrUsgSclsCtgrNm") or "").strip()
            or str(it.get("cltrUsgMclsCtgrNm") or "").strip()
            or str(it.get("cltrUsgLclsCtgrNm") or "").strip()
            or str(it.get("prptDivNm") or "").strip()
        )
        kind_src = (
            str(it.get("cltrUsgSclsCtgrNm") or "")
            + str(it.get("cltrUsgMclsCtgrNm") or "")
            + str(it.get("prptDivNm") or "")
        )

        return {
            "source": "onbid",
            "item_no": item_no,
            "cltr_mng_no": cltr_mng_no or None,
            "pbct_cdtn_no": pbct_cdtn_no or None,
            "rank": _parse_int(it.get("sn")),
            "kind": normalize_kind(kind_src),
            "kind_name": usage or None,
            "usage": usage or None,
            "region_sido": _sido_from_address(address),
            "region_sigungu": "",
            "bjd_code": "",
            "pnu": "",
            "address": address,
            "appraisal_price": _parse_amount(it.get("apslEvlAmt")),
            # "비공개"면 None(가짜 금지).
            "min_bid_price": _parse_amount(it.get("lowstBidPrcIndctCont")),
            "fail_count": None,
            "discount_rate": _parse_rate(it.get("feeRate")),
            "status": str(it.get("pbctStatNm") or it.get("dspsMthodNm") or "").strip() or None,
            "disposal_method": str(it.get("dspsMthodNm") or "").strip() or None,
            "thumbnail": str(it.get("thnlImgUrlAdr") or "").strip() or None,
            "bid_start": _parse_dt(it.get("cltrBidBgngDt")),
            "bid_end": _parse_dt(it.get("cltrBidEndDt")),
            "opbd_dt": None,
            "raw": it,
        }

    @staticmethod
    def _normalize_bid_result(it: dict[str, Any]) -> Optional[dict[str, Any]]:
        """온비드 입찰결과목록(getCltrBidRsltList2 item)을 내부 스키마로 정규화.

        ★실데이터 채움: 유찰횟수(usbdNft)·감정가(apslEvlAmt)·최저입찰가(lowstBidPrc)·
        낙찰가율(%)·낙찰가격·입찰결과(pbctStatNm)·면적·개찰일시·회차.
        최저입찰가 "비공개"면 None(정직).
        """
        cltr_mng_no = str(it.get("cltrMngNo") or "").strip()
        pbct_cdtn_no = str(it.get("pbctCdtnNo") or it.get("pbctNo") or "").strip()
        item_no = cltr_mng_no
        if pbct_cdtn_no:
            item_no = f"{cltr_mng_no}-{pbct_cdtn_no}" if cltr_mng_no else pbct_cdtn_no
        if not item_no:
            return None

        address = str(it.get("onbidCltrNm") or it.get("cltrNm") or "").strip()
        usage = (
            str(it.get("cltrUsgSclsCtgrNm") or "").strip()
            or str(it.get("cltrUsgMclsCtgrNm") or "").strip()
            or str(it.get("cltrUsgLclsCtgrNm") or "").strip()
            or str(it.get("prptDivNm") or "").strip()
        )
        kind_src = (
            str(it.get("cltrUsgSclsCtgrNm") or "")
            + str(it.get("cltrUsgMclsCtgrNm") or "")
            + str(it.get("prptDivNm") or "")
        )

        return {
            "source": "onbid",
            "item_no": item_no,
            "cltr_mng_no": cltr_mng_no or None,
            "pbct_cdtn_no": pbct_cdtn_no or None,
            "kind": normalize_kind(kind_src),
            "kind_name": usage or None,
            "usage": usage or None,
            "region_sido": _sido_from_address(address),
            "region_sigungu": "",
            "bjd_code": "",
            "pnu": "",
            "address": address,
            "appraisal_price": _parse_amount(it.get("apslEvlAmt")),
            "min_bid_price": _parse_amount(it.get("lowstBidPrc")),
            "fail_count": _parse_int(it.get("usbdNft")),
            "round_no": _parse_int(it.get("pbctNo") or it.get("rcnRtNo")),
            "land_area": _parse_rate(it.get("ldaQ") or it.get("landSqms")),
            "bld_area": _parse_rate(it.get("bldSqms") or it.get("bldgSqms")),
            "status": str(it.get("pbctStatNm") or "").strip() or None,
            "disposal_method": str(it.get("dspsMthodNm") or "").strip() or None,
            # 낙찰 실데이터.
            "win_rate": _parse_rate(it.get("scsbidRate") or it.get("scsbidPrcRate")),
            "win_price": _parse_amount(it.get("scsbidAmt") or it.get("scsbidPrc")),
            "valid_bidder_count": _parse_int(it.get("vldBidrCnt") or it.get("validBidrCnt")),
            "bid_start": _parse_dt(it.get("cltrBidBgngDt")),
            "bid_end": _parse_dt(it.get("cltrBidEndDt")),
            "opbd_dt": _parse_dt(it.get("opbdDt") or it.get("cltrOpbdDt")),
            "raw": it,
        }
