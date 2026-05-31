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
_RESULT_CACHE = _TTLCache(ttl_sec=int(os.environ.get("INTERP_CACHE_TTL_SEC", "3600")))


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
    ) -> dict[str, str]:
        """시스템/유저 프롬프트로 LLM을 호출하고 파싱된 dict를 반환.

        - cache_data가 주어지면 입력 해시로 캐시 조회/저장(P4).
        - evidence_data가 주어지면 _evidence()로 추가 근거를 user_prompt에 부착(P3).
        - 시스템 프롬프트에는 그라운딩 규칙을 자동 주입(P3).
        - 모든 실패는 graceful: 빈 dict 반환(호출자 폴백).
        """
        cache_key = self._cache_key(cache_data) if cache_data is not None else None
        if cache_key:
            cached = _RESULT_CACHE.get(cache_key)
            if cached is not None:
                logger.info("인터프리터 캐시 적중", interp=self.name)
                return cached

        # P3: 추가 근거 부착
        if evidence_data is not None:
            extra = self._evidence(evidence_data)
            if extra:
                user_prompt = f"{user_prompt}\n\n## 추가 근거 자료\n{extra}"

        try:
            llm = self._get_llm()
        except Exception as e:  # noqa: BLE001
            logger.warning("LLM 초기화 실패", interp=self.name, error=str(e)[:120])
            return {}

        from langchain_core.messages import HumanMessage, SystemMessage

        system_prompt = (self.system_prompt or "") + GROUNDING_RULE
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        logger.info("인터프리터 LLM 요청", interp=self.name, prompt_chars=len(user_prompt))

        try:
            response = await asyncio.wait_for(
                llm.ainvoke(messages), timeout=self._timeout_sec
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("인터프리터 LLM 호출 실패", interp=self.name, error=str(e)[:120])
            return {}

        raw_text = response.content if hasattr(response, "content") else str(response)
        result = self._parse_response(raw_text)
        logger.info("인터프리터 LLM 완료", interp=self.name, keys=list(result.keys()))

        if cache_key and result:
            _RESULT_CACHE.set(cache_key, result)
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
