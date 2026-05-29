from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

from apps.api.app.services.market.conversational_market_ai import ConversationalMarketAI
from apps.api.auth.jwt_handler import CurrentUser, get_current_user

router = APIRouter()


class MarketQueryRequest(BaseModel):
    query: str
    context: Optional[dict] = None


@router.post("/ask")
async def ask_market(
    req: MarketQueryRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    ai = ConversationalMarketAI()
    return await ai.analyze(req.query, req.context)


@router.get("/tools")
async def list_tools(
    current_user: CurrentUser = Depends(get_current_user),
):
    return {"tools": ConversationalMarketAI.AVAILABLE_TOOLS}
