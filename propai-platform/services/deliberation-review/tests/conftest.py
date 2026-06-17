"""Phase 0 — 공용 픽스처: TestClient + async db 세션."""
from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _test_adapter_isolation(monkeypatch):
    """테스트는 배포 .env(SHEET_CLASSIFIER=vllm/JURISDICTION_ADAPTER=vworld/시크릿로드)와 무관하게
    결정론 mock 기본·키 없음으로 격리. 개별 테스트는 자체 monkeypatch.setenv로 override."""
    monkeypatch.setenv("SHEET_CLASSIFIER", "mock")
    monkeypatch.setenv("JURISDICTION_ADAPTER", "mock")
    monkeypatch.setenv("LOAD_PLATFORM_SECRETS", "false")
    monkeypatch.setenv("PLATFORM_ENV_FILE", "")
    monkeypatch.setenv("EMBEDDER", "hash")  # 결정론 임베더 격리(실 OpenAI 호출 차단)
    monkeypatch.setenv("QDRANT_URL", "")    # in-memory mock 격리(실 Qdrant/서버 차단)
    monkeypatch.setenv("MOLEG_API_KEY", "")  # 국가법령정보(law.go.kr) 실 호출 차단
    monkeypatch.setenv("MOLIT_API_KEY", "")  # 국토부 건축물대장(data.go.kr) 실 호출 차단
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("VWORLD_API_KEY", raising=False)
    # 마스터키 누수 차단(다른 테스트가 os.environ 직접 설정 시) — 각 테스트가 자체 setenv로 override.
    monkeypatch.delenv("SECRET_STORE_KEY", raising=False)
    monkeypatch.delenv("APP_SECRET_KEY", raising=False)
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    # settings 레벨 폴백 중화 — dev 머신에 .env.secrets(실 키)가 있어도 테스트는 키 없음 가정.
    from app.settings import settings as _settings
    monkeypatch.setattr(_settings, "ANTHROPIC_API_KEY", "", raising=False)
    monkeypatch.setattr(_settings, "VWORLD_API_KEY", "", raising=False)
    monkeypatch.setattr(_settings, "MOLEG_API_KEY", "", raising=False)
    monkeypatch.setattr(_settings, "OPENAI_API_KEY", "", raising=False)
    monkeypatch.setattr(_settings, "MOLIT_API_KEY", "", raising=False)


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app
    return TestClient(app)


@pytest.fixture
async def db():
    from app.db.session import async_session, engine

    await engine.dispose()  # 교차-이벤트루프 풀 초기화(테스트 격리)
    async with async_session() as session:
        yield session


@pytest.fixture
def spy_network(monkeypatch):
    """라이브 외부 호출 choke point(LiveNetwork.get)를 카운팅 스파이로 교체(INV-13 검증).

    소비/검증 경로가 호출하지 않으면 live_calls==0. 호출 시도 시 카운트 후 NetworkError.
    """
    from app.adapters import network

    class _Spy:
        live_calls = 0

    spy = _Spy()

    def counting_get(self, url):
        spy.live_calls += 1
        raise network.NetworkError(f"spied live call: {url}")

    monkeypatch.setattr(network.LiveNetwork, "get", counting_get)
    return spy
