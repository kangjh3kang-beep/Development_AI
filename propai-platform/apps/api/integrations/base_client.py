"""외부 API 공통 베이스 클라이언트.

모든 외부 API 클라이언트가 상속한다.

기능:
- Circuit Breaker (CLOSED → OPEN → HALF_OPEN)
- 지수 백오프 재시도 (tenacity)
- Redis 기반 응답 캐시
- Prometheus 메트릭 (호출 수, 에러율, 응답 시간)
- 공통 오류 래핑
"""

import enum
import time

try:
    from enum import StrEnum
except ImportError:
    # Python 3.10 호환성 백포트
    class StrEnum(enum.StrEnum):
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


def _emit_growth_fallback(service_name: str, circuit_state: Any) -> None:
    """자가성장 엔진에 폴백/장애 이벤트 1건 발행(best-effort, 로직불변).

    외부 API 호출 실패 시 record_failure 인접에서 호출된다. 성장엔진 capture_service
    큐에 논블로킹 push 만 한다(동기 INSERT 없음). 어떤 예외도(import 실패·순환·큐
    오류) 호출경로로 전파하지 않는다 — 기존 재시도·circuit 로직에 영향 없음.
    """
    try:
        from app.services.growth import capture_service

        capture_service.record_event("fallback", {
            "surface": "api", "service": service_name, "severity": "error",
            "payload": {"circuit_state": str(circuit_state)},
        })
    except Exception:  # noqa: BLE001 — 수집은 절대 호출경로를 깨뜨리면 안 됨.
        pass


# threshold_relax effector multiplier 범위 가드(폭주·역효과 방지).
# 참고(M-1): rate_limit_multiplier 는 현재 BaseAPIClient 에 클라측 rate limiter 가
# 없어 미적용(예약 필드)이다. 실효 멀티플라이어는 timeout_multiplier 뿐이다.
_RELAX_MULT_MIN = 0.5
_RELAX_MULT_MAX = 3.0

# 핫패스 DB 오버헤드 방지용 프로세스-로컬 TTL 캐시(M-2).
# relax 값은 분 단위로 바뀌므로 짧은 TTL 캐시로 매 _request 마다의 platform_settings
# 조회(재시도 포함 최대 6 SELECT)를 제거한다. 캐시 미스/만료 시에만 DB 를 조회한다.
# 만료를 monotonic 시계로 판정하므로 TTL 경과 후 자동 재조회 → 자동 원복 의미 보존.
_RELAX_CACHE_TTL = 10.0  # 초
_relax_cache: dict[str, tuple[dict[str, float], float]] = {}


def _clamp_relax_mult(x: float) -> float:
    """multiplier 범위 가드(0.5~3.0). NaN 등 비정상은 기본값 1.0 으로."""
    try:
        if x != x:  # NaN
            return 1.0
        return max(_RELAX_MULT_MIN, min(_RELAX_MULT_MAX, x))
    except Exception:  # noqa: BLE001
        return 1.0


async def _read_relax_multipliers(service_name: str) -> dict[str, float]:
    """자가치유 threshold_relax 가 platform_settings 에 쓴 값을 best-effort 로 읽는다.

    heal_actions._do_threshold_relax 가 쓰는 키/값 구조와 정합:
      setting_key = f"relax.{service}" (service 없으면 "relax.global")
      value       = {"rate_limit_multiplier": float, "timeout_multiplier": float}
    TTL 만료 시 get_setting 이 None → 기본값(1.0) = 자동 원복.

    핫패스 보호(M-2): service_name 단위 프로세스-로컬 TTL 캐시(약 10초)를 먼저 본다.
    캐시 히트면 DB 미조회. 미스/만료 시에만 새 AsyncSession 1개를 짧게 열고 닫는다.
    캐시 조회/저장도 best-effort(예외 시 기본 1.0). 시계는 time.monotonic() 사용.

    반드시 best-effort: import 순환·DB 미가용·키 부재·예외 시 기본 {1.0, 1.0} 반환
    (기존 timeout/재시도 동작 그대로).
    service 전용 키가 없으면 relax.global 로 폴백. multiplier 는 범위로 클램프.
    """
    # 1) 프로세스-로컬 TTL 캐시 조회(best-effort). 히트 시 DB 미조회.
    try:
        now = time.monotonic()
        cached = _relax_cache.get(service_name)
        if cached is not None and cached[1] > now:
            return cached[0]
    except Exception:  # noqa: BLE001 — 캐시 조회 실패는 DB 조회로 폴백.
        pass

    timeout_mult = 1.0
    rate_mult = 1.0
    try:
        from app.services.growth import schema_guard
        from apps.api.database.session import AsyncSessionLocal

        async with AsyncSessionLocal() as _s:
            val = await schema_guard.get_setting(_s, f"relax.{service_name}")
            if not isinstance(val, dict):
                val = await schema_guard.get_setting(_s, "relax.global")
        if isinstance(val, dict):
            try:
                timeout_mult = float(val.get("timeout_multiplier", 1.0))
            except (TypeError, ValueError):
                timeout_mult = 1.0
            try:
                rate_mult = float(val.get("rate_limit_multiplier", 1.0))
            except (TypeError, ValueError):
                rate_mult = 1.0
    except Exception:  # noqa: BLE001 — 효과기는 절대 호출경로를 깨뜨리면 안 됨.
        return {"timeout_multiplier": 1.0, "rate_limit_multiplier": 1.0}

    result = {"timeout_multiplier": _clamp_relax_mult(timeout_mult),
              "rate_limit_multiplier": _clamp_relax_mult(rate_mult)}

    # 2) 캐시 저장(best-effort). 저장 실패해도 결과 반환에는 영향 없음.
    try:
        _relax_cache[service_name] = (result, time.monotonic() + _RELAX_CACHE_TTL)
    except Exception:  # noqa: BLE001
        pass

    return result


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

        # 자가치유 threshold_relax effector(best-effort·로직불변): platform_settings 의
        # relax.{service} timeout_multiplier 가 살아있으면 이 요청의 read 타임아웃을
        # 일시 상향(TTL 만료 시 자동 1.0 복귀). 실패·키부재 시 기본 타임아웃 그대로.
        request_kwargs: dict[str, Any] = {"params": params, "json": json_data}
        try:
            relax = await _read_relax_multipliers(self.service_name)
            # relax(완화)=상향만 의미. 하한 1.0 으로 클램프해 timeout 단축(0.5~1.0)을
            # 방지한다(클램프 상수는 그대로, 적용 지점에서만 하한 1.0). rate_limit 는 별개.
            tmult = max(1.0, relax.get("timeout_multiplier", 1.0))
            if tmult != 1.0:
                base_read = float(getattr(self, "timeout", 30.0) or 30.0)
                request_kwargs["timeout"] = httpx.Timeout(
                    connect=5.0, read=base_read * tmult, write=10.0, pool=5.0
                )
                logger.debug("threshold_relax 적용", service=self.service_name,
                             timeout_multiplier=tmult)
        except Exception:  # noqa: BLE001 — effector 실패는 기본 동작으로.
            pass

        try:
            response = await client.request(method, path, **request_kwargs)
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
            _emit_growth_fallback(self.service_name, self.circuit_breaker.state)  # 성장엔진 관측(로직불변·best-effort)
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
