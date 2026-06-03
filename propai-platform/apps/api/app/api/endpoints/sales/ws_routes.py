"""sales 실시간 WebSocket — 단체톡/동호배치도 채널. main 에 직접 등록(/ws/sales/...)."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.sales.mh.ws import ws_manager

ws_router = APIRouter()


@ws_router.websocket("/ws/sales/{channel_id}")
async def channel_ws(ws: WebSocket, channel_id: str):
    await ws_manager.connect(channel_id, ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(channel_id, ws)
