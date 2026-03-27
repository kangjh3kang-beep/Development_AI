"""개발 워크플로 관리 서비스."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import get_settings
from apps.api.database.models.development_workflow import DevelopmentWorkflow

_DEFAULT_STAGES = [
    "토지매입",
    "설계",
    "인허가",
    "시공",
    "분양",
    "준공",
    "입주",
]


class WorkflowService:
    """부동산 개발 워크플로 상태 관리를 제공한다."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()

    async def create_workflow(
        self,
        tenant_id: UUID,
        project_id: UUID,
        workflow_name: str,
        stages: list[str],
    ) -> dict:
        """새 워크플로를 생성한다."""
        record = DevelopmentWorkflow(
            id=uuid4(),
            tenant_id=tenant_id,
            project_id=project_id,
            workflow_name=workflow_name,
            stages_json=stages,
            current_stage=stages[0] if stages else "init",
            stage_index=0,
            status="pending",
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)
        return self._to_dict(record)

    async def get_workflow(self, workflow_id: UUID, tenant_id: UUID) -> dict | None:
        """ID로 워크플로를 조회한다."""
        result = await self.db.scalar(
            select(DevelopmentWorkflow).where(
                DevelopmentWorkflow.id == workflow_id,
                DevelopmentWorkflow.tenant_id == tenant_id,
            )
        )
        return self._to_dict(result) if result else None

    async def advance_stage(self, workflow_id: UUID, tenant_id: UUID) -> dict:
        """워크플로를 다음 단계로 진행한다."""
        record = await self.db.scalar(
            select(DevelopmentWorkflow).where(
                DevelopmentWorkflow.id == workflow_id,
                DevelopmentWorkflow.tenant_id == tenant_id,
            )
        )
        if not record:
            raise ValueError("워크플로를 찾을 수 없습니다.")

        stages = record.stages_json or []
        next_index = record.stage_index + 1

        if next_index >= len(stages):
            record.status = "completed"
            record.completed_at = datetime.now(timezone.utc)
        else:
            record.stage_index = next_index
            record.current_stage = stages[next_index]
            record.status = "in_progress"

        await self.db.commit()
        await self.db.refresh(record)
        return self._to_dict(record)

    async def set_status(self, workflow_id: UUID, tenant_id: UUID, status: str) -> dict:
        """워크플로 상태를 직접 설정한다."""
        record = await self.db.scalar(
            select(DevelopmentWorkflow).where(
                DevelopmentWorkflow.id == workflow_id,
                DevelopmentWorkflow.tenant_id == tenant_id,
            )
        )
        if not record:
            raise ValueError("워크플로를 찾을 수 없습니다.")

        record.status = status
        if status == "completed":
            record.completed_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(record)
        return self._to_dict(record)

    async def list_workflows(
        self,
        project_id: UUID,
        tenant_id: UUID,
        status: str | None = None,
    ) -> list[dict]:
        """프로젝트의 워크플로 목록을 조회한다."""
        stmt = select(DevelopmentWorkflow).where(
            DevelopmentWorkflow.project_id == project_id,
            DevelopmentWorkflow.tenant_id == tenant_id,
        )
        if status:
            stmt = stmt.where(DevelopmentWorkflow.status == status)
        result = await self.db.execute(stmt.order_by(DevelopmentWorkflow.created_at.desc()))
        return [self._to_dict(r) for r in result.scalars().all()]

    @staticmethod
    def get_default_stages() -> list[str]:
        """기본 워크플로 단계 목록을 반환한다."""
        return list(_DEFAULT_STAGES)

    @staticmethod
    def _to_dict(record: DevelopmentWorkflow) -> dict:
        """모델 인스턴스를 딕셔너리로 변환한다."""
        return {
            "id": str(record.id),
            "tenant_id": str(record.tenant_id),
            "project_id": str(record.project_id),
            "workflow_name": record.workflow_name,
            "current_stage": record.current_stage,
            "stage_index": record.stage_index,
            "stages_json": record.stages_json,
            "started_at": record.started_at.isoformat() if record.started_at else None,
            "completed_at": record.completed_at.isoformat() if record.completed_at else None,
            "assigned_to": str(record.assigned_to) if record.assigned_to else None,
            "status": record.status,
            "notes": record.notes,
        }
