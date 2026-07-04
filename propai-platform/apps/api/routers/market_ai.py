
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from apps.api.app.services.market.conversational_market_ai import ConversationalMarketAI
from apps.api.auth.jwt_handler import CurrentUser, get_current_user

router = APIRouter()


class MarketQueryRequest(BaseModel):
    query: str
    context: dict | None = None


@router.post("/ask")
async def ask_market(
    req: MarketQueryRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    ai = ConversationalMarketAI()
    result = await ai.analyze(req.query, req.context)
    # 표준 근거 블록(#5): 실거래 통계 값·산식·출처를 가산(graceful·무목업 — 실값만).
    if isinstance(result, dict):
        try:
            from app.services.data_validation.evidence_contract import build_evidence_block
            data = result.get("data") or {}
            stats = data.get("statistics") or {}
            items = []
            if data.get("total_count") is not None:
                items.append({"label": "조회 거래건수", "value": data.get("total_count"),
                              "basis": "MOLIT 실거래가 공개시스템(지역·기간 필터)"})
            if stats.get("avg_price_10k") is not None:
                items.append({"label": "평균 거래가(만원)", "value": stats.get("avg_price_10k"),
                              "basis": "조회 실거래 전수 평균(거래사례비교)"})
            if stats.get("min_price_10k") is not None:
                items.append({"label": "최저 거래가(만원)", "value": stats.get("min_price_10k"), "basis": "조회 실거래 최저"})
            if stats.get("max_price_10k") is not None:
                items.append({"label": "최고 거래가(만원)", "value": stats.get("max_price_10k"), "basis": "조회 실거래 최고"})
            if items:
                result["evidence"] = build_evidence_block(
                    items=items, legal_ref_keys=["realtx_report"],
                    sources=["국토교통부 실거래가(MOLIT)"])
        except Exception:  # noqa: BLE001 — 근거 블록 실패는 결과를 막지 않음.
            pass
    return result


@router.get("/tools")
async def list_tools(
    current_user: CurrentUser = Depends(get_current_user),
):
    return {"tools": ConversationalMarketAI.AVAILABLE_TOOLS}
