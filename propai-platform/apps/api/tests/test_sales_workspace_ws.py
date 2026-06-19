"""#2 워크스페이스 — sales 실시간 WebSocket 인증/인가·채널 격리 단위테스트.

대상: app.api.endpoints.sales.ws_routes (channel_ws + 보조 헬퍼).

검증 포인트(현장 격리·보안):
  1) 토큰 없음/위조 → accept 전에 close(4401)로 거부(인증).
  2) 유효 토큰이지만 그 현장 멤버가 아니면 → close(4403)로 거부(인가·채널 격리).
  3) 멤버면 → 채널 합류 + 인바운드 메시지 스키마 검증(PING→PONG, 미허용 타입 무시).
  4) 채널명 파싱(board:{site_id}) — 비현장 채널은 멤버십 인가를 건너뛴다(인증은 항상).

★샌드박스: 실 DB 없이 검증하기 위해 멤버십 인가(_authorize_site_channel)는 monkeypatch 로
대체한다(인가 '판정 결과' 가 4403/합류로 정확히 반영되는지 = WS 게이트 로직을 검증).
실 DB 멤버십 인가의 라이브 검증은 deploy-pending.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from jose import jwt

from app.api.endpoints.sales import ws_routes
from app.core.config import settings

# 엔드포인트 흐름 테스트(async)만 asyncio 로 표시한다. 헬퍼 단위테스트는 동기 함수라
# 모듈 전역 mark 를 쓰지 않고 각 async 테스트에 개별 적용한다(불필요한 asyncio 경고 제거).
_asyncio = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _reset_conn_throttle():
    """테스트 간 연결 throttle 인메모리 카운터 초기화(테스트끼리 동일 sub 재사용 시 누적→오탐 방지)."""
    ws_routes._conn_log.clear()
    yield
    ws_routes._conn_log.clear()


# ── 가짜 WebSocket(기존 test_ws_manager._FakeWS 패턴 + receive/close 확장) ──
class _FakeWS:
    """채널 WS 흐름 검증용 가짜 소켓.

    - accept(): 합류 여부 추적.
    - receive_text(): _inbound 큐를 차례로 반환, 소진되면 WebSocketDisconnect 로 루프 종료.
    - send_json(): 서버→클라 전송(PONG 등) 기록.
    - close(code): 거부/종료 코드 기록.
    """

    def __init__(self, inbound: list[str] | None = None):
        self.accepted = False
        self.sent: list = []
        self.closed_code: int | None = None
        self._inbound = list(inbound or [])

    async def accept(self):
        self.accepted = True

    async def receive_text(self) -> str:
        from fastapi import WebSocketDisconnect

        if not self._inbound:
            raise WebSocketDisconnect()
        return self._inbound.pop(0)

    async def send_json(self, msg):
        self.sent.append(msg)

    async def close(self, code: int = 1000):
        self.closed_code = code


def _make_token(*, scope: str | None = None, kind: str | None = "access",
                sub: str = "11111111-1111-1111-1111-111111111111",
                expired: bool = False) -> str:
    """테스트용 JWT 발급(엔드포인트가 읽는 settings.JWT_SECRET_KEY 와 동일 키로 서명)."""
    now = datetime.now(UTC)
    payload: dict = {"sub": sub, "iat": now,
                     "exp": now - timedelta(hours=1) if expired else now + timedelta(hours=1)}
    if kind:
        payload["type"] = kind
    if scope:
        payload["scope"] = scope
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


# ── 헬퍼 단위테스트 ───────────────────────────────────────────────────────────
def test_authenticate_ws_rejects_empty_and_garbage():
    assert ws_routes._authenticate_ws("") is None
    assert ws_routes._authenticate_ws("not-a-jwt") is None


def test_authenticate_ws_rejects_expired():
    assert ws_routes._authenticate_ws(_make_token(expired=True)) is None


def test_authenticate_ws_rejects_wrong_kind_and_scope():
    # type!=access 이고 scope!=sales_site → 거부.
    assert ws_routes._authenticate_ws(_make_token(kind="refresh", scope=None)) is None


def test_authenticate_ws_accepts_platform_access_token():
    uid = "22222222-2222-2222-2222-222222222222"
    assert ws_routes._authenticate_ws(_make_token(kind="access", sub=uid)) == uid


def test_authenticate_ws_accepts_site_session_token():
    # 현장 세션토큰(scope=sales_site)도 허용(type 이 access 라도 scope 로 추가 허용).
    uid = "33333333-3333-3333-3333-333333333333"
    assert ws_routes._authenticate_ws(_make_token(kind="access", scope="sales_site", sub=uid)) == uid


def test_site_id_from_channel():
    assert ws_routes._site_id_from_channel("board:abc-123") == "abc-123"
    assert ws_routes._site_id_from_channel("board:") is None          # 빈 site_id → 비현장 취급
    assert ws_routes._site_id_from_channel("risk-alerts") is None     # 비현장 채널
    assert ws_routes._site_id_from_channel("chat") is None


# ── 엔드포인트 흐름: 인증 거부(4401) ──────────────────────────────────────────
@_asyncio
async def test_channel_ws_closes_4401_without_token():
    # ★accept-then-close(전송계층 갭 봉합): 인증 실패도 accept 후 close(4401) 해야 실브라우저가
    #   코드 4401 을 그대로 받는다(pre-accept close 는 handshake 거부→1006 으로 변환). 따라서
    #   accept 는 True 이되 채널 합류는 하지 않고 4401 로 닫혀야 한다.
    ws = _FakeWS()
    await ws_routes.channel_ws(ws, "board:site-1", token="")
    assert ws.closed_code == 4401
    assert ws.accepted is True  # accept 후 close 해야 4401 코드가 클라에 그대로 전달됨.


@_asyncio
async def test_channel_ws_closes_4401_invalid_token():
    ws = _FakeWS()
    await ws_routes.channel_ws(ws, "board:site-1", token="forged.token.value")
    assert ws.closed_code == 4401
    assert ws.accepted is True  # accept-then-close(코드 전달 보장).


# ── 엔드포인트 흐름: 인가 거부(4403) — 타 현장 채널 격리 ──────────────────────
@_asyncio
async def test_channel_ws_closes_4403_when_not_member(monkeypatch):
    # 토큰은 유효하지만 그 현장 멤버가 아니면(인가 False) → 4403 거부.
    async def _deny(user_id, site_id):
        return False

    monkeypatch.setattr(ws_routes, "_authorize_site_channel", _deny)
    ws = _FakeWS()
    await ws_routes.channel_ws(ws, "board:other-site", token=_make_token())
    assert ws.closed_code == 4403
    # ★accept-then-close: 4403 코드를 클라에 전달하려면 accept 후 close 해야 한다(accepted=True).
    #   단 채널 합류(ws_manager.connect)는 하지 않으므로 도청/주입은 여전히 차단된다.
    assert ws.accepted is True


# ── 엔드포인트 흐름: 멤버 합류 + 메시지 스키마 검증 ──────────────────────────
@_asyncio
async def test_channel_ws_member_joins_and_ping_pongs(monkeypatch):
    async def _allow(user_id, site_id):
        return True

    monkeypatch.setattr(ws_routes, "_authorize_site_channel", _allow)
    # PING → PONG, 미허용 타입(EVIL)·잘못된 JSON 은 무시(서버 상태 변경/주입 차단).
    ws = _FakeWS(inbound=['{"type": "PING"}', '{"type": "EVIL"}', "not-json"])
    await ws_routes.channel_ws(ws, "board:my-site", token=_make_token())
    assert ws.accepted is True            # 멤버는 채널 합류.
    assert ws.closed_code is None         # 정상 disconnect(코드 close 호출 없음).
    assert {"type": "PONG"} in ws.sent    # PING 에만 PONG 응답.
    assert len(ws.sent) == 1              # EVIL/비JSON 은 응답 없음(주입 무시).


@_asyncio
async def test_channel_ws_non_site_channel_skips_membership(monkeypatch):
    # 비현장 채널(board: 아님)은 멤버십 인가를 건너뛰되 인증은 통과해야 합류.
    called = {"authz": False}

    async def _track(user_id, site_id):  # 호출되면 안 됨(비현장 채널).
        called["authz"] = True
        return True

    monkeypatch.setattr(ws_routes, "_authorize_site_channel", _track)
    ws = _FakeWS(inbound=['{"type": "PING"}'])
    await ws_routes.channel_ws(ws, "risk-alerts", token=_make_token())
    assert ws.accepted is True
    assert called["authz"] is False       # 비현장 채널은 멤버십 인가 미수행.


# ── 헬퍼 단위테스트: URL 인코딩 채널명(encodeURIComponent 회귀) ───────────────
def test_site_id_from_channel_url_encoded():
    # 프론트가 채널명을 encodeURIComponent 로 인코딩하면 콜론이 %3A 로 들어온다.
    # unquote 1회 정규화로 인코딩/비인코딩 모두 동일 site_id 를 뽑아야 한다(멱등).
    assert ws_routes._site_id_from_channel("board%3Aabc-123") == "abc-123"
    assert ws_routes._site_id_from_channel("board:abc-123") == "abc-123"   # 비인코딩도 동일.
    assert ws_routes._site_id_from_channel("board%3A") is None             # 인코딩된 빈 site_id.


# ── 엔드포인트 흐름: rate-limit(4429) + 유령소켓 방지(disconnect 호출) ────────
@_asyncio
async def test_channel_ws_rate_limit_closes_4429_and_disconnects(monkeypatch):
    # _RATE_MAX_MSGS+1 개 메시지를 보내면 4429 로 끊고, 종료 경로(break)에서도 finally 가
    # ws_manager.disconnect 를 정확히 호출해 유령소켓이 남지 않아야 한다.
    async def _allow(user_id, site_id):
        return True

    monkeypatch.setattr(ws_routes, "_authorize_site_channel", _allow)

    disconnects: list = []
    # 동일 채널·소켓으로 disconnect 가 호출됐는지 기록(유령소켓 방지 검증).
    monkeypatch.setattr(
        ws_routes.ws_manager, "disconnect",
        lambda channel_id, ws: disconnects.append((channel_id, ws)),
    )

    # 윈도(_RATE_WINDOW_SEC) 내에 한도 초과되도록 한도+1 개를 한 번에 투입.
    over = ws_routes._RATE_MAX_MSGS + 1
    ws = _FakeWS(inbound=['{"type": "PING"}'] * over)
    await ws_routes.channel_ws(ws, "board:my-site", token=_make_token())

    assert ws.closed_code == 4429                 # 플러딩 차단 코드로 종료.
    assert len(disconnects) == 1                  # break 종료여도 finally 가 정확히 1회 구독 해제.
    assert disconnects[0] == ("board:my-site", ws)  # 같은 채널·소켓을 해제(유령소켓 잔존 방지).


# ── 엔드포인트 흐름: 과대 페이로드(멀티바이트 바이트 기준) 무시 ──────────────
@_asyncio
async def test_channel_ws_oversized_multibyte_message_ignored(monkeypatch):
    # 한글(UTF-8 3바이트/자)로 _MAX_MSG_BYTES 를 바이트 기준으로 초과하는 메시지는 무시돼야 한다
    # (len(str) 문자수 기준이면 과소측정으로 통과해버리는 회귀 방지).
    async def _allow(user_id, site_id):
        return True

    monkeypatch.setattr(ws_routes, "_authorize_site_channel", _allow)

    # '가'(3바이트)를 채워 바이트 길이는 한도 초과, 그 뒤 정상 PING 으로 루프 정상 동작 확인.
    big = '{"type":"PING","x":"' + ("가" * ws_routes._MAX_MSG_BYTES) + '"}'
    assert len(big) <= ws_routes._MAX_MSG_BYTES * 3  # 문자수는 작아도(과소측정 함정)…
    assert len(big.encode("utf-8")) > ws_routes._MAX_MSG_BYTES  # …바이트는 한도 초과.
    ws = _FakeWS(inbound=[big, '{"type": "PING"}'])
    await ws_routes.channel_ws(ws, "board:my-site", token=_make_token())

    assert ws.accepted is True
    # 과대 메시지는 무시(PONG 없음), 뒤이은 정상 PING 1건에만 PONG → 정확히 1회.
    assert ws.sent == [{"type": "PONG"}]


# ── 화이트리스트 협소화: dead 'SUBSCRIBE' 제거(공격면 축소) ────────────────────
def test_allowed_client_types_narrowed_to_ping_only():
    # 유일 클라(unitBoardWs)는 PING 만 보낸다 → 화이트리스트는 {PING} 으로 협소화돼야 한다.
    assert "PING" in ws_routes._ALLOWED_CLIENT_TYPES
    assert len(ws_routes._ALLOWED_CLIENT_TYPES) == 1
    assert "SUBSCRIBE" not in ws_routes._ALLOWED_CLIENT_TYPES


# ── 연결 throttle 헬퍼: 슬라이딩윈도(한도 내 허용·초과 거부·윈도 경과 후 회복) ─────
def test_connection_allowed_sliding_window():
    ws_routes._conn_log.clear()
    key = "sub:test-user"
    base = 1000.0
    # 한도(_CONN_MAX)까지는 허용.
    for i in range(ws_routes._CONN_MAX):
        assert ws_routes._connection_allowed(key, now=base + i * 0.01) is True
    # 한도 초과(같은 윈도 내)는 거부.
    assert ws_routes._connection_allowed(key, now=base + 0.5) is False
    # 윈도(_CONN_WINDOW_SEC) 경과 후엔 오래된 연결이 빠져 다시 허용(슬라이딩윈도 회복).
    assert ws_routes._connection_allowed(
        key, now=base + ws_routes._CONN_WINDOW_SEC + 0.1
    ) is True


def test_connection_allowed_prunes_drained_keys_no_leak():
    # ★메모리 누수 회귀 방지: 윈도가 완전히 비워진(오래 안 들어온) 키는 _conn_log dict 에
    #   잔존하면 안 된다(distinct sub/IP 무한 누적 차단). 한 번 기록 후 윈도를 넘겨 재판정하면
    #   그 키의 빈 deque 가 dict 에서 제거돼야 한다.
    ws_routes._conn_log.clear()
    key = "ip:198.51.100.7"
    base = 5000.0
    # 1) 한 번 연결(기록 생성) → 키가 dict 에 등장.
    assert ws_routes._connection_allowed(key, now=base) is True
    assert key in ws_routes._conn_log
    # 2) 윈도 경과 후 '다른 키'를 판정하면, 드레인된 원 키는 정리되어야 한다.
    #    (드레인은 그 키를 다시 판정할 때 일어나므로, 같은 키를 윈도 밖 시각으로 재호출해 확인.)
    far = base + ws_routes._CONN_WINDOW_SEC + 1.0
    assert ws_routes._connection_allowed(key, now=far) is True  # 회복(재허용).
    # 재허용 시 새 기록이 들어가 키는 존재하되, 윈도 안 항목은 정확히 1개여야 한다(과거 기록 누적 0).
    assert len(ws_routes._conn_log[key]) == 1


def test_connection_allowed_drained_key_removed_from_dict():
    # 드레인만 일어나고 재기록이 없는 경로(거부 직후/윈도 경과 후 미접속)에서 빈 deque 가
    # dict 에 남지 않는지 직접 확인한다. 내부 deque 를 비워(윈도 밖) 두고 재판정.
    ws_routes._conn_log.clear()
    key = "sub:drain-user"
    # 윈도를 가득 채워 거부 상태로 만든 뒤,
    base = 7000.0
    for i in range(ws_routes._CONN_MAX):
        ws_routes._connection_allowed(key, now=base + i * 0.001)
    # 윈도를 완전히 벗어난 시각으로 재판정하면(이전 기록 전부 드레인) 허용되고,
    far = base + ws_routes._CONN_WINDOW_SEC + 5.0
    assert ws_routes._connection_allowed(key, now=far) is True
    # 윈도 안 항목은 방금 기록한 1개뿐(과거 _CONN_MAX 개가 누적 잔존하지 않음).
    assert len(ws_routes._conn_log[key]) == 1


def test_connection_throttle_key_prefers_sub_then_ip():
    # 인증된 sub 우선.
    class _C:
        host = "203.0.113.9"

    class _WS:
        client = _C()

    assert ws_routes._conn_throttle_key("u-123", _WS()) == "sub:u-123"
    # sub 없으면 client IP.
    assert ws_routes._conn_throttle_key(None, _WS()) == "ip:203.0.113.9"
    # 둘 다 없으면 unknown(파괴 방지 — getattr 안전).
    assert ws_routes._conn_throttle_key(None, object()) == "unknown"


# ── 엔드포인트 흐름: 연결 throttle(4429) — 인가 DB 조회 이전 차단(DB 증폭 DoS 방어) ──
@_asyncio
async def test_channel_ws_connection_throttle_closes_4429_before_authz(monkeypatch):
    # 동일 토큰(sub)으로 _CONN_MAX 초과 재연결 시, 인가(_authorize_site_channel) DB 조회를
    # 호출하지 않고(=DB 증폭 차단) 즉시 4429 로 끊어야 한다.
    ws_routes._conn_log.clear()
    authz_calls = {"n": 0}

    async def _track_authz(user_id, site_id):
        authz_calls["n"] += 1
        return True

    monkeypatch.setattr(ws_routes, "_authorize_site_channel", _track_authz)

    tok = _make_token(sub="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    last = None
    # 한도+여유 만큼 빠르게 재연결(같은 윈도). 마지막 몇 개는 4429 로 끊겨야 한다.
    for _ in range(ws_routes._CONN_MAX + 3):
        last = _FakeWS()
        await ws_routes.channel_ws(last, "board:some-site", token=tok)

    assert last is not None
    assert last.closed_code == 4429              # 한도 초과 연결은 4429 로 거부.
    assert last.accepted is False                # 채널 합류 안 함.
    # 인가 DB 조회는 허용된 연결(_CONN_MAX)에서만 호출 — 거부된 초과 연결은 DB 를 건드리지 않음.
    assert authz_calls["n"] <= ws_routes._CONN_MAX


# ── 슬라이딩윈도 인바운드: 경계 2배 버스트 제거(고정윈도 회귀 방지) ─────────────
@_asyncio
async def test_channel_ws_inbound_sliding_window_no_boundary_burst(monkeypatch):
    # 한도 이하 메시지는 통과하되, 연속으로 한도를 넘기면 4429. (고정윈도였다면 경계에서
    # 2배까지 통과했겠지만, 슬라이딩윈도는 임의 연속 구간으로 판정해 그 버스트를 막는다.)
    ws_routes._conn_log.clear()

    async def _allow(user_id, site_id):
        return True

    monkeypatch.setattr(ws_routes, "_authorize_site_channel", _allow)

    over = ws_routes._RATE_MAX_MSGS + 1  # 한 윈도 안에서 한도+1 → 초과.
    ws = _FakeWS(inbound=['{"type": "PING"}'] * over)
    await ws_routes.channel_ws(ws, "board:my-site", token=_make_token())
    assert ws.closed_code == 4429  # 한도 초과 즉시 차단(슬라이딩윈도).


# ── 교차계층 계약: WS close 코드 의미 고정(프론트 unitBoardWs.ts 재연결 분기 의존) ──
# 프론트(apps/web/lib/unitBoardWs.ts)의 onclose 는 이 코드들로 재연결 정책을 가른다:
#   4401(인증)/4403(인가) = 영구 거부 → 재연결 중단(토큰갱신/현장재진입 안내),
#   4429(throttle) = 일시 → 지수 백오프 재연결.
# 백엔드가 이 코드 의미를 바꾸면 프론트 분기가 조용히 어긋나(거부 소켓 무한재연결/정상 차단)
# 므로, '관측 가능한 계약'으로 잠가 동시 변경을 강제한다.
@_asyncio
async def test_close_code_contract_4401_unauthenticated():
    # 인증 실패(토큰 없음) → 4401. 프론트는 이 코드를 영구 거부로 보고 재연결을 멈춘다.
    ws = _FakeWS()
    await ws_routes.channel_ws(ws, "board:any-site", token="")
    assert ws.closed_code == 4401


@_asyncio
async def test_close_code_contract_4403_forbidden(monkeypatch):
    # 인가 실패(비멤버) → 4403. 프론트는 영구 거부로 보고 재연결을 멈춘다.
    async def _deny(user_id, site_id):
        return False

    monkeypatch.setattr(ws_routes, "_authorize_site_channel", _deny)
    ws = _FakeWS()
    await ws_routes.channel_ws(ws, "board:any-site", token=_make_token())
    assert ws.closed_code == 4403


@_asyncio
async def test_close_code_contract_4429_throttle_is_transient(monkeypatch):
    # throttle 초과 → 4429. 프론트는 일시 오류로 보고 지수 백오프로 재연결한다(영구 거부 아님).
    ws_routes._conn_log.clear()

    async def _allow(user_id, site_id):
        return True

    monkeypatch.setattr(ws_routes, "_authorize_site_channel", _allow)
    last = None
    for _ in range(ws_routes._CONN_MAX + 3):
        last = _FakeWS()
        await ws_routes.channel_ws(last, "board:some-site", token=_make_token())
    assert last is not None
    assert last.closed_code == 4429
    # 4401/4403 과 달라야 한다(일시 vs 영구 — 프론트 분기 분별의 근거).
    assert last.closed_code not in (4401, 4403)
