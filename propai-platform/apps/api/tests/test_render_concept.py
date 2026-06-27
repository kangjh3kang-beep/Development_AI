"""컨셉 렌더(text2img·INC3) 테스트 — 텍스트만으로 조감도/투시도 생성.

검증 경로(공용 image_provider는 monkeypatch stub — 실제 외부 호출 0회):
1. provider="google" → generate_image 호출(input_image 없음=text2img) → ok+image_base64+view
2. view→프롬프트 프리픽스 검증(generate_image에 넘어간 prompt가 프리픽스 포함)
3. 빈 prompt → error(외부 호출 0회·가짜 이미지 금지)
4. ImageGenerationError(key_not_configured/package_missing)→no_key, (api_error)→error
5. 빈 결과(images·image_urls 모두 비면)→error(가짜 이미지 금지)
6. provider None + 가용목록 비면 no_key(정직), 가용 있으면 첫 항목 택1
7. image_urls만 채워지면 → ok + image_url(공용 계약)
8. 엔드포인트: status!=ok면 과금 0회, ok면 charge_service 호출(monkeypatch)
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services.ai.image_provider import ImageGenerationError
from app.services.drawing import photoreal_render_service as svc

_OUT_B64 = "BASE64_CONCEPT_IMAGE_PAYLOAD=="
_OUT_URL = "https://example.com/concept.png"


# ──────────────────────────────────────────────
# 1. 성공 + view 프리픽스(text2img)
# ──────────────────────────────────────────────


class TestConceptSuccess:
    """provider 지정 시 공용 image_provider(text2img)로 성공 반환 + view 프리픽스 합성."""

    @pytest.mark.asyncio
    async def test_성공_image_base64_view(self, monkeypatch):
        """generate_image stub(images=[b64]) → ok + image_base64 + view + text2img(입력이미지 없음)."""
        captured = {}

        async def _stub(prov, *, prompt, model=None, size=None, timeout=None, **kw):
            captured.update(provider=prov, prompt=prompt, model=model, size=size, kw=kw)
            return {"provider": prov, "model": model or "default-model", "images": [_OUT_B64], "image_urls": []}

        import app.services.ai.image_provider as ip
        monkeypatch.setattr(ip, "generate_image", _stub)

        result = await svc.render_concept(
            "한강뷰 모던 주상복합", view="aerial", provider="google", model="custom-model"
        )

        assert result["status"] == "ok"
        assert result["image_base64"] == _OUT_B64
        assert result["provider"] == "google"
        assert result["model"] == "custom-model"
        assert result["view"] == "aerial"
        assert "image_url" not in result
        # text2img: input_image_b64를 넘기지 않는다(키워드 부재 또는 None).
        assert captured["kw"].get("input_image_b64") is None
        # view 프리픽스가 최종 프롬프트 앞에 붙는다.
        assert captured["prompt"].startswith("aerial bird's-eye view architectural rendering of")
        assert "한강뷰 모던 주상복합" in captured["prompt"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("view", "expected_prefix"),
        [
            ("aerial", "aerial bird's-eye view architectural rendering of"),
            ("perspective", "eye-level street perspective photorealistic rendering of"),
            ("street", "street-level photorealistic rendering of"),
            ("unknown", "aerial bird's-eye view architectural rendering of"),  # 미지정 view→aerial 폴백
        ],
    )
    async def test_view별_프롬프트_프리픽스(self, monkeypatch, view, expected_prefix):
        """view마다 프롬프트 프리픽스가 달라지고, 미지원 view는 aerial로 폴백."""
        captured = {}

        async def _stub(prov, *, prompt, **kw):
            captured["prompt"] = prompt
            return {"provider": prov, "model": "m", "images": [_OUT_B64], "image_urls": []}

        import app.services.ai.image_provider as ip
        monkeypatch.setattr(ip, "generate_image", _stub)

        result = await svc.render_concept("테스트 건물", view=view, provider="openai")

        assert result["status"] == "ok"
        assert captured["prompt"].startswith(expected_prefix)

    @pytest.mark.asyncio
    async def test_image_urls만_채워지면_image_url(self, monkeypatch):
        """images 비고 image_urls만 있으면 ok + image_url(공용 계약)."""
        async def _stub(prov, **kw):
            return {"provider": prov, "model": "m", "images": [], "image_urls": [_OUT_URL]}

        import app.services.ai.image_provider as ip
        monkeypatch.setattr(ip, "generate_image", _stub)

        result = await svc.render_concept("건물", provider="replicate")

        assert result["status"] == "ok"
        assert result["image_url"] == _OUT_URL
        assert "image_base64" not in result


# ──────────────────────────────────────────────
# 2. 빈 prompt 가드(외부 호출 전 차단)
# ──────────────────────────────────────────────


class TestEmptyPrompt:
    """설명이 비면 외부 호출 전 정직 에러(가짜 이미지·과금 금지)."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("prompt", ["", "   ", "\n"])
    async def test_빈_prompt_외부호출전_에러(self, monkeypatch, prompt):
        called = {"n": 0}

        async def _stub(prov, **kw):
            called["n"] += 1
            return {"provider": prov, "model": "m", "images": [_OUT_B64], "image_urls": []}

        import app.services.ai.image_provider as ip
        monkeypatch.setattr(ip, "generate_image", _stub)

        result = await svc.render_concept(prompt, provider="google")

        assert result["status"] == "error"
        assert called["n"] == 0  # 외부 호출 0회


# ──────────────────────────────────────────────
# 3. 정직 강등 — ImageGenerationError 매핑
# ──────────────────────────────────────────────


class TestHonestDegrade:
    """ImageGenerationError를 가짜 이미지 없이 no_key/error로 정직 매핑한다."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("err_type", ["key_not_configured", "package_missing"])
    async def test_키_패키지_부재_no_key(self, monkeypatch, err_type):
        async def _raise(prov, **kw):
            raise ImageGenerationError("미설정", error_type=err_type)

        import app.services.ai.image_provider as ip
        monkeypatch.setattr(ip, "generate_image", _raise)

        result = await svc.render_concept("건물", provider="google")

        assert result["status"] == "no_key"
        assert result["provider"] == "google"
        assert "image_base64" not in result and "image_url" not in result

    @pytest.mark.asyncio
    async def test_api_오류_error(self, monkeypatch):
        async def _raise(prov, **kw):
            raise ImageGenerationError("외부 API 실패", error_type="api_error")

        import app.services.ai.image_provider as ip
        monkeypatch.setattr(ip, "generate_image", _raise)

        result = await svc.render_concept("건물", provider="openai")

        assert result["status"] == "error"
        assert "image_base64" not in result and "image_url" not in result

    @pytest.mark.asyncio
    async def test_빈_결과_error(self, monkeypatch):
        async def _stub(prov, **kw):
            return {"provider": prov, "model": "m", "images": [], "image_urls": []}

        import app.services.ai.image_provider as ip
        monkeypatch.setattr(ip, "generate_image", _stub)

        result = await svc.render_concept("건물", provider="openai")

        assert result["status"] == "error"
        assert "image_base64" not in result and "image_url" not in result


# ──────────────────────────────────────────────
# 4. provider None — 가용목록 기반 정직 택1
# ──────────────────────────────────────────────


class TestProviderResolution:
    """provider 미지정 시 라이브 가용목록 첫 항목 택1, 없으면 no_key(정직)."""

    @pytest.mark.asyncio
    async def test_가용목록_비면_no_key(self, monkeypatch):
        """가용 프로바이더가 하나도 없으면 no_key(외부 호출 0회·가짜 이미지 금지)."""
        called = {"n": 0}

        async def _stub(prov, **kw):
            called["n"] += 1
            return {"provider": prov, "model": "m", "images": [_OUT_B64], "image_urls": []}

        import app.services.ai.image_provider as ip
        monkeypatch.setattr(ip, "get_available_image_providers", lambda: [])
        monkeypatch.setattr(ip, "generate_image", _stub)

        result = await svc.render_concept("건물", provider=None)

        assert result["status"] == "no_key"
        assert called["n"] == 0

    @pytest.mark.asyncio
    async def test_가용목록_있으면_첫항목_택1(self, monkeypatch):
        """가용목록 첫 항목 provider로 생성한다."""
        captured = {}

        async def _stub(prov, **kw):
            captured["provider"] = prov
            return {"provider": prov, "model": "m", "images": [_OUT_B64], "image_urls": []}

        import app.services.ai.image_provider as ip
        monkeypatch.setattr(
            ip, "get_available_image_providers",
            lambda: [{"provider": "openai"}, {"provider": "google"}],
        )
        monkeypatch.setattr(ip, "generate_image", _stub)

        result = await svc.render_concept("건물", provider=None)

        assert result["status"] == "ok"
        assert result["provider"] == "openai"
        assert captured["provider"] == "openai"


# ──────────────────────────────────────────────
# 5. 엔드포인트 — 과금 게이트(status!=ok→0, ok→charge)
# ──────────────────────────────────────────────


def _client():
    from app.routers.design_v61 import router
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class _FakeUser:
    id = "user-123"


class TestEndpointBilling:
    """status!=ok면 과금 0회, ok면 charge_service 1회(미설정무료·best-effort)."""

    def _override_deps(self, app, user):
        from app.routers import design_v61 as mod
        app.dependency_overrides[mod.get_db] = lambda: None
        app.dependency_overrides[mod.get_current_user_optional] = lambda: user

    def test_no_key면_과금_0회(self, monkeypatch):
        """서비스가 no_key 반환 시 charge_service 미호출(과금 0)."""
        charge_calls = {"n": 0}

        async def _svc_render(prompt, *, view="aerial", provider=None, model=None):
            return {"status": "no_key", "message": "키 미설정"}

        async def _charge(db, uid, action):
            charge_calls["n"] += 1
            return {"charged_krw": 0}

        from app.services.billing import billing_service as bsvc
        from app.services.drawing import photoreal_render_service as psvc
        monkeypatch.setattr(psvc, "render_concept", _svc_render)
        monkeypatch.setattr(bsvc, "charge_service", _charge)

        client = _client()
        self._override_deps(client.app, _FakeUser())

        resp = client.post("/api/v1/design/proj-1/render-concept", json={"prompt": "건물", "view": "aerial"})

        assert resp.status_code == 200
        assert resp.json()["status"] == "no_key"
        assert charge_calls["n"] == 0  # 과금 0회

    def test_ok면_charge_호출(self, monkeypatch):
        """서비스가 ok 반환 시 charge_service 1회 호출(concept_render)."""
        charge_calls = {"n": 0, "action": None}

        async def _svc_render(prompt, *, view="aerial", provider=None, model=None):
            return {"status": "ok", "image_base64": _OUT_B64, "provider": "google", "model": "m", "view": view}

        async def _load(db):
            return None

        async def _charge(db, uid, action):
            charge_calls["n"] += 1
            charge_calls["action"] = action
            return {"charged_krw": 0, "free": True}

        from app.services.billing import billing_service as bsvc
        from app.services.drawing import photoreal_render_service as psvc
        monkeypatch.setattr(psvc, "render_concept", _svc_render)
        monkeypatch.setattr(bsvc, "load_config", _load)
        monkeypatch.setattr(bsvc, "charge_service", _charge)

        client = _client()
        self._override_deps(client.app, _FakeUser())

        resp = client.post("/api/v1/design/proj-1/render-concept", json={"prompt": "건물", "view": "perspective"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["image_base64"] == _OUT_B64
        assert body["view"] == "perspective"
        assert charge_calls["n"] == 1
        assert charge_calls["action"] == "concept_render"
