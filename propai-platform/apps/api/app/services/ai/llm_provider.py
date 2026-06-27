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

# ── 등록된 프로바이더 목록 ──
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


def get_llm(
    provider: str = "anthropic",
    model: str | None = None,
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

        return ChatAnthropic(
            model=model_id,
            anthropic_api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )
    elif provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model_id,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )
    elif provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model_id,
            google_api_key=api_key,
            temperature=temperature,
            max_output_tokens=max_tokens,
            timeout=timeout,
        )
    else:
        raise ValueError(f"Unsupported provider: {provider}")
