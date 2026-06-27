"""image_provider — 키+패키지 가드·정직 에러·env 모델 오버라이드·data URI 처리 검증(네트워크 불필요)."""
import asyncio

import pytest

from app.services.ai import image_provider as ip


def test_resolve_model_default_and_env_override(monkeypatch):
    monkeypatch.delenv("GEMINI_IMAGE_MODEL", raising=False)
    assert ip.resolve_model("google") == "gemini-2.5-flash-image"  # 기본
    monkeypatch.setenv("GEMINI_IMAGE_MODEL", "gemini-3-pro-image")
    assert ip.resolve_model("google") == "gemini-3-pro-image"      # ★신모델 ID env 오버라이드
    assert ip.resolve_model("openai") == "gpt-image-1"


def test_available_providers_gated_by_key_and_package(monkeypatch):
    # 키 없으면(그리고/또는 패키지 없으면) 미노출 — 반쪽출하 방지.
    for env in ("OPENAI_API_KEY", "GOOGLE_API_KEY", "REPLICATE_API_TOKEN"):
        monkeypatch.delenv(env, raising=False)
    assert ip.get_available_image_providers() == []
    # 키가 있어도 SDK 패키지가 없으면 여전히 미노출(가드).
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-xxxxxxxx")
    monkeypatch.setattr(ip, "_image_package_available", lambda p: False)
    assert ip.get_available_image_providers() == []
    # 키+패키지 둘 다 있으면 노출.
    monkeypatch.setattr(ip, "_image_package_available", lambda p: p == "openai")
    avail = {p["provider"] for p in ip.get_available_image_providers()}
    assert avail == {"openai"}


def test_unknown_provider_raises_honest_error():
    with pytest.raises(ip.ImageGenerationError) as ei:
        asyncio.run(ip.generate_image(provider="dalle9000", prompt="x"))
    assert ei.value.error_type == "unknown_provider"


def test_missing_package_raises_honest_error(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setattr(ip, "_image_package_available", lambda p: False)
    with pytest.raises(ip.ImageGenerationError) as ei:
        asyncio.run(ip.generate_image(provider="google", prompt="x"))
    assert ei.value.error_type == "package_missing"  # ★무목업: 가짜 이미지 대신 정직 예외


def test_missing_key_raises_honest_error(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(ip, "_image_package_available", lambda p: True)
    with pytest.raises(ip.ImageGenerationError) as ei:
        asyncio.run(ip.generate_image(provider="openai", prompt="x"))
    assert ei.value.error_type == "key_not_configured"


def test_data_uri_helpers():
    assert ip._strip_data_uri("data:image/png;base64,AAAA") == "AAAA"
    assert ip._strip_data_uri("AAAA") == "AAAA"
    assert ip._ensure_data_uri("AAAA").startswith("data:image/png;base64,")
    assert ip._ensure_data_uri("data:image/jpeg;base64,BBBB") == "data:image/jpeg;base64,BBBB"
