"""수지분석 Repository — DB 접근 계층 (get/save/update).

비동기 SQLAlchemy 세션 기반. 서비스 계층에서 호출.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feasibility import (
    FeasibilityProject,
    FeasibilityVersion,
    FeasibilitySummary,
    RevenueInput,
    LandCostInput,
    ConstructionCostInput,
    FinanceCostInput,
    OtherCostInput,
    TaxCostItem,
    ModuleConfig,
)


class FeasibilityRepository:
    """수지분석 DB 접근 계층."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── 프로젝트 ──

    async def get_project(self, project_id: UUID) -> FeasibilityProject | None:
        result = await self.db.execute(
            select(FeasibilityProject).where(
                FeasibilityProject.id == project_id,
                FeasibilityProject.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_projects_by_parent(self, parent_project_id: UUID) -> list[FeasibilityProject]:
        result = await self.db.execute(
            select(FeasibilityProject).where(
                FeasibilityProject.project_id == parent_project_id,
                FeasibilityProject.deleted_at.is_(None),
            )
        )
        return list(result.scalars().all())

    async def save_project(self, project: FeasibilityProject) -> FeasibilityProject:
        self.db.add(project)
        await self.db.flush()
        return project

    # ── 버전 ──

    async def get_version(self, version_id: UUID) -> FeasibilityVersion | None:
        result = await self.db.execute(
            select(FeasibilityVersion).where(
                FeasibilityVersion.id == version_id,
                FeasibilityVersion.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_current_version(self, feasibility_project_id: UUID) -> FeasibilityVersion | None:
        result = await self.db.execute(
            select(FeasibilityVersion).where(
                FeasibilityVersion.feasibility_project_id == feasibility_project_id,
                FeasibilityVersion.is_current.is_(True),
                FeasibilityVersion.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def create_version(
        self,
        feasibility_project_id: UUID,
        version_number: int,
        label: str | None = None,
        parent_version_id: UUID | None = None,
    ) -> FeasibilityVersion:
        # 기존 current 해제
        await self.db.execute(
            update(FeasibilityVersion)
            .where(
                FeasibilityVersion.feasibility_project_id == feasibility_project_id,
                FeasibilityVersion.is_current.is_(True),
            )
            .values(is_current=False)
        )

        version = FeasibilityVersion(
            feasibility_project_id=feasibility_project_id,
            version_number=version_number,
            label=label,
            is_current=True,
            parent_version_id=parent_version_id,
        )
        self.db.add(version)
        await self.db.flush()
        return version

    # ── 수지 합산 ──

    async def get_summary(self, version_id: UUID) -> FeasibilitySummary | None:
        result = await self.db.execute(
            select(FeasibilitySummary).where(FeasibilitySummary.version_id == version_id)
        )
        return result.scalar_one_or_none()

    async def save_summary(self, summary: FeasibilitySummary) -> FeasibilitySummary:
        self.db.add(summary)
        await self.db.flush()
        return summary

    # ── 수입 입력 ──

    async def get_revenue_input(self, version_id: UUID) -> RevenueInput | None:
        result = await self.db.execute(
            select(RevenueInput).where(RevenueInput.version_id == version_id)
        )
        return result.scalar_one_or_none()

    async def save_revenue_input(self, revenue_input: RevenueInput) -> RevenueInput:
        self.db.add(revenue_input)
        await self.db.flush()
        return revenue_input

    # ── 토지비 입력 ──

    async def get_land_cost_input(self, version_id: UUID) -> LandCostInput | None:
        result = await self.db.execute(
            select(LandCostInput).where(LandCostInput.version_id == version_id)
        )
        return result.scalar_one_or_none()

    async def save_land_cost_input(self, land_cost_input: LandCostInput) -> LandCostInput:
        self.db.add(land_cost_input)
        await self.db.flush()
        return land_cost_input

    # ── 공사비 입력 ──

    async def get_construction_cost_input(self, version_id: UUID) -> ConstructionCostInput | None:
        result = await self.db.execute(
            select(ConstructionCostInput).where(ConstructionCostInput.version_id == version_id)
        )
        return result.scalar_one_or_none()

    async def save_construction_cost_input(self, inp: ConstructionCostInput) -> ConstructionCostInput:
        self.db.add(inp)
        await self.db.flush()
        return inp

    # ── 금융비 입력 ──

    async def get_finance_cost_input(self, version_id: UUID) -> FinanceCostInput | None:
        result = await self.db.execute(
            select(FinanceCostInput).where(FinanceCostInput.version_id == version_id)
        )
        return result.scalar_one_or_none()

    async def save_finance_cost_input(self, inp: FinanceCostInput) -> FinanceCostInput:
        self.db.add(inp)
        await self.db.flush()
        return inp

    # ── 기타경비 입력 ──

    async def get_other_cost_input(self, version_id: UUID) -> OtherCostInput | None:
        result = await self.db.execute(
            select(OtherCostInput).where(OtherCostInput.version_id == version_id)
        )
        return result.scalar_one_or_none()

    async def save_other_cost_input(self, inp: OtherCostInput) -> OtherCostInput:
        self.db.add(inp)
        await self.db.flush()
        return inp

    # ── 세금 항목 ──

    async def get_tax_items(self, version_id: UUID) -> list[TaxCostItem]:
        result = await self.db.execute(
            select(TaxCostItem).where(TaxCostItem.version_id == version_id)
        )
        return list(result.scalars().all())

    async def save_tax_item(self, item: TaxCostItem) -> TaxCostItem:
        self.db.add(item)
        await self.db.flush()
        return item

    async def save_tax_items_bulk(self, items: list[TaxCostItem]) -> list[TaxCostItem]:
        self.db.add_all(items)
        await self.db.flush()
        return items

    # ── 모듈 설정 ──

    async def get_module_config(self, version_id: UUID) -> ModuleConfig | None:
        result = await self.db.execute(
            select(ModuleConfig).where(ModuleConfig.version_id == version_id)
        )
        return result.scalar_one_or_none()

    async def save_module_config(self, config: ModuleConfig) -> ModuleConfig:
        self.db.add(config)
        await self.db.flush()
        return config
