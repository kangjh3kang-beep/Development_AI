import asyncio
import os
from typing import Any

import structlog

from apps.api.app.core.config import settings as sgis_settings
from apps.api.app.services.market.market_models import MigrationData, PopulationData
from apps.api.integrations.base_client import BaseAPIClient

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
    # SGIS OpenAPI 실제 처리 호스트. 문서상 sgisapi.kostat.go.kr 는 sgisapi.mods.go.kr 로
    # 302 리다이렉트되는데, 공용 httpx 클라이언트가 리다이렉트를 따르지 않아 인증이 실패했다
    # (원래 'mcds' 는 'mods' 오타로 DNS 미해석). 리다이렉트 회피 위해 처리 호스트를 직접 지정.
    base_url = "https://sgisapi.mods.go.kr"

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

    async def _fetch_with_auth_retry(
        self, path: str, params: dict, fallback_func: Any, *fallback_args: Any
    ) -> dict[str, Any]:
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

    # 법정동(MOLIT) 시도코드 → SGIS(통계청 KOSTAT) 시도코드. 서울만 우연히 11로 같고 나머지
    # 는 다르다(예: 경기 41→31). 강원/전북 특별자치(51/52)도 구 코드(32/35)로 매핑.
    _LAWD_TO_KOSTAT_SIDO = {
        "11": "11", "26": "21", "27": "22", "28": "23", "29": "24", "30": "25",
        "31": "26", "36": "29", "41": "31", "42": "32", "43": "33", "44": "34",
        "45": "35", "46": "36", "47": "37", "48": "38", "50": "39",
        "51": "32", "52": "35",
    }

    # SGIS searchpopulation age_type 코드 → 10세 단위 연령대(강남·파주 교차검증으로 확정).
    # 합이 총인구의 약 1% 내(인구총조사 경계/반올림)로 일치, 분포 형태 현실 부합(40대 피크).
    _AGE_TYPE_LABELS = {
        "30": "0-9", "31": "10-19", "32": "20-29", "33": "30-39", "34": "40-49",
        "35": "50-59", "36": "60-69", "37": "70-79", "38": "80-89", "39": "90+",
    }

    async def _fetch_age_distribution(self, sgis_cd: str, year: str) -> dict[str, int]:
        """SGIS 10세 단위 연령대별 인구를 동시 조회한다(실측). 실패 코드는 제외(정직)."""
        token = await self.get_access_token()
        if not token:
            return {}
        client = await self._get_client()

        async def one(at: str) -> tuple[str, int]:
            try:
                resp = await asyncio.wait_for(
                    client.request("GET", "/OpenAPI3/stats/searchpopulation.json",
                                   params={"accessToken": token, "year": year,
                                           "adm_cd": sgis_cd, "age_type": at}), timeout=6.0)
                data = resp.json()
                if data.get("errCd") == 0:
                    pop = sum(int(x.get("population", 0) or 0) for x in data.get("result", []))
                    return self._AGE_TYPE_LABELS[at], pop
            except Exception:  # noqa: BLE001
                pass
            return self._AGE_TYPE_LABELS[at], -1

        pairs = await asyncio.gather(*[one(at) for at in self._AGE_TYPE_LABELS])
        return {label: pop for label, pop in pairs if pop >= 0}

    async def _resolve_sgis_sigungu_cd(self, adm_cd: str, region_name: str | None) -> str | None:
        """법정동/시군구 코드 + 시군구명 → SGIS 자체 행정코드(예: 강남구 11230)를 해석한다.

        SGIS 통계는 법정동코드(11680)가 아닌 통계청 코드를 쓴다. 법정동 시도(앞 2자리)를 KOSTAT
        시도코드로 변환 후, 그 하위 시군구 목록(stage.json)에서 시군구명이 일치하는 SGIS 코드를
        찾는다. 못 찾으면 None.
        """
        lawd_sido = (adm_cd or "")[:2]
        sido = self._LAWD_TO_KOSTAT_SIDO.get(lawd_sido, lawd_sido)
        if not sido or not region_name:
            return None
        cache_key = f"sgis:stage:{sido}"
        cached = await self._get_cached(cache_key)
        children = cached if isinstance(cached, list) else None
        if children is None:
            token = await self.get_access_token()
            if not token:
                return None
            client = await self._get_client()
            resp = await asyncio.wait_for(
                client.request("GET", "/OpenAPI3/addr/stage.json",
                               params={"accessToken": token, "cd": sido}), timeout=6.0)
            resp.raise_for_status()
            children = (resp.json() or {}).get("result", [])
            if children:
                await self._set_cache(cache_key, children, ttl=7 * 24 * 3600)
        target = region_name.strip()
        for c in children or []:
            if (c.get("addr_name") or "").strip() == target:
                return c.get("cd")
        return None

    @staticmethod
    def _estimate_household_sizes(avg_size: float) -> dict[str, float]:
        """실측 평균 가구원수(SGIS)를 앵커로 1·2·3·4인+ 가구 비율(%)을 추정한다.

        SGIS는 가구원수별 분포를 직접 주지 않으므로(가구유형만 제공), 지역의 '실제' 평균
        가구원수에 맞춰 단조 보간한다(고정 상수 아님 — 지역별로 달라짐). 합=100.
        """
        a = max(1.2, min(3.2, avg_size or 2.3))
        # 평균이 작을수록 1인 비중↑. 앵커: avg 1.8→1인55%, 2.3→38%, 2.8→22%.
        one = max(10.0, min(60.0, 110.0 - 38.0 * a))
        four = max(8.0, min(45.0, 12.0 * a - 12.0))   # 평균 클수록 4인+↑
        rest = max(0.0, 100.0 - one - four)
        two, three = round(rest * 0.55, 1), round(rest * 0.45, 1)
        return {"1_person": round(one, 1), "2_person": two,
                "3_person": three, "4_over": round(four, 1)}

    def _fallback_population(self, adm_cd: str, year: str, reason: str = "") -> dict[str, Any]:
        """실데이터 미확보 시 정직 fallback(분포는 전국 평균 가구원수 2.3 기반 추정)."""
        return {
            "target_adm_cd": adm_cd, "year": year,
            "total_population": 0, "household_count": 0, "avg_household_size": 0.0,
            "age_distribution": {},
            "household_types": self._estimate_household_sizes(2.3),
            "data_source": "fallback",
            "note": f"SGIS 인구 미확보({reason}) — 가구원수 분포는 전국 평균 기반 추정.",
        }

    async def get_population_stats(
        self,
        adm_cd: str,
        year: str,
        region_name: str | None = None,
        use_mock: bool | None = None,
    ) -> dict[str, Any]:
        """대상 시군구의 총인구·가구수·평균가구원수를 SGIS 실데이터로 조회한다.

        총인구/가구수/평균가구원수는 실측(live). 가구원수별 분포는 SGIS 미제공이라 실측 평균을
        앵커로 추정(가짜 상수 금지·지역별 변동). region_name(예:'강남구')으로 SGIS 코드를 해석.
        SGIS 인구주택총조사는 최신이 보통 2023이라 요청연도→2023→2022 순으로 시도한다.
        """
        has_key = bool(self._sgis_key())
        if use_mock is None:
            use_mock = not has_key
        if use_mock or not has_key:
            return self._mock_population_data(adm_cd, year)

        try:
            sgis_cd = await self._resolve_sgis_sigungu_cd(adm_cd, region_name)
            if not sgis_cd:
                return self._fallback_population(adm_cd, year, "SGIS 시군구코드 미해석")

            # 인구주택총조사 수록연도 폴백(요청연도→최신 실측연도).
            years = [year] + [y for y in ("2023", "2022", "2021") if y != year]
            total = 0
            data_year = year
            for yr in years:
                pop = await self._fetch_with_auth_retry(
                    "/OpenAPI3/stats/searchpopulation.json",
                    {"year": yr, "adm_cd": sgis_cd},
                    self._fallback_population, adm_cd, year,
                )
                if isinstance(pop, dict) and "result" in pop:
                    total = sum(int(it.get("population", 0) or 0) for it in pop.get("result", []))
                    if total > 0:
                        data_year = yr
                        break
            if total <= 0:
                return self._fallback_population(adm_cd, year, "SGIS 인구 수록연도 없음")

            # 가구수·평균가구원수(실측).
            household_cnt = 0
            avg_size = 0.0
            hh = await self._fetch_with_auth_retry(
                "/OpenAPI3/stats/household.json",
                {"year": data_year, "adm_cd": sgis_cd},
                self._fallback_population, adm_cd, year,
            )
            if isinstance(hh, dict) and "result" in hh and hh.get("result"):
                row = hh["result"][0]
                household_cnt = int(row.get("household_cnt", 0) or 0)
                try:
                    avg_size = float(row.get("avg_family_member_cnt", 0) or 0)
                except (TypeError, ValueError):
                    avg_size = 0.0
            if avg_size <= 0 and household_cnt > 0:
                avg_size = round(total / household_cnt, 2)

            # 10세 단위 연령대별 인구(실측, 동시조회). 실패 시 빈 dict(정직).
            age_dist = await self._fetch_age_distribution(sgis_cd, data_year)

            parsed_data = {
                "target_adm_cd": adm_cd,
                "year": data_year,
                "total_population": total,
                "household_count": household_cnt,
                "avg_household_size": avg_size or round(total / max(household_cnt, 1), 2),
                "age_distribution": age_dist,  # 10세 단위 실측(0-9…90+)
                "household_types": self._estimate_household_sizes(avg_size or 2.3),
                "data_source": "live",  # 총인구·가구수·평균가구원수·연령분포는 실측.
                "note": (f"SGIS {data_year} 실측: 총인구 {total:,}·가구 {household_cnt:,}·"
                         f"평균 {avg_size}명·연령 {len(age_dist)}구간. 가구원수 분포는 평균 기반 추정."),
            }

            validated = PopulationData(**parsed_data)
            out = validated.model_dump()
            # 모델에 없는 부가 실측/주석 필드 보존.
            for k in ("household_count", "avg_household_size", "note"):
                out[k] = parsed_data[k]
            return out

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
