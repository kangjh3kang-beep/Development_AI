"""sales 실시간 WebSocket — 단체톡/동호배치도 채널. main 에 직접 등록(/ws/sales/...).

★현장 격리(보안): 과거엔 인증/인가 없이 임의 channel_id 연결을 허용해, 타 현장 채널을
도청하거나 메시지를 주입할 수 있었다(현장격리 붕괴). 이를 막기 위해:
  0) ★연결 시도 자체를 (토큰 sub 또는 IP)별 슬라이딩윈도로 throttle 한다(★accept·인가 DB 조회
     모두 이전). 유효 토큰 1개로 board:{무작위} 무한 재연결→연결당 인가 DB 조회 증폭(silent-DoS)
     을 막는다. throttle 거부(4429)는 클라가 '코드'가 아니라 '백오프 재연결'로 대응하므로,
     전송계층이 pre-accept close 를 1006 으로 바꿔도 클라 동작이 동일해 accept 이전에 둬도 무방.
  1) 쿼리토큰(?token=) JWT 를 검증한다(플랫폼 access 토큰 또는 현장 세션토큰).
  2) 채널이 현장 스코프(board:{site_id})면, 그 토큰 사용자가 해당 현장의 멤버인지
     DB 로 인가한다(resolve_site_membership 단일 기준). 비멤버는 거부(4403).
  3) 인바운드 메시지는 허용 스키마(PING 소형 JSON)만 받고, 과도한 전송은 슬라이딩윈도 rate-limit
     으로 끊는다(메시지 주입/플러딩 방어).

★공용 하드닝(iter-7 — 전역전파규칙): 위 0)~3) 하드닝 로직(연결 throttle·인증·accept-then-close·
  인바운드 rate-limit·바이트 크기캡·타입 화이트리스트·close-code 계약)은 공용 모듈
  _ws_hardening 으로 추출했다. 채널 WS(여기)와 소셜 WS(social.social_ws)가 같은 헬퍼를 소비해
  동일클래스 결함의 재발을 막고 close-code(4401/4403/4429) 계약을 공유한다.

★accept-then-close(전송계층 갭 봉합 — iter-6): 인증(4401)/인가(4403) 거부는 반드시 ws.accept()
  이후에 close 해야 한다. accept 이전 close 는 uvicorn 0.42.0(websockets 16.0)이 handshake
  거부(HTTP 업그레이드 4xx)로 변환해 Close 프레임을 보내지 않으므로, 실브라우저는
  CloseEvent.code=1006 만 받고 4401/4403 분기(lib/unitBoardWs.ts)가 영구 미발화한다(배너/CTA/
  재연결중단 무력화). 그래서 throttle(4429)만 accept 이전에 두고, 인증/인가 거부는 accept 후
  close 로 코드를 그대로 전달한다. 권한 없는 연결은 accept 되더라도 채널 합류(ws_manager.connect)
  전에 닫히므로 도청/주입은 여전히 차단된다.

★backlog(iter-8+ 이연 — 추가구현 금지, 스파이럴 방지):
  - [MED] _conn_log 는 활성 키만 보존(드레인 시 제거)하나 burst 분산 공격 시 일시적으로 키가
    늘 수 있다 → LRU 캡(상한) 도입 검토.
  - [LOW] units_live 의 broadcast payload held_by 마스킹(개인정보 최소노출), 채널키 정규화 일원화.
  - [LOW] 멀티워커 전역 throttle(Redis 공유스토어) — 현재는 단일워커(uvicorn --workers 1) 전제.
"""

from __future__ import annotations

import contextlib
import logging
import uuid
from urllib.parse import unquote

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.api.endpoints.sales import _ws_hardening as _wsh
from app.api.endpoints.sales._ws_hardening import (
    WS_CLOSE_FORBIDDEN,
    WS_CLOSE_THROTTLED,
    WS_CLOSE_UNAUTHENTICATED,
    ConnThrottle,
    InboundLimiter,
    authenticate_ws,
)
from app.services.sales.mh.ws import ws_manager

ws_router = APIRouter()
logger = logging.getLogger(__name__)

# 클라이언트가 보낼 수 있는 메시지 타입 화이트리스트(채널은 broadcast 전용이라 매우 제한적).
# ★유일 클라(lib/unitBoardWs.ts)는 PING(heartbeat)만 보낸다. 미사용(dead) 'SUBSCRIBE' 는
#   공격면만 넓히므로 제외하고 {PING} 으로 협소화한다.
_ALLOWED_CLIENT_TYPES = {"PING"}

# ── 연결 throttle(공용 하드닝 인스턴스) ──
# 유효 토큰 1개로 board:{무작위} 채널에 무한 재연결하면, 매 연결마다 인가 DB 조회(bootstrap
# SET LOCAL 3회 + SalesSite SELECT + User SELECT + resolve_site_membership 의 조직 조회)가
# 증폭돼 silent-DoS 가 된다. 채널 WS 전용 throttle 인스턴스로 연결 폭주를 막는다.
_conn_throttle = ConnThrottle()
# ★호환: 통합테스트(test_sales_workspace_ws_integration)와 운영 디버깅이 모듈 속성 _conn_log
#   (키별 타임스탬프 dict)을 직접 초기화/조회한다. 인스턴스 내부 dict 를 그대로 노출해 .clear()
#   등 기존 호출이 그대로 동작하게 한다(공용화 후에도 외부 계약 무파괴).
_conn_log = _conn_throttle._log

# ── ★하위호환 얇은 재노출(공용화 후 외부 계약 무파괴) ──
# 공용 하드닝(_ws_hardening)으로 추출하기 전에는 아래 상수·함수가 이 모듈에 직접 있었고, 기존
# 단위테스트(test_sales_workspace_ws)와 운영 코드가 ws_routes.<이름> 으로 참조한다. 추출 후에도
# 동일 이름을 같은 throttle 인스턴스/헬퍼에 위임하는 얇은 별칭으로 재노출해 무회귀를 보장한다
# (단일 진실: 실제 로직·기본값은 _ws_hardening 한 곳, 여기선 위임/재노출만).
_RATE_WINDOW_SEC = _wsh._RATE_WINDOW_SEC
_RATE_MAX_MSGS = _wsh._RATE_MAX_MSGS
_MAX_MSG_BYTES = _wsh._MAX_MSG_BYTES
_CONN_WINDOW_SEC = _wsh._CONN_WINDOW_SEC
_CONN_MAX = _wsh._CONN_MAX


def _conn_throttle_key(user_id: str | None, ws: WebSocket) -> str:
    """[하위호환] 연결 throttle 키 산출 — 채널 WS 전용 throttle 인스턴스 위임."""
    return _conn_throttle.key_for(user_id, ws)


def _connection_allowed(key: str, *, now: float | None = None) -> bool:
    """[하위호환] 슬라이딩윈도 연결 throttle 판정 — 채널 WS 전용 throttle 인스턴스 위임."""
    return _conn_throttle.allowed(key, now=now)


def _authenticate_ws(token: str) -> str | None:
    """[하위호환] WS 토큰 검증(채널 WS 규칙: access 또는 현장 세션토큰) — 공용 헬퍼 위임."""
    return authenticate_ws(token)


def _site_id_from_channel(channel_id: str) -> str | None:
    """채널명에서 현장 스코프 site_id 를 추출. 'board:{site_id}' 형식이면 site_id, 아니면 None.

    None 이면 '현장 스코프가 아닌 채널' 로 보고 멤버십 인가를 건너뛴다(단, 인증은 항상 수행).

    ★URL 인코딩 정규화(멱등): 프론트가 채널명을 encodeURIComponent 로 인코딩하면 콜론이
      'board%3A...' 로 들어와 startswith('board:') 가 빗나가 '비현장 채널'로 오판→인가 누락
      위험이 있다. 그래서 진입부에서 unquote 로 1회 정규화한다(이미 디코드된 값은 그대로 =
      멱등). WS 백엔드(ASGI 서버)의 path 디코드 동작에 의존하지 않고 여기서 결정적으로 처리.
    """
    decoded = unquote(channel_id)
    if decoded.startswith("board:"):
        sid = decoded.split(":", 1)[1].strip()
        return sid or None
    return None


async def _authorize_site_channel(user_id: str, site_id: str) -> bool:
    """user_id 가 해당 현장(site_id)의 멤버(또는 폴백 권한자)인지 DB 로 인가한다.

    멤버십 판정은 비-WS 경로(deps_sales)와 동일한 공용 헬퍼 resolve_site_membership 를 쓴다
    (단일 기준 — 표시=적용 일관, 8h 권한지연 없이 최신 DB 멤버십만 신뢰).
    멤버/폴백이면 True, 아니면 False. 조회 실패는 fail-closed(False)로 거부한다.
    """
    try:
        from sqlalchemy import select

        from app.api.deps_sales import resolve_site_membership
        from app.core.database import async_session_factory
        from app.services.sales.sales_rls_bootstrap import bootstrap_superadmin_ctx
        from apps.api.database.models.sales.site_org import SalesSite
        from apps.api.database.models.user import User as DBUser

        async with async_session_factory() as db:
            # ★[RLS ctx 주입] SalesSite·SalesOrgNode 는 ENABLE+FORCE RLS 보호 테이블이다.
            #   bare 세션은 세션변수 미주입이라 운영 non-bypassrls role 에서 0행만 보여(fail-closed)
            #   정상 멤버를 4403 으로 오판→재연결 폭주(silent-DoS)한다. 그래서 인가 조회 직전에
            #   SUPERADMIN 부트스트랩 컨텍스트를 명시 주입해 두 테이블을 정상 조회한다(공용 헬퍼 재사용).
            await bootstrap_superadmin_ctx(db)
            # 현장 조회: site_id 는 UUID 또는 사람이 읽는 site_code 둘 다 허용(비-WS 경로와 동일).
            sid = site_id.strip()
            try:
                cond = SalesSite.id == uuid.UUID(sid)
            except (ValueError, AttributeError, TypeError):
                cond = SalesSite.site_code == sid
            site = (await db.execute(select(SalesSite).where(cond))).scalar_one_or_none()
            if site is None:
                return False  # 존재하지 않는 현장 → 거부.

            # ★User.id 는 UUID 컬럼이므로 토큰 sub(문자열)를 uuid.UUID 로 명시 변환해 비교한다
            #   (드라이버/컬럼 타입에 따른 암묵 캐스팅에 의존하지 않음 — 형식오류 sub 는 거부).
            try:
                user_uuid = uuid.UUID(user_id)
            except (ValueError, AttributeError, TypeError):
                return False  # 형식이 잘못된 user_id(sub) → 거부.
            user = (await db.execute(
                select(DBUser).where(DBUser.id == user_uuid, DBUser.is_active.is_(True))
            )).scalar_one_or_none()
            if user is None:
                return False  # 비활성/삭제 사용자 → 거부.

            membership = await resolve_site_membership(db, site, user)
            return membership is not None
    except Exception:  # noqa: BLE001 - 인가 조회 중 어떤 오류든 안전하게 거부(fail-closed).
        # ★분류 로깅(silent swallow 사유 구분): DB 장애·RLS 미주입 등 '조회 실패'로 인한 거부와
        #   '비멤버(정상 False)'를 운영에서 구분 가능하게 한다. 거부 동작 자체는 fail-closed 유지.
        logger.warning(
            "WS 현장 인가 조회 실패(fail-closed 거부) site_id=%s user_id=%s",
            site_id, user_id, exc_info=True,
        )
        return False


@ws_router.websocket("/ws/sales/{channel_id}")
async def channel_ws(ws: WebSocket, channel_id: str, token: str = Query(default="")):
    # ── 0) 연결 throttle(★accept 이전 유지·인증/인가 DB 조회 이전): 유효 토큰으로 board:{무작위}
    #   무한 재연결 → 매 연결마다 인가 DB 조회 증폭(SET LOCAL 3회+SalesSite/User SELECT+멤버십 org
    #   조회)이 silent-DoS 가 된다. 그래서 가장 앞단(handshake 비용 발생 전)에서 슬라이딩윈도로
    #   연결을 세고, 한도 초과 시 accept 도 DB 조회도 없이 즉시 4429 로 끊는다.
    #   ★throttle 만 accept 이전에 남기는 이유: pre-accept close 는 전송계층(uvicorn 0.42.0/
    #     websockets 16.0)에서 handshake 거부(HTTP 4xx)로 변환돼 Close 코드 프레임이 클라에
    #     전달되지 않는다. 하지만 throttle 의 클라 동작은 '4429 코드 분기'가 아니라 '백오프 재연결'
    #     이라, 브라우저가 4429 대신 1006(비정상 종료)을 받아도 동일하게 백오프로 재시도해 무방하다.
    #     (한편 인증/인가 거부 4401/4403 은 프론트가 '코드'로 영구거부를 판별해야 하므로 아래에서
    #      accept-then-close 로 전환한다.)
    #   ★연결 throttle 키는 토큰 sub 우선이다. accept 이전이라 토큰 검증을 먼저 수행하되, 검증
    #     실패(무효 토큰)면 user_id=None → IP/unknown 키로 throttle 한다(무효 토큰 연결 폭주도 차단).
    user_id = authenticate_ws(token)
    if not _conn_throttle.allowed(_conn_throttle.key_for(user_id, ws)):
        await ws.close(code=WS_CLOSE_THROTTLED)  # 연결 폭주 차단(accept/DB 조회 이전).
        return

    # ── 1) accept(★전송계층 갭 봉합): 인증/인가 거부 코드(4401/4403)를 클라에 코드 그대로 전달하려면
    #   반드시 accept(handshake 완료) 이후에 close 해야 한다. accept 이전 close 는 uvicorn 0.42.0
    #   (websockets 16.0)이 handshake 거부(HTTP 업그레이드 4xx)로 변환해 Close 프레임을 보내지
    #   않으므로 실브라우저는 CloseEvent.code=1006 만 받고 4401/4403 분기가 영구 미발화한다
    #   (배너/CTA/재연결중단 무력화). throttle 이 앞단에서 연결 폭주를 막으므로 accept 후 인증/인가
    #   비용은 제한된다.
    await ws.accept()

    # ── 2) 인증: 토큰 없으면/무효면 accept 후 close(4401) → 클라가 코드 4401 을 그대로 수신 ──
    if not user_id:
        await ws.close(code=WS_CLOSE_UNAUTHENTICATED)  # accept 후이므로 Close 코드가 그대로 전달됨.
        return

    # ── 3) 인가: 현장 스코프 채널(board:{site_id})은 멤버십 확인. 비멤버는 거부(4403) ──
    #   accept 후 close 라 4403 코드가 클라에 그대로 전달된다(타 현장 채널 도청/주입 차단).
    site_id = _site_id_from_channel(channel_id)
    if site_id is not None and not await _authorize_site_channel(user_id, site_id):
        await ws.close(code=WS_CLOSE_FORBIDDEN)  # 타 현장 채널 도청/주입 차단(코드 그대로 전달).
        return

    # 인증·인가 통과 후에만 채널에 합류한다.
    # ★이미 위에서 ws.accept() 했으므로, ws_manager.connect 는 이중 accept 하지 않도록 already_accepted
    #   힌트를 전달한다(connect 가 accept 를 호출하면 'WebSocket is not connected. Need to call accept'
    #   계약 위반/RuntimeError 가 난다).
    await ws_manager.connect(channel_id, ws, already_accepted=True)

    # ── 3) 메시지 스키마 검증 + rate-limit(주입/플러딩 방어) ──
    # ★구독 해제(유령소켓 방지)는 try/finally 로 단일화한다. rate-limit close(4429) 후 break,
    #   정상 close, WebSocketDisconnect, 예기치 못한 예외 — '모든 종료 경로'가 finally 를 거쳐
    #   ws_manager.disconnect 를 정확히 1회 호출하므로, 닫힌 소켓이 channels 에 잔존하지 않는다.
    #   (과거엔 break 가 예외가 아니라 두 except 모두 미발동→disconnect 미호출=유령소켓 누수였음.)
    # ★공용 InboundLimiter(슬라이딩윈도 rate-limit·바이트 크기캡·타입 화이트리스트) 소비.
    limiter = InboundLimiter()
    try:
        while True:
            raw = await ws.receive_text()
            # 최근 윈도 구간의 메시지 수 카운트 — 초과 시 연결 종료(플러딩 차단).
            if limiter.over_rate():
                await ws.close(code=WS_CLOSE_THROTTLED)
                break
            # 과도한 페이로드 차단(바이트 길이 기준 — 멀티바이트 한글 과소측정 방지).
            if limiter.too_large(raw):
                continue  # 비정상 대형 메시지는 무시(채널 broadcast 영향 없음).
            # 허용 스키마만 수용 — 잘못된 JSON·비-dict·미허용 타입은 무시(서버 상태 변경 없음).
            msg = limiter.parse_allowed(raw, _ALLOWED_CLIENT_TYPES)
            if msg is None:
                continue
            # PING heartbeat 응답(클라 재연결 판단 보조). 채널은 broadcast 전용이라 그 외 무동작.
            # 전송 실패(소켓 종료 중 등)는 무해 — 다음 루프/onclose 가 구독을 정리한다.
            if msg.get("type") == "PING":
                with contextlib.suppress(Exception):
                    await ws.send_json({"type": "PONG"})
    except WebSocketDisconnect:
        pass  # 정상 종료 — 구독 해제는 finally 에서 단일 수행.
    except Exception:  # noqa: BLE001 - 예기치 못한 오류도 finally 에서 반드시 구독 해제(유령소켓 방지).
        logger.warning("WS 채널 루프 예외 종료 channel_id=%s", channel_id, exc_info=True)
    finally:
        # ★모든 종료 경로 단일 구독 해제(break/예외/정상 close 무관). 멱등(disconnect 가 set.discard 류).
        ws_manager.disconnect(channel_id, ws)
