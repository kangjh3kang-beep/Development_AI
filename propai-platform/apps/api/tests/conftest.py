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
