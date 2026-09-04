"""PropAI v58 공유 테스트 픽스처."""

import os
import sys

import pytest

# 프로젝트 루트를 path에 추가 (apps/api + propai-platform root)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))


# ── async httpx 클라이언트 (client 픽스쳐) ──

@pytest.fixture
async def client():
    """FastAPI TestClient (async httpx) — 전체 앱 기반 라우터 테스트에서 사용."""
    import httpx

    from apps.api.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac


# ── 프로젝트 샘플 (integration 테스트용) ──

@pytest.fixture
def sample_project():
    """통합 테스트용 프로젝트 데이터."""
    return {
        "project_id": "test-project-001",
        "name": "테스트 프로젝트",
        "address": "서울특별시 강남구 역삼동 123-45",
        "area_sqm": 25000,
        "total_households": 500,
        "development_type": "M06",
        "sido_name": "서울",
        "sigungu_name": "강남구",
        "total_gfa_sqm": 75000,
        "estimated_cost_krw": 50_000_000_000,
        "estimated_revenue_krw": 70_000_000_000,
        "budget_krw": 80_000_000_000,
        "total_floor_area_sqm": 75000,
        "floors_above": 25,
        "project_type": "apartment",
        "location": {"latitude": 37.5665, "longitude": 126.9780},
    }


# ── 기존 픽스쳐 ──

@pytest.fixture
def sample_comparables():
    """AVM 테스트용 비교 매물 데이터."""
    return [
        {"latitude": 37.5665, "longitude": 126.9780, "price_per_sqm": 12000000},
        {"latitude": 37.5700, "longitude": 126.9800, "price_per_sqm": 11500000},
        {"latitude": 37.5630, "longitude": 126.9750, "price_per_sqm": 12500000},
    ]


@pytest.fixture
def sample_materials():
    """LCA 테스트용 자재 수량."""
    return {
        "concrete_C25": 500000,
        "steel_rebar": 80000,
        "glass": 15000,
        "insulation_eps": 5000,
    }


@pytest.fixture
def sample_epd_materials():
    """EPD 테스트용 한국 자재 목록."""
    return [
        {"name": "일반 콘크리트 (C25)", "quantity_kg": 500000},
        {"name": "철근 (SD500)", "quantity_kg": 80000},
        {"name": "단열재 (EPS)", "quantity_kg": 5000},
    ]


@pytest.fixture
def sample_monte_carlo_params():
    """Monte Carlo 테스트용 파라미터."""
    return {
        "total_cost_krw": 50_000_000_000,
        "expected_revenue_krw": 70_000_000_000,
        "construction_period_months": 36,
    }


@pytest.fixture(autouse=True)
def _isolate_registry_source_cache():
    """등기 **발급 원본 캐시**를 테스트마다 비운다.

    ★왜 필요한가: 이 캐시는 필지(주소·구분·동/호)만으로 키를 만든다 — 프로덕션에서는 옳다
      (같은 필지는 같은 등기부다). 그런데 테스트는 **같은 주소에 서로 다른 프로바이더 동작**을
      스텁한다(이미지 PDF · 텍스트 제공 · 발급 실패…). 캐시가 남아 있으면 앞 테스트가 심은
      발급본이 뒤 테스트에 재사용돼, 실제로 `origin` 이 `hyphen` 대신 `hyphen+pdf` 로 나오고
      "이미지 PDF 는 가짜 안전등급을 만들지 않는다"가 무너졌다(2026-08-24 실측 3건).

    ★캐시를 지우는 것이지 **끄는 것이 아니다** — 재사용 동작 자체는 전용 테스트
      (`test_registry_no_reissue_on_llm_failure.py`)가 그대로 태운다.
    """
    try:
        from app.services.registry import registry_analysis_service as _svc
    except Exception:  # noqa: BLE001 — 이 모듈이 없는 환경에서는 할 일이 없다
        yield
        return
    try:
        from app.services.registry import registry_service as _rsvc
    except Exception:  # noqa: BLE001
        _rsvc = None

    def _clear() -> None:
        _svc._SOURCE_CACHE.clear()
        # ★결정론 실패 기억도 비운다 — 남으면 뒤 테스트가 "LLM 을 안 불렀다"를 보고
        #   앞 테스트의 기억을 자기 결과로 오독한다(#46 과 같은 클래스).
        _svc._FAILURE_MEMO.clear()
        # ★발급 캐시(유료 길목)도 함께 비운다. 여기를 빼면 같은 누수가 **한 층 아래에서**
        #   그대로 재발한다 — 실제로 위층만 비웠을 때 3건이 계속 빨갰다.
        if _rsvc is not None:
            _rsvc._ISSUE_CACHE.clear()

    _clear()
    yield
    _clear()
