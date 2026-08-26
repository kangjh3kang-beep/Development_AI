"""국토교통부 실거래가 API 클라이언트.

아파트/연립/단독/오피스텔/토지/상업시설 실거래가 + 전월세 조회.
건축물대장(건축 인허가) 정보 조회 (XML 파싱 체계 포함).
AVM 서비스의 비교 사례 데이터 소스.
공공데이터포털: http://openapi.molit.go.kr
"""

import re
from datetime import datetime
from typing import Any

import structlog

from apps.api.integrations.base_client import BaseAPIClient

logger = structlog.get_logger(__name__)

# xmltodict 임포트 (없으면 regex 폴백)
try:
    import xmltodict
    _HAS_XMLTODICT = True
except ImportError:
    _HAS_XMLTODICT = False

# 부동산 유형별 실거래 API 엔드포인트
_TRADE_ENDPOINTS: dict[str, str] = {
    "apt": "getRTMSDataSvcAptTradeDev",
    "villa": "getRTMSDataSvcRHTrade",
    "house": "getRTMSDataSvcSHTrade",
    "officetel": "getRTMSDataSvcOffiTrade",
    "land": "getRTMSDataSvcLandTrade",
    "commercial": "getRTMSDataSvcNrgTrade",
}

_RENT_ENDPOINTS: dict[str, str] = {
    "apt": "getRTMSDataSvcAptRent",
    "villa": "getRTMSDataSvcRHRent",
    "house": "getRTMSDataSvcSHRent",
    "officetel": "getRTMSDataSvcOffiRent",
}

# 공공데이터포털 신 엔드포인트(apis.data.go.kr/1613000). 구 openapi.molit.go.kr는 폐기됨.
# operation 'getRTMSDataSvc...' → 경로 '/1613000/{service}/{operation}' (service = operation[3:]).
# 응답은 _type=json 파라미터로 JSON, 필드명은 영문(dealAmount/excluUseAr/aptNm/umdNm 등).
_RTMS_HOST_PATH = "/1613000"


# ── 실거래 캐시 TTL — 과거 월은 오래 들고 있는다 ─────────────────────────────
#
# ★★2026-08-06 실측 배경: 토지 통계는 **30개월 창**이 필요하다(6개월로는 강남조차 동 단위가
# 무너진다 — 전처리 후 36건). 그런데 30개월 × 여러 지역을 매번 조회하면 **일일 쿼터**에
# 걸린다(`HTTP 429 × 60건` 실측). 속도는 문제가 아니었다(병렬 30회 0.7초).
#
# ★해법의 근거: 실거래는 **확정 신고분**이라 지난 달들의 내용은 거의 변하지 않는다.
# 변할 수 있는 것은 (a)지연 신고 (b)계약 해제 반영(`cdealType`)이고, 둘 다 **최근 몇 달**에
# 몰린다. 그래서 최근 구간만 짧게 들고, 나머지는 길게 캐시해 쿼터를 아낀다.
#
# ★경계(6개월)는 **보수적 추정**이지 측정값이 아니다 — 과거 월이 실제로 얼마나 변하는지는
# 재보지 못했다(측정하려던 시점에 쿼터가 소진됐다). 지연 신고·해제가 6개월을 넘겨 반영되면
# 그만큼 낡은 값을 보게 된다. 더 짧게 잡는 쪽이 안전한 방향이고, 실측이 생기면 조정해야 한다.
_RECENT_MONTHS_SHORT_TTL = 6
_TTL_RECENT = 86_400        # 1일 — 아직 움직일 수 있는 구간
_TTL_SETTLED = 2_592_000    # 30일 — 사실상 확정된 구간


def _deal_ymd_ttl(deal_ymd: str, *, now: "datetime | None" = None) -> int:
    """`YYYYMM` 이 얼마나 지났는지로 캐시 수명을 정한다. 파싱 실패 시 **짧은 쪽**(안전)."""
    try:
        year, month = int(str(deal_ymd)[:4]), int(str(deal_ymd)[4:6])
        if not (1 <= month <= 12):
            return _TTL_RECENT
    except (TypeError, ValueError):
        return _TTL_RECENT
    ref = now or datetime.now()
    elapsed = (ref.year - year) * 12 + (ref.month - month)
    return _TTL_SETTLED if elapsed > _RECENT_MONTHS_SHORT_TTL else _TTL_RECENT


def _rtms_path(operation: str) -> str:
    """RTMS operation명을 신 엔드포인트 경로로 변환한다."""
    service = operation[3:] if operation.startswith("get") else operation
    return f"{_RTMS_HOST_PATH}/{service}/{operation}"


def _to_int(v: Any, default: int = 0) -> int:
    """공백/빈값/콤마 방어 정수 변환. (상업 floor=' ' 등으로 인한 파싱 전체 실패 방지)"""
    try:
        s = str(v).replace(",", "").strip()
        return int(float(s)) if s else default
    except (ValueError, TypeError):
        return default


def _to_float(v: Any, default: float = 0.0) -> float:
    """공백/빈값/콤마 방어 실수 변환."""
    try:
        s = str(v).replace(",", "").strip()
        return float(s) if s else default
    except (ValueError, TypeError):
        return default


class MolitClient(BaseAPIClient):
    """국토부 실거래가 API 클라이언트."""

    service_name = "molit"
    base_url = "https://apis.data.go.kr"

    # ── 통합 조회 (표준화 파싱 포함) ──

    async def get_transactions(
        self,
        lawd_cd: str,
        deal_ymd: str,
        prop_type: str = "apt",
        num_rows: int = 1000,
        max_pages: int = 10,
    ) -> list[dict[str, Any]]:
        """실거래 데이터를 **전수 수집**(totalCount 페이지 루프)하여 표준화 목록으로 반환한다.

        ★무음절단 제거(원칙: 광범위 누락없는 수집): 단일 페이지(numOfRows=100)로 끊지 않고
        totalCount까지 페이지를 순회한다. max_pages 상한 도달 시 절단을 경고 로깅(은닉 금지).

        Args:
            lawd_cd: 법정동코드 (5자리)
            deal_ymd: 거래년월 (YYYYMM)
            prop_type: 부동산 유형 (apt/villa/house/officetel/land/commercial)
            num_rows: 페이지당 조회 건수 / max_pages: 페이지 상한(num_rows×max_pages 까지 수집)
        """
        endpoint = _TRADE_ENDPOINTS.get(prop_type, _TRADE_ENDPOINTS["apt"])
        return await self._collect_paginated(
            endpoint, lawd_cd, deal_ymd, num_rows, max_pages,
            cache_ns=f"molit:trade:{prop_type}",
            parse=lambda d: self._parse_trade_items(d, prop_type),
            kind=f"실거래({prop_type})",
        )

    async def get_rent_transactions(
        self,
        lawd_cd: str,
        deal_ymd: str,
        prop_type: str = "apt",
        num_rows: int = 1000,
        max_pages: int = 10,
    ) -> list[dict[str, Any]]:
        """전월세 실거래 데이터를 **전수 수집**(totalCount 페이지 루프)하여 표준화 목록으로 반환한다."""
        endpoint = _RENT_ENDPOINTS.get(prop_type, _RENT_ENDPOINTS["apt"])
        return await self._collect_paginated(
            endpoint, lawd_cd, deal_ymd, num_rows, max_pages,
            cache_ns=f"molit:rent:{prop_type}",
            parse=self._parse_rent_items,
            kind=f"전월세({prop_type})",
        )

    async def _collect_paginated(
        self, endpoint: str, lawd_cd: str, deal_ymd: str,
        num_rows: int, max_pages: int, *, cache_ns: str,
        parse: Any, kind: str,
    ) -> list[dict[str, Any]]:
        """공통 페이지 루프 — response.body.totalCount까지 전수 수집(무음절단 제거). 페이지별 캐시."""
        all_items: list[dict[str, Any]] = []
        total: int | None = None
        page = 1
        while page <= max_pages:
            data = await self._request(
                "GET", _rtms_path(endpoint),
                params={
                    "serviceKey": self.settings.molit_api_key,
                    "LAWD_CD": lawd_cd, "DEAL_YMD": deal_ymd,
                    "pageNo": str(page), "numOfRows": str(num_rows), "_type": "json",
                },
                cache_key=f"{cache_ns}:{lawd_cd}:{deal_ymd}:{num_rows}:p{page}",
                # ★과거 월은 길게 — 30개월 창을 매번 새로 받으면 쿼터가 버티지 못한다.
                cache_ttl=_deal_ymd_ttl(deal_ymd),
            )
            items = parse(data)
            all_items.extend(items)
            total = self._extract_total_count(data)
            # 더 받을 게 없으면 종료: 빈 페이지·totalCount 미상·이미 전수 수집.
            if not items or total is None or len(all_items) >= total:
                break
            page += 1
        if total is not None and len(all_items) < total:
            logger.warning("MOLIT 페이지 상한 도달 — 일부 절단(수집 미완)",
                           kind=kind, collected=len(all_items), total=total,
                           lawd_cd=lawd_cd, deal_ymd=deal_ymd, max_pages=max_pages)
        return all_items

    # ── 개별 조회 (하위 호환) ──

    async def get_apartment_trades(self, lawd_cd: str, deal_ymd: str) -> dict:
        """아파트 매매 실거래가를 조회한다."""
        return await self._request(
            "GET",
            _rtms_path("getRTMSDataSvcAptTradeDev"),
            params={
                "serviceKey": self.settings.molit_api_key,
                "LAWD_CD": lawd_cd,
                "DEAL_YMD": deal_ymd,
                "pageNo": "1",
                "numOfRows": "100",
                "_type": "json",
            },
            cache_key=f"molit:apt_trade:{lawd_cd}:{deal_ymd}",
            cache_ttl=86400,
        )

    async def get_apartment_rent(self, lawd_cd: str, deal_ymd: str) -> dict:
        """아파트 전월세 실거래가를 조회한다."""
        return await self._request(
            "GET",
            _rtms_path("getRTMSDataSvcAptRent"),
            params={
                "serviceKey": self.settings.molit_api_key,
                "LAWD_CD": lawd_cd,
                "DEAL_YMD": deal_ymd,
                "pageNo": "1",
                "numOfRows": "100",
                "_type": "json",
            },
            cache_key=f"molit:apt_rent:{lawd_cd}:{deal_ymd}",
            cache_ttl=86400,
        )

    async def get_land_price(self, pnu: str, year: str) -> dict:
        """개별공시지가를 조회한다."""
        return await self._request(
            "GET",
            "/1611000/nsdi/IndvdLandPriceService/attr/getIndvdLandPriceAttr",
            params={
                "serviceKey": self.settings.molit_api_key,
                "pnu": pnu,
                "stdrYear": year,
                "format": "json",
            },
            cache_key=f"molit:land_price:{pnu}:{year}",
            cache_ttl=604800,
        )

    async def get_building_permit(self, sigungu_cd: str) -> list[dict[str, Any]]:
        """건축 인허가 정보를 조회한다.

        국토부 건축물대장 API는 XML 응답을 반환한다.
        xmltodict로 파싱하며, 없을 경우 regex 기반 폴백 파서를 사용한다.
        어떤 오류가 발생해도 예외를 던지지 않고 빈 리스트를 반환한다.
        """
        cache_key = f"molit:permit:{sigungu_cd}"

        # 캐시 확인
        cached = await self._get_cached(cache_key)
        if cached is not None and isinstance(cached, list):
            return list(cached)

        if not self.circuit_breaker.can_execute():
            logger.warning("Circuit Breaker OPEN — 건축 인허가 스킵", sigungu_cd=sigungu_cd)
            return []

        client = await self._get_client()

        try:
            response = await client.request(
                "GET",
                "/1613000/BldRgstService_v2/getBrBasisOulnInfo",
                params={
                    "serviceKey": self.settings.molit_api_key,
                    "sigunguCd": sigungu_cd,
                    "bjdongCd": "",
                    "numOfRows": "100",
                },
            )
            response.raise_for_status()
            self.circuit_breaker.record_success()

            content_type = response.headers.get("content-type", "")

            # JSON 응답인 경우
            if "json" in content_type:
                data = response.json()
                items = self._extract_items(data)
                result = self._parse_permit_items(items)
            else:
                # XML 응답 파싱
                result = self._parse_xml_permit_response(response.text)

            await self._set_cache(cache_key, result, 86400)
            logger.info("건축 인허가 조회 완료", sigungu_cd=sigungu_cd, count=len(result))
            return result

        except Exception as e:
            self.circuit_breaker.record_failure()
            logger.warning("건축 인허가 조회 실패", sigungu_cd=sigungu_cd, error=str(e))
            return []

    def _parse_xml_permit_response(self, xml_text: str) -> list[dict[str, Any]]:
        """건축물대장 XML 응답을 파싱한다.

        1차: xmltodict 사용
        2차: regex 기반 폴백
        """
        if _HAS_XMLTODICT:
            return self._parse_xml_with_xmltodict(xml_text)
        return self._parse_xml_with_regex(xml_text)

    @staticmethod
    def _parse_xml_with_xmltodict(xml_text: str) -> list[dict[str, Any]]:
        """xmltodict로 XML을 파싱한다."""
        try:
            parsed = xmltodict.parse(xml_text)
            body = (
                parsed.get("response", {})
                .get("body", {})
                .get("items", {})
                .get("item", [])
            )
            if isinstance(body, dict):
                body = [body]
            if not isinstance(body, list):
                return []

            result: list[dict[str, Any]] = []
            for item in body:
                result.append({
                    "permit_date": str(item.get("crtnDay", "")),
                    "building_name": str(item.get("bldNm", "")),
                    "main_purpose": str(item.get("mainPurpsCdNm", "")),
                    "structure": str(item.get("strctCdNm", "")),
                    "ground_floors": int(item.get("grndFlrCnt", 0) or 0),
                    "underground_floors": int(item.get("ugrndFlrCnt", 0) or 0),
                    "total_area_m2": float(item.get("totArea", 0) or 0),
                    "building_area_m2": float(item.get("archArea", 0) or 0),
                    "floor_area_ratio": float(item.get("vlRat", 0) or 0),
                    "building_coverage": float(item.get("bcRat", 0) or 0),
                })
            return result
        except Exception as e:
            logger.warning("xmltodict 파싱 실패", error=str(e))
            return []

    @staticmethod
    def _parse_xml_with_regex(xml_text: str) -> list[dict[str, Any]]:
        """xmltodict가 없을 때 regex로 XML을 파싱한다."""
        result: list[dict[str, Any]] = []
        item_pattern = re.compile(r"<item>(.*?)</item>", re.DOTALL)
        tag_pattern = re.compile(r"<(\w+)>(.*?)</\1>")

        for item_match in item_pattern.finditer(xml_text):
            item_xml = item_match.group(1)
            fields: dict[str, str] = {}
            for tag_match in tag_pattern.finditer(item_xml):
                fields[tag_match.group(1)] = tag_match.group(2)

            if fields:
                result.append({
                    "permit_date": fields.get("crtnDay", ""),
                    "building_name": fields.get("bldNm", ""),
                    "main_purpose": fields.get("mainPurpsCdNm", ""),
                    "structure": fields.get("strctCdNm", ""),
                    "ground_floors": int(fields.get("grndFlrCnt", "0") or 0),
                    "underground_floors": int(fields.get("ugrndFlrCnt", "0") or 0),
                    "total_area_m2": float(fields.get("totArea", "0") or 0),
                    "building_area_m2": float(fields.get("archArea", "0") or 0),
                    "floor_area_ratio": float(fields.get("vlRat", "0") or 0),
                    "building_coverage": float(fields.get("bcRat", "0") or 0),
                })
        return result

    @staticmethod
    def _parse_permit_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """JSON 형태의 건축 인허가 아이템을 표준화한다."""
        result: list[dict[str, Any]] = []
        for item in items:
            result.append({
                "permit_date": str(item.get("crtnDay", "")),
                "building_name": str(item.get("bldNm", "")),
                "main_purpose": str(item.get("mainPurpsCdNm", "")),
                "structure": str(item.get("strctCdNm", "")),
                "ground_floors": int(item.get("grndFlrCnt", 0) or 0),
                "underground_floors": int(item.get("ugrndFlrCnt", 0) or 0),
                "total_area_m2": float(item.get("totArea", 0) or 0),
                "building_area_m2": float(item.get("archArea", 0) or 0),
                "floor_area_ratio": float(item.get("vlRat", 0) or 0),
                "building_coverage": float(item.get("bcRat", 0) or 0),
            })
        return result

    # ── 응답 파싱 유틸 ──

    @staticmethod
    def _extract_items(data: dict) -> list[dict]:
        """공통: response.body.items.item 배열을 추출한다."""
        body = (data.get("response") or {}).get("body")
        if not body:
            return []
        items = (body.get("items") or {}).get("item", [])
        if isinstance(items, dict):
            items = [items]
        return items if isinstance(items, list) else []

    @staticmethod
    def _extract_total_count(data: dict) -> int | None:
        """공통: response.body.totalCount → int(없으면 None). 페이지 루프 종료 판단용."""
        body = (data.get("response") or {}).get("body") or {}
        tc = body.get("totalCount")
        try:
            return int(tc) if tc not in (None, "") else None
        except (TypeError, ValueError):
            return None

    def _parse_trade_items(
        self, data: dict, prop_type: str,
    ) -> list[dict[str, Any]]:
        """실거래 응답을 표준화된 거래 목록으로 변환한다.

        신 JSON API는 영문 필드명(dealAmount/excluUseAr/aptNm/umdNm…),
        구 XML/테스트는 한글 필드명(거래금액/전용면적…) → 영문 우선·한글 폴백.
        """
        try:
            items = self._extract_items(data)
            result: list[dict[str, Any]] = []
            for item in items:
                def g(en: str, ko: str, default: Any = "") -> Any:
                    v = item.get(en)
                    return v if v not in (None, "") else item.get(ko, default)

                year = g("dealYear", "년", "")
                month = g("dealMonth", "월", "")
                day = g("dealDay", "일", "")
                # 면적: 유형별 상이 — 아파트/연립/오피=전용, 단독=연면적, 상업=건물,
                #       토지=거래면적, 차선책으로 대지면적.
                area = (
                    _to_float(g("excluUseAr", "전용면적"))
                    or _to_float(item.get("totalFloorAr"))
                    or _to_float(item.get("buildingAr"))
                    or _to_float(item.get("dealArea"))
                    or _to_float(item.get("plottageAr"))
                )
                result.append({
                    "prop_type": prop_type,
                    "deal_date": f"{year}년 {month}월 {day}일",
                    "price_10k_won": _to_int(g("dealAmount", "거래금액", "0")),
                    "area_m2": area,
                    "floor": _to_int(g("floor", "층", 0)),
                    "building_name": str(
                        g("aptNm", "아파트", "")
                        or item.get("mhouseNm")  # 연립·다세대
                        or item.get("offiNm")  # 오피스텔
                        or item.get("연립다세대", "")
                        or ""
                    ),
                    "sigungu": str(g("estateAgentSggNm", "시군구", "")),
                    "dong": str(g("umdNm", "법정동", "")),
                    "jibun": str(g("jibun", "지번", "")),
                    "build_year": _to_int(g("buildYear", "건축년도", 0)),
                    # 토지 매매(getRTMSDataSvcLandTrade) 전용 — 지목/용도지역(없으면 빈값)
                    "jimok": str(g("jimok", "지목", "")),
                    "land_use": str(g("landUse", "용도지역", "")),
                    # ★★2026-08-06 실측으로 추가 — 원천이 주는데 **우리가 버리던** 필드.
                    #   MOLIT 토지 매매는 `shareDealingType`("지분"/공백)으로 **지분거래**를
                    #   구분해 준다. 우리는 이걸 읽지 않아 지분과 일반을 **한 통에 섞어** 왔다.
                    #   ★라이브 실측(3지역·30개월 3,113건): 지분 비율이 지역마다 크고
                    #   단가 차이도 **방향이 제각각**이다 — 강남 0.27배 · 해운대 0.65배 ·
                    #   포항북 2.14배(일반 대비 지분 중앙값). 즉 섞으면 그 값은 무의미하다.
                    #   ★여기서는 **읽어서 보존만** 한다(무날조) — 제외·가중은 소비처 판단이고,
                    #   무엇이 섞여 있는지 말할 수 있는 것이 먼저다.
                    "share_dealing_type": str(g("shareDealingType", "거래구분", "")).strip(),
                    # ── 계약 상태·소유권 (2026-08-26) ────────────────────────────
                    # ★같은 결함이 이 파일에서 두 번째다. `molit_client.py:56` 주석은
                    #   캐시 TTL 근거로 **`cdealType` 을 이미 언급**하고 있었다
                    #   (*"변할 수 있는 것은 지연 신고와 계약 해제 반영(cdealType)"*).
                    #   **알면서 파싱하지 않았다** — 위 `share_dealing_type` 과 같은 얼굴이다.
                    #
                    # ★라이브 원문 실측(강남·용인수지·서울중구 × 3개월 **3,482건**):
                    #     cdealType  공백 3,414 · **'O' 68건(1.95%)**
                    #     dealingGbn 중개거래 3,381 · 직거래 101
                    #     rgstDate   공백 2,430 · 있음 1,052(30.2%)
                    #     buyerGbn   개인 3,475 · 법인 7
                    # ★해제 건 평균이 정상 대비 **+11.5%**(고가 편향). 전체 평균 왜곡은
                    #   **+0.22%** 로 작지만 — 과장하지 않는다 — **개별 표시가 거짓**이고
                    #   소표본(AVM·탁상감정 반경 표본)에서 증폭된다.
                    #
                    # ★★정상 건은 `' '`(**스페이스**)다. `strip()` 없이 truthy 로 보면
                    #   **전건이 해제**가 된다.
                    #
                    # ★원칙은 형제 그대로 — **읽어서 보존만 한다(무날조).**
                    #   해제 건도 **행을 버리지 않는다**; 제외·가중은 **소비처 판단**이다.
                    "cancel_type": str(g("cdealType", "해제여부", "")).strip(),
                    "cancel_date": str(g("cdealDay", "해제사유발생일", "")).strip(),
                    "is_cancelled": bool(str(g("cdealType", "해제여부", "")).strip()),
                    "dealing_type": str(g("dealingGbn", "거래유형", "")).strip(),
                    # 3층(소유권 추적) 재료 — **별도 등기 API 없이 같은 응답**에 있다.
                    "registered_date": str(g("rgstDate", "등기일자", "")).strip(),
                    "buyer_type": str(g("buyerGbn", "매수자", "")).strip(),
                    "seller_type": str(g("slerGbn", "매도자", "")).strip(),
                })
            # (Fix #2·감사 HIGH) 수집 검증 게이트 — 정의만 돼 있고 소비처 0건이던 TransactionRecord
            # 스키마를 실수집 경로에 배선. 가격<=0·**유형별 면적상한**·층(-5~120) 위반행을 드롭한다
            # (★면적상한은 유형별이다 — 아파트 1000㎡ / 토지는 절대상한만. 종전 일괄 1000㎡ 는
            #  라이브 실측에서 **정상 토지거래의 60%(68/114)를 드롭**했다).
            # (무목업: 가짜 생성 없이 드롭만, 드롭 사실은 로그로 관측).
            from app.services.data_validation.validator import validate_transactions

            validated, vreport = validate_transactions(result, prop_type=prop_type)
            if vreport["dropped"]:
                logger.warning(
                    "실거래 스키마 검증 드롭",
                    prop_type=prop_type,
                    dropped=vreport["dropped"],
                    accepted=vreport["accepted"],
                )
            return validated
        except Exception:
            logger.warning("실거래 파싱 실패", prop_type=prop_type)
            return []

    def _parse_rent_items(self, data: dict) -> list[dict[str, Any]]:
        """전월세 응답을 표준화한다. (영문 필드 우선·한글 폴백)"""
        try:
            items = self._extract_items(data)
            result: list[dict[str, Any]] = []
            for item in items:
                def g(en: str, ko: str, default: Any = "") -> Any:
                    v = item.get(en)
                    return v if v not in (None, "") else item.get(ko, default)

                year = g("dealYear", "년", "")
                month = g("dealMonth", "월", "")
                day = g("dealDay", "일", "")
                area = (
                    _to_float(g("excluUseAr", "전용면적"))
                    or _to_float(item.get("totalFloorAr"))
                )
                result.append({
                    "deal_date": f"{year}년 {month}월 {day}일",
                    "deposit_10k_won": _to_int(g("deposit", "보증금액", "0")),
                    "monthly_rent_10k_won": _to_int(g("monthlyRent", "월세금액", "0")),
                    "area_m2": area,
                    "floor": _to_int(g("floor", "층", 0)),
                    "building_name": str(
                        g("aptNm", "아파트", "")
                        or item.get("mhouseNm")  # 연립·다세대
                        or item.get("offiNm")  # 오피스텔
                        or ""
                    ),
                    "sigungu": str(g("estateAgentSggNm", "시군구", "") or g("sggNm", "", "")),
                    "dong": str(g("umdNm", "법정동", "")),
                    "jibun": str(g("jibun", "지번", "")),
                })
            return result
        except Exception:
            logger.warning("전월세 파싱 실패")
            return []
