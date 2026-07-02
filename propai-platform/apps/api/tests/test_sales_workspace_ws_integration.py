"""#2 워크스페이스 — sales 실시간 WebSocket 전송계층 통합테스트(★거짓통과 봉합).

대상: app.api.endpoints.sales.ws_routes.channel_ws 를 '실 앱 + 실 WS 전송계층'으로 구동.

배경(iter-5 센터피스 무력화 — HIGH):
  기존 단위테스트(test_sales_workspace_ws.py)는 _FakeWS 에 close code 를 직접 주입해
  '전송계층(accept/close 순서)' 을 우회한다. 그래서 ws.close(4401/4403) 가 accept *이전* 에
  호출돼도(과거 버그) 단위테스트는 통과해버렸다(거짓통과). 그러나 실 전송계층(uvicorn 0.42.0 /
  websockets 16.0)에서 pre-accept close 는 handshake 거부(HTTP 업그레이드 4xx)로 변환돼
  Close 프레임이 전달되지 않고, 실브라우저는 CloseEvent.code=1006 만 받는다(4401/4403 미수신
  → 프론트 unitBoardWs.ts 의 4401/4403 분기 영구 미발화 → 배너/CTA/재연결중단 무력화).

이 통합테스트는 starlette TestClient(인프로세스 ASGI WS 전송)로 channel_ws 를 실제 구동해,
'클라가 실제로 받는 결과(WebSocketDisconnect.code 와 handshake 성립 여부)'를 단언한다.
  - accept-then-close(수정 후): handshake 성립(connect __enter__ 성공) → 이후 첫 수신에서
    WebSocketDisconnect(4401/4403). 즉 클라가 코드를 그대로 수신.
  - pre-accept close(과거 버그): connect __enter__ 단계에서 handshake 거부로 즉시 실패(코드를
    프레임으로 받지 못함 = 실브라우저 1006 등가). → 본 테스트가 실패해 버그를 잠근다.

★샌드박스: 실 DB 없이 멤버십 인가(_authorize_site_channel)는 monkeypatch 로 판정만 주입한다
(인증 _authenticate_ws 는 실 JWT 검증). 실 DB 멤버십 인가의 라이브 검증은 deploy-pending.

★중요(이중 import 함정): main.py 는 ws_routes 를 'apps.api.app.api.endpoints.sales.ws_routes'
또는 'app.api.endpoints.sales.ws_routes' 로 import 한다(폴백). PYTHONPATH 구성상 둘은 sys.modules
에 '서로 다른 모듈 객체'로 동시 로드될 수 있다. 그래서 단순히 'app.*' 경로로 import 한 ws_routes
의 _authorize_site_channel 을 monkeypatch 해도, 실제 라우트가 'apps.api.app.*' 사본에 바인딩돼
있으면 패치가 먹지 않아(실 DB 인가가 그대로 호출) 거짓실패한다. 따라서 라이브 라우트의 endpoint
함수에서 '바인딩된 실제 모듈'을 역추적해 그 모듈에 패치/초기화를 적용한다(import 경로 무관·견고).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from jose import jwt
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.config import settings


def _bound_module_for_path(app, path: str):
    """앱 라우트에서 주어진 path 의 endpoint 가 실제로 바인딩한 모듈을 역추적한다.

    이중 import(apps.api.app.* vs app.*) 로 모듈 사본이 갈리는 함정을 피하기 위해, 라우트
    endpoint 의 __module__ 로 '실제로 호출되는 사본'을 찾는다(monkeypatch·throttle 초기화가
    헛돌지 않도록).
    """
    import importlib
    import sys

    for r in app.routes:
        if getattr(r, "path", None) == path:
            mod_name = r.endpoint.__module__
            return sys.modules.get(mod_name) or importlib.import_module(mod_name)
    return None


@pytest.fixture(scope="module")
def app_and_ws_module():
    """실 앱과 '라이브 WS 라우트가 실제로 바인딩한 ws_routes·social 모듈' 을 함께 반환한다.

    채널 WS(/ws/sales/{channel_id})와 소셜 WS(/api/v1/social/ws) 양쪽의 바인딩 모듈을
    역추적한다(공용 하드닝을 두 라우트가 동일 소비하는지 전송계층으로 검증하기 위함).
    """
    from apps.api.main import app

    bound_module = _bound_module_for_path(app, "/ws/sales/{channel_id}")
    assert bound_module is not None, "WS 라우트(/ws/sales/{channel_id}) 가 앱에 없음"
    social_module = _bound_module_for_path(app, "/api/v1/social/ws")
    assert social_module is not None, "소셜 WS 라우트(/api/v1/social/ws) 가 앱에 없음"
    return app, bound_module, social_module


@pytest.fixture
def ws_routes(app_and_ws_module):
    """라이브 라우트가 바인딩한 실제 ws_routes 모듈(패치/단언 대상)."""
    return app_and_ws_module[1]


@pytest.fixture
def social_routes(app_and_ws_module):
    """라이브 라우트가 바인딩한 실제 social 모듈(패치/단언 대상)."""
    return app_and_ws_module[2]


@pytest.fixture(autouse=True)
def _reset_conn_throttle(ws_routes, social_routes):
    """테스트 간 연결 throttle 인메모리 카운터 초기화(동일 sub 재사용 누적→오탐 방지).

    ★바인딩된 실제 모듈의 채널 WS(_conn_log)·소셜 WS(_social_conn_log) throttle 카운터를 모두
      초기화한다(사본 불일치로 초기화가 헛돌지 않게).
    """
    social_routes._social_conn_log.clear()
    ws_routes._conn_log.clear()
    yield
    ws_routes._conn_log.clear()
    social_routes._social_conn_log.clear()


@pytest.fixture
def test_client(app_and_ws_module):
    """실 FastAPI 앱 기반 starlette TestClient — 실 WS 전송계층으로 channel_ws 를 구동한다.

    TestClient 는 인프로세스 ASGI 라 라이브 서버/멀티워커 없이도 accept/close 순서의
    전송계층 결과(handshake 성립 여부·Close 코드 전달)를 검증할 수 있다.
    """
    app = app_and_ws_module[0]
    with TestClient(app) as client:
        yield client


def _make_token(*, scope: str | None = None, kind: str | None = "access",
                sub: str = "11111111-1111-1111-1111-111111111111",
                expired: bool = False) -> str:
    """테스트용 JWT 발급(앱이 읽는 settings.JWT_SECRET_KEY 와 동일 키로 서명)."""
    now = datetime.now(UTC)
    payload: dict = {"sub": sub, "iat": now,
                     "exp": now - timedelta(hours=1) if expired else now + timedelta(hours=1)}
    if kind:
        payload["type"] = kind
    if scope:
        payload["scope"] = scope
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


# ── 인증 거부(4401): 무효/누락 토큰 → 클라가 실제로 4401 을 코드로 수신 ──────────────
def test_ws_transport_invalid_token_delivers_4401(test_client):
    """무효 토큰 → accept-then-close 로 클라가 WebSocketDisconnect(4401) 를 코드 그대로 수신.

    ★전송계층 잠금: 과거 pre-accept close 였다면 connect __enter__ 에서 handshake 거부로 실패해
    아래 'handshake 성립 후 첫 수신에서 4401' 단언이 깨진다(버그 회귀 차단).
    """
    # handshake 성립(accept 됨) 후 첫 수신에서 4401 — accept-then-close 라야 connect 가 성립한다.
    with (
        test_client.websocket_connect("/ws/sales/board:site-1?token=forged.bad.token") as ws,
        pytest.raises(WebSocketDisconnect) as ei,
    ):
        ws.receive_text()
    assert ei.value.code == 4401  # 클라가 인증실패 코드를 그대로 수신(1006 아님).


def test_ws_transport_missing_token_delivers_4401(test_client):
    """토큰 누락(?token 없음) → 동일하게 4401 코드 전달."""
    with (
        test_client.websocket_connect("/ws/sales/board:site-1") as ws,
        pytest.raises(WebSocketDisconnect) as ei,
    ):
        ws.receive_text()
    assert ei.value.code == 4401


def test_ws_transport_expired_token_delivers_4401(test_client):
    """만료 토큰 → 인증 실패 → 4401 코드 전달(만료도 위조와 동일 처리)."""
    tok = _make_token(expired=True)
    with (
        test_client.websocket_connect(f"/ws/sales/board:site-1?token={tok}") as ws,
        pytest.raises(WebSocketDisconnect) as ei,
    ):
        ws.receive_text()
    assert ei.value.code == 4401


# ── 인가 거부(4403): 유효 토큰·비멤버 → 클라가 실제로 4403 을 코드로 수신 ───────────
def test_ws_transport_non_member_delivers_4403(test_client, ws_routes, monkeypatch):
    """유효 토큰이지만 그 현장 비멤버(인가 False) → accept-then-close 로 클라가 4403 수신.

    ★샌드박스: 멤버십 인가는 monkeypatch 로 False 만 주입(실 DB 인가 검증은 deploy-pending).
    핵심은 '인가 거부 코드 4403 이 전송계층을 통해 코드 그대로 클라에 전달되는가' 다.
    """
    async def _deny(user_id, site_id):
        return False

    monkeypatch.setattr(ws_routes, "_authorize_site_channel", _deny)
    tok = _make_token()
    with (
        test_client.websocket_connect(f"/ws/sales/board:other-site?token={tok}") as ws,
        pytest.raises(WebSocketDisconnect) as ei,
    ):
        ws.receive_text()
    assert ei.value.code == 4403  # 타 현장 채널 거부 코드를 그대로 수신(1006 아님).


# ── 정상 멤버: accept 성립 + PING→PONG 왕복(전송계층 정상 동작) ─────────────────────
def test_ws_transport_member_accepts_and_ping_pongs(test_client, ws_routes, monkeypatch):
    """멤버(인가 True) → handshake 성립 후 PING 전송 시 서버 PONG 응답(채널 합류·메시지 왕복)."""
    async def _allow(user_id, site_id):
        return True

    monkeypatch.setattr(ws_routes, "_authorize_site_channel", _allow)
    tok = _make_token()
    with test_client.websocket_connect(f"/ws/sales/board:my-site?token={tok}") as ws:
        ws.send_text('{"type": "PING"}')
        msg = ws.receive_json()
        assert msg == {"type": "PONG"}  # 멤버는 합류·heartbeat 왕복 정상.


def test_ws_transport_member_ignores_disallowed_type(test_client, ws_routes, monkeypatch):
    """미허용 타입(EVIL)은 무시(서버 상태/응답 없음) — 이후 PING 만 PONG 으로 응답."""
    async def _allow(user_id, site_id):
        return True

    monkeypatch.setattr(ws_routes, "_authorize_site_channel", _allow)
    tok = _make_token()
    with test_client.websocket_connect(f"/ws/sales/board:my-site?token={tok}") as ws:
        ws.send_text('{"type": "EVIL"}')  # 화이트리스트 밖 → 무시(응답 없음).
        ws.send_text('{"type": "PING"}')  # 정상 PING → PONG.
        msg = ws.receive_json()
        assert msg == {"type": "PONG"}  # EVIL 응답이 끼지 않고 PONG 만 수신.


# ── 비현장 채널: 멤버십 인가 건너뜀(인증만 통과하면 합류) ─────────────────────────────
def test_ws_transport_non_site_channel_skips_membership(test_client, ws_routes, monkeypatch):
    """board: 가 아닌 채널은 멤버십 인가를 건너뛰고(인증만) 합류 — accept 후 PING/PONG 정상."""
    called = {"authz": False}

    async def _track(user_id, site_id):  # 호출되면 안 됨(비현장 채널).
        called["authz"] = True
        return True

    monkeypatch.setattr(ws_routes, "_authorize_site_channel", _track)
    tok = _make_token()
    with test_client.websocket_connect(f"/ws/sales/risk-alerts?token={tok}") as ws:
        ws.send_text('{"type": "PING"}')
        msg = ws.receive_json()
        assert msg == {"type": "PONG"}
    assert called["authz"] is False  # 비현장 채널은 멤버십 인가 미수행.


# ════════════════════════════════════════════════════════════════════════════════
# 소셜 WS(/api/v1/social/ws) — 채널 WS 와 동일 공용 하드닝(accept-then-close·throttle·
# rate-limit)을 전송계층으로 검증한다(★전역전파규칙 — social_ws 동일클래스 결함 봉합).
# ════════════════════════════════════════════════════════════════════════════════
def _install_fake_db(monkeypatch, social_routes):
    """소셜 WS 성공 경로의 DB 접근(_ensure + chat_members SELECT)을 실 DB 없이 우회한다.

    ★샌드박스: 실 DB 멤버십/방 구독의 라이브 검증은 deploy-pending. 본 테스트의 핵심은
      '인증·throttle·rate-limit·타입 화이트리스트가 전송계층을 통해 동일 계약으로 동작하는가' 다.
      그래서 async_session_factory 를 빈 결과를 주는 가짜 세션으로 대체하고 _ensure 는 no-op 으로
      만든다(내 방 0개 → READY{rooms:[]} 후 PING/PONG 왕복).
    """
    class _FakeResult:
        def scalars(self):
            return self
        def all(self):
            return []  # 내 방 0개(빈 구독).

    class _FakeSession:
        async def execute(self, *a, **k):
            return _FakeResult()
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False

    async def _noop_ensure(db):
        return None

    monkeypatch.setattr(social_routes, "async_session_factory", lambda: _FakeSession())
    monkeypatch.setattr(social_routes, "_ensure", _noop_ensure)


def test_social_ws_invalid_token_delivers_4401(test_client):
    """소셜 WS 무효 토큰 → accept-then-close 로 클라가 WebSocketDisconnect(4401) 를 코드 그대로 수신.

    ★전송계층 잠금: 과거 pre-accept close(social.py:761) 였다면 connect __enter__ 에서 handshake
    거부로 실패해 'handshake 성립 후 첫 수신에서 4401' 단언이 깨진다(동일클래스 버그 회귀 차단).
    """
    with (
        test_client.websocket_connect("/api/v1/social/ws?token=forged.bad.token") as ws,
        pytest.raises(WebSocketDisconnect) as ei,
    ):
        ws.receive_text()
    assert ei.value.code == 4401  # 클라가 인증실패 코드를 그대로 수신(1006 아님).


def test_social_ws_expired_token_delivers_4401(test_client):
    """소셜 WS 만료 토큰 → 인증 실패 → 4401 코드 전달(만료도 위조와 동일 처리)."""
    tok = _make_token(expired=True)
    with (
        test_client.websocket_connect(f"/api/v1/social/ws?token={tok}") as ws,
        pytest.raises(WebSocketDisconnect) as ei,
    ):
        ws.receive_text()
    assert ei.value.code == 4401


def test_social_ws_site_session_token_rejected_4401(test_client):
    """소셜 WS 는 PUBLIC(전역 SSO access 토큰)만 허용 — 현장 세션토큰(scope=sales_site)은 거부(4401).

    채널 WS 는 현장 세션토큰을 허용하지만, 소셜 WS 는 require_access_only 로 access 만 받는다
    (get_current_user 와 동일 규칙 — 공용 헬퍼 authenticate_ws 의 분기 검증).
    """
    tok = _make_token(kind=None, scope="sales_site")  # access 아님, 현장 세션토큰.
    with (
        test_client.websocket_connect(f"/api/v1/social/ws?token={tok}") as ws,
        pytest.raises(WebSocketDisconnect) as ei,
    ):
        ws.receive_text()
    assert ei.value.code == 4401


def test_social_ws_member_accepts_ready_and_ping_pongs(test_client, social_routes, monkeypatch):
    """소셜 WS 정상 토큰 → handshake 성립 후 READY 수신, PING 전송 시 PONG 응답(전송계층 왕복)."""
    _install_fake_db(monkeypatch, social_routes)
    tok = _make_token()
    with test_client.websocket_connect(f"/api/v1/social/ws?token={tok}") as ws:
        ready = ws.receive_json()
        assert ready == {"type": "READY", "rooms": []}  # 내 방 0개(빈 구독) READY.
        ws.send_text('{"type": "PING"}')
        msg = ws.receive_json()
        assert msg == {"type": "PONG"}  # heartbeat 왕복 정상.


def test_social_ws_ignores_disallowed_type(test_client, social_routes, monkeypatch):
    """소셜 WS 미허용 타입(EVIL)은 무시(응답 없음) — 이후 PING 만 PONG 으로 응답."""
    _install_fake_db(monkeypatch, social_routes)
    tok = _make_token()
    with test_client.websocket_connect(f"/api/v1/social/ws?token={tok}") as ws:
        assert ws.receive_json()["type"] == "READY"
        ws.send_text('{"type": "EVIL"}')  # 화이트리스트({PING,SUBSCRIBE}) 밖 → 무시.
        ws.send_text('{"type": "PING"}')
        msg = ws.receive_json()
        assert msg == {"type": "PONG"}  # EVIL 응답이 끼지 않고 PONG 만 수신.


def test_social_ws_flood_delivers_4429(test_client, social_routes, monkeypatch):
    """소셜 WS 인바운드 플러딩 → 슬라이딩윈도 rate-limit 초과 시 4429 로 끊김(전송계층 코드 전달).

    한도(_RATE_MAX_MSGS=60)를 넘겨 메시지를 보내면 서버가 4429 로 close 한다. 클라는 그 코드를
    그대로 수신한다(채널 WS 와 동일 계약).
    """
    _install_fake_db(monkeypatch, social_routes)
    tok = _make_token()
    with (
        test_client.websocket_connect(f"/api/v1/social/ws?token={tok}") as ws,
        pytest.raises(WebSocketDisconnect) as ei,
    ):
        assert ws.receive_json()["type"] == "READY"
        # 한도(60) + 여유분 초과 전송 → over_rate 발화 → 4429 close.
        for _ in range(80):
            ws.send_text('{"type": "PING"}')
            # PONG 이 쌓여 버퍼가 막히지 않도록 가능한 만큼 비운다(close 시 예외로 빠져나감).
            try:
                ws.receive_json()
            except WebSocketDisconnect:
                raise
    assert ei.value.code == 4429  # 플러딩 차단 코드 그대로 수신.


def test_social_ws_connection_throttle_delivers_4429(test_client, social_routes, monkeypatch):
    """소셜 WS 연결 폭주 → 연결 throttle(_CONN_MAX=20) 초과 시 4429(★accept/DB 조회 이전 차단).

    동일 토큰(sub)으로 한도를 넘겨 반복 연결하면, 한도 초과 연결은 accept 전에 4429 로 거부된다.
    이는 인증·구독 DB 조회 증폭(silent-DoS)을 막는 연결단 게이트(채널 WS 와 동일 계약)다.
    """
    _install_fake_db(monkeypatch, social_routes)
    tok = _make_token(sub="22222222-2222-2222-2222-222222222222")
    # 한도(20)까지는 정상 연결(READY 수신 후 즉시 닫음).
    for _ in range(20):
        with test_client.websocket_connect(f"/api/v1/social/ws?token={tok}") as ws:
            assert ws.receive_json()["type"] == "READY"
    # 21번째 연결은 throttle 초과 → 4429 로 거부(handshake 성립 못 하거나 첫 수신서 4429).
    with (
        pytest.raises(WebSocketDisconnect) as ei,
        test_client.websocket_connect(f"/api/v1/social/ws?token={tok}") as ws,
    ):
        ws.receive_text()
    assert ei.value.code == 4429
