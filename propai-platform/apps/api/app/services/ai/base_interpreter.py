"""인터프리터 공통 기반 클래스 (P2/P3/P4 통합).

9개 LLM 해석 서비스(avm/market/feasibility/esg/permit/report/site_analysis/tax/cost)가
공유하는 LLM 생성·호출·파싱·캐시·그라운딩 로직을 한 곳에 모은다.

설계 원칙:
- P2(공통화): _get_llm / _invoke / _parse_response 를 기반 클래스로 단일화.
  버그를 한 곳에서 고치면 전체에 적용된다(과거 timeout·max_tokens 버그가 9곳
  반복이었던 교훈).
- P3(그라운딩): 시스템 프롬프트에 '수치 인용 강제·데이터 없으면 명시' 규칙을 자동
  주입해 환각을 줄인다. 서브클래스는 _evidence()를 오버라이드해 추가 근거(실거래·
  법규 RAG 등)를 주입할 수 있다(기본 None).
- P4(캐시): 동일 입력(컴팩트 데이터 해시) 재호출 시 LLM을 건너뛰고 결과를 재사용한다.
  in-process TTL 캐시 + 선택적 Redis(가용 시). 캐시 인프라가 없어도 무중단 동작.

서브클래스 계약:
    class FooInterpreter(BaseInterpreter):
        name = "foo"
        expected_keys = ["a", "b", ...]
        fallback_key = "a"           # JSON 파싱 완전 실패 시 원문을 담을 키
        max_tokens = 4096            # 출력 절단 방지(섹션 수에 비례)
        system_prompt = SYSTEM_PROMPT
        def _extract_compact_data(self, data): ...
        async def generate_interpretation(self, data):
            compact = self._extract_compact_data(data)
            prompt = USER_PROMPT_TEMPLATE.format(...)
            return await self._invoke(prompt, cache_data=compact)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from typing import Any

import structlog

logger = structlog.get_logger()

# ── P3: 그라운딩 규칙(시스템 프롬프트에 자동 주입) ──
GROUNDING_RULE = """\

[데이터 근거 규칙 — 반드시 준수]
- 모든 수치는 위에 제공된 데이터에서만 인용한다. 데이터에 없는 수치를 지어내지 않는다.
- 제공 데이터에 없는 값이 필요하면 "데이터 없음"으로 명시한다.
- 계산·추정한 값은 "추정" 또는 "약"을 붙여 사실값과 구분한다.
- 결론에는 근거가 된 수치를 함께 제시한다."""


# ── P4: 캐시(in-process TTL + 선택적 Redis) ──
class _TTLCache:
    """프로세스 내 TTL 캐시. Redis 가용 시 보조로 사용(없어도 동작)."""

    def __init__(self, ttl_sec: int = 3600, max_entries: int = 512) -> None:
        self._ttl = ttl_sec
        self._max = max_entries
        self._store: dict[str, tuple[float, dict[str, str]]] = {}

    def _now(self) -> float:
        # time.monotonic은 테스트 환경 제약(Date 금지)과 무관하게 안전.
        return time.monotonic()

    def get(self, key: str) -> dict[str, str] | None:
        item = self._store.get(key)
        if item is None:
            return None
        ts, val = item
        if self._now() - ts > self._ttl:
            self._store.pop(key, None)
            return None
        return val

    def set(self, key: str, value: dict[str, str]) -> None:
        if len(self._store) >= self._max:
            # 가장 오래된 1건 제거(간단한 용량 관리).
            oldest = min(self._store.items(), key=lambda kv: kv[1][0])[0]
            self._store.pop(oldest, None)
        self._store[key] = (self._now(), value)


# 인터프리터 전역 공유 캐시(클래스명+입력해시로 충돌 방지).
_CACHE_TTL_SEC = int(os.environ.get("INTERP_CACHE_TTL_SEC", "3600"))
_RESULT_CACHE = _TTLCache(ttl_sec=_CACHE_TTL_SEC)

# 기능 토글(운영 중 환경변수로 끌 수 있도록).
_REDIS_CACHE_ENABLED = os.environ.get("INTERP_REDIS_CACHE", "1") != "0"
_PROMPT_CACHE_ENABLED = os.environ.get("INTERP_PROMPT_CACHE", "1") != "0"


async def _redis_get(key: str | None) -> dict[str, str] | None:
    """P4-L2: Redis에서 결과 조회. 미가용/오류 시 None(무중단).

    integrations/base_client.py의 검증된 패턴(from_url→get→aclose)을 재사용.
    다중 워커/인스턴스 간 캐시 공유가 목적(L1은 프로세스 한정).
    """
    if not key or not _REDIS_CACHE_ENABLED:
        return None
    try:
        import redis.asyncio as aioredis

        from app.core.config import settings

        r = aioredis.from_url(settings.REDIS_URL)
        data = await r.get(key)
        await r.aclose()
        if data:
            return json.loads(data)
    except Exception:  # noqa: BLE001 — 캐시는 best-effort, 실패해도 LLM 호출로 진행
        pass
    return None


async def _redis_set(key: str | None, value: dict[str, str], ttl: int = _CACHE_TTL_SEC) -> None:
    """P4-L2: Redis에 결과 저장. 미가용/오류 시 무시(무중단)."""
    if not key or not _REDIS_CACHE_ENABLED:
        return
    try:
        import redis.asyncio as aioredis

        from app.core.config import settings

        r = aioredis.from_url(settings.REDIS_URL)
        await r.setex(key, ttl, json.dumps(value, ensure_ascii=False, default=str))
        await r.aclose()
    except Exception:  # noqa: BLE001
        pass


async def _record_llm_billing(
    model: str,
    input_tokens: int,
    output_tokens: int,
    service: str | None = None,
) -> None:
    """로그인 구독자(metered)의 LLM 사용량을 청구에 누적 + llm_usage_log 실계측(best-effort).

    요청 컨텍스트(미들웨어가 주입)의 user_id가 있을 때만 동작. 실패는 무시.
    service: 사용량 귀속 서비스명(인터프리터 self.name = site_analysis/market/... 등).
    토큰이 0이면(캐시 적중·계측 누락) 정직하게 미기록.
    """
    try:
        from app.core.request_context import get_current_user_id

        uid = get_current_user_id()
        if not uid:
            return
        if (input_tokens or 0) <= 0 and (output_tokens or 0) <= 0:
            return  # 토큰 미계측(캐시 등) — 정직하게 미기록
        from app.core.billing import model_cost_usd

        usd = model_cost_usd(model, input_tokens, output_tokens)
        if usd <= 0:
            return
        from app.core.database import async_session_factory
        from app.services.billing import billing_service

        async with async_session_factory() as db:
            await billing_service.record_usage_usd(
                db, uid, usd,
                service=service or "llm",
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
    except Exception:  # noqa: BLE001
        pass


class BaseInterpreter:
    """LLM 해석 인터프리터의 공통 기반."""

    # ── 서브클래스가 반드시 정의 ──
    name: str = "base"
    expected_keys: list[str] = []
    fallback_key: str = ""
    max_tokens: int = 4096
    system_prompt: str = ""

    def __init__(self, *, timeout_sec: float = 90.0) -> None:
        self._timeout_sec = timeout_sec
        self._llm: Any = None
        # 검증 실패 피드백(재생성 1회용). set_retry_feedback로 주입하면
        # _invoke가 user_prompt 뒤에 부착하고 캐시 키에 반영해 재생성을 강제한다.
        self._retry_feedback: str | None = None

    def set_retry_feedback(self, feedback: str | None) -> None:
        """검증관 이슈를 다음 1회 생성에 주입(재생성 피드백 루프).

        부착된 피드백은 프롬프트에 더해지고 캐시 키에 반영되므로, 같은 입력이라도
        피드백이 있으면 캐시를 우회해 LLM을 다시 호출한다(상한은 호출처가 통제).
        """
        self._retry_feedback = (feedback or "").strip() or None

    # ── P2: LLM 지연 생성(키 정상화 경유, ImportError 폴백) ──
    def _get_llm(self) -> Any:
        if self._llm is not None:
            return self._llm
        try:
            from app.services.ai.llm_provider import get_llm

            self._llm = get_llm(timeout=self._timeout_sec, max_tokens=self.max_tokens)
        except ImportError:
            from langchain_anthropic import ChatAnthropic

            from app.services.ai.key_sanitizer import get_clean_env_key

            self._llm = ChatAnthropic(
                model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
                anthropic_api_key=get_clean_env_key("ANTHROPIC_API_KEY"),
                temperature=0.3,
                max_tokens=self.max_tokens,
                timeout=self._timeout_sec,
            )
        return self._llm

    # ── P3: 추가 근거 주입 훅(서브클래스 오버라이드) ──
    def _evidence(self, data: dict) -> str | None:  # noqa: ARG002
        """서브클래스가 실거래·법규 RAG·지역통계 등 추가 근거를 반환하면
        user_prompt 뒤에 붙는다. 기본은 None(추가 근거 없음)."""
        return None

    @staticmethod
    def _regional_benchmark(address: str = "", region: str = "") -> str | None:
        """P3: 지역 평균 분양가 벤치마크를 근거 문자열로 반환.

        regional_pricing(sync·외부키 불필요·결정적)만 사용해 결합도·지연·키의존을
        만들지 않는다. 실거래가/법규RAG/용도지역 같은 async+키 소스는 호출처가
        data로 주입하는 게 올바른 계층이라 여기서 직접 호출하지 않는다.
        주소를 못 찾으면 None(근거 미부착).
        """
        if not (address or region):
            return None
        try:
            from app.services.feasibility.regional_pricing import (
                get_regional_base_price_man_won,
            )

            man_won = get_regional_base_price_man_won(region=region, address=address)
            if man_won:
                won_per_sqm = int(man_won * 10000 / 3.305785)
                return (
                    f"- 지역 평균 분양가 벤치마크: 약 {man_won:,}만원/평"
                    f"(약 {won_per_sqm:,}원/㎡), 2026년 보수적 시세 테이블 기준. "
                    f"이 값과 분석 데이터의 가격을 비교해 적정성을 판단할 것."
                )
        except Exception:  # noqa: BLE001
            pass
        return None

    # ── P4: 캐시 키 ──
    def _cache_key(self, cache_data: Any) -> str:
        payload = json.dumps(cache_data, ensure_ascii=False, sort_keys=True, default=str)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
        return f"{self.name}:{self.max_tokens}:{digest}"

    # ── P2+P3+P4: 통합 호출 진입점 ──
    async def _invoke(
        self,
        user_prompt: str,
        *,
        cache_data: Any = None,
        evidence_data: dict | None = None,
        evidence_text: str | None = None,
    ) -> dict[str, str]:
        """시스템/유저 프롬프트로 LLM을 호출하고 파싱된 dict를 반환.

        - cache_data가 주어지면 입력 해시로 캐시 조회/저장(P4).
        - evidence_data가 주어지면 _evidence()로 sync 근거(지역시세 등)를 부착(P3).
        - evidence_text가 주어지면 호출처(서비스/라우터)가 async로 만든 근거
          (MOLIT 실거래·법규 RAG 등)를 그대로 부착(P3 라우터 주입). 키·async는
          호출처 책임. evidence_text는 캐시 키에 반영돼 근거가 다르면 다른 결과로 본다.
        - 시스템 프롬프트에는 그라운딩 규칙을 자동 주입(P3).
        - 모든 실패는 graceful: 빈 dict 반환(호출자 폴백).
        """
        # P4: evidence_text는 결과를 바꾸므로 캐시 키에 포함(근거 다르면 캐시 분리).
        if cache_data is not None and evidence_text:
            cache_data = {"_data": cache_data, "_evidence": evidence_text}
        # 검증 재생성 피드백도 결과를 바꾸므로 캐시 키에 포함 → 기존 캐시 우회(재호출 강제).
        if cache_data is not None and self._retry_feedback:
            cache_data = {"_data": cache_data, "_retry": self._retry_feedback}

        # P4: L1(in-process) → L2(Redis) 순으로 조회. 적중 시 LLM 스킵.
        cache_key = self._cache_key(cache_data) if cache_data is not None else None
        redis_key = f"interp:{cache_key}" if cache_key else None
        if cache_key:
            cached = _RESULT_CACHE.get(cache_key)
            if cached is not None:
                logger.info("인터프리터 캐시 적중(L1)", interp=self.name)
                return cached
            l2 = await _redis_get(redis_key)
            if l2 is not None:
                logger.info("인터프리터 캐시 적중(L2 Redis)", interp=self.name)
                _RESULT_CACHE.set(cache_key, l2)  # L1 워밍
                return l2

        # P3: 추가 근거 부착 — (1) sync 자체근거(_evidence: 지역시세 등)
        #                        (2) 호출처 주입 근거(evidence_text: MOLIT·법규RAG 등)
        evidences: list[str] = []
        if evidence_data is not None:
            extra = self._evidence(evidence_data)
            if extra:
                evidences.append(extra)
        if evidence_text:
            evidences.append(evidence_text)
        if evidences:
            joined = "\n".join(evidences)
            user_prompt = f"{user_prompt}\n\n## 추가 근거 자료\n{joined}"
        # 검증 재생성 피드백 부착 — 직전 출력의 결함(할루시네이션·수치불일치 등)을
        # 교정하도록 강한 지시를 프롬프트 말미에 추가(1회 재생성용).
        if self._retry_feedback:
            user_prompt = (
                f"{user_prompt}\n\n## 검증 실패 — 재작성 필수\n"
                f"직전 응답이 아래 사유로 검증에 실패했습니다. 반드시 교정해 다시 작성하세요.\n"
                f"제공된 데이터에 근거하지 않은 수치·사실을 제거하고, 모든 값은 원본 데이터에서만 "
                f"인용하세요(없으면 '데이터 없음'으로 명시).\n{self._retry_feedback}"
            )

        try:
            llm = self._get_llm()
        except Exception as e:  # noqa: BLE001
            logger.warning("LLM 초기화 실패", interp=self.name, error=str(e)[:120])
            return {}

        from langchain_core.messages import HumanMessage, SystemMessage

        # P3: 그라운딩 규칙을 시스템 프롬프트에 결합.
        system_text = (self.system_prompt or "") + GROUNDING_RULE
        # P4-b: Anthropic prompt caching — 고정 시스템 프롬프트를 ephemeral 블록으로
        # 표기하면 재호출 시 입력 토큰을 캐시에서 읽어 비용↓(시스템 프롬프트가
        # 캐시 최소 토큰 미만이면 Anthropic이 무시, 오류 없음). 비-Anthropic이면
        # 일반 문자열로 폴백.
        if _PROMPT_CACHE_ENABLED:
            system_content: Any = [
                {"type": "text", "text": system_text, "cache_control": {"type": "ephemeral"}}
            ]
        else:
            system_content = system_text
        messages = [
            SystemMessage(content=system_content),
            HumanMessage(content=user_prompt),
        ]
        logger.info("인터프리터 LLM 요청", interp=self.name, prompt_chars=len(user_prompt))

        # LangSmith 트레이스 라벨링: 어떤 인터프리터·어떤 사용자의 호출인지 식별 가능하게.
        # (추적 비활성이면 LangChain이 이 config를 무시하므로 완전 무해.)
        try:
            from app.core.request_context import get_current_user_id

            _trace_cfg: dict[str, Any] = {
                "run_name": f"interp:{self.name}",
                "tags": ["propai", "interpreter", self.name],
                "metadata": {
                    "service": self.name,
                    "user_id": get_current_user_id() or "anon",
                },
            }
        except Exception:  # noqa: BLE001
            _trace_cfg = {}

        try:
            response = await asyncio.wait_for(
                llm.ainvoke(messages, config=_trace_cfg), timeout=self._timeout_sec
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("인터프리터 LLM 호출 실패", interp=self.name, error=str(e)[:120])
            return {}

        raw_text = response.content if hasattr(response, "content") else str(response)
        result = self._parse_response(raw_text)

        # P4-b: prompt caching 효과 모니터링 — cache_read 비율 로깅.
        # langchain usage_metadata.input_token_details.{cache_read,cache_creation}
        cache_read = cache_creation = input_tokens = output_tokens = 0
        try:
            meta = getattr(response, "usage_metadata", None) or {}
            details = meta.get("input_token_details", {}) if isinstance(meta, dict) else {}
            cache_read = int(details.get("cache_read", 0) or 0)
            cache_creation = int(details.get("cache_creation", 0) or 0)
            input_tokens = int(meta.get("input_tokens", 0) or 0) if isinstance(meta, dict) else 0
            output_tokens = int(meta.get("output_tokens", 0) or 0) if isinstance(meta, dict) else 0
        except Exception:  # noqa: BLE001
            pass

        # 과금: 로그인 구독자면 이번 LLM 사용량을 청구에 누적 + service 귀속 실계측(best-effort).
        await _record_llm_billing(
            getattr(llm, "model", ""), input_tokens, output_tokens, service=self.name
        )
        cached_total = cache_read + cache_creation
        cache_hit_ratio = round(cache_read / cached_total, 3) if cached_total else 0.0
        logger.info(
            "인터프리터 LLM 완료",
            interp=self.name,
            keys=list(result.keys()),
            input_tokens=input_tokens,
            cache_read=cache_read,
            cache_creation=cache_creation,
            cache_hit_ratio=cache_hit_ratio,
        )

        # P4: 결과를 L1·L2 모두에 저장.
        if cache_key and result:
            _RESULT_CACHE.set(cache_key, result)
            await _redis_set(redis_key, result)
        return result

    # ── P2: 공통 JSON 파서(expected_keys/fallback_key 파라미터화) ──
    def _parse_response(self, raw: str) -> dict[str, str]:
        text = raw.strip()

        # ```json ... ``` 코드블록 제거
        if text.startswith("```"):
            lines = text.split("\n")
            end = len(lines)
            for i in range(len(lines) - 1, 0, -1):
                if lines[i].strip() == "```":
                    end = i
                    break
            text = "\n".join(lines[1:end])

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            brace_start = text.find("{")
            brace_end = text.rfind("}")
            if brace_start != -1 and brace_end != -1:
                try:
                    parsed = json.loads(text[brace_start : brace_end + 1])
                except json.JSONDecodeError:
                    logger.warning("AI 응답 JSON 파싱 최종 실패", interp=self.name, raw_length=len(raw))
                    return {self.fallback_key: text[:500]} if self.fallback_key else {}
            else:
                logger.warning("AI 응답에서 JSON 미발견", interp=self.name, raw_length=len(raw))
                return {self.fallback_key: text[:500]} if self.fallback_key else {}

        result: dict[str, str] = {}
        for key in self.expected_keys:
            val = parsed.get(key)
            if val is not None:
                result[key] = str(val)
        return result
