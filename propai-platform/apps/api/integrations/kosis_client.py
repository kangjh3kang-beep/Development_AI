"""KOSIS(국가통계포털) API 클라이언트.

광역 단위의 거시적 소득, 급여, 고용 통계 데이터 수집용.
공공데이터포털 연계 또는 KOSIS Open API 직접 연동.
"""

import asyncio
from typing import Any

import structlog
from apps.api.integrations.base_client import BaseAPIClient
from apps.api.app.core.config import settings as kosis_settings
from apps.api.app.services.market.market_models import MacroIncomeData

logger = structlog.get_logger(__name__)

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

    async def get_macro_income_stats(
        self,
        sigungu_cd: str,
        year: str,
        use_mock: bool = True
    ) -> dict[str, Any]:
        """해당 시/군/구의 연령별/산업별 평균 급여(소득) 거시 지표를 조회합니다.
        
        Args:
            sigungu_cd: 시군구 코드
            year: 조회 연도
            use_mock: True일 경우 시뮬레이션 데이터 반환
        """
        if use_mock or not getattr(self.api_settings, 'KOSIS_API_KEY', None):
            return self._mock_income_data(sigungu_cd, year)
            
        # 실제 KOSIS API 연동 로직
        try:
            client = await self._get_client()
            resp = await asyncio.wait_for(
                client.request(
                    "GET",
                    "/Param/statisticsParameterData.do",
                    params={
                        "method": "getList",
                        "apiKey": self.api_settings.KOSIS_API_KEY,
                        "format": "json",
                        "jsonVD": "Y",
                        "orgId": "101", # 통계청
                        "tblId": "DT_1EW0010", # 일자리행정통계(예시)
                        "itmId": "T10",
                        "objL1": sigungu_cd,
                        "prdSe": "Y",
                        "prdDe": year
                    }
                ),
                timeout=5.0
            )
            resp.raise_for_status()
            
            data = resp.json()
            if isinstance(data, dict) and data.get("errMsg"):
                logger.warning("KOSIS API Error", err=data)
                return self._mock_income_data(sigungu_cd, year)

            if not isinstance(data, list) or len(data) == 0:
                return self._mock_income_data(sigungu_cd, year)
                
            val = float(data[0].get("DT", 0))
            
            parsed_data = {
                "sigungu_cd": sigungu_cd,
                "year": year,
                "avg_income_10k": int(val) if val > 0 else 4620,
                "median_income_10k": int(val * 0.85) if val > 0 else 3800,
                "income_bracket_ratio": {
                    "under_30m": 35.5,
                    "30m_to_70m": 45.0,
                    "over_70m": 19.5
                }
            }
            
            validated = MacroIncomeData(**parsed_data)
            return validated.model_dump()
            
        except Exception as e:
            logger.warning("KOSIS data fetch failed, using fallback", err=str(e))
            return self._mock_income_data(sigungu_cd, year)

    def _mock_income_data(self, sigungu_cd: str, year: str) -> dict[str, Any]:
        """테스트 및 UI 개발을 위한 Mock 거시 소득 데이터."""
        return {
            "sigungu_cd": sigungu_cd,
            "year": year,
            "avg_income_10k": 4620,
            "median_income_10k": 3800,
            "income_bracket_ratio": {
                "under_30m": 35.5,
                "30m_to_70m": 45.0,
                "over_70m": 19.5
            },
            "note": "본 데이터는 KOSIS 일자리행정통계 기반의 Mock 데이터입니다."
        }
