"""테스트용 모델 팩토리.

factory-boy 대신 간단한 팩토리 함수로 구현한다.
서비스 테스트에서 DB 모델 인스턴스를 빠르게 생성하기 위한 용도.
"""

from datetime import UTC, datetime

UTC = UTC
from uuid import UUID, uuid4

from apps.api.tests.conftest import TEST_PROJECT_ID, TEST_TENANT_ID, TEST_USER_ID

# ──────────────────────────────────────────────
# 기본 엔티티
# ──────────────────────────────────────────────


def make_tenant(*, tenant_id: UUID | None = None, name: str = "테스트 테넌트") -> dict:
    return {
        "id": tenant_id or TEST_TENANT_ID,
        "name": name,
        "plan": "enterprise",
        "is_active": True,
        "created_at": datetime.now(tz=UTC),
    }


def make_user(
    *,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    email: str = "test@propai.kr",
    role: str = "admin",
) -> dict:
    return {
        "id": user_id or TEST_USER_ID,
        "tenant_id": tenant_id or TEST_TENANT_ID,
        "email": email,
        "name": "테스트 사용자",
        "hashed_password": "$2b$12$dummyhash",
        "role": role,
        "is_active": True,
        "created_at": datetime.now(tz=UTC),
    }


def make_project(
    *,
    project_id: UUID | None = None,
    tenant_id: UUID | None = None,
    name: str = "테스트 프로젝트",
    status: str = "planning",
) -> dict:
    return {
        "id": project_id or TEST_PROJECT_ID,
        "tenant_id": tenant_id or TEST_TENANT_ID,
        "name": name,
        "status": status,
        "address": "서울시 강남구 테헤란로 1",
        "latitude": 37.5065,
        "longitude": 127.0536,
        "total_area_sqm": 500.0,
        "created_at": datetime.now(tz=UTC),
        "updated_at": datetime.now(tz=UTC),
    }


# ──────────────────────────────────────────────
# AVM / 재무 분석
# ──────────────────────────────────────────────


def make_avm_valuation(
    *,
    project_id: UUID | None = None,
    tenant_id: UUID | None = None,
    estimated_price: float = 1_500_000_000.0,
) -> dict:
    return {
        "id": uuid4(),
        "project_id": project_id or TEST_PROJECT_ID,
        "tenant_id": tenant_id or TEST_TENANT_ID,
        "estimated_price": estimated_price,
        "price_per_sqm": estimated_price / 84.0,
        "confidence_score": 0.87,
        "comparable_count": 15,
        "model_version": "avm-xgb-test",
        "created_at": datetime.now(tz=UTC),
    }


def make_financial_analysis(
    *,
    project_id: UUID | None = None,
    tenant_id: UUID | None = None,
) -> dict:
    return {
        "id": uuid4(),
        "project_id": project_id or TEST_PROJECT_ID,
        "tenant_id": tenant_id or TEST_TENANT_ID,
        "total_cost": 10_000_000_000.0,
        "total_revenue": 15_000_000_000.0,
        "npv": 2_000_000_000.0,
        "irr": 0.12,
        "roi": 0.50,
        "payback_months": 36,
        "created_at": datetime.now(tz=UTC),
    }


# ──────────────────────────────────────────────
# 필지 / 법규
# ──────────────────────────────────────────────


def make_parcel(
    *,
    project_id: UUID | None = None,
    tenant_id: UUID | None = None,
    pnu: str = "1168010100101230001",
) -> dict:
    return {
        "id": uuid4(),
        "project_id": project_id or TEST_PROJECT_ID,
        "tenant_id": tenant_id or TEST_TENANT_ID,
        "pnu": pnu,
        "address": "서울시 강남구 삼성동 123",
        "land_area_sqm": 500.0,
        "land_category": "대",
        "zoning": "2종일반주거",
        "official_price_per_sqm": 5_000_000.0,
        "created_at": datetime.now(tz=UTC),
    }


def make_regulation(
    *,
    project_id: UUID | None = None,
    tenant_id: UUID | None = None,
) -> dict:
    return {
        "id": uuid4(),
        "project_id": project_id or TEST_PROJECT_ID,
        "tenant_id": tenant_id or TEST_TENANT_ID,
        "regulation_type": "zoning",
        "is_compliant": True,
        "violations": [],
        "details": {"bcr_limit": 0.60, "far_limit": 2.50},
        "created_at": datetime.now(tz=UTC),
    }


# ──────────────────────────────────────────────
# 블록체인 / 에스크로
# ──────────────────────────────────────────────


def make_escrow_transaction(
    *,
    project_id: UUID | None = None,
    tenant_id: UUID | None = None,
    status: str = "pending_funding",
) -> dict:
    return {
        "id": uuid4(),
        "project_id": project_id or TEST_PROJECT_ID,
        "tenant_id": tenant_id or TEST_TENANT_ID,
        "buyer_address": "0x1234567890abcdef1234567890abcdef12345678",
        "seller_address": "0xabcdef1234567890abcdef1234567890abcdef12",
        "amount_wei": 1_000_000_000_000_000_000,
        "status": status,
        "tx_hash": None,
        "created_at": datetime.now(tz=UTC),
    }


# ──────────────────────────────────────────────
# 세금 / 설계 / 드론
# ──────────────────────────────────────────────


def make_tax_calculation(
    *,
    project_id: UUID | None = None,
    tenant_id: UUID | None = None,
    tax_type: str = "acquisition",
) -> dict:
    return {
        "id": uuid4(),
        "project_id": project_id or TEST_PROJECT_ID,
        "tenant_id": tenant_id or TEST_TENANT_ID,
        "tax_type": tax_type,
        "taxable_value": 1_000_000_000.0,
        "amount": 40_000_000.0,
        "tax_rate": 0.04,
        "effective_date": "2024-01-01",
        "created_at": datetime.now(tz=UTC),
    }


def make_design(
    *,
    project_id: UUID | None = None,
    tenant_id: UUID | None = None,
    design_type: str = "floor_plan",
) -> dict:
    return {
        "id": uuid4(),
        "project_id": project_id or TEST_PROJECT_ID,
        "tenant_id": tenant_id or TEST_TENANT_ID,
        "design_type": design_type,
        "image_url": "https://storage.propai.kr/designs/test.png",
        "bim_data": {},
        "created_at": datetime.now(tz=UTC),
        "updated_at": datetime.now(tz=UTC),
    }


def make_drone_inspection(
    *,
    project_id: UUID | None = None,
    tenant_id: UUID | None = None,
) -> dict:
    return {
        "id": uuid4(),
        "project_id": project_id or TEST_PROJECT_ID,
        "tenant_id": tenant_id or TEST_TENANT_ID,
        "image_url": "https://storage.propai.kr/drones/test.jpg",
        "defect_count": 3,
        "defects": [
            {"type": "crack", "severity": "HIGH", "confidence": 0.92},
            {"type": "spalling", "severity": "MEDIUM", "confidence": 0.85},
            {"type": "moisture", "severity": "LOW", "confidence": 0.78},
        ],
        "gps_lat": 37.5065,
        "gps_lng": 127.0536,
        "created_at": datetime.now(tz=UTC),
    }


# ──────────────────────────────────────────────
# Phase E~G 확장 모델
# ──────────────────────────────────────────────


def make_chatbot_session(
    *,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
) -> dict:
    return {
        "id": uuid4(),
        "tenant_id": tenant_id or TEST_TENANT_ID,
        "user_id": user_id or TEST_USER_ID,
        "domain": "general",
        "title": "테스트 대화",
        "message_count": 0,
        "total_tokens": 0,
        "model_name": "claude-sonnet-4-5",
        "last_activity_at": datetime.now(tz=UTC),
        "created_at": datetime.now(tz=UTC),
    }


def make_auction_listing(
    *,
    tenant_id: UUID | None = None,
) -> dict:
    return {
        "id": uuid4(),
        "tenant_id": tenant_id or TEST_TENANT_ID,
        "auction_type": "court_auction",
        "case_number": "2024타경12345",
        "court_name": "서울중앙지방법원",
        "address": "서울시 강남구 테헤란로 100",
        "property_type": "residential",
        "appraised_value_krw": 1_000_000_000.0,
        "minimum_bid_krw": 700_000_000.0,
        "bid_count": 0,
        "status": "pending",
        "analysis_json": {
            "discount_ratio": 0.30,
            "market_gap_ratio": 0.15,
            "investment_score": 72.5,
            "recommended_max_bid_krw": 850_000_000.0,
            "expected_margin_krw": 150_000_000.0,
            "diligence_flags": ["선순위 없음"],
        },
        "created_at": datetime.now(tz=UTC),
    }


def make_contractor(*, tenant_id: UUID | None = None) -> dict:
    return {
        "id": uuid4(),
        "tenant_id": tenant_id or TEST_TENANT_ID,
        "company_name": "테스트건설(주)",
        "business_number": "1234567890",
        "category": "general_contractor",
        "specialties": ["철근콘크리트", "리모델링"],
        "contact_name": "홍길동",
        "contact_phone": "010-1234-5678",
        "contact_email": "hong@test.kr",
        "rating": 4.2,
        "is_active": True,
        "created_at": datetime.now(tz=UTC),
    }
