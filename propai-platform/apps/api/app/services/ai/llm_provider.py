"""LLM 멀티 프로바이더 관리.

지원 프로바이더:
- anthropic: Claude (claude-sonnet-4-20250514, claude-opus-4-20250514)
- openai: GPT (gpt-4o, gpt-4o-mini)
- google: Gemini (gemini-2.0-flash, gemini-2.5-pro)

사용법:
    from app.services.ai.llm_provider import get_llm, get_available_providers

    # 사용 가능한 프로바이더 조회
    providers = get_available_providers()

    # LLM 인스턴스 생성
    llm = get_llm(provider="anthropic", model="claude-sonnet-4-20250514")
    llm = get_llm(provider="openai", model="gpt-4o-mini")
    llm = get_llm(provider="google", model="gemini-2.0-flash")
"""

from __future__ import annotations

import os
from typing import Any

# ── 등록된 프로바이더 목록 ──
PROVIDERS: dict[str, dict[str, Any]] = {
    "anthropic": {
        "name": "Anthropic Claude",
        "models": [
            {"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4", "tier": "standard"},
            {"id": "claude-opus-4-20250514", "name": "Claude Opus 4", "tier": "premium"},
        ],
        "env_key": "ANTHROPIC_API_KEY",
        "default_model": "claude-sonnet-4-20250514",
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
            {"id": "gemini-2.0-flash", "name": "Gemini 2.0 Flash", "tier": "economy"},
            {"id": "gemini-2.5-pro", "name": "Gemini 2.5 Pro", "tier": "standard"},
        ],
        "env_key": "GOOGLE_API_KEY",
        "default_model": "gemini-2.0-flash",
    },
}


def get_available_providers() -> list[dict[str, Any]]:
    """API 키가 설정된 사용 가능한 프로바이더 목록 반환.

    Returns:
        각 프로바이더의 이름, 모델 목록, 기본 모델을 담은 dict 리스트.
        API 키가 환경변수에 설정되지 않은 프로바이더는 제외된다.
    """
    available: list[dict[str, Any]] = []
    for key, provider in PROVIDERS.items():
        api_key = os.environ.get(provider["env_key"], "")
        if api_key:
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

    api_key = os.environ.get(config["env_key"], "")
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
    max_tokens = kwargs.get("max_tokens", 2048)
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
