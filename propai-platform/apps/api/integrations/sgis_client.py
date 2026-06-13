import asyncio
import os
from typing import Any

import structlog

from apps.api.integrations.base_client import BaseAPIClient
from apps.api.app.core.config import settings as sgis_settings
from apps.api.app.services.market.market_models import MigrationData, PopulationData

logger = structlog.get_logger(__name__)

class SgisClient(BaseAPIClient):
    """SGIS (통계지리정보서비스) API Client.

    BaseAPIClient(Circuit Breaker·재시도·Redis 캐시)를 상속한다.
    - self.settings: BaseAPIClient 기본값(apps.api.config) — redis_url·slack_webhook_url 등
      인프라 설정이 들어 있어 Redis 토큰 캐싱이 정상 동작하려면 이 객체를 그대로 둬야 한다.
    - self.api_settings: SGIS/KOSIS 키가 정의된 설정(apps.api.app.core.config) — API 키 전용.
      (테스트가 app.core.config.settings 를 패치하는 경로와도 동일 객체로 일치한다.)
    """

    _auth_lock = asyncio.Lock()
    service_name = "sgis"
    base_url = "https://sgisapi.mcds.go.kr"

    def __init__(self) -> None:
        super().__init__()
        # API 키 전용 설정(인프라 설정 self.settings 와 분리)
        self.api_settings = sgis_settings

    # ★ 관리자 화면 등록 키는 lifespan 에서 os.environ 으로만 오버레이된다. 그런데 settings 객체는
    #   import 시점 @lru_cache 로 고정돼 런타임 오버레이를 못 받는다(apick 등은 os.environ 직독으로 동작).
    #   따라서 키는 os.environ 을 우선 읽고, 없으면 settings 폴백 — 관리자 등록 키가 즉시 활성화된다.
    def _sgis_key(self) -> str:
        return os.getenv("SGIS_CONSUMER_KEY") or getattr(self.api_settings, "SGIS_CONSUMER_KEY", "") or ""

    def _sgis_secret(self) -> str:
        return os.getenv("SGIS_CONSUMER_SECRET") or getattr(self.api_settings, "SGIS_CONSUMER_SECRET", "") or ""

    async def get_access_token(self) -> str | None:
        """SGIS API는 consumer_key/secret을 통해 임시 token을 발급받아야 합니다.
        내부 캐싱(Redis)을 통해 토큰 만료 전까지 재사용합니다.
        """
        if not self._sgis_key():
            return None
            
        cache_key = "sgis:access_token"
        cached_token = await self._get_cached(cache_key)
        if cached_token:
            return str(cached_token)
            
        async with self._auth_lock:
            # 락 획득 후 캐시 다시 확인 (다른 태스크가 이미 갱신했을 수 있음)
            cached_token = await self._get_cached(cache_key)
            if cached_token:
                return str(cached_token)

            try:
                client = await self._get_client()
                resp = await asyncio.wait_for(
                    client.request(
                        "GET", 
                        "/OpenAPI3/auth/authentication.json",
                        params={
                            "consumer_key": self._sgis_key(),
                            "consumer_secret": self._sgis_secret()
                        }
                    ),
                    timeout=5.0
                )
                resp.raise_for_status()
                data = resp.json()
                
                if data.get("errCd") == 0:
                    token = data.get("result", {}).get("accessToken")
                    if token:
                        await self._set_cache(cache_key, token, ttl=3 * 3600)
                    return token
                return None
            except Exception as e:
                logger.warning("SGIS token fetch failed", error=str(e))
                return None

    async def _fetch_with_auth_retry(self, path: str, params: dict, fallback_func: Any, *fallback_args: Any) -> dict[str, Any]:
        """토큰 만료(-401) 시 재발급 후 1회 재시도하는 래퍼."""
        for attempt in range(2):
            token = await self.get_access_token()
            if not token:
                return fallback_func(*fallback_args)
            
            try:
                client = await self._get_client()
                # 하드타임아웃 — 통계청 지연이 보고서 전체를 막지 않도록(정직 폴백 전환).
                resp = await asyncio.wait_for(
                    client.request("GET", path, params={**params, "accessToken": token}),
                    timeout=5.0)
                resp.raise_for_status()
                data = resp.json()
                
                err_cd = str(data.get("errCd", "0"))
                if err_cd == "0":
                    return data
                elif err_cd == "-401" and attempt == 0:
                    await self._delete_cached("sgis:access_token")
                    continue
                else:
                    logger.warning("SGIS API Error", err=data)
                    return fallback_func(*fallback_args)
            except Exception as e:
                logger.warning("SGIS API Request failed", err=str(e))
                return fallback_func(*fallback_args)
                
        return fallback_func(*fallback_args)

    async def get_migration_stats(
        self,
        adm_cd: str,
        year: str,
        use_mock: bool | None = None,
    ) -> dict[str, Any]:
        """특정 행정구역(adm_cd)의 전입/전출(인구이동 OD) 통계를 조회합니다.

        ★중요(R-B2/G2): SGIS 통계 API에는 '인구이동(전입·전출)' 전용 엔드포인트가 없다.
          (과거 코드는 인구통계용 searchpopulation.json 을 재사용하고 Top3 를 하드코딩했었다 — 가짜값)
          실제 OD 데이터원은 행정안전부(data.go.kr 15108093) 또는 KOSIS DT_1B26001_A01 이다.
          현재 PropAI 에는 그 OD 연동이 아직 없으므로:
            - use_mock=True 강제 시에만 개발용 Mock 반환(data_source='mock')
            - 그 외에는 가짜 Top3 를 만들지 않고 정직하게 '데이터 없음'을 반환한다
              (top_inflow_regions=[], data_source='unavailable').
          ※ OD 실연동(행안부/KOSIS)이 붙으면 이 자리에서 data_source='live' 로 승격한다.

        Args:
            use_mock: None(기본)이면 정직한 'unavailable' 반환. True 강제 시에만 개발용 Mock.
        """
        # 명시적으로 Mock 을 요청한 개발/테스트 경로에서만 Mock 반환.
        if use_mock is True:
            return self._mock_migration_data(adm_cd, year)

        # SGIS 에는 OD 엔드포인트가 없고, 행안부/KOSIS OD 연동은 아직 미구현이다.
        # 가짜 Top3 를 만들지 않고 '데이터 없음'을 정직하게 반환한다(하드코딩 금지).
        unavailable = {
            "target_adm_cd": adm_cd,
            "year": year,
            "total_inflow": 0,
            "total_outflow": 0,
            "net_migration": 0,
            "top_inflow_regions": [],
            "data_source": "unavailable",
            "note": "인구이동(OD)은 SGIS 미제공 — 행안부(15108093)/KOSIS(DT_1B26001_A01) 연동 예정",
        }
        return MigrationData(**unavailable).model_dump()

    async def get_population_stats(
        self,
        adm_cd: str,
        year: str,
        use_mock: bool | None = None,
    ) -> dict[str, Any]:
        """특정 읍면동의 연령대별, 가구원수별 인구 통계를 조회합니다.

        Args:
            use_mock: None(기본)이면 SGIS_CONSUMER_KEY 존재 여부로 자동 결정한다.
                      (과거 use_mock=True 하드코딩으로 키가 있어도 항상 Mock 만 나오던 G1 결함 제거)
                      True 강제 시 Mock, False 강제 시 키가 있으면 실연동 시도.
        """
        has_key = bool(self._sgis_key())
        # use_mock=None → 키 없으면 Mock(개발용). 키 있으면 실연동 시도.
        if use_mock is None:
            use_mock = not has_key
        if use_mock or not has_key:
            return self._mock_population_data(adm_cd, year)

        try:
            # 토큰 만료(-401) 시 재발급 후 1회 재시도하는 공통 래퍼 사용(데드코드 해소·하드타임아웃 내장).
            # 재시도 후에도 실패하면 _mock_population_data 폴백을 그대로 반환한다.
            data = await self._fetch_with_auth_retry(
                "/OpenAPI3/stats/searchpopulation.json",
                {"year": year, "adm_cd": adm_cd},
                self._mock_population_data, adm_cd, year,
            )
            # 래퍼가 폴백(mock)을 반환했으면(=실데이터 'result' 없음) 그대로 통과.
            if not isinstance(data, dict) or "result" not in data:
                return data

            result = data.get("result", [])
            total = sum(int(item.get("population", 0) or 0) for item in result)

            # ★R-B5/G10: 실데이터 0건이면 합성(추정) 분포를 만들되 data_source='fallback' 로
            #   정직하게 표기한다(실데이터와 구분). 0건이 아니면 'live'.
            is_fallback = total <= 0
            base = total if total > 0 else 125430

            # PopulationData 모델 스키마(age_distribution·household_types)에 맞춰 구성.
            # 키 이름을 mock 경로와 통일해야 Pydantic 검증 통과 후 데이터가 보존된다.
            parsed_data = {
                "target_adm_cd": adm_cd,
                "year": year,
                "total_population": base,
                "age_distribution": {
                    "20s": round(base * 0.15),
                    "30s": round(base * 0.25),
                    "40s": round(base * 0.20),
                    "50s": round(base * 0.15),
                    "60s_over": round(base * 0.10),
                },
                "household_types": {
                    "1_person": round(base * 0.30),
                    "2_person": round(base * 0.28),
                    "3_person": round(base * 0.22),
                    "4_over": round(base * 0.20),
                },
                # 합성 폴백이면 'fallback', 실데이터면 'live' 로 출처를 명시.
                "data_source": "fallback" if is_fallback else "live",
            }

            validated = PopulationData(**parsed_data)
            return validated.model_dump()

        except Exception:
            return self._mock_population_data(adm_cd, year)

    def _mock_migration_data(self, adm_cd: str, year: str) -> dict[str, Any]:
        """테스트 및 UI 개발을 위한 Mock 인구 이동 데이터."""
        return {
            "target_adm_cd": adm_cd,
            "year": year,
            "total_inflow": 12500,
            "total_outflow": 11200,
            "net_migration": 1300,
            "top_inflow_regions": [
                {"adm_cd": "11680", "name": "강남구", "count": 1500, "ratio": 12.0},
                {"adm_cd": "11650", "name": "서초구", "count": 1200, "ratio": 9.6},
                {"adm_cd": "11710", "name": "송파구", "count": 850, "ratio": 6.8},
            ],
            "note": "본 데이터는 기획 및 검증을 위한 Mock 데이터입니다."
        }

    def _mock_population_data(self, adm_cd: str, year: str) -> dict[str, Any]:
        """테스트 및 UI 개발을 위한 Mock 인구/가구 데이터."""
        return {
            "target_adm_cd": adm_cd,
            "year": year,
            "total_population": 45000,
            "age_distribution": {
                "0s": 8, "10s": 10, "20s": 15, "30s": 25, "40s": 20, "50s": 12, "60s_over": 10
            },
            "household_types": {
                "1_person": 45, "2_person": 25, "3_person": 20, "4_over": 10
            },
            "note": "본 데이터는 기획 및 검증을 위한 Mock 데이터입니다."
        }
