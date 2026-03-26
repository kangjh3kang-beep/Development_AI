"""세금 계산 라우터."""

from uuid import UUID

from fastapi import APIRouter, Depends
from packages.schemas.models import TaxCalculationResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.services.tax_ai_service import TaxAIService

router = APIRouter()


class TaxCalculateRequest(BaseModel):
    project_id: UUID
    tax_type: str
    taxable_value: float
    is_first_home: bool = False
    holding_years: int = 5


@router.post("/calculate", response_model=TaxCalculationResponse)
async def calculate_tax(
    body: TaxCalculateRequest,
    current_user: CurrentUser = Depends(RequirePermission("tax", "write")),
    db: AsyncSession = Depends(get_db),
) -> TaxCalculationResponse:
    """세금을 계산한다."""
    svc = TaxAIService(db)
    return await svc.calculate(
        project_id=body.project_id,
        tenant_id=current_user.tenant_id,
        tax_type=body.tax_type,
        taxable_value=body.taxable_value,
        is_first_home=body.is_first_home,
        holding_years=body.holding_years,
    )
