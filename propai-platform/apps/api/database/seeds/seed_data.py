"""개발/테스트용 시드 데이터.

python -m apps.api.database.seeds.seed_data 로 실행.
"""

import asyncio
import hashlib
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# 고정 UUID (재실행 시 idempotent)
TENANT_ID = uuid.UUID("10000000-0000-0000-0000-000000000001")
ADMIN_ID = uuid.UUID("20000000-0000-0000-0000-000000000001")
MANAGER_ID = uuid.UUID("20000000-0000-0000-0000-000000000002")
VIEWER_ID = uuid.UUID("20000000-0000-0000-0000-000000000003")
PROJECT1_ID = uuid.UUID("30000000-0000-0000-0000-000000000001")
PROJECT2_ID = uuid.UUID("30000000-0000-0000-0000-000000000002")

now = datetime.now(tz=UTC)


def _hash_pw(pw: str) -> str:
    """간이 해시 (시드 전용, 실 운영에서는 bcrypt 사용)."""
    return hashlib.sha256(pw.encode()).hexdigest()


async def seed_tenants(db: AsyncSession) -> None:
    """테넌트 시드."""
    await db.execute(
        text(
            "INSERT INTO tenants (id, name, plan, created_at) "
            "VALUES (:id, :name, :plan, :created_at) "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {
            "id": str(TENANT_ID),
            "name": "PropAI 데모 테넌트",
            "plan": "enterprise",
            "created_at": now,
        },
    )


async def seed_users(db: AsyncSession) -> None:
    """사용자 3명 시드 (admin, manager, viewer)."""
    users = [
        {
            "id": str(ADMIN_ID),
            "email": "admin@propai.dev",
            "name": "관리자",
            "hashed_password": _hash_pw("admin1234!"),
            "role": "admin",
            "tenant_id": str(TENANT_ID),
            "created_at": now,
        },
        {
            "id": str(MANAGER_ID),
            "email": "manager@propai.dev",
            "name": "프로젝트 매니저",
            "hashed_password": _hash_pw("manager1234!"),
            "role": "manager",
            "tenant_id": str(TENANT_ID),
            "created_at": now,
        },
        {
            "id": str(VIEWER_ID),
            "email": "viewer@propai.dev",
            "name": "열람자",
            "hashed_password": _hash_pw("viewer1234!"),
            "role": "viewer",
            "tenant_id": str(TENANT_ID),
            "created_at": now,
        },
    ]
    for u in users:
        await db.execute(
            text(
                "INSERT INTO users (id, email, name, hashed_password, role, tenant_id, created_at) "
                "VALUES (:id, :email, :name, :hashed_password, :role, :tenant_id, :created_at) "
                "ON CONFLICT (id) DO NOTHING"
            ),
            u,
        )


async def seed_projects(db: AsyncSession) -> None:
    """프로젝트 2건 시드."""
    projects = [
        {
            "id": str(PROJECT1_ID),
            "name": "강남역 복합개발",
            "description": "강남역 인근 복합용도 부동산 개발 프로젝트",
            "address": "서울특별시 강남구 강남대로 396",
            "status": "planning",
            "tenant_id": str(TENANT_ID),
            "owner_id": str(ADMIN_ID),
            "created_at": now - timedelta(days=30),
        },
        {
            "id": str(PROJECT2_ID),
            "name": "판교 오피스텔 신축",
            "description": "판교 테크노밸리 인근 오피스텔 신축 사업",
            "address": "경기도 성남시 분당구 판교역로 235",
            "status": "design",
            "tenant_id": str(TENANT_ID),
            "owner_id": str(MANAGER_ID),
            "created_at": now - timedelta(days=15),
        },
    ]
    for p in projects:
        await db.execute(
            text(
                "INSERT INTO projects (id, name, description, address, status, tenant_id, owner_id, created_at) "
                "VALUES (:id, :name, :description, :address, :status, :tenant_id, :owner_id, :created_at) "
                "ON CONFLICT (id) DO NOTHING"
            ),
            p,
        )


async def seed_avm_valuations(db: AsyncSession) -> None:
    """AVM 시세 추정 결과 샘플."""
    valuations = [
        {
            "id": str(uuid.UUID("40000000-0000-0000-0000-000000000001")),
            "project_id": str(PROJECT1_ID),
            "tenant_id": str(TENANT_ID),
            "estimated_price": 15_000_000_000,
            "price_per_sqm": 25_000_000,
            "confidence_score": 0.92,
            "comparable_count": 15,
            "model_version": "avm-xgb-202603",
            "created_at": now - timedelta(days=5),
        },
        {
            "id": str(uuid.UUID("40000000-0000-0000-0000-000000000002")),
            "project_id": str(PROJECT2_ID),
            "tenant_id": str(TENANT_ID),
            "estimated_price": 8_500_000_000,
            "price_per_sqm": 18_000_000,
            "confidence_score": 0.87,
            "comparable_count": 10,
            "model_version": "avm-xgb-202603",
            "created_at": now - timedelta(days=3),
        },
    ]
    for v in valuations:
        await db.execute(
            text(
                "INSERT INTO avm_valuations "
                "(id, project_id, tenant_id, estimated_price, price_per_sqm, "
                "confidence_score, comparable_count, model_version, created_at) "
                "VALUES (:id, :project_id, :tenant_id, :estimated_price, :price_per_sqm, "
                ":confidence_score, :comparable_count, :model_version, :created_at) "
                "ON CONFLICT (id) DO NOTHING"
            ),
            v,
        )


async def run_seed() -> None:
    """시드 데이터 전체 실행."""
    from apps.api.database.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await seed_tenants(db)
        await seed_users(db)
        await seed_projects(db)
        await seed_avm_valuations(db)
        await db.commit()

    print(f"시드 완료: 테넌트 1, 사용자 3, 프로젝트 2, AVM 2")


if __name__ == "__main__":
    asyncio.run(run_seed())
