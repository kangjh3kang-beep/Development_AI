"""국제화(i18n) 통합 테스트 스켈레톤.

Accept-Language 헤더 기반 다국어 전환 검증.
i18n 미들웨어가 구현된 후 활성화.
"""

import pytest

pytestmark = pytest.mark.integration


@pytest.mark.skip(reason="Requires i18n middleware implementation")
class TestI18nLanguageSwitch:
    """Accept-Language 헤더 기반 다국어 전환 검증."""

    async def test_default_language_korean(self) -> None:
        """Accept-Language 미설정 시 기본 한국어 응답."""
        import httpx
        async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
            resp = await client.get("/health")
        assert resp.status_code == 200

    async def test_accept_language_ko(self) -> None:
        """Accept-Language: ko → 한국어 응답."""
        import httpx
        async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
            resp = await client.get(
                "/health",
                headers={"Accept-Language": "ko"},
            )
        assert resp.status_code == 200

    async def test_accept_language_en(self) -> None:
        """Accept-Language: en → 영어 응답."""
        import httpx
        async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
            resp = await client.get(
                "/health",
                headers={"Accept-Language": "en"},
            )
        assert resp.status_code == 200

    async def test_unsupported_language_fallback(self) -> None:
        """지원하지 않는 언어 → 기본 한국어 폴백."""
        import httpx
        async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
            resp = await client.get(
                "/health",
                headers={"Accept-Language": "ja"},
            )
        assert resp.status_code == 200
