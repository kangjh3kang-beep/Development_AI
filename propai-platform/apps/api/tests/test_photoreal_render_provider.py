"""포토리얼 렌더 프로바이더 선택형(INC2) 테스트 — openai/google img2img + 가용목록 엔드포인트.

검증 경로(공용 image_provider는 monkeypatch stub — 실제 외부 호출 0회):
1. provider="openai"/"google" → generate_image 호출 → status=ok + image_base64
2. ImageGenerationError(key_not_configured)→no_key, (api_error)→error (정직 강등)
3. provider=None → 기존 replicate 경로(키 부재 시 no_key — 회귀 없음)
4. images/image_urls 모두 비면 → status=error(가짜 이미지 금지)
5. image_urls만 채워지면 → status=ok + image_url
6. 빈 입력 이미지(openai 분기) → 외부 호출 전 status=error(기존 가드 유지)
7. GET /api/v1/design/image-providers → get_available_image_providers 결과 노출
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services.ai.image_provider import ImageGenerationError
from app.services.drawing import photoreal_render_service as svc

_FAKE_IMAGE_B64 = "iVBORw0KGgoAAAANSUhEUg=="
_OUT_B64 = "BASE64_GENERATED_IMAGE_PAYLOAD=="
_OUT_URL = "https://example.com/generated.png"


# ──────────────────────────────────────────────
# 1. openai/google 성공 → image_base64
# ──────────────────────────────────────────────


class TestProviderSuccess:
    """openai/google 선택 시 공용 image_provider(img2img)로 성공 반환."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("provider", ["openai", "google"])
    async def test_프로바이더_성공_image_base64(self, monkeypatch, provider):
        """generate_image stub(images=[b64]) → status=ok + image_base64 + 입력 구조보존."""
        captured = {}

        async def _stub(prov, *, prompt, model=None, input_image_b64=None, size=None, timeout=None, **kw):
            captured.update(
                provider=prov, prompt=prompt, model=model,
                input_image_b64=input_image_b64, size=size,
            )
            return {"provider": prov, "model": model or "default-model", "images": [_OUT_B64], "image_urls": []}

        monkeypatch.setattr(svc, "generate_image", _stub, raising=False)
        # 서비스가 함수 내부에서 import하므로 모듈 경로도 patch.
        import app.services.ai.image_provider as ip
        monkeypatch.setattr(ip, "generate_image", _stub)

        result = await svc.render_photoreal(
            _FAKE_IMAGE_B64, style="야간", provider=provider, model="custom-model"
        )

        assert result["status"] == "ok"
        assert result["image_base64"] == _OUT_B64
        assert result["provider"] == provider
        assert result["model"] == "custom-model"
        assert "image_url" not in result
        # img2img: 3D 캡처가 input_image_b64로 전달되어 구조 보존.
        assert captured["input_image_b64"] == _FAKE_IMAGE_B64
        assert captured["provider"] == provider
        assert captured["model"] == "custom-model"

    @pytest.mark.asyncio
    async def test_image_urls만_채워지면_image_url(self, monkeypatch):
        """images 비고 image_urls만 있으면 status=ok + image_url(공용 계약)."""
        async def _stub(prov, **kw):
            return {"provider": prov, "model": "m", "images": [], "image_urls": [_OUT_URL]}

        import app.services.ai.image_provider as ip
        monkeypatch.setattr(ip, "generate_image", _stub)

        result = await svc.render_photoreal(_FAKE_IMAGE_B64, provider="openai")

        assert result["status"] == "ok"
        assert result["image_url"] == _OUT_URL
        assert "image_base64" not in result


# ──────────────────────────────────────────────
# 2. 정직 강등 — ImageGenerationError 매핑
# ──────────────────────────────────────────────


class TestHonestDegrade:
    """ImageGenerationError를 가짜 이미지 없이 no_key/error로 정직 매핑한다."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("err_type", ["key_not_configured", "package_missing"])
    async def test_키_패키지_부재_no_key(self, monkeypatch, err_type):
        """키/SDK 부재(key_not_configured/package_missing) → status=no_key."""
        async def _raise(prov, **kw):
            raise ImageGenerationError("미설정", error_type=err_type)

        import app.services.ai.image_provider as ip
        monkeypatch.setattr(ip, "generate_image", _raise)

        result = await svc.render_photoreal(_FAKE_IMAGE_B64, provider="google")

        assert result["status"] == "no_key"
        assert result["provider"] == "google"
        assert "image_base64" not in result and "image_url" not in result

    @pytest.mark.asyncio
    async def test_api_오류_error(self, monkeypatch):
        """api_error(외부 호출 실패) → status=error(가짜 이미지 금지)."""
        async def _raise(prov, **kw):
            raise ImageGenerationError("외부 API 실패", error_type="api_error")

        import app.services.ai.image_provider as ip
        monkeypatch.setattr(ip, "generate_image", _raise)

        result = await svc.render_photoreal(_FAKE_IMAGE_B64, provider="openai")

        assert result["status"] == "error"
        assert "image_base64" not in result and "image_url" not in result

    @pytest.mark.asyncio
    async def test_빈_결과_error(self, monkeypatch):
        """images·image_urls 모두 비면 status=error(가짜 이미지 금지)."""
        async def _stub(prov, **kw):
            return {"provider": prov, "model": "m", "images": [], "image_urls": []}

        import app.services.ai.image_provider as ip
        monkeypatch.setattr(ip, "generate_image", _stub)

        result = await svc.render_photoreal(_FAKE_IMAGE_B64, provider="openai")

        assert result["status"] == "error"
        assert "image_base64" not in result and "image_url" not in result

    @pytest.mark.asyncio
    async def test_빈_입력_이미지_외부호출전_에러(self, monkeypatch):
        """openai 분기에서도 빈 입력은 외부 호출 전 status=error(기존 가드 유지)."""
        called = {"n": 0}

        async def _stub(prov, **kw):
            called["n"] += 1
            return {"provider": prov, "model": "m", "images": [_OUT_B64], "image_urls": []}

        import app.services.ai.image_provider as ip
        monkeypatch.setattr(ip, "generate_image", _stub)

        result = await svc.render_photoreal("   ", provider="openai")

        assert result["status"] == "error"
        assert called["n"] == 0  # 외부 호출 0회


# ──────────────────────────────────────────────
# 3. 무회귀 — provider=None은 기존 replicate 경로
# ──────────────────────────────────────────────


class TestReplicateNoRegression:
    """provider=None이면 기존 Replicate 경로 그대로(image_provider 미경유)."""

    @pytest.mark.asyncio
    async def test_provider_none_키부재_no_key(self, monkeypatch):
        """provider=None + Replicate 키 부재 → 기존대로 no_key(회귀 없음)."""
        monkeypatch.delenv("REPLICATE_API_TOKEN", raising=False)
        monkeypatch.delenv("REPLICATE_API_KEY", raising=False)

        # image_provider가 잘못 호출되면 즉시 실패하도록 가드.
        async def _boom(*a, **k):
            raise AssertionError("provider=None은 image_provider를 호출하면 안 됨")

        import app.services.ai.image_provider as ip
        monkeypatch.setattr(ip, "generate_image", _boom)

        result = await svc.render_photoreal(_FAKE_IMAGE_B64, provider=None)

        assert result["status"] == "no_key"


# ──────────────────────────────────────────────
# 4. GET /api/v1/design/image-providers
# ──────────────────────────────────────────────


def _client():
    from app.routers.design_v61 import router
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestListImageProviders:
    """가용목록 엔드포인트 — get_available_image_providers 결과를 그대로 노출."""

    def test_가용목록_노출(self, monkeypatch):
        """GET /api/v1/design/image-providers → {"providers": [...]}."""
        fake = [
            {"provider": "openai", "name": "OpenAI gpt-image", "default_model": "gpt-image-1"},
            {"provider": "google", "name": "Google Gemini Image", "default_model": "gemini-2.5-flash-image"},
        ]
        import app.services.ai.image_provider as ip
        monkeypatch.setattr(ip, "get_available_image_providers", lambda: fake)

        resp = _client().get("/api/v1/design/image-providers")

        assert resp.status_code == 200
        assert resp.json() == {"providers": fake}

    def test_가용목록_빈경우(self, monkeypatch):
        """키/SDK 미설정 → 빈 목록(반쪽출하 방지 — 에러 아님)."""
        import app.services.ai.image_provider as ip
        monkeypatch.setattr(ip, "get_available_image_providers", lambda: [])

        resp = _client().get("/api/v1/design/image-providers")

        assert resp.status_code == 200
        assert resp.json() == {"providers": []}
