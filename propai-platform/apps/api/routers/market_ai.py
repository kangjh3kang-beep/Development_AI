from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from apps.api.app.services.market.conversational_market_ai import ConversationalMarketAI

router = APIRouter()


class MarketQueryRequest(BaseModel):
    query: str
    context: Optional[dict] = None


@router.post("/ask")
async def ask_market(req: MarketQueryRequest):
    ai = ConversationalMarketAI()
    return await ai.analyze(req.query, req.context)


@router.get("/tools")
async def list_tools():
    return {"tools": ConversationalMarketAI.AVAILABLE_TOOLS}
