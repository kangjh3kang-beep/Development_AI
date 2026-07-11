"""Finance router for jeonse risk analysis."""

import logging

from fastapi import APIRouter, Depends
from packages.schemas.models import (
    JeonseRiskRequest,
    JeonseRiskResponse,
)
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.services.jeonse_risk_service import JeonseRiskService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/jeonse-risk", response_model=JeonseRiskResponse)
async def analyze_jeonse_risk(
    body: JeonseRiskRequest,
    current_user: CurrentUser = Depends(RequirePermission("finance", "read")),
    db: AsyncSession = Depends(get_db),
) -> JeonseRiskResponse:
    """전세 리스크를 분석한다. 전세가율 기반 위험도 + LLM 종합 분석."""
    service = JeonseRiskService(db)
    result = await service.analyze(
        project_id=body.project_id,
        tenant_id=current_user.tenant_id,
        address=body.address,
        jeonse_price=body.jeonse_price,
        sale_price=body.sale_price,
    )
    # 표준 근거 블록(#5): 전세가율·위험점수의 실값·산식·출처를 가산(graceful·무목업).
    evidence_block = None
    try:
        from app.services.data_validation.evidence_contract import build_evidence_block

        evidence_block = build_evidence_block(
            items=[
                {"label": "전세가율", "value": round(result.jeonse_ratio, 4),
                 "basis": "전세가 ÷ 매매가(추정시세)"},
                {"label": "위험등급", "value": result.risk_level,
                 "basis": "전세가율 구간 분류(SAFE<0.6≤LOW<0.7≤MEDIUM<0.8≤HIGH<0.9≤CRITICAL)"},
                {"label": "위험점수", "value": round(result.risk_score, 4),
                 "basis": f"위험등급 {result.risk_level} 기준 점수"},
            ],
            sources=["국토교통부 실거래가(MOLIT)"],
        )
    except Exception as e:  # noqa: BLE001 — 근거 블록 실패는 기존 결과를 막지 않음(가산·정직).
        logger.warning("전세 리스크 근거 블록 생성 스킵: %s", str(e)[:120])
    return JeonseRiskResponse(
        jeonse_ratio=result.jeonse_ratio,
        risk_level=result.risk_level,
        risk_score=result.risk_score,
        analysis=result.analysis,
        factors=result.factors,
        evidence=evidence_block,
    )
