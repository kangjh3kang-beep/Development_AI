"""단체톡/실시간 채널 WebSocket 매니저 (백엔드 인프로세스).

백엔드는 Oracle 단일 컨테이너라 인프로세스 매니저로 충분.
(프론트 Cloudflare 호스팅 제약과는 무관 — WS 종단은 백엔드)
"""

from collections import defaultdict

from fastapi import WebSocket


class WSManager:
    def __init__(self):
        self.channels: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, channel_id: str, ws: WebSocket):
        await ws.accept()
        self.channels[channel_id].add(ws)

    def disconnect(self, channel_id: str, ws: WebSocket):
        self.channels[channel_id].discard(ws)

    async def broadcast(self, channel_id: str, message: dict):
        dead = []
        for ws in list(self.channels.get(channel_id, set())):
            try:
                await ws.send_json(message)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            self.channels[channel_id].discard(ws)


ws_manager = WSManager()
