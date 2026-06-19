"""단체톡/실시간 채널 WebSocket 매니저 (백엔드 인프로세스).

백엔드는 Oracle 단일 컨테이너라 인프로세스 매니저로 충분.
(프론트 Cloudflare 호스팅 제약과는 무관 — WS 종단은 백엔드)
"""

from collections import defaultdict

from fastapi import WebSocket


class WSManager:
    def __init__(self):
        self.channels: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, channel_id: str, ws: WebSocket, already_accepted: bool = False):
        # already_accepted=True 면 호출부가 이미 ws.accept() 를 끝낸 상태(예: ws_routes 의
        # accept-then-close 인증/인가 게이트)다. 이때 다시 accept 하면 'WebSocket already accepted'
        # 계약 위반/RuntimeError 가 나므로 accept 를 건너뛴다. 기본값 False 라 기존 호출부는 무영향.
        if not already_accepted:
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
