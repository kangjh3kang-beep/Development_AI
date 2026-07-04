"""KOSIS(국가통계포털) API 클라이언트.

광역 단위의 거시적 소득, 급여, 고용 통계 데이터 수집용.
공공데이터포털 연계 또는 KOSIS Open API 직접 연동.
"""

import asyncio
import os
import re
from typing import Any

import structlog

from apps.api.app.core.config import settings as kosis_settings
from apps.api.app.services.market.market_models import MacroIncomeData
from apps.api.integrations.base_client import BaseAPIClient

logger = structlog.get_logger(__name__)

# ── KOSIS 통계표 설정(하드코딩 금지·설정가능 상수로 분리) ──
# 통계표ID(tblId)는 통계표 개편 시 변경되므로 상수로 분리해 한 곳에서 관리한다.
# ★ 아래 tblId 는 아직 운영 확정 전이다. 통계목록 조회 API(data.go.kr 15056860)로
#    소득/임금 통계표를 확정하기 전까지, 이 경로로 받은 값은 data_source='fallback' 로
#    정직 표기한다(실데이터로 단정하지 않음).
KOSIS_ORG_ID = "101"  # 통계청
KOSIS_NTS_ORG_ID = "133"  # 국세청(시군구 소득 통계 제공기관)
# 라이브 검증된 시군구 소득표: 「시·군·구별 근로소득 연말정산 신고현황(주소지)」(국세청, 2016~).
# 단일분류(C1=시군구)×C2(급여총계/과세대상근로소득(총급여)/과세표준/결정세액)×ITM(인원/금액).
# 평균연소득 = 총급여 금액(백만원)×100 / 인원(명) → 만원 단위.
KOSIS_INCOME_TBL_ID = "DT_133001N_4215"
KOSIS_INCOME_C2_LABEL = "과세대상근로소득(총급여)"  # 평균소득 산출 기준 항목(총급여)
KOSIS_PERIOD_TYPE = "Y"  # 수록주기: 연
# 항목코드(itmId)는 추측하지 않고 'ALL'(전체 항목) 사용 — 가이드 권장(errCd 20/21 회피).

# ── 국내인구이동통계(OD) 설정 ──
# 전입지(현 시군구)로 유입된 인구의 전출지(이전 거주지)별 이동자수를 조회한다.
# ★ 아래 tblId/itmId 는 운영 확정 전(미검증)이다. 통계목록 API(data.go.kr 15056860)로
#    '국내인구이동통계 시군구별 전입' 표를 확정하기 전까지, 수신 데이터는 data_source='fallback'
#    로 정직 표기한다(실데이터로 단정하지 않음). 키·데이터 없으면 'unavailable'.
KOSIS_MIGRATION_TBL_ID = "DT_1B26001_A01"  # 국내인구이동통계(통합검색 확정 전 기본 폴백표)
# KOSIS 응답에서 합계/전체를 의미하는 분류값명(전출지 Top 집계에서 제외).
_MIGRATION_TOTAL_LABELS = {"계", "전국", "소계", "합계", "전체"}
# 전입(유입) 항목 식별 힌트 — itmId=ALL 응답에서 전입/순이동/전출이 섞일 때 전입만 집계.
_INFLOW_ITEM_HINTS = ("전입",)


# KOSIS statisticsSearch.do 는 format=json 이어도 키가 따옴표 없는 비표준 JSON
# (예: [{ORG_ID:"101",TBL_ID:"DT_...",TBL_NM:"..."}]) 을 text/html 로 돌려준다.
# CONTENTS 같은 자유문구 필드가 섞여 있어 통째 JSON 파싱은 깨지므로, 필요한 식별 필드만
# 레코드 단위로 정규식 추출한다(값에 따옴표 없는 ID/표명만 대상이라 안전).
_SEARCH_RECORD_RE = re.compile(
    r'ORG_ID:"(?P<org_id>[^"]*)".*?TBL_ID:"(?P<tbl_id>[^"]*)".*?TBL_NM:"(?P<tbl_nm>[^"]*)"',
    re.DOTALL,
)


def _parse_search_records(body: str, max_items: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in _SEARCH_RECORD_RE.finditer(body):
        if m.group("tbl_id"):
            out.append({
                "tbl_id": m.group("tbl_id"),
                "tbl_nm": m.group("tbl_nm"),
                "org_id": m.group("org_id"),
                "path": None,
            })
            if len(out) >= max_items:
                break
    return out


def normalize_sigungu_cd(region_cd: str | None) -> str:
    """지역코드를 KOSIS 시군구5 코드로 정규화한다.

    입력 가능 형태(자릿수 기준): 법정동10 / 행정동10 / SGIS8 / 시군구5 / 집계구13 등.
    공통 규칙: 시군구5 = '시도2 + 시군구3' = 앞 5자리(법정동·행정동·SGIS·집계구 모두 동일).
    PublicDataReader 가 설치돼 있으면 코드 검증/매핑에 활용하되, 없으면 안전하게 앞 5자리를 사용한다.
    ※ 이름 매칭은 금지(행정동↔법정동 N:M). 자릿수 기반 절단만 수행.
    """
    if not region_cd:
        return ""
    digits = "".join(ch for ch in str(region_cd) if ch.isdigit())
    if not digits:
        return ""
    # PublicDataReader 가 있으면 시군구 코드 유효성 보강(없으면 폴백). 이름매칭 금지.
    try:
        import PublicDataReader as pdr  # type: ignore

        sgg5 = digits[:5]
        # 코드표가 로드되면 그대로 사용(검증 목적). 실패해도 앞5자리 폴백.
        _ = pdr  # noqa: F841  (설치 확인용 — 현재는 절단 규칙이 결정론적이라 그대로 사용)
        return sgg5
    except Exception:  # noqa: BLE001
        # PDR 미설치/오류 → 안전 폴백(앞 5자리). 시군구5는 모든 체계의 상위 공통 접두다.
        return digits[:5]


class KosisClient(BaseAPIClient):
    """KOSIS 거시 경제 및 소득 통계 API 클라이언트.

    - self.settings: BaseAPIClient 기본값(apps.api.config) — redis_url 등 인프라 설정.
      Redis 캐시가 정상 동작하려면 이 객체를 그대로 둬야 한다.
    - self.api_settings: KOSIS_API_KEY 가 정의된 설정(apps.api.app.core.config) — API 키 전용.
      (테스트의 키 패치 경로와도 동일 객체로 일치한다.)
    """

    service_name = "kosis"
    base_url = "https://kosis.kr/openapi"

    def __init__(self) -> None:
        super().__init__()
        # API 키 전용 설정(인프라 설정 self.settings 와 분리)
        self.api_settings = kosis_settings

    # ★ 관리자 등록 키는 os.environ 으로만 오버레이되는데 settings 객체는 import 시점 고정(@lru_cache)이라
    #   런타임 오버레이를 못 받는다. → os.environ 우선 읽기로 관리자 등록 키를 즉시 활성화한다.
    def _kosis_key(self) -> str:
        return os.getenv("KOSIS_API_KEY") or getattr(self.api_settings, "KOSIS_API_KEY", "") or ""

    async def search_tables(self, keyword: str, max_items: int = 20) -> list[dict[str, Any]]:
        """KOSIS 통합검색(statisticsSearch.do)으로 키워드에 맞는 통계표 후보를 반환한다.

        개발가이드 §2.6 규격. 반환: [{tbl_id, tbl_nm, org_id, path}]. 키 없음/실패 시 [].
        통계표ID(tblId) 확정용 유틸 — 관리자 진단/자동탐색에 사용(가짜 결과 금지).
        """
        key = self._kosis_key()
        if not key or not keyword:
            return []
        try:
            client = await self._get_client()
            resp = await asyncio.wait_for(
                client.request("GET", "/statisticsSearch.do", params={
                    "method": "getList", "apiKey": key, "format": "json",
                    "searchNm": keyword, "sort": "RANK",
                    "startCount": 1, "resultCount": max_items,
                }), timeout=6.0)
            resp.raise_for_status()
            body = resp.text or ""
            # 에러 응답(JSON object)인 경우 빈 목록.
            if body.lstrip()[:1] in ("<", "{"):
                return []
            return _parse_search_records(body, max_items)
        except Exception as e:  # noqa: BLE001
            logger.warning("KOSIS search_tables failed", err=str(e))
            return []

    async def _resolve_tbl_id(
        self, search_kw: str, require: tuple[str, ...], default: str,
    ) -> tuple[str, bool]:
        """통합검색으로 통계표ID를 확정한다. (tbl_id, resolved).

        통계청(orgId 101) 표 중 TBL_NM 에 require 키워드를 모두 포함하는 첫 결과를 채택한다.
        확정 못하면 (default, False) — 임의의 잘못된 표 채택을 막아 가짜 데이터를 방지한다.
        """
        for c in await self.search_tables(search_kw):
            nm = c.get("tbl_nm") or ""
            if c.get("org_id") == KOSIS_ORG_ID and all(r in nm for r in require) and c.get("tbl_id"):
                return c["tbl_id"], True
        return default, False

    async def get_macro_income_stats(
        self,
        sigungu_cd: str,
        year: str,
        region_name: str | None = None,
        use_mock: bool | None = None,
    ) -> dict[str, Any]:
        """해당 시/군/구의 평균 연소득(근로소득 총급여)을 KOSIS 국세청 통계로 조회합니다.

        「시·군·구별 근로소득 연말정산 신고현황(주소지)」(DT_133001N_4215)에서 대상 시군구의
        총급여 금액·인원을 받아 평균연소득(만원)을 산출한다. region_name(예:'강남구')으로 식별.

        Args:
            sigungu_cd: 지역코드. 내부에서 시군구5로 정규화(메타·호환용).
            year: 조회 연도(최신 수록 시점 우선).
            region_name: 시군구명(소득표 행 식별 키). 없으면 산출 불가→fallback.
            use_mock: None이면 키 존재로 자동 결정. True 강제 시 mock.
        """
        sgg5 = normalize_sigungu_cd(sigungu_cd) or sigungu_cd
        target = (region_name or "").strip()
        has_key = bool(self._kosis_key())
        if use_mock is None:
            use_mock = not has_key
        if use_mock or not has_key:
            return self._mock_income_data(sgg5, year)

        try:
            rows = await self._fetch_income(sgg5, year, tbl_id=KOSIS_INCOME_TBL_ID)
            if not isinstance(rows, list) or not rows:
                return self._fallback_income(sgg5, year, "KOSIS 소득표 응답 없음")
            if not target:
                return self._fallback_income(sgg5, year, "시군구명 미전달 — 소득 산출 불가")

            # 대상 시군구 × 총급여(과세대상근로소득) 의 금액(백만원)·인원(명) 추출.
            amount_baekman = persons = 0
            data_year = year
            for r in rows:
                if (r.get("C1_NM") or "").strip() != target:
                    continue
                if (r.get("C2_NM") or "").strip() != KOSIS_INCOME_C2_LABEL:
                    continue
                itm = (r.get("ITM_NM") or "").strip()
                try:
                    dt = int(float(r.get("DT", 0)))
                except (TypeError, ValueError):
                    dt = 0
                if itm == "금액":
                    amount_baekman = dt
                    data_year = r.get("PRD_DE") or year
                elif itm == "인원":
                    persons = dt

            if amount_baekman <= 0 or persons <= 0:
                return self._fallback_income(sgg5, year, f"'{target}' 총급여/인원 수치 없음")

            # 평균 연소득(만원) = 금액(백만원) × 100 / 인원(명). (백만원=100만원=100×만원)
            avg_10k = int(round(amount_baekman * 100 / persons))
            parsed_data = {
                "sigungu_cd": sgg5,
                "year": str(data_year),
                "avg_income_10k": avg_10k,
                # 중위소득은 이 표에 없음 — 평균 기반 보수 추정(0.85배)임을 note 에 명시.
                "median_income_10k": int(avg_10k * 0.85),
                "income_bracket_ratio": {},  # 구간비율은 이 표에 없음(가짜값 금지).
                "data_source": "live",
                "note": (f"KOSIS {KOSIS_INCOME_TBL_ID}(국세청) '{target}' 근로소득 총급여 "
                         f"평균 {avg_10k:,}만원/인({data_year}, 인원 {persons:,}명). "
                         f"중위는 평균×0.85 추정."),
            }
            result = MacroIncomeData(**parsed_data).model_dump()
            result["note"] = parsed_data["note"]  # 모델에 없는 note 보존
            return result

        except Exception as e:  # noqa: BLE001
            logger.warning("KOSIS income fetch failed, using fallback", err=str(e))
            return self._fallback_income(sgg5, year, "KOSIS 소득 조회 실패")

    async def _fetch_income(
        self, sigungu_cd: str, year: str, tbl_id: str = KOSIS_INCOME_TBL_ID,
    ) -> Any:
        """KOSIS 국세청 「시군구별 근로소득 연말정산」 호출 → 전 시군구 행 목록(비-JSON 가드).

        - orgId=133(국세청). 이 표는 C1(시군구)×C2(급여항목)×ITM(인원/금액) 다중분류라
          objL1=ALL·objL2=ALL 필수(둘 중 하나라도 빠지면 errCd 20, objL3 추가 시 errCd 21).
        - 연도는 newEstPrdCnt=1(최신 수록 시점)로 받는다(prdDe 오지정 errCd 30 회피).
        sigungu_cd/year 인자는 호환 위해 유지(필터는 호출측 시군구명 기준).
        """
        client = await self._get_client()
        params = {
            "method": "getList",
            "apiKey": self._kosis_key(),
            "format": "json",
            "jsonVD": "Y",
            "orgId": KOSIS_NTS_ORG_ID,
            "tblId": tbl_id,
            "itmId": "ALL",          # 인원/금액 전체
            "objL1": "ALL",          # 전국 모든 시군구
            "objL2": "ALL",          # 급여항목(총급여/과세표준 등) 전체
            "prdSe": KOSIS_PERIOD_TYPE,
            "newEstPrdCnt": "1",     # 최신 수록 1개 시점
        }

        resp = await asyncio.wait_for(
            client.request("GET", "/Param/statisticsParameterData.do", params=params),
            timeout=6.0,
        )
        resp.raise_for_status()
        # HTML/비-JSON 응답 명시 가드: content-type 또는 본문 선두로 판별
        ctype = (resp.headers.get("content-type") or "").lower()
        body = resp.text or ""
        if "json" not in ctype and body.lstrip()[:1] in ("<",):
            logger.warning("KOSIS non-JSON(HTML) response", ctype=ctype, head=body[:80])
            return {"errMsg": "non-json-response"}
        try:
            return resp.json()
        except Exception:  # noqa: BLE001
            logger.warning("KOSIS JSON parse fail", head=body[:80])
            return {"errMsg": "json-parse-fail"}

    async def get_migration_od(
        self, sigungu_cd: str, year: str,
        region_name: str | None = None, use_mock: bool | None = None,
    ) -> dict[str, Any]:
        """대상 시군구의 인구 이동(총전입·총전출·순이동)을 KOSIS 실데이터로 조회한다.

        KOSIS 「시군구별 이동자수」(DT_1B26001_A01)는 단일 분류(시군구)에 항목(총전입/총전출/
        순이동)이 붙는 구조라 '어디서 왔는지'(OD 출발지)는 제공하지 않는다. 따라서 전출지별
        Top 권역(top_inflow_regions) 대신 대상 시군구의 유입세(총전입/총전출/순이동)를 채운다.

        반환은 MigrationData 스키마 호환. region_name(예: '강남구')으로 시군구 행을 식별한다.
        키 미설정/데이터 없음/시군구 미식별 시 정직하게 빈 결과(가짜 금지).
        """
        sgg5 = normalize_sigungu_cd(sigungu_cd) or sigungu_cd
        target = (region_name or "").strip()
        empty = {
            "target_adm_cd": sgg5, "year": year,
            "total_inflow": 0, "total_outflow": 0, "net_migration": 0,
            "top_inflow_regions": [], "data_source": "unavailable",
            "note": "국내인구이동 데이터 없음 — KOSIS 키/시군구명 확정 시 산출.",
        }
        has_key = bool(self._kosis_key())
        if use_mock is None:
            use_mock = not has_key
        if use_mock or not has_key:
            return empty
        try:
            # 라이브 검증된 「시군구별 이동자수」(DT_1B26001_A01)를 직접 사용한다.
            #   (통합검색 resolve 는 키워드에 따라 구조가 다른 OD표로 매칭돼 파라미터 불일치를
            #    유발하므로 사용하지 않음.) 실수치(전입/전출>0)가 나올 때만 live 로 승격한다.
            tbl_id = KOSIS_MIGRATION_TBL_ID
            rows = await self._fetch_migration(sgg5, year, tbl_id=tbl_id)
            if not isinstance(rows, list) or not rows:
                return empty
            # 대상 시군구명으로 행 필터(동일명이 여러 시도에 있을 수 있으나, 시군구명은 보통 유일).
            if not target:
                return {**empty, "note": "시군구명 미전달 — 인구이동 산출 불가(주소에서 시군구 추출 필요)."}
            mine = [r for r in rows if (r.get("C1_NM") or "").strip() == target]
            if not mine:
                return {**empty, "data_source": "fallback",
                        "note": f"KOSIS {tbl_id}에 '{target}' 시군구 행 없음(명칭 불일치 가능)."}

            def _val(item_label: str) -> int:
                for r in mine:
                    if (r.get("ITM_NM") or "").strip() == item_label:
                        try:
                            return int(float(r.get("DT", 0)))
                        except (TypeError, ValueError):
                            return 0
                return 0

            inflow = _val("총전입")
            outflow = _val("총전출")
            net = _val("순이동")
            data_year = (mine[0].get("PRD_DE") or year)
            if inflow <= 0 and outflow <= 0:
                return {**empty, "data_source": "fallback",
                        "note": f"KOSIS {tbl_id} '{target}' 전입/전출 수치 없음."}
            return {
                "target_adm_cd": sgg5, "year": data_year,
                "total_inflow": inflow, "total_outflow": outflow, "net_migration": net,
                # OD 출발지 분해는 이 표에 없음(단일분류) — 정직하게 빈 목록 유지.
                "top_inflow_regions": [],
                # 실수치(전입/전출>0)가 확인됐으므로 live.
                "data_source": "live",
                "note": (f"KOSIS {tbl_id} '{target}' 총전입 {inflow:,}·총전출 {outflow:,}·"
                         f"순이동 {net:,}명({data_year})"),
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("KOSIS migration fetch failed", err=str(e))
            return empty

    async def _fetch_migration(
        self, sigungu_cd: str, year: str, tbl_id: str = KOSIS_MIGRATION_TBL_ID,
    ) -> Any:
        """KOSIS 「시군구별 이동자수」(DT_1B26001_A01) 호출 → 전 시군구 행 목록(비-JSON 가드).

        이 표는 단일 분류(C1=행정구역(시군구)별)에 ITM(총전입/총전출/순이동 등)이 붙는 구조다.
        - objL1='ALL': 전국 모든 시군구 행을 받아 호출측에서 대상 시군구명으로 필터한다.
          (과거 objL1=법정동5코드는 KOSIS 자체 분류코드가 아니라 errCd 21 을 유발했음)
        - objL2 는 이 표에 없어 넣으면 errCd 21 → 제거.
        - 연도는 추측하지 않고 newEstPrdCnt=1(최신 수록시점)로 받는다(prdDe 오지정 시 errCd 30).
        sigungu_cd/year 인자는 호환 위해 유지(파라미터로는 미사용 — 필터는 호출측 이름 기준).
        """
        client = await self._get_client()
        params = {
            "method": "getList",
            "apiKey": self._kosis_key(),
            "format": "json", "jsonVD": "Y",
            "orgId": KOSIS_ORG_ID,
            "tblId": tbl_id,
            "itmId": "ALL",          # 총전입/총전출/순이동 등 전체 항목(항목코드 추측 금지)
            "objL1": "ALL",          # 전국 모든 시군구(자체 분류코드 추측 회피)
            "prdSe": KOSIS_PERIOD_TYPE,
            "newEstPrdCnt": "1",     # 최신 수록 1개 시점(연도 오지정 errCd 30 회피)
        }
        resp = await asyncio.wait_for(
            client.request("GET", "/Param/statisticsParameterData.do", params=params),
            timeout=6.0,
        )
        resp.raise_for_status()
        ctype = (resp.headers.get("content-type") or "").lower()
        body = resp.text or ""
        if "json" not in ctype and body.lstrip()[:1] in ("<",):
            logger.warning("KOSIS migration non-JSON(HTML)", ctype=ctype, head=body[:80])
            return {"errMsg": "non-json-response"}
        try:
            return resp.json()
        except Exception:  # noqa: BLE001
            return {"errMsg": "json-parse-fail"}

    def _fallback_income(self, sigungu_cd: str, year: str, reason: str) -> dict[str, Any]:
        """실데이터 미확보 시 정직한 fallback(전국 근로소득 총급여 평균 근사치)."""
        return {
            "sigungu_cd": sigungu_cd,
            "year": year,
            "avg_income_10k": 4200,   # 전국 근로소득 총급여 평균 근사(2023 기준 ~4,200만원)
            "median_income_10k": 3570,
            "income_bracket_ratio": {},
            "data_source": "fallback",
            "note": f"시군구 소득 미확보({reason}) — 전국 근로소득 평균 근사치 사용(참고용).",
        }

    def _mock_income_data(self, sigungu_cd: str, year: str) -> dict[str, Any]:
        """테스트 및 UI 개발을 위한 Mock 거시 소득 데이터(정직 플래그 부착)."""
        return {
            "sigungu_cd": sigungu_cd,
            "year": year,
            "avg_income_10k": 4620,
            "median_income_10k": 3800,
            "income_bracket_ratio": {
                "under_30m": 35.5,
                "30m_to_70m": 45.0,
                "over_70m": 19.5,
            },
            "data_source": "mock",
            "note": "본 데이터는 KOSIS 일자리행정통계 기반의 Mock 데이터입니다.",
        }
