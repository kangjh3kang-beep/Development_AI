"""외부 API 공통 베이스 클라이언트.

모든 외부 API 클라이언트가 상속한다.

기능:
- Circuit Breaker (CLOSED → OPEN → HALF_OPEN)
- 지수 백오프 재시도 (tenacity)
- Redis 기반 응답 캐시
- Prometheus 메트릭 (호출 수, 에러율, 응답 시간)
- 공통 오류 래핑
"""

import time
try:
    from enum import StrEnum
except ImportError:
    # Python 3.10 호환성 백포트
    from enum import Enum
    class StrEnum(str, Enum):
        pass
from typing import Any

import httpx
import structlog
from prometheus_client import Counter, Histogram
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from apps.api.config import get_settings
from apps.api.exceptions import ExternalServiceError

logger = structlog.get_logger(__name__)

# Prometheus 메트릭
EXTERNAL_API_REQUESTS = Counter(
    "propai_external_api_requests_total",
    "외부 API 호출 총 수",
    ["service", "method", "status"],
)
EXTERNAL_API_LATENCY = Histogram(
    "propai_external_api_latency_seconds",
    "외부 API 응답 시간",
    ["service"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Circuit Breaker 구현."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max: int = 3,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max = half_open_max
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: float = 0.0
        self.half_open_calls = 0

    def can_execute(self) -> bool:
        """요청 실행 가능 여부를 확인한다."""
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                return True
            return False

        # HALF_OPEN
        return self.half_open_calls < self.half_open_max

    def record_success(self) -> None:
        """성공 기록."""
        if self.state == CircuitState.HALF_OPEN:
            self.half_open_calls += 1
            if self.half_open_calls >= self.half_open_max:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
        self.failure_count = 0

    def record_failure(self) -> None:
        """실패 기록. 상태 전이 시 이전/이후 상태를 로그에 남긴다."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        prev_state = self.state

        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            if prev_state != CircuitState.OPEN:
                logger.warning(
                    "Circuit Breaker 상태 전이",
                    prev=prev_state,
                    next=self.state,
                    failures=self.failure_count,
                )


class BaseAPIClient:
    """외부 API 공통 베이스 클라이언트."""

    service_name: str = "unknown"
    base_url: str = ""
    timeout: float = 30.0

    def __init__(self) -> None:
        self.settings = get_settings()
        self.circuit_breaker = CircuitBreaker()
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """HTTP 클라이언트를 반환한다. 커넥션 풀 최적화 적용."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0),
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
                headers=self._default_headers(),
            )
        return self._client

    def _default_headers(self) -> dict[str, str]:
        """기본 헤더. 하위 클래스에서 오버라이드."""
        return {"User-Agent": "PropAI/30.0"}

    async def _get_cached(self, cache_key: str) -> Any | None:
        """Redis 캐시에서 조회한다."""
        try:
            import redis.asyncio as aioredis
            r = aioredis.from_url(self.settings.redis_url)
            data = await r.get(cache_key)
            await r.aclose()
            if data:
                import json
                return json.loads(data)
        except Exception:
            pass
        return None

    async def _set_cache(self, cache_key: str, data: Any, ttl: int = 3600) -> None:
        """Redis 캐시에 저장한다."""
        try:
            import json

            import redis.asyncio as aioredis
            r = aioredis.from_url(self.settings.redis_url)
            await r.setex(cache_key, ttl, json.dumps(data, ensure_ascii=False, default=str))
            await r.aclose()
        except Exception:
            pass

    async def _delete_cached(self, cache_key: str) -> None:
        """Redis 캐시에서 키를 삭제한다."""
        try:
            import redis.asyncio as aioredis
            r = aioredis.from_url(self.settings.redis_url)
            await r.delete(cache_key)
            await r.aclose()
        except Exception:
            pass

    @retry(
        retry=retry_if_exception_type(httpx.HTTPStatusError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json_data: dict | None = None,
        cache_key: str | None = None,
        cache_ttl: int = 3600,
    ) -> dict:
        """공통 HTTP 요청. Circuit Breaker + 재시도 + 캐시."""

        # 캐시 확인
        if cache_key and method.upper() == "GET":
            cached = await self._get_cached(cache_key)
            if cached is not None:
                logger.debug("캐시 히트", service=self.service_name, key=cache_key)
                return dict(cached)  # type: ignore[arg-type]

        # Circuit Breaker 확인
        if not self.circuit_breaker.can_execute():
            logger.warning("Circuit Breaker OPEN — 캐시 폴백", service=self.service_name)
            if cache_key:
                cached = await self._get_cached(cache_key)
                if cached is not None:
                    return dict(cached)  # type: ignore[arg-type]
            raise ExternalServiceError(self.service_name, "서비스 일시 중단")

        # HTTP 요청
        client = await self._get_client()
        start = time.perf_counter()

        try:
            response = await client.request(
                method, path, params=params, json=json_data,
            )
            response.raise_for_status()
            data: dict[str, Any] = response.json()

            self.circuit_breaker.record_success()
            duration = time.perf_counter() - start

            EXTERNAL_API_REQUESTS.labels(self.service_name, method, "success").inc()
            EXTERNAL_API_LATENCY.labels(self.service_name).observe(duration)

            # 캐시 저장
            if cache_key:
                await self._set_cache(cache_key, data, cache_ttl)

            return data

        except Exception as e:
            self.circuit_breaker.record_failure()
            EXTERNAL_API_REQUESTS.labels(self.service_name, method, "error").inc()
            logger.error("외부 API 호출 실패", service=self.service_name, error=str(e))
            # Circuit OPEN 시 Slack 알림
            if self.circuit_breaker.state == CircuitState.OPEN:
                await self._alert_ops(
                    f"{self.service_name}: {self.circuit_breaker.failure_count}회 연속 실패 — Circuit OPEN"
                )
            raise ExternalServiceError(self.service_name, str(e)) from e

    async def _alert_ops(self, message: str) -> None:
        """Slack #propai-alerts 채널로 장애 알림을 전송한다.

        Circuit Breaker 상태 변경 시 호출된다.
        Slack webhook URL이 설정되지 않은 경우 logger에만 기록한다.
        """
        payload = {
            "text": f":warning: *PropAI 외부 API 장애*\n"
            f"서비스: `{self.service_name}`\n"
            f"상태: `{self.circuit_breaker.state}`\n"
            f"연속 실패: {self.circuit_breaker.failure_count}회\n"
            f"내용: {message}",
            "channel": "#propai-alerts",
        }

        # 항상 구조화 로그 기록
        logger.warning(
            "OPS 알림 발생",
            service=self.service_name,
            circuit_state=str(self.circuit_breaker.state),
            failure_count=self.circuit_breaker.failure_count,
            message=message,
        )

        webhook_url = self.settings.slack_webhook_url
        if not webhook_url:
            logger.debug("Slack webhook URL 미설정 — 로그 기록만 수행")
            return

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(webhook_url, json=payload)
        except Exception:
            logger.debug("Slack 알림 전송 실패", service=self.service_name)

    async def close(self) -> None:
        """클라이언트를 종료한다."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
