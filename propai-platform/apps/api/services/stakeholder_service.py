"""이해관계자 관리 서비스."""

from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import get_settings
from apps.api.database.models.stakeholder import Stakeholder

_VALID_ROLES = ["developer", "investor", "contractor", "architect", "authority"]


class StakeholderService:
    """이해관계자 CRUD 및 역할 기반 조회를 제공한다."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()

    async def create_stakeholder(
        self,
        tenant_id: UUID,
        project_id: UUID,
        name: str,
        role: str,
        **kwargs,
    ) -> dict:
        """이해관계자를 생성한다."""
        record = Stakeholder(
            id=uuid4(),
            tenant_id=tenant_id,
            project_id=project_id,
            name=name,
            role=role,
            organization=kwargs.get("organization"),
            email=kwargs.get("email"),
            phone=kwargs.get("phone"),
            responsibility=kwargs.get("responsibility"),
            notes=kwargs.get("notes"),
        )
        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)
        return self._to_dict(record)

    async def get_stakeholder(self, stakeholder_id: UUID, tenant_id: UUID) -> dict | None:
        """ID로 이해관계자를 조회한다."""
        result = await self.db.scalar(
            select(Stakeholder).where(
                Stakeholder.id == stakeholder_id,
                Stakeholder.tenant_id == tenant_id,
            )
        )
        return self._to_dict(result) if result else None

    async def list_stakeholders(
        self,
        project_id: UUID,
        tenant_id: UUID,
        role: str | None = None,
    ) -> list[dict]:
        """프로젝트의 이해관계자 목록을 조회한다."""
        stmt = select(Stakeholder).where(
            Stakeholder.project_id == project_id,
            Stakeholder.tenant_id == tenant_id,
            Stakeholder.is_active.is_(True),
        )
        if role:
            stmt = stmt.where(Stakeholder.role == role)
        result = await self.db.execute(stmt.order_by(Stakeholder.created_at.desc()))
        return [self._to_dict(r) for r in result.scalars().all()]

    async def update_stakeholder(
        self,
        stakeholder_id: UUID,
        tenant_id: UUID,
        **kwargs,
    ) -> dict:
        """이해관계자 정보를 수정한다."""
        record = await self.db.scalar(
            select(Stakeholder).where(
                Stakeholder.id == stakeholder_id,
                Stakeholder.tenant_id == tenant_id,
            )
        )
        if not record:
            raise ValueError("이해관계자를 찾을 수 없습니다.")
        for key in ("name", "role", "organization", "email", "phone", "responsibility", "notes"):
            if key in kwargs:
                setattr(record, key, kwargs[key])
        await self.db.commit()
        await self.db.refresh(record)
        return self._to_dict(record)

    async def deactivate_stakeholder(self, stakeholder_id: UUID, tenant_id: UUID) -> bool:
        """이해관계자를 비활성화한다."""
        result = await self.db.execute(
            update(Stakeholder)
            .where(Stakeholder.id == stakeholder_id, Stakeholder.tenant_id == tenant_id)
            .values(is_active=False)
        )
        await self.db.commit()
        return result.rowcount > 0

    @staticmethod
    def get_valid_roles() -> list[str]:
        """허용된 역할 목록을 반환한다."""
        return list(_VALID_ROLES)

    @staticmethod
    def _to_dict(record: Stakeholder) -> dict:
        """모델 인스턴스를 딕셔너리로 변환한다."""
        return {
            "id": str(record.id),
            "tenant_id": str(record.tenant_id),
            "project_id": str(record.project_id),
            "name": record.name,
            "role": record.role,
            "organization": record.organization,
            "email": record.email,
            "phone": record.phone,
            "responsibility": record.responsibility,
            "is_active": record.is_active,
            "notes": record.notes,
        }
