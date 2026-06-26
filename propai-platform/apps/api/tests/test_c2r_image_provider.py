"""C2R image_provider 정직경로 테스트 — 키 없으면 provider_unconfigured(가짜 이미지 금지).

★핵심: 외부 키 없이도 통과해야 하며, 키가 없을 때 절대 가짜 이미지 바이트를 만들지 않는다.
환경변수/설정에 키가 없는 상태를 보장하기 위해 monkeypatch로 키를 제거한다.
"""

import pytest

from app.services.c2r.image_provider import render_image


def _brief() -> dict:
    return {
        "role": "부지 맞춤 건축 외관 렌더",
        "program": {"building_use": "공동주택", "scale": "중층"},
        "envelope_constraints": {
            "building_coverage_ratio_pct": {"value": 60},
            "floor_area_ratio_pct": {"value": 250},
        },
        "accuracy_guards": ["대지경계 보존"],
        "negative": ["조경 장식 금지"],
        "output": {"resolution": "1024x1024", "aspect_ratio": "1:1"},
    }


def _strip_keys(monkeypatch):
    """OPENAI/GEMINI 키를 env·canonical Settings 양쪽에서 비운다(미설정 상태 보장)."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    from app.core.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "OPENAI_API_KEY", "", raising=False)
    monkeypatch.setattr(s, "GEMINI_API_KEY", "", raising=False)


async def test_openai_unconfigured_when_no_key(monkeypatch):
    _strip_keys(monkeypatch)
    out = await render_image(_brief(), provider="openai")
    assert out["status"] == "provider_unconfigured"
    assert out["provider"] == "openai"
    assert out["image"] is None
    assert "OPENAI_API_KEY" in out["reason"]


async def test_gemini_unconfigured_when_no_key(monkeypatch):
    _strip_keys(monkeypatch)
    out = await render_image(_brief(), provider="gemini")
    assert out["status"] == "provider_unconfigured"
    assert out["provider"] == "gemini"
    assert out["image"] is None
    assert "GEMINI_API_KEY" in out["reason"]


async def test_no_fake_image_bytes_when_unconfigured(monkeypatch):
    """미설정 경로에서 image 가 절대 가짜 바이트를 갖지 않는다."""
    _strip_keys(monkeypatch)
    for provider in ("openai", "gemini"):
        out = await render_image(_brief(), provider=provider)
        assert out.get("image") is None


async def test_unsupported_provider(monkeypatch):
    _strip_keys(monkeypatch)
    out = await render_image(_brief(), provider="midjourney")
    assert out["status"] == "unsupported_provider"
    assert out["image"] is None


@pytest.mark.parametrize("provider", ["OpenAI", "  gemini  "])
async def test_provider_name_normalized(monkeypatch, provider):
    """provider 대소문자/공백을 정규화해도 정직 미설정 경로로 간다."""
    _strip_keys(monkeypatch)
    out = await render_image(_brief(), provider=provider)
    assert out["status"] == "provider_unconfigured"
