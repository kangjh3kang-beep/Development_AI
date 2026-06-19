"""sales 실시간 WebSocket 공용 하드닝 — 채널 WS(ws_routes)·소셜 WS(social) 양쪽이 동일 소비.

★전역전파규칙(공용화·표준계약, 국소패치 금지): 과거 채널 WS(ws_routes.channel_ws)에만 있던
  WS 하드닝(연결 throttle·인증·accept-then-close·인바운드 rate-limit·바이트 크기캡·타입
  화이트리스트)을 이 한 모듈로 추출한다. 소셜 WS(social.social_ws)도 동일 헬퍼를 소비해
  같은 결함(동일클래스 버그)이 재발하지 않게 한다. 두 라우트가 같은 close-code 계약을 공유하므로
  프론트(unitBoardWs.ts·socialWs.ts)의 재연결 분기도 일관된다.

★close-code 계약(SSOT — 프론트 unitBoardWs.ts·socialWs.ts 와 동일 의미):
  - 4401 = 인증 실패(토큰 없음/위조/만료) → 토큰 재발급 전엔 재연결해도 동일 거부(영구).
  - 4403 = 인가 실패(그 현장 비멤버 등) → 멤버십이 바뀌기 전엔 동일 거부(영구).
  - 4429 = 연결/메시지 throttle 초과 → 일시적, 지수 백오프 재연결로 대응.

★accept-then-close(전송계층 갭 봉합): 인증(4401)/인가(4403) 거부는 반드시 ws.accept() 이후에
  close 해야 한다. accept 이전 close 는 uvicorn 0.42.0(websockets 16.0)이 handshake 거부
  (HTTP 업그레이드 4xx)로 변환해 Close 프레임을 보내지 않으므로, 실브라우저는
  CloseEvent.code=1006 만 받고 4401/4403 분기가 영구 미발화한다(배너/CTA/재연결중단 무력화).
  그래서 throttle(4429)만 accept 이전에 두고(클라가 '백오프 재연결'로 대응하므로 1006 으로
  바뀌어도 동작 동일), 인증/인가 거부는 accept 후 close 로 코드를 그대로 전달한다.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict, deque

from fastapi import WebSocket

# ── close-code 상수(SSOT) ──
WS_CLOSE_UNAUTHENTICATED = 4401  # 인증 실패(영구)
WS_CLOSE_FORBIDDEN = 4403        # 인가 실패(영구)
WS_CLOSE_THROTTLED = 4429        # 연결/메시지 throttle(일시)

# ── 인바운드 메시지 rate-limit(★슬라이딩윈도) ──
# 채널/소셜 모두 서버→클라 push 가 주이고 클라→서버는 heartbeat(PING)·구독갱신 정도라 넉넉히
# 잡되, 폭주(주입/플러딩)는 끊는다.
# ★고정윈도(reset)는 경계에서 '직전 윈도 끝 + 새 윈도 시작'에 2배 버스트가 통과하는 결함이 있다.
#   그래서 최근 _RATE_WINDOW_SEC 초의 수신 타임스탬프를 deque 로 유지하는 슬라이딩윈도로 바꿔,
#   '임의 연속 _RATE_WINDOW_SEC 구간'의 메시지 수가 한도를 넘으면 끊는다(경계 2배 버스트 제거).
_RATE_WINDOW_SEC = 10.0
_RATE_MAX_MSGS = 60
# 인바운드 메시지 최대 길이(바이트) — 비정상 대형 페이로드 차단.
_MAX_MSG_BYTES = 4096

# ── 연결 시도 rate-limit(★연결단 DB증폭 DoS 차단) ──
# 인바운드 메시지 rate-limit 은 accept 이후에만 동작한다. 그래서 유효 토큰 1개로 무작위 채널/
# 소켓에 무한 재연결하면, 매 연결마다 인증·인가·구독 DB 조회가 증폭돼 silent-DoS 가 된다.
# 이를 막기 위해 WS 진입부(★인증/인가 DB 조회 이전)에서 (토큰 sub 또는 client IP)별로 최근
# _CONN_WINDOW_SEC 초의 연결 타임스탬프를 슬라이딩윈도로 세고, 한도 초과 시 즉시 4429 로 끊는다.
# 인메모리(프로세스 로컬) 카운터라 정상 heartbeat 클라엔 영향 0.
# (분산 다중워커 전역 throttle 은 Redis 등 공유스토어 필요 = deploy-pending. 본 인메모리
#  카운터는 단일 워커 기준 연결 증폭을 막는다.)
_CONN_WINDOW_SEC = 10.0
_CONN_MAX = 20


class ConnThrottle:
    """슬라이딩윈도 연결 throttle(인스턴스별 인메모리 카운터).

    ★ws_routes·social 이 각자 별도 인스턴스를 둔다(엔드포인트별 격리 — 채널 WS 폭주가 소셜 WS
      카운터를 오염시키지 않음). 키 = 토큰 sub(우선) 또는 client IP.
    """

    def __init__(self, *, window_sec: float = _CONN_WINDOW_SEC, max_conn: int = _CONN_MAX) -> None:
        self._window_sec = window_sec
        self._max = max_conn
        # 키별 연결 타임스탬프 deque(슬라이딩윈도). 키 = 토큰 sub(우선) 또는 client IP.
        self._log: dict[str, deque[float]] = defaultdict(deque)

    def clear(self) -> None:
        """인메모리 카운터 초기화(테스트 간 누적 오탐 방지용)."""
        self._log.clear()

    def key_for(self, user_id: str | None, ws: WebSocket) -> str:
        """연결 throttle 키 — 인증된 토큰 sub(우선), 없으면 client IP. 둘 다 없으면 'unknown'.

        토큰 sub 우선: 동일 사용자의 무작위 채널/소켓 재연결 증폭을 사용자 단위로 묶어 막는다.
        """
        if user_id:
            return f"sub:{user_id}"
        client = getattr(ws, "client", None)
        host = getattr(client, "host", None) if client is not None else None
        return f"ip:{host}" if host else "unknown"

    def allowed(self, key: str, *, now: float | None = None) -> bool:
        """슬라이딩윈도 연결 throttle 판정. 최근 window_sec 초 내 연결이 max 이하면 허용.

        허용 시 현재 시각을 기록한다(거부 시엔 기록하지 않아 폭주 키가 윈도를 계속 밀어내지 않게 한다).
        ★인증/인가 DB 조회 이전에 호출해 연결단 DB 증폭을 차단한다.
        """
        t = time.monotonic() if now is None else now
        # ★메모리 누수 방지(defaultdict 무한증식 차단): 먼저 기존 deque 만 조회한다(.get).
        #   defaultdict[key] 로 바로 접근하면 처음 보는 키마다 빈 deque 가 생성·영구 잔존해
        #   distinct sub/IP 수만큼 dict 가 무한 누적된다. 윈도가 빈 키는 dict 에서 제거하고,
        #   새 기록이 필요할 때만 새 deque 를 dict 에 등록한다(활성 키만 보존).
        log = self._log.get(key)
        cutoff = t - self._window_sec
        if log is not None:
            # 윈도 밖(오래된) 타임스탬프 제거 — 슬라이딩윈도 유지.
            while log and log[0] <= cutoff:
                log.popleft()
            if not log:
                # 윈도가 완전히 비워진 키는 dict 에서 제거(빈 deque 잔존 방지). 아래에서 재등록 가능.
                self._log.pop(key, None)
                log = None
        if log is not None and len(log) >= self._max:
            # 한도 초과(윈도 가득) → 기록하지 않고 거부(폭주 키가 윈도를 계속 밀어내지 않게).
            return False
        # 허용 — 현재 시각 기록(키가 없으면 새 deque 를 dict 에 등록).
        if log is None:
            log = self._log[key]  # defaultdict 가 새 deque 생성·등록.
        log.append(t)
        return True


def authenticate_ws(token: str, *, require_access_only: bool = False) -> str | None:
    """WS 쿼리 토큰(JWT) 검증 → user_id. 실패(만료/위조/형식오류) 시 None.

    - require_access_only=False(채널 WS 기본): 플랫폼 access 토큰(type=access) 또는 현장
      세션토큰(scope=sales_site) 둘 중 하나라도 유효하면 허용.
    - require_access_only=True(소셜 WS): PUBLIC 컨텐츠라 전역 SSO access 토큰만 허용
      (현장 세션토큰은 거부 — get_current_user 와 동일 규칙).
    호출부가 None 이면 즉시 close(4401) 한다.
    """
    if not token:
        return None
    try:
        from jose import jwt

        from app.core.config import settings

        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except Exception:  # noqa: BLE001 - 만료/위조/형식오류 모두 인증 실패로 처리
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    kind = payload.get("type") or payload.get("token_type")
    scope = payload.get("scope")
    if require_access_only:
        # 소셜 WS: access 토큰만 허용(현장 세션토큰 거부).
        if kind != "access":
            return None
    else:
        # 채널 WS: access 토큰 또는 현장 세션토큰 허용.
        if kind != "access" and scope != "sales_site":
            return None
    return str(user_id)


class InboundLimiter:
    """인바운드 메시지 슬라이딩윈도 rate-limit + 바이트 크기캡 + 타입 화이트리스트(소켓당 1개).

    ★accept 이후 수신 루프에서 메시지마다 호출한다. 채널/소셜 양쪽 동일 계약:
      - over_rate(): 최근 window 초 메시지 수가 한도 초과면 True(호출부가 4429 close).
      - too_large(raw): 바이트 길이가 캡 초과면 True(호출부가 무시).
      - parse_allowed(raw, allowed_types): JSON dict 이고 type 이 화이트리스트면 dict 반환, 아니면 None.
    """

    def __init__(self, *, window_sec: float = _RATE_WINDOW_SEC, max_msgs: int = _RATE_MAX_MSGS,
                 max_bytes: int = _MAX_MSG_BYTES) -> None:
        self._window_sec = window_sec
        self._max = max_msgs
        self._max_bytes = max_bytes
        # 최근 window 초의 수신 타임스탬프(슬라이딩윈도).
        self._recv_log: deque[float] = deque()

    def over_rate(self, *, now: float | None = None) -> bool:
        """이번 수신을 카운트하고, 최근 window 초 메시지 수가 한도 초과면 True(플러딩 차단)."""
        t = time.monotonic() if now is None else now
        cutoff = t - self._window_sec
        while self._recv_log and self._recv_log[0] <= cutoff:
            self._recv_log.popleft()  # 윈도 밖(오래된) 수신 제거.
        self._recv_log.append(t)
        return len(self._recv_log) > self._max

    def too_large(self, raw: str) -> bool:
        """과도한 페이로드 차단 — ★바이트 길이로 판정한다. len(str)은 '문자수'라 멀티바이트
        한글(UTF-8 3바이트/자)이 실제 전송 바이트를 과소측정해 차단이 헐거워진다.
        """
        return len(raw.encode("utf-8")) > self._max_bytes

    def parse_allowed(self, raw: str, allowed_types: set[str]) -> dict | None:
        """허용 스키마만 수용 — 잘못된 JSON·비-dict·미허용 타입은 None(서버 상태 변경 없음)."""
        try:
            msg = json.loads(raw)
        except (ValueError, TypeError):
            return None
        if not isinstance(msg, dict):
            return None
        if msg.get("type") not in allowed_types:
            return None
        return msg
