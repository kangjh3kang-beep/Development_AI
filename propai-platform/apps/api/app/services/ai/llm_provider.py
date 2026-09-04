"""LLM 멀티 프로바이더 관리.

지원 프로바이더:
- anthropic: Claude (claude-sonnet-4-6, claude-opus-4-8, claude-haiku-4-5-20251001)
- openai: GPT (gpt-4o, gpt-4o-mini)
- google: Gemini (gemini-2.5-flash, gemini-2.5-pro, gemini-2.0-flash)

★프로바이더 노출은 'API 키 설정 + SDK 패키지 설치' 둘 다 충족 시에만(get_available_providers).
  langchain-google-genai 미설치 시 GOOGLE_API_KEY가 있어도 google은 노출하지 않는다(반쪽출하 방지).

사용법:
    from app.services.ai.llm_provider import get_llm, get_available_providers

    # 사용 가능한 프로바이더 조회
    providers = get_available_providers()

    # LLM 인스턴스 생성
    llm = get_llm(provider="anthropic", model="claude-sonnet-4-6")
    llm = get_llm(provider="openai", model="gpt-4o-mini")
    llm = get_llm(provider="google", model="gemini-2.5-flash")
"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# ── 등록된 프로바이더 목록 ──
class _TemperatureAwareChat:
    """`temperature` 를 거부하는 모델을 **런타임에 감지**해 그 인자 없이 재시도하는 얇은 래퍼.

    ★왜 래퍼인가 — 모델별 지원 여부를 표로 들고 있으면 **그 표가 곧 상한**이 된다.
      이 저장소는 이미 같은 자리에서 한 번 데였다(`llm_provider.py` 주석:
      *"구 claude-sonnet-4-20250514/opus-4-20250514는 퇴역 → 전 인터프리터 빈결과 유발"*).
      모델은 계속 바뀌므로 **실패를 보고 배우는** 쪽이 표보다 오래 산다.

    ★감지 조건은 좁게 둔다 — 400 계열 + 메시지에 `temperature`. 그 외 오류는 **그대로 올린다**
      (모든 실패를 삼키면 진짜 장애가 다시 조용해진다).
    ★재시도는 **한 번만**. 두 번째도 실패하면 원래 예외를 올린다.
    """

    __slots__ = ("_build", "_temperature", "_model_id", "_inner", "_dropped")

    def __init__(self, build: Any, temperature: float | None, model_id: str) -> None:
        self._build = build
        self._temperature = temperature
        self._model_id = model_id
        self._dropped = False
        self._inner = build(temperature)

    # 내부 객체의 속성(bind_tools·with_structured_output·model_name 등)을 그대로 위임한다.
    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    @staticmethod
    def _is_temperature_rejection(exc: Exception) -> bool:
        msg = str(exc)
        return "temperature" in msg and ("400" in msg or "invalid_request_error" in msg)

    def _drop_temperature(self) -> None:
        """이 인스턴스에서 temperature 를 영구히 뺀다(같은 객체 재사용 시 재실패 방지)."""
        self._inner = self._build(None)
        self._dropped = True
        logger.info(
            "모델이 temperature 를 거부해 해당 인자 없이 재시도한다",
            model=self._model_id,
        )

    async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
        try:
            return await self._inner.ainvoke(*args, **kwargs)
        except Exception as exc:
            if self._dropped or not self._is_temperature_rejection(exc):
                raise
            self._drop_temperature()
            return await self._inner.ainvoke(*args, **kwargs)

    def invoke(self, *args: Any, **kwargs: Any) -> Any:
        try:
            return self._inner.invoke(*args, **kwargs)
        except Exception as exc:
            if self._dropped or not self._is_temperature_rejection(exc):
                raise
            self._drop_temperature()
            return self._inner.invoke(*args, **kwargs)


PROVIDERS: dict[str, dict[str, Any]] = {
    "anthropic": {
        "name": "Anthropic Claude",
        # ★모델 ID는 Anthropic이 구버전을 퇴역(404 not_found)시키므로 현행 ID로 유지해야 한다.
        #   (구 claude-sonnet-4-20250514/opus-4-20250514는 퇴역 → 전 인터프리터 빈결과 유발).
        "models": [
            {"id": "claude-sonnet-4-6", "name": "Claude Sonnet 4.6", "tier": "standard"},
            {"id": "claude-opus-4-8", "name": "Claude Opus 4.8", "tier": "premium"},
            {"id": "claude-haiku-4-5-20251001", "name": "Claude Haiku 4.5", "tier": "economy"},
        ],
        "env_key": "ANTHROPIC_API_KEY",
        "default_model": "claude-sonnet-4-6",
    },
    "openai": {
        "name": "OpenAI GPT",
        "models": [
            {"id": "gpt-4o", "name": "GPT-4o", "tier": "standard"},
            {"id": "gpt-4o-mini", "name": "GPT-4o Mini", "tier": "economy"},
        ],
        "env_key": "OPENAI_API_KEY",
        "default_model": "gpt-4o-mini",
    },
    "google": {
        "name": "Google Gemini",
        "models": [
            {"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash", "tier": "economy"},
            {"id": "gemini-2.5-pro", "name": "Gemini 2.5 Pro", "tier": "standard"},
            {"id": "gemini-2.0-flash", "name": "Gemini 2.0 Flash (레거시)", "tier": "legacy"},
        ],
        "env_key": "GOOGLE_API_KEY",
        "default_model": "gemini-2.5-flash",
    },
}

# 프로바이더 키 → LLM SDK 패키지 임포트명(노출 가드용 — 미설치 프로바이더는 드롭다운 미노출).
_PROVIDER_PACKAGE = {
    "anthropic": "langchain_anthropic",
    "openai": "langchain_openai",
    "google": "langchain_google_genai",
}


def _provider_package_available(provider_key: str) -> bool:
    """프로바이더 LLM SDK 패키지가 실제 설치됐는지. ★미설치면 노출 금지(반쪽출하/dead-channel 방지).

    예: GOOGLE_API_KEY를 넣어도 langchain-google-genai 미설치면 google을 노출하지 않는다
    (노출 시 사용자가 선택→get_llm이 ModuleNotFoundError로 분석을 깨뜨리는 것을 사전 차단).
    """
    import importlib.util
    pkg = _PROVIDER_PACKAGE.get(provider_key)
    if not pkg:
        return False
    return importlib.util.find_spec(pkg) is not None


def get_available_providers() -> list[dict[str, Any]]:
    """API 키가 설정된 사용 가능한 프로바이더 목록 반환.

    Returns:
        각 프로바이더의 이름, 모델 목록, 기본 모델을 담은 dict 리스트.
        API 키가 환경변수에 설정되지 않은 프로바이더는 제외된다.
    """
    from app.services.ai.key_sanitizer import get_clean_env_key

    available: list[dict[str, Any]] = []
    for key, provider in PROVIDERS.items():
        api_key = get_clean_env_key(provider["env_key"])
        # ★키가 있어도 SDK 패키지가 미설치면 미노출(선택 시 ModuleNotFoundError로 깨지는 반쪽상태 방지).
        if api_key and _provider_package_available(key):
            available.append({
                "provider": key,
                "name": provider["name"],
                "models": provider["models"],
                "default_model": provider["default_model"],
            })
    return available


def _observe(llm: Any, service: str | None) -> Any:
    """`service` 가 주어졌을 때만 감싼다 — 안 주면 종전과 **바이트 동일**한 객체를 돌려준다."""
    return _ObservedChat(llm, service) if service else llm


def observe_llm(llm: Any, service: str) -> Any:
    """**직접 만든 LLM**에 실패 계측을 붙인다(`get_llm` 을 안 거치는 모듈용).

    일부 서비스는 `ChatOpenAI(...)` 를 직접 만들거나 자체 빌더를 쓴다. 그런 모듈은
    `get_llm(service=…)` 로 옵트인할 수 없어 관측 사각으로 남는다. 한 줄로 붙일 수 있게
    같은 래퍼를 공개한다 — `except` 블록을 손대지 않아도 된다.

    ★`service` 이름은 그 모듈이 `record_llm_response_billing` 에 넘기는 것과 **반드시 같아야**
      한다(분모·분자가 같은 버킷에 떨어져야 한다). `tests/test_llm_observability_pairing.py` 가 강제한다.
    """
    return _ObservedChat(llm, service)


class _ObservedChat:
    """LLM 을 감싸 **실패만** 성장루프에 남긴다(=`fallback_rate` 의 분자).

    ## 왜 팩토리에서 감싸나

    `llm_call` 이벤트는 오래도록 `BaseInterpreter` 안에서만 기록됐다. 그 밖에서
    `llm.ainvoke` 를 직접 부르는 서비스가 **21개**라 분모가 0이었고, 등기 권리분석이
    통째로 죽어도 인사이트가 한 번도 뜨지 않았다(2026-08-24 실장애).

    분모는 `record_llm_response_billing`(성공 시 호출)이 채웠지만 **분자**는 서비스마다
    `except` 안에 손으로 배선해야 했다 — 17개 모듈이 미배선으로 남았고, 그 상태에서
    분모만 흐르면 그 서비스는 **폴백률 0%** 로 읽힌다(침묵보다 나쁜 거짓 초록).

    그래서 **호출 지점이 아니라 팩토리**에서 감싼다. 서비스는 `get_llm(service="X")`
    한 줄만 더하면 실패가 자동으로 집계된다.

    ## 이중계상을 피하는 방법

    · **성공은 기록하지 않는다** — 분모는 이미 과금 헬퍼가 남긴다.
    · `BaseInterpreter` 는 `service` 를 넘기지 않으므로 **감싸이지 않는다**
      (그 클래스는 성공·실패를 스스로 기록한다).

    ## 이름은 반드시 분모와 같아야 한다

    `fallback_rate` SQL 은 `service` 로 GROUP BY 한다. 분자와 분모의 이름이 갈리면
    **서로 다른 버킷에 떨어져** 한쪽은 100%, 다른 쪽은 0% 가 된다 — 안 하느니 못하다.
    `tests/test_llm_observability_pairing.py` 가 그 동일성을 강제한다.
    """

    def __init__(self, inner: Any, service: str) -> None:
        self._inner = inner
        self._service = service

    def __getattr__(self, name: str) -> Any:
        # 나머지 속성(model·bind 등)은 그대로 위임한다 — 관측이 계약을 바꾸지 않는다.
        return getattr(self._inner, name)

    async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
        try:
            return await self._inner.ainvoke(*args, **kwargs)
        except BaseException as e:
            from app.services.ai.base_interpreter import record_llm_failure

            record_llm_failure(self._service, e)
            raise


def get_llm(
    provider: str = "anthropic",
    model: str | None = None,
    service: str | None = None,
    **kwargs: Any,
) -> Any:
    """지정된 프로바이더/모델로 LLM 인스턴스를 생성.

    Args:
        provider: 프로바이더 키 ("anthropic", "openai", "google")
        model: 모델 ID (None이면 프로바이더 기본 모델 사용)
        **kwargs: temperature, max_tokens, timeout 등 LLM 파라미터

    Returns:
        LangChain ChatModel 인스턴스

    Raises:
        ValueError: 알 수 없는 프로바이더이거나 API 키 미설정 시
    """
    config = PROVIDERS.get(provider)
    if not config:
        valid = ", ".join(PROVIDERS.keys())
        raise ValueError(
            f"Unknown provider: {provider}. Valid providers: {valid}"
        )

    from app.services.ai.key_sanitizer import get_clean_env_key

    # .env 복사 사고로 키에 비-ASCII('→')·공백·줄바꿈이 섞이면 httpx 헤더
    # 인코딩 단계에서 UnicodeEncodeError로 터진다. 로드 시점에 정상화한다.
    api_key = get_clean_env_key(config["env_key"])
    if not api_key:
        raise ValueError(
            f"{provider} API key not configured. "
            f"Set {config['env_key']} environment variable."
        )

    model_id = model or config["default_model"]

    # 모델 ID 유효성 검사
    valid_model_ids = [m["id"] for m in config["models"]]
    if model_id not in valid_model_ids:
        raise ValueError(
            f"Unknown model '{model_id}' for provider '{provider}'. "
            f"Valid models: {valid_model_ids}"
        )

    temperature = kwargs.get("temperature", 0.3)
    max_tokens = kwargs.get("max_tokens", 4096)
    timeout = kwargs.get("timeout", 10.0)

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        def _build(temp: float | None) -> Any:
            kw: dict[str, Any] = {
                "model": model_id,
                "anthropic_api_key": api_key,
                "max_tokens": max_tokens,
                "timeout": timeout,
            }
            if temp is not None:
                kw["temperature"] = temp
            return ChatAnthropic(**kw)

        # ★신세대 모델은 `temperature` 를 **거부**한다(400 invalid_request_error).
        #   2026-08-21 라이브 실측:
        #     claude-opus-5 / sonnet-5 / opus-4-8 → temp 지정 시 **FAIL**, 미지정 시 OK
        #     claude-sonnet-4-6 / haiku-4-5      → temp 지정해도 OK
        #   이 정책은 **모델 목록 API 가 알려주지 않는다**. 그래서 목록을 하드코딩하지 않고
        #   **호출 실패를 보고 판단**한다(목록형은 그 목록이 곧 상한이 된다).
        #   이 감지가 없던 동안 사용자가 프리미엄 모델을 고를수록 모든 해석이 죽었고,
        #   폴백이 "일시적으로 미제공"이라고만 말해 **아무도 몰랐다**.
        return _observe(_TemperatureAwareChat(_build, temperature, model_id), service)
    elif provider == "openai":
        from langchain_openai import ChatOpenAI

        return _observe(ChatOpenAI(
            model=model_id,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        ), service)
    elif provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return _observe(ChatGoogleGenerativeAI(
            model=model_id,
            google_api_key=api_key,
            temperature=temperature,
            max_output_tokens=max_tokens,
            timeout=timeout,
        ), service)
    else:
        raise ValueError(f"Unsupported provider: {provider}")
