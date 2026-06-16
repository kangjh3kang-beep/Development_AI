"""Phase 4 — 일반 실시간 WebSocket 매니저(인프로세스) + 위험알림 브로드캐스트.

채널별 WebSocket 집합 관리 + broadcast. risk_monitor의 `_ws_notifier`가 `broadcast_risk_alert`로
호출한다(능동 위험감지 → 실시간 push). 백엔드 단일 컨테이너 인프로세스 매니저로 충분
(sales/mh/ws.py 패턴 일반화). 죽은 커넥션은 broadcast 시 자동 정리.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_RISK_CHANNEL = "risk-alerts"


class RealtimeManager:
    """채널(문자열)별 WebSocket 집합 관리."""

    def __init__(self) -> None:
        self.channels: dict[str, set[Any]] = defaultdict(set)

    async def connect(self, channel: str, ws: Any) -> None:
        await ws.accept()
        self.channels[channel].add(ws)

    def disconnect(self, channel: str, ws: Any) -> None:
        self.channels[channel].discard(ws)

    async def broadcast(self, channel: str, message: dict[str, Any]) -> int:
        """채널의 모든 연결에 message 전송. 전송 실패한 죽은 연결은 제거. 전송 수 반환."""
        dead: list[Any] = []
        sent = 0
        for ws in list(self.channels.get(channel, set())):
            try:
                await ws.send_json(message)
                sent += 1
            except Exception:  # noqa: BLE001 — 죽은 연결은 제거(무중단)
                dead.append(ws)
        for ws in dead:
            self.channels[channel].discard(ws)
        return sent


# 인프로세스 싱글턴
manager = RealtimeManager()


async def broadcast_risk_alert(alert: dict[str, Any]) -> int:
    """위험 알림을 risk-alerts 채널 + (project_id 있으면) 프로젝트 채널로 브로드캐스트. 전송 수 반환."""
    payload = {"type": "risk_alert", **alert}
    sent = await manager.broadcast(_RISK_CHANNEL, payload)
    pid = alert.get("project_id")
    if pid:
        sent += await manager.broadcast(f"project:{pid}", payload)
    return sent
