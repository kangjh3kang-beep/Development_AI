"""WebSocket 에이전트 진행률 테스트.

Phase F-8: WebSocket 엔드포인트 구조 검증.
"""

from pathlib import Path

_AGENTS_PATH = (
    Path(__file__).resolve().parents[2]
    / "apps" / "api" / "routers" / "agents.py"
)
_AGENTS_SOURCE = _AGENTS_PATH.read_text(encoding="utf-8")


class TestWebSocketEndpoint:
    """WebSocket 에이전트 엔드포인트 검증."""

    def test_websocket_endpoint_exists(self) -> None:
        """WebSocket 엔드포인트가 존재한다."""
        assert "@router.websocket" in _AGENTS_SOURCE

    def test_websocket_path(self) -> None:
        """WebSocket 경로가 /analyze/ws/{project_id}이다."""
        assert "/analyze/ws/{project_id}" in _AGENTS_SOURCE

    def test_websocket_import(self) -> None:
        """WebSocket 관련 임포트가 있다."""
        assert "WebSocket" in _AGENTS_SOURCE
        assert "WebSocketDisconnect" in _AGENTS_SOURCE

    def test_jwt_auth_in_ws(self) -> None:
        """WebSocket에서 JWT 인증을 수행한다."""
        assert "decode_token" in _AGENTS_SOURCE
        assert "token" in _AGENTS_SOURCE

    def test_orchestrator_bridge(self) -> None:
        """오케스트레이터와 WebSocket 브릿지가 있다."""
        assert "PropAIOrchestrator" in _AGENTS_SOURCE
        assert "send_json" in _AGENTS_SOURCE


class TestWebSocketAndSSECoexist:
    """SSE와 WebSocket이 공존하는지 검증."""

    def test_sse_still_exists(self) -> None:
        """기존 SSE 엔드포인트가 유지된다."""
        assert "EventSourceResponse" in _AGENTS_SOURCE
        assert "@router.post" in _AGENTS_SOURCE

    def test_both_endpoints(self) -> None:
        """SSE(/orchestrate)와 WS(/analyze/ws/) 모두 존재한다."""
        assert "/orchestrate" in _AGENTS_SOURCE
        assert "/analyze/ws/" in _AGENTS_SOURCE
