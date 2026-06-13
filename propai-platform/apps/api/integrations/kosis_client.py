"""KOSIS(국가통계포털) API 클라이언트.

광역 단위의 거시적 소득, 급여, 고용 통계 데이터 수집용.
공공데이터포털 연계 또는 KOSIS Open API 직접 연동.
"""

import asyncio
import os
from typing import Any

import structlog
from apps.api.integrations.base_client import BaseAPIClient
from apps.api.app.core.config import settings as kosis_settings
from apps.api.app.services.market.market_models import MacroIncomeData

logger = structlog.get_logger(__name__)

# ── KOSIS 통계표 설정(하드코딩 금지·설정가능 상수로 분리) ──
# 통계표ID(tblId)는 통계표 개편 시 변경되므로 상수로 분리해 한 곳에서 관리한다.
# ★ 아래 tblId 는 아직 운영 확정 전이다. 통계목록 조회 API(data.go.kr 15056860)로
#    소득/임금 통계표를 확정하기 전까지, 이 경로로 받은 값은 data_source='fallback' 로
#    정직 표기한다(실데이터로 단정하지 않음).
KOSIS_ORG_ID = "101"  # 통계청
KOSIS_INCOME_TBL_ID = "DT_1EW0010"  # 일자리행정통계(임시·미확정) — 확정 전까지 fallback 표기
KOSIS_INCOME_ITM_ID = "T10"
KOSIS_PERIOD_TYPE = "Y"  # 수록주기: 연

# ── 국내인구이동통계(OD) 설정 ──
# 전입지(현 시군구)로 유입된 인구의 전출지(이전 거주지)별 이동자수를 조회한다.
# ★ 아래 tblId/itmId 는 운영 확정 전(미검증)이다. 통계목록 API(data.go.kr 15056860)로
#    '국내인구이동통계 시군구별 전입' 표를 확정하기 전까지, 수신 데이터는 data_source='fallback'
#    로 정직 표기한다(실데이터로 단정하지 않음). 키·데이터 없으면 'unavailable'.
KOSIS_MIGRATION_TBL_ID = "DT_1B26001_A01"  # 국내인구이동통계(미확정)
KOSIS_MIGRATION_ITM_ID = "T1"               # 이동자수(미확정)
# KOSIS 응답에서 합계/전체를 의미하는 분류값명(전출지 Top 집계에서 제외).
_MIGRATION_TOTAL_LABELS = {"계", "전국", "소계", "합계", "전체"}


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

    async def get_macro_income_stats(
        self,
        sigungu_cd: str,
        year: str,
        use_mock: bool | None = None,
    ) -> dict[str, Any]:
        """해당 시/군/구의 연령별/산업별 평균 급여(소득) 거시 지표를 조회합니다.

        Args:
            sigungu_cd: 지역코드(법정동10/행정동10/SGIS8/시군구5/집계구13 등). 내부에서 시군구5로 정규화.
            year: 조회 연도
            use_mock: None(기본)이면 KOSIS_API_KEY 존재 여부로 자동 결정.
                      True 강제 시 mock, False 강제 시 키가 있으면 실연동 시도.
        """
        # 지역코드 정규화(이름매칭 금지·자릿수 기반 시군구5 절단)
        sgg5 = normalize_sigungu_cd(sigungu_cd) or sigungu_cd

        has_key = bool(self._kosis_key())
        # use_mock=None → 키 없으면 mock(폴백). 키 있으면 실연동 시도.
        if use_mock is None:
            use_mock = not has_key
        if use_mock or not has_key:
            return self._mock_income_data(sgg5, year)

        # 실제 KOSIS API 연동 로직
        try:
            data = await self._fetch_income(sgg5, year, obj_level="ALL")

            # KOSIS 에러 응답: errCd 20 = 필수요청변수 누락(분류레벨) → objL ALL 폴백 후 재시도
            if isinstance(data, dict) and str(data.get("errCd")) == "20":
                logger.info("KOSIS errCd 20 — objL ALL 폴백 재시도", sigungu=sgg5)
                data = await self._fetch_income(sgg5, year, obj_level="ALL", extra_levels=True)

            if isinstance(data, dict) and (data.get("errMsg") or data.get("errCd")):
                logger.warning("KOSIS API Error", err=data)
                return self._mock_income_data(sgg5, year)

            if not isinstance(data, list) or len(data) == 0:
                return self._mock_income_data(sgg5, year)

            val = float(data[0].get("DT", 0))

            parsed_data = {
                "sigungu_cd": sgg5,
                "year": year,
                "avg_income_10k": int(val) if val > 0 else 4620,
                "median_income_10k": int(val * 0.85) if val > 0 else 3800,
                "income_bracket_ratio": {
                    "under_30m": 35.5,
                    "30m_to_70m": 45.0,
                    "over_70m": 19.5,
                },
                # ★ 통계표ID 미확정 상태 → 호출에 성공해도 실데이터로 단정하지 않고 fallback 표기.
                #    통계목록 API로 tblId 확정 후 'live' 로 승격 예정.
                "data_source": "fallback",
            }

            validated = MacroIncomeData(**parsed_data)
            return validated.model_dump()

        except Exception as e:  # noqa: BLE001
            logger.warning("KOSIS data fetch failed, using fallback", err=str(e))
            return self._mock_income_data(sgg5, year)

    async def _fetch_income(
        self, sigungu_cd: str, year: str, obj_level: str = "ALL", extra_levels: bool = False
    ) -> Any:
        """KOSIS statisticsParameterData.do 호출 → JSON 파싱(비-JSON/HTML 가드 포함)."""
        client = await self._get_client()
        params = {
            "method": "getList",
            "apiKey": self._kosis_key(),
            "format": "json",
            "jsonVD": "Y",
            "orgId": KOSIS_ORG_ID,
            "tblId": KOSIS_INCOME_TBL_ID,
            "itmId": KOSIS_INCOME_ITM_ID,
            # objL1: 분류레벨 누락(errCd 20) 방지를 위해 ALL 우선 사용
            "objL1": obj_level if obj_level == "ALL" else sigungu_cd,
            "prdSe": KOSIS_PERIOD_TYPE,
            "prdDe": year,
        }
        # errCd 20 재시도 시 하위 분류레벨도 ALL 로 보강
        if extra_levels:
            params["objL2"] = "ALL"
            params["objL3"] = "ALL"

        resp = await asyncio.wait_for(
            client.request("GET", "/Param/statisticsParameterData.do", params=params),
            timeout=5.0,
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
        self, sigungu_cd: str, year: str, use_mock: bool | None = None,
    ) -> dict[str, Any]:
        """해당 시군구로의 전입 인구를 전출지(이전 거주지)별로 집계해 유입 Top 권역을 반환한다.

        반환은 MigrationData 스키마와 호환(target_adm_cd/total_inflow/top_inflow_regions/data_source).
        키 미설정/데이터 없음/통계표 미확정 시 정직하게 빈 결과(가짜 Top 금지).
        """
        sgg5 = normalize_sigungu_cd(sigungu_cd) or sigungu_cd
        empty = {
            "target_adm_cd": sgg5, "year": year,
            "total_inflow": 0, "total_outflow": 0, "net_migration": 0,
            "top_inflow_regions": [], "data_source": "unavailable",
            "note": "국내인구이동(OD) 데이터 없음 — KOSIS 키/통계표 확정 시 산출.",
        }
        has_key = bool(self._kosis_key())
        if use_mock is None:
            use_mock = not has_key
        if use_mock or not has_key:
            return empty
        try:
            rows = await self._fetch_migration(sgg5, year)
            if not isinstance(rows, list) or not rows:
                return empty
            regions: list[dict[str, Any]] = []
            for r in rows:
                name = (r.get("C1_NM") or r.get("C2_NM") or "").strip()
                try:
                    cnt = int(float(r.get("DT", 0)))
                except (TypeError, ValueError):
                    cnt = 0
                if name and cnt > 0 and name not in _MIGRATION_TOTAL_LABELS:
                    regions.append({"name": name, "count": cnt})
            if not regions:
                return empty
            regions.sort(key=lambda x: x["count"], reverse=True)
            total = sum(x["count"] for x in regions)
            top = regions[:3]
            for t in top:
                t["ratio"] = round(t["count"] / total * 100, 1) if total else 0.0
            return {
                "target_adm_cd": sgg5, "year": year,
                "total_inflow": total, "total_outflow": 0, "net_migration": 0,
                "top_inflow_regions": top,
                # 통계표ID 미확정 → 실데이터로 단정하지 않고 fallback(확정 후 live 승격).
                "data_source": "fallback",
                "note": "KOSIS 국내인구이동통계 기반(통계표 확정 전 추정). 전출지별 전입 Top.",
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("KOSIS migration OD fetch failed", err=str(e))
            return empty

    async def _fetch_migration(self, sigungu_cd: str, year: str) -> Any:
        """KOSIS 국내인구이동통계(전입지=시군구, 전출지별) 호출 → JSON(비-JSON 가드)."""
        client = await self._get_client()
        params = {
            "method": "getList",
            "apiKey": self._kosis_key(),
            "format": "json", "jsonVD": "Y",
            "orgId": KOSIS_ORG_ID,
            "tblId": KOSIS_MIGRATION_TBL_ID,
            "itmId": KOSIS_MIGRATION_ITM_ID,
            "objL1": sigungu_cd,  # 전입지(현 시군구)
            "objL2": "ALL",        # 전출지(이전 거주지) 전체
            "prdSe": KOSIS_PERIOD_TYPE, "prdDe": year,
        }
        resp = await asyncio.wait_for(
            client.request("GET", "/Param/statisticsParameterData.do", params=params),
            timeout=5.0,
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
