"""Phase1-H 소셜 네트워크 — 친구(소셜그래프)·단톡(그룹채팅, 영속/읽음/WS)·FCM 푸시·다중톡.

분양현장앱의 인맥기반 바이럴 레이어. 친구네트워크는 1-E 마켓(구인구직)과 연계되어
동료에게 모집공고를 홍보하는 바이럴 채널이 된다.

★★격리모델 — PUBLIC/전역(현장 RLS 적용 금지)
  friendships / chat_rooms / chat_members / chat_messages / push_devices 는 분양 sales
  테이블(site_id RLS 대상)과 달리 site RLS 를 걸지 않는다.
  - 테이블명에 sales_ / mh_ 접두를 쓰지 않으므로 sales_rls_bootstrap.py 의 동적
    대상조회(table LIKE 'sales\\_%' OR 'mh\\_%')에서 자동 제외된다(부트스트랩 목록 미추가).
  - 격리는 애플리케이션 계층에서 친구관계(accepted)·방 멤버십으로 엄격히 강제.
  - 차단(block) 시 상호 비노출. 방 멤버만 메시지 조회·발송.

인증
  PUBLIC 컨텐츠이므로 sales_ctx(현장 컨텍스트) 가 아니라 get_current_user(전역 SSO)를 쓴다.
  WebSocket 은 쿼리스트링 토큰(?token=)으로 JWT 검증 후 사용자 식별.

재사용(기존 무파괴)
  - 사용자        : public.users(id·email·name) + get_current_user
  - 이미지업로드  : 기존 /api/v1/uploads/image 로 업로드한 public URL 을 media_urls 로 전달
  - WS 매니저     : app.services.sales.mh.ws.WSManager 패턴(인프로세스, 단일워커 전제)
  - FCM/알림톡    : app.services.sales.mh.notify 의 firebase_admin/kakao 발송 패턴

신규 PUBLIC 테이블(_ensure, 멱등, gen_random_uuid 기본)
  friendships    : 소셜그래프(요청자→수신자, pending/accepted/blocked)
  chat_rooms     : 채팅방(direct/group, 현장연계 site_id 선택)
  chat_members   : 방 멤버십(owner/member, last_read_message_id)
  chat_messages  : 메시지 영속(text/image/system, media_urls[])
  push_devices   : FCM 디바이스 토큰(web/ios/android)

★★단일워커(uvicorn --workers 1) 전제 — 인프로세스 WS 매니저로 충분.
  worker>1 로 스케일아웃 시 룸 구독이 워커별로 분산되어 브로드캐스트 누락 발생.
  → Redis Pub/Sub 백플레인(채널=room_id) 도입 필요(아래 _SocialWSManager TODO 참조).
"""

import contextlib
import uuid
from datetime import UTC, datetime

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.endpoints.sales._ws_hardening import (
    WS_CLOSE_THROTTLED,
    WS_CLOSE_UNAUTHENTICATED,
    ConnThrottle,
    InboundLimiter,
    authenticate_ws,
)
from app.core.config_sales import sales_settings
from app.core.database import async_session_factory

social_router = APIRouter(prefix="/api/v1/social", tags=["sales-social"])

# ── 소셜 WS 인바운드 타입 화이트리스트 + 연결 throttle(공용 하드닝) ──
# 소셜 WS 클라(lib/socialWs.ts)는 PING(heartbeat)·SUBSCRIBE(방 구독)만 보낸다. 그 외 타입은
# 무시한다(공격면 협소화). 연결 throttle 은 채널 WS 와 분리된 전용 인스턴스(엔드포인트별 격리).
_SOCIAL_ALLOWED_CLIENT_TYPES = {"PING", "SUBSCRIBE"}
_social_conn_throttle = ConnThrottle()
# ★호환: 운영 디버깅/테스트가 모듈 속성으로 키별 타임스탬프 dict 를 직접 조회/초기화할 수 있게 노출.
_social_conn_log = _social_conn_throttle._log

# 광고성 다중톡(broadcast) 야간 발송 제한(개인정보보호법·정보통신망법 야간광고 가드)
_NIGHT_START_HOUR = 21  # 21:00 이후
_NIGHT_END_HOUR = 8     # 08:00 이전


# ── 멱등 테이블(_ensure) ─────────────────────────────────────────────────────
_FRIENDSHIPS_DDL = (
    "CREATE TABLE IF NOT EXISTS friendships ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  requester_user_id uuid NOT NULL,"
    "  addressee_user_id uuid NOT NULL,"
    "  status varchar(12) NOT NULL DEFAULT 'pending',"   # pending|accepted|blocked
    "  created_at timestamptz NOT NULL DEFAULT now(),"
    "  updated_at timestamptz NOT NULL DEFAULT now(),"
    "  CONSTRAINT uq_friendship UNIQUE (requester_user_id, addressee_user_id)"
    ")"
)
_CHAT_ROOMS_DDL = (
    "CREATE TABLE IF NOT EXISTS chat_rooms ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  kind varchar(12) NOT NULL DEFAULT 'group',"       # direct|group
    "  title varchar(200),"
    "  site_id uuid,"                                     # 현장연계(선택)
    "  created_by uuid NOT NULL,"
    "  created_at timestamptz NOT NULL DEFAULT now()"
    ")"
)
_CHAT_MEMBERS_DDL = (
    "CREATE TABLE IF NOT EXISTS chat_members ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  room_id uuid NOT NULL,"
    "  user_id uuid NOT NULL,"
    "  role varchar(12) NOT NULL DEFAULT 'member',"      # owner|member
    "  last_read_message_id uuid,"
    "  joined_at timestamptz NOT NULL DEFAULT now(),"
    "  CONSTRAINT uq_chat_member UNIQUE (room_id, user_id)"
    ")"
)
_CHAT_MESSAGES_DDL = (
    "CREATE TABLE IF NOT EXISTS chat_messages ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  room_id uuid NOT NULL,"
    "  sender_user_id uuid,"                             # system 메시지는 NULL 허용
    "  body text,"
    "  media_urls text[] DEFAULT '{}',"
    "  kind varchar(12) NOT NULL DEFAULT 'text',"        # text|image|system
    "  created_at timestamptz NOT NULL DEFAULT now()"
    ")"
)
_PUSH_DEVICES_DDL = (
    "CREATE TABLE IF NOT EXISTS push_devices ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  user_id uuid NOT NULL,"
    "  token text NOT NULL,"
    "  platform varchar(12) NOT NULL DEFAULT 'web',"     # web|ios|android
    "  created_at timestamptz NOT NULL DEFAULT now(),"
    "  CONSTRAINT uq_push_token UNIQUE (token)"
    ")"
)
_MESSAGES_INDEX_DDL = (
    "CREATE INDEX IF NOT EXISTS ix_chat_messages_room_created "
    "ON chat_messages (room_id, created_at DESC)"
)


async def _ensure(db: AsyncSession) -> None:
    """소셜 PUBLIC 테이블 멱등 생성(최초 호출 시 1회). 기존 sales/mh 테이블 무파괴.

    ★ 테이블명에 sales_/mh_ 접두를 쓰지 않으므로 RLS 부트스트랩 동적조회에서 자동 제외.
    """
    await db.execute(text(_FRIENDSHIPS_DDL))
    await db.execute(text(_CHAT_ROOMS_DDL))
    await db.execute(text(_CHAT_MEMBERS_DDL))
    await db.execute(text(_CHAT_MESSAGES_DDL))
    await db.execute(text(_PUSH_DEVICES_DDL))
    await db.execute(text(_MESSAGES_INDEX_DDL))


# ── 인프로세스 WS 매니저(룸별 구독) ──────────────────────────────────────────
class _SocialWSManager:
    """룸별 WebSocket 구독 매니저(인프로세스).

    ★★단일워커 전제. worker>1 시 룸 구독이 워커마다 분산되어 다른 워커가 처리한
    메시지 POST 의 브로드캐스트를 받지 못한다. 그 경우 Redis Pub/Sub 백플레인 필요:
      - 메시지 POST → redis.publish(f"room:{room_id}", payload)
      - 각 워커가 room 채널 구독 → 자기 워커의 로컬 소켓에만 fan-out
    현재는 Oracle 단일 컨테이너(uvicorn --workers 1)라 인프로세스로 충분.
    """

    def __init__(self) -> None:
        # user_id -> 연결된 소켓들(멀티탭/멀티디바이스 동시접속 허용)
        self.user_sockets: dict[str, set[WebSocket]] = {}
        # room_id -> 구독 user_id 들
        self.room_users: dict[str, set[str]] = {}

    async def connect(self, user_id: str, ws: WebSocket, already_accepted: bool = False) -> None:
        # already_accepted=True 면 호출부가 이미 ws.accept() 를 끝낸 상태(accept-then-close 인증
        # 게이트)다. 이때 다시 accept 하면 'WebSocket already accepted' 계약 위반/RuntimeError 가
        # 나므로 accept 를 건너뛴다. 기본값 False 라 기존 호출부(있다면)는 무영향.
        if not already_accepted:
            await ws.accept()
        self.user_sockets.setdefault(user_id, set()).add(ws)

    def disconnect(self, user_id: str, ws: WebSocket) -> None:
        socks = self.user_sockets.get(user_id)
        if socks:
            socks.discard(ws)
            if not socks:
                self.user_sockets.pop(user_id, None)

    def subscribe(self, room_id: str, user_id: str) -> None:
        self.room_users.setdefault(room_id, set()).add(user_id)

    def set_rooms(self, room_ids: list[str], user_id: str) -> None:
        for rid in room_ids:
            self.subscribe(rid, user_id)

    def is_online(self, user_id: str) -> bool:
        return bool(self.user_sockets.get(user_id))

    async def broadcast_room(self, room_id: str, member_user_ids: list[str], message: dict) -> set[str]:
        """방 구독자에게 fan-out. 전송 성공한 user_id 집합 반환(오프라인 판정용)."""
        delivered: set[str] = set()
        for uid in member_user_ids:
            socks = self.user_sockets.get(uid)
            if not socks:
                continue
            dead = []
            ok = False
            for ws in list(socks):
                try:
                    await ws.send_json(message)
                    ok = True
                except Exception:  # noqa: BLE001
                    dead.append(ws)
            for ws in dead:
                socks.discard(ws)
            if ok:
                delivered.add(uid)
        return delivered


social_ws_manager = _SocialWSManager()


# ── FCM/알림톡 발송(기존 notify 패턴 재사용, 키없으면 안전 폴백) ──────────────
async def _send_fcm_to_users(db: AsyncSession, user_ids: list[str], title: str, body: str) -> dict:
    """오프라인 수신자에게 FCM 푸시. 키 미설정 시 graceful skip(기록만)."""
    if not user_ids:
        return {"sent": 0, "skipped": 0, "failed": 0, "tokens": 0}
    rows = (await db.execute(
        text("SELECT user_id, token FROM push_devices WHERE user_id = ANY(:uids)"),
        {"uids": user_ids},
    )).mappings().all()
    sent = skipped = failed = 0
    creds = sales_settings.fcm_credentials_json
    messaging = None
    if creds and rows:
        try:
            from firebase_admin import credentials, get_app, initialize_app
            from firebase_admin import messaging as _messaging
            try:
                get_app()
            except ValueError:
                initialize_app(credentials.Certificate(creds))
            messaging = _messaging
        except Exception:  # noqa: BLE001
            messaging = None
    for r in rows:
        if messaging is None:
            skipped += 1
            continue
        try:
            messaging.send(messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                token=r["token"],
            ))
            sent += 1
        except Exception:  # noqa: BLE001
            failed += 1
    return {"sent": sent, "skipped": skipped, "failed": failed, "tokens": len(rows)}


# ── 친구(소셜그래프) 헬퍼 ────────────────────────────────────────────────────
async def _are_blocked(db: AsyncSession, a: str, b: str) -> bool:
    row = (await db.execute(text(
        "SELECT 1 FROM friendships WHERE status = 'blocked' AND "
        "((requester_user_id = :a AND addressee_user_id = :b) OR "
        " (requester_user_id = :b AND addressee_user_id = :a)) LIMIT 1"
    ), {"a": a, "b": b})).first()
    return row is not None


async def _are_friends(db: AsyncSession, a: str, b: str) -> bool:
    row = (await db.execute(text(
        "SELECT 1 FROM friendships WHERE status = 'accepted' AND "
        "((requester_user_id = :a AND addressee_user_id = :b) OR "
        " (requester_user_id = :b AND addressee_user_id = :a)) LIMIT 1"
    ), {"a": a, "b": b})).first()
    return row is not None


# ── 스키마 ───────────────────────────────────────────────────────────────────
class FriendRequest(BaseModel):
    addressee_user_id: uuid.UUID


class RoomCreate(BaseModel):
    kind: str = "group"                 # direct|group
    title: str | None = None
    site_id: uuid.UUID | None = None
    member_user_ids: list[uuid.UUID] = Field(default_factory=list)


class MessageCreate(BaseModel):
    body: str | None = None
    media_urls: list[str] = Field(default_factory=list)
    kind: str = "text"                  # text|image


class ReadMark(BaseModel):
    last_message_id: uuid.UUID


class InviteBody(BaseModel):
    user_ids: list[uuid.UUID]


class PushRegister(BaseModel):
    token: str
    platform: str = "web"               # web|ios|android


class BroadcastBody(BaseModel):
    user_ids: list[uuid.UUID] = Field(default_factory=list)
    room_id: uuid.UUID | None = None
    body: str
    consent: bool = False               # 광고성 발송 수신동의 확인
    force_night: bool = False           # (관리 목적) 야간가드 우회 — 비광고 한정


# ════════════════════════════════════ 친구 ════════════════════════════════════
@social_router.post("/friends/request")
async def friend_request(body: FriendRequest, db: AsyncSession = Depends(get_db),
                         user=Depends(get_current_user)) -> dict:
    await _ensure(db)
    me = str(user.id)
    target = str(body.addressee_user_id)
    if me == target:
        raise HTTPException(status_code=400, detail="자기 자신에게 친구요청 불가")
    if await _are_blocked(db, me, target):
        raise HTTPException(status_code=403, detail="차단된 관계입니다")
    # 역방향 요청이 이미 있으면 자동 수락(상호요청 = 친구확정)
    rev = (await db.execute(text(
        "SELECT id, status FROM friendships WHERE requester_user_id = :t AND addressee_user_id = :m"
    ), {"t": target, "m": me})).mappings().first()
    if rev and rev["status"] == "pending":
        await db.execute(text(
            "UPDATE friendships SET status = 'accepted', updated_at = now() WHERE id = :id"
        ), {"id": rev["id"]})
        await db.commit()
        return {"id": str(rev["id"]), "status": "accepted"}
    fid = uuid.uuid4()
    await db.execute(text(
        "INSERT INTO friendships (id, requester_user_id, addressee_user_id, status) "
        "VALUES (:id, :m, :t, 'pending') "
        "ON CONFLICT (requester_user_id, addressee_user_id) DO UPDATE "
        "SET status = CASE WHEN friendships.status = 'blocked' THEN 'blocked' ELSE 'pending' END, "
        "updated_at = now()"
    ), {"id": fid, "m": me, "t": target})
    await db.commit()
    row = (await db.execute(text(
        "SELECT id, status FROM friendships WHERE requester_user_id = :m AND addressee_user_id = :t"
    ), {"m": me, "t": target})).mappings().first()
    return {"id": str(row["id"]), "status": row["status"]}


async def _transition(db: AsyncSession, friendship_id: str, me: str, new_status: str,
                      allow_self_block: bool = False) -> dict:
    f = (await db.execute(text(
        "SELECT id, requester_user_id, addressee_user_id, status FROM friendships WHERE id = :id"
    ), {"id": friendship_id})).mappings().first()
    if not f:
        raise HTTPException(status_code=404, detail="친구요청을 찾을 수 없음")
    req = str(f["requester_user_id"])
    addr = str(f["addressee_user_id"])
    if me not in (req, addr):
        raise HTTPException(status_code=403, detail="권한이 없습니다")
    if new_status == "accepted":
        # 수신자만 수락 가능, pending 상태에서만
        if me != addr or f["status"] != "pending":
            raise HTTPException(status_code=400, detail="수락할 수 없는 요청 상태")
    await db.execute(text(
        "UPDATE friendships SET status = :s, updated_at = now() WHERE id = :id"
    ), {"s": new_status, "id": friendship_id})
    await db.commit()
    return {"id": friendship_id, "status": new_status}


@social_router.post("/friends/{friendship_id}/accept")
async def friend_accept(friendship_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                        user=Depends(get_current_user)) -> dict:
    await _ensure(db)
    return await _transition(db, str(friendship_id), str(user.id), "accepted")


@social_router.post("/friends/{friendship_id}/reject")
async def friend_reject(friendship_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                        user=Depends(get_current_user)) -> dict:
    await _ensure(db)
    # 거절 = 레코드 삭제(재요청 허용)
    f = (await db.execute(text(
        "SELECT requester_user_id, addressee_user_id FROM friendships WHERE id = :id"
    ), {"id": str(friendship_id)})).mappings().first()
    if not f:
        raise HTTPException(status_code=404, detail="친구요청을 찾을 수 없음")
    me = str(user.id)
    if me not in (str(f["requester_user_id"]), str(f["addressee_user_id"])):
        raise HTTPException(status_code=403, detail="권한이 없습니다")
    await db.execute(text("DELETE FROM friendships WHERE id = :id AND status != 'blocked'"),
                     {"id": str(friendship_id)})
    await db.commit()
    return {"id": str(friendship_id), "status": "rejected"}


@social_router.post("/friends/{friendship_id}/block")
async def friend_block(friendship_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                       user=Depends(get_current_user)) -> dict:
    await _ensure(db)
    return await _transition(db, str(friendship_id), str(user.id), "blocked", allow_self_block=True)


@social_router.get("/friends")
async def list_friends(status: str | None = Query(default=None),
                       db: AsyncSession = Depends(get_db),
                       user=Depends(get_current_user)) -> dict:
    await _ensure(db)
    me = str(user.id)
    params: dict = {"me": me}
    status_filter = ""
    if status in ("pending", "accepted", "blocked"):
        status_filter = " AND f.status = :st"
        params["st"] = status
    rows = (await db.execute(text(
        "SELECT f.id, f.requester_user_id, f.addressee_user_id, f.status, f.created_at, "
        "  CASE WHEN f.requester_user_id = :me THEN f.addressee_user_id "
        "       ELSE f.requester_user_id END AS other_id, "
        "  CASE WHEN f.requester_user_id = :me THEN 'outgoing' ELSE 'incoming' END AS direction, "
        "  u.name AS other_name "
        "FROM friendships f "
        "JOIN users u ON u.id = (CASE WHEN f.requester_user_id = :me "
        "  THEN f.addressee_user_id ELSE f.requester_user_id END) "
        "WHERE (f.requester_user_id = :me OR f.addressee_user_id = :me)" + status_filter +
        " ORDER BY f.updated_at DESC"
    ), params)).mappings().all()
    return {"friends": [{
        "friendship_id": str(r["id"]),
        "user_id": str(r["other_id"]),
        "name": r["other_name"],
        "status": r["status"],
        "direction": r["direction"],
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
    } for r in rows]}


@social_router.get("/friends/search")
async def search_users(q: str = Query(min_length=2),
                       db: AsyncSession = Depends(get_db),
                       user=Depends(get_current_user)) -> dict:
    """사용자 검색 — 이름만 노출, 연락처/이메일 비노출. 차단관계 상호 제외."""
    await _ensure(db)
    me = str(user.id)
    rows = (await db.execute(text(
        "SELECT u.id, u.name FROM users u "
        "WHERE u.is_active = true AND u.id != :me AND u.name ILIKE :q "
        "AND NOT EXISTS (SELECT 1 FROM friendships b WHERE b.status = 'blocked' AND "
        "  ((b.requester_user_id = :me AND b.addressee_user_id = u.id) OR "
        "   (b.requester_user_id = u.id AND b.addressee_user_id = :me))) "
        "ORDER BY u.name LIMIT 20"
    ), {"me": me, "q": f"%{q}%"})).mappings().all()
    results = []
    for r in rows:
        uid = str(r["id"])
        f = (await db.execute(text(
            "SELECT status, requester_user_id FROM friendships WHERE "
            "(requester_user_id = :me AND addressee_user_id = :u) OR "
            "(requester_user_id = :u AND addressee_user_id = :me) LIMIT 1"
        ), {"me": me, "u": uid})).mappings().first()
        rel = "none"
        if f:
            if f["status"] == "accepted":
                rel = "friend"
            elif f["status"] == "pending":
                rel = "outgoing" if str(f["requester_user_id"]) == me else "incoming"
        # 연락처/이메일은 응답에 포함하지 않음(이름·관계만)
        results.append({"user_id": uid, "name": r["name"], "relation": rel})
    return {"results": results}


# ════════════════════════════════════ 단톡 ════════════════════════════════════
async def _member_ids(db: AsyncSession, room_id: str) -> list[str]:
    rows = (await db.execute(text(
        "SELECT user_id FROM chat_members WHERE room_id = :r"
    ), {"r": room_id})).scalars().all()
    return [str(x) for x in rows]


async def _require_member(db: AsyncSession, room_id: str, user_id: str) -> dict:
    m = (await db.execute(text(
        "SELECT role FROM chat_members WHERE room_id = :r AND user_id = :u"
    ), {"r": room_id, "u": user_id})).mappings().first()
    if not m:
        raise HTTPException(status_code=403, detail="방 멤버만 접근할 수 있습니다")
    return dict(m)


@social_router.post("/rooms")
async def create_room(body: RoomCreate, db: AsyncSession = Depends(get_db),
                      user=Depends(get_current_user)) -> dict:
    await _ensure(db)
    me = str(user.id)
    members = {str(x) for x in body.member_user_ids}
    members.add(me)
    if body.kind not in ("direct", "group"):
        raise HTTPException(status_code=400, detail="kind는 direct|group")
    # 차단관계 멤버 제외(상호 비노출)
    for other in list(members):
        if other != me and await _are_blocked(db, me, other):
            raise HTTPException(status_code=403, detail="차단된 사용자는 초대할 수 없습니다")
    rid = uuid.uuid4()
    await db.execute(text(
        "INSERT INTO chat_rooms (id, kind, title, site_id, created_by) "
        "VALUES (:id, :k, :t, :s, :by)"
    ), {"id": rid, "k": body.kind, "t": body.title, "s": body.site_id, "by": me})
    for uid in members:
        await db.execute(text(
            "INSERT INTO chat_members (id, room_id, user_id, role) VALUES (:id, :r, :u, :role) "
            "ON CONFLICT (room_id, user_id) DO NOTHING"
        ), {"id": uuid.uuid4(), "r": rid, "u": uid, "role": "owner" if uid == me else "member"})
    await db.commit()
    return {"room_id": str(rid), "kind": body.kind, "title": body.title,
            "member_user_ids": sorted(members)}


@social_router.get("/rooms")
async def list_rooms(db: AsyncSession = Depends(get_db),
                     user=Depends(get_current_user)) -> dict:
    await _ensure(db)
    me = str(user.id)
    rows = (await db.execute(text(
        "SELECT r.id, r.kind, r.title, r.site_id, r.created_at, cm.last_read_message_id, "
        "  (SELECT row_to_json(lm) FROM (SELECT m.id, m.body, m.kind, m.sender_user_id, m.created_at "
        "     FROM chat_messages m WHERE m.room_id = r.id ORDER BY m.created_at DESC LIMIT 1) lm) AS last_message, "
        "  (SELECT count(*) FROM chat_messages m2 WHERE m2.room_id = r.id "
        "     AND (cm.last_read_message_id IS NULL OR m2.created_at > "
        "          (SELECT created_at FROM chat_messages WHERE id = cm.last_read_message_id)) "
        "     AND m2.sender_user_id IS DISTINCT FROM :me) AS unread_count "
        "FROM chat_members cm JOIN chat_rooms r ON r.id = cm.room_id "
        "WHERE cm.user_id = :me "
        "ORDER BY (SELECT max(created_at) FROM chat_messages mm WHERE mm.room_id = r.id) DESC NULLS LAST, "
        "  r.created_at DESC"
    ), {"me": me})).mappings().all()
    out = []
    for r in rows:
        out.append({
            "room_id": str(r["id"]),
            "kind": r["kind"],
            "title": r["title"],
            "site_id": str(r["site_id"]) if r["site_id"] else None,
            "last_read_message_id": str(r["last_read_message_id"]) if r["last_read_message_id"] else None,
            "last_message": r["last_message"],
            "unread_count": int(r["unread_count"] or 0),
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        })
    return {"rooms": out}


@social_router.get("/rooms/{room_id}/messages")
async def list_messages(room_id: uuid.UUID, before: str | None = Query(default=None),
                        limit: int = Query(default=30, ge=1, le=100),
                        db: AsyncSession = Depends(get_db),
                        user=Depends(get_current_user)) -> dict:
    await _ensure(db)
    await _require_member(db, str(room_id), str(user.id))
    params: dict = {"r": str(room_id), "lim": limit}
    cursor = ""
    if before:
        cursor = (" AND created_at < (SELECT created_at FROM chat_messages WHERE id = :before)")
        params["before"] = before
    rows = (await db.execute(text(
        "SELECT id, room_id, sender_user_id, body, media_urls, kind, created_at "
        "FROM chat_messages WHERE room_id = :r" + cursor +
        " ORDER BY created_at DESC LIMIT :lim"
    ), params)).mappings().all()
    msgs = [{
        "id": str(r["id"]),
        "room_id": str(r["room_id"]),
        "sender_user_id": str(r["sender_user_id"]) if r["sender_user_id"] else None,
        "body": r["body"],
        "media_urls": list(r["media_urls"] or []),
        "kind": r["kind"],
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
    } for r in rows]
    msgs.reverse()  # 오래된→최신 순으로 반환(채팅 렌더 순서)
    next_before = msgs[0]["id"] if (msgs and len(rows) == limit) else None
    return {"messages": msgs, "next_before": next_before}


@social_router.post("/rooms/{room_id}/messages")
async def send_message(room_id: uuid.UUID, body: MessageCreate, db: AsyncSession = Depends(get_db),
                       user=Depends(get_current_user)) -> dict:
    await _ensure(db)
    me = str(user.id)
    await _require_member(db, str(room_id), me)
    if not body.body and not body.media_urls:
        raise HTTPException(status_code=400, detail="본문 또는 미디어가 필요합니다")
    kind = "image" if (body.media_urls and not body.body) else body.kind
    if kind not in ("text", "image"):
        kind = "text"
    mid = uuid.uuid4()
    now = datetime.now(UTC)
    await db.execute(text(
        "INSERT INTO chat_messages (id, room_id, sender_user_id, body, media_urls, kind, created_at) "
        "VALUES (:id, :r, :s, :b, :media, :k, :ts)"
    ), {"id": mid, "r": str(room_id), "s": me, "b": body.body,
        "media": body.media_urls, "k": kind, "ts": now})
    await db.commit()
    payload = {
        "type": "MESSAGE",
        "room_id": str(room_id),
        "message": {
            "id": str(mid),
            "room_id": str(room_id),
            "sender_user_id": me,
            "body": body.body,
            "media_urls": body.media_urls,
            "kind": kind,
            "created_at": now.isoformat(),
        },
    }
    members = await _member_ids(db, str(room_id))
    # WS 브로드캐스트(접속자) → delivered 반환, 미접속자(오프라인) 차집합에 FCM 푸시
    delivered = await social_ws_manager.broadcast_room(str(room_id), members, payload)
    offline = [u for u in members if u != me and u not in delivered]
    sender_name = (await db.execute(text("SELECT name FROM users WHERE id = :id"),
                                    {"id": me})).scalar_one_or_none() or "메시지"
    push = await _send_fcm_to_users(db, offline,
                                    title=sender_name,
                                    body=(body.body or "[사진]")[:120])
    return {"message_id": str(mid), "delivered_online": sorted(delivered), "push": push}


@social_router.post("/rooms/{room_id}/read")
async def mark_read(room_id: uuid.UUID, body: ReadMark, db: AsyncSession = Depends(get_db),
                    user=Depends(get_current_user)) -> dict:
    await _ensure(db)
    me = str(user.id)
    await _require_member(db, str(room_id), me)
    # 메시지가 해당 방 소속인지 확인(타방 메시지 ID 주입 방지)
    ok = (await db.execute(text(
        "SELECT 1 FROM chat_messages WHERE id = :m AND room_id = :r"
    ), {"m": str(body.last_message_id), "r": str(room_id)})).first()
    if not ok:
        raise HTTPException(status_code=400, detail="해당 방의 메시지가 아닙니다")
    await db.execute(text(
        "UPDATE chat_members SET last_read_message_id = :m WHERE room_id = :r AND user_id = :u"
    ), {"m": str(body.last_message_id), "r": str(room_id), "u": me})
    await db.commit()
    return {"room_id": str(room_id), "last_read_message_id": str(body.last_message_id)}


@social_router.post("/rooms/{room_id}/invite")
async def invite_members(room_id: uuid.UUID, body: InviteBody, db: AsyncSession = Depends(get_db),
                         user=Depends(get_current_user)) -> dict:
    await _ensure(db)
    me = str(user.id)
    await _require_member(db, str(room_id), me)
    added = []
    for uid in body.user_ids:
        u = str(uid)
        if u == me or await _are_blocked(db, me, u):
            continue
        res = await db.execute(text(
            "INSERT INTO chat_members (id, room_id, user_id, role) VALUES (:id, :r, :u, 'member') "
            "ON CONFLICT (room_id, user_id) DO NOTHING RETURNING user_id"
        ), {"id": uuid.uuid4(), "r": str(room_id), "u": u})
        if res.first():
            added.append(u)
    if added:
        # system 메시지로 입장 알림(영속 + 브로드캐스트)
        sid = uuid.uuid4()
        now = datetime.now(UTC)
        await db.execute(text(
            "INSERT INTO chat_messages (id, room_id, sender_user_id, body, kind, created_at) "
            "VALUES (:id, :r, NULL, :b, 'system', :ts)"
        ), {"id": sid, "r": str(room_id), "b": f"{len(added)}명이 초대되었습니다", "ts": now})
        await db.commit()
        members = await _member_ids(db, str(room_id))
        await social_ws_manager.broadcast_room(str(room_id), members, {
            "type": "SYSTEM", "room_id": str(room_id),
            "message": {"id": str(sid), "kind": "system",
                        "body": f"{len(added)}명이 초대되었습니다",
                        "created_at": now.isoformat()},
        })
    else:
        await db.commit()
    return {"room_id": str(room_id), "added_user_ids": added}


# ════════════════════════════════════ 푸시 ════════════════════════════════════
@social_router.post("/push/register")
async def register_push(body: PushRegister, db: AsyncSession = Depends(get_db),
                        user=Depends(get_current_user)) -> dict:
    await _ensure(db)
    if body.platform not in ("web", "ios", "android"):
        raise HTTPException(status_code=400, detail="platform은 web|ios|android")
    await db.execute(text(
        "INSERT INTO push_devices (id, user_id, token, platform) VALUES (:id, :u, :tok, :p) "
        "ON CONFLICT (token) DO UPDATE SET user_id = :u, platform = :p"
    ), {"id": uuid.uuid4(), "u": str(user.id), "tok": body.token, "p": body.platform})
    await db.commit()
    return {"registered": True, "platform": body.platform}


# ═══════════════════════════════════ 다중톡 ═══════════════════════════════════
@social_router.post("/broadcast")
async def broadcast(body: BroadcastBody, db: AsyncSession = Depends(get_db),
                    user=Depends(get_current_user)) -> dict:
    """알림톡 bulk 다중톡. 광고성 발송 = 수신동의 + 야간(21~08시) 제한 가드."""
    await _ensure(db)
    me = str(user.id)
    # 대상 산출: room_id 우선(멤버), 아니면 user_ids(친구 한정 — 무단발송 방지)
    targets: list[str] = []
    if body.room_id:
        await _require_member(db, str(body.room_id), me)
        targets = [u for u in await _member_ids(db, str(body.room_id)) if u != me]
    elif body.user_ids:
        for uid in body.user_ids:
            u = str(uid)
            if u == me:
                continue
            if not await _are_friends(db, me, u):
                raise HTTPException(status_code=403, detail="친구가 아닌 사용자에게는 발송할 수 없습니다")
            if await _are_blocked(db, me, u):
                continue
            targets.append(u)
    else:
        raise HTTPException(status_code=400, detail="user_ids 또는 room_id가 필요합니다")
    if not targets:
        raise HTTPException(status_code=400, detail="발송 대상이 없습니다")
    # 광고성 발송 동의·야간 가드
    if not body.consent:
        raise HTTPException(status_code=400, detail="수신동의(consent) 확인이 필요합니다")
    hour = datetime.now(UTC).astimezone().hour
    is_night = hour >= _NIGHT_START_HOUR or hour < _NIGHT_END_HOUR
    if is_night and not body.force_night:
        raise HTTPException(status_code=403, detail="야간(21~08시) 광고성 발송은 제한됩니다")
    # 알림톡 bulk — 키 미설정 시 graceful skip(notify 패턴). 실연동은 운영 키 주입 시 활성.
    delivered_count = 0
    skipped = True
    if sales_settings.kakao_biz_key:
        try:
            import httpx
            phones = (await db.execute(text(
                "SELECT token FROM push_devices WHERE user_id = ANY(:uids)"
            ), {"uids": targets})).scalars().all()
            async with httpx.AsyncClient(timeout=10) as cli:
                for tok in phones:
                    await cli.post(
                        "https://kakaoapi.example/v2/sender/send",
                        headers={"Authorization": f"Bearer {sales_settings.kakao_biz_key}"},
                        json={"senderKey": sales_settings.kakao_sender_key, "to": tok,
                              "templateCode": "SOCIAL_BROADCAST", "text": body.body},
                    )
                    delivered_count += 1
            skipped = False
        except Exception:  # noqa: BLE001
            skipped = True
    # 동시에 앱푸시(FCM)로도 도달(접속 무관)
    push = await _send_fcm_to_users(db, targets, title="알림", body=body.body[:120])
    return {"targets": len(targets), "alimtalk_sent": delivered_count,
            "alimtalk_skipped": skipped, "push": push}


# ═══════════════════════════════════ WebSocket ════════════════════════════════
@social_router.websocket("/ws")
async def social_ws(ws: WebSocket, token: str = Query(...)):
    """소셜 실시간 WS — 토큰 인증 후 내 방 전부 구독. 메시지 POST 시 룸 구독자에게 push.

    ★공용 하드닝(iter-7 — 채널 WS 와 동일 계약): 연결 throttle(4429)·accept-then-close 인증
      거부(4401)·인바운드 슬라이딩윈도 rate-limit(4429)·바이트 크기캡·타입 화이트리스트
      ({PING,SUBSCRIBE})를 _ws_hardening 공용 헬퍼로 적용한다. close-code 의미는 채널 WS 와
      동일(SSOT)이라 프론트(socialWs.ts) 재연결 분기가 일관된다.

    ★★단일워커 전제. worker>1 시 Redis Pub/Sub 백플레인 필요(상단 _SocialWSManager 주석).
    """
    # ── 0) 연결 throttle(★accept·인증/DB 조회 이전): 유효 토큰 1개로 무한 재연결 → 매 연결마다
    #   인증 + 내 방 구독 DB 조회(_ensure + chat_members SELECT)가 증폭돼 silent-DoS 가 된다.
    #   가장 앞단에서 슬라이딩윈도로 연결을 세고, 한도 초과 시 accept/DB 조회 없이 즉시 4429 로 끊는다.
    #   ★throttle 만 accept 이전: pre-accept close 는 전송계층(uvicorn)에서 1006 으로 변환되나,
    #     throttle 클라 동작은 '백오프 재연결'이라 1006 을 받아도 동일해 무방하다(아래 인증 거부는
    #     accept-then-close 로 4401 코드를 그대로 전달).
    #   ★키는 토큰 sub 우선. 무효 토큰이면 user_id=None → IP/unknown 키로 throttle(무효 토큰 폭주도 차단).
    user_id = authenticate_ws(token, require_access_only=True)
    if not _social_conn_throttle.allowed(_social_conn_throttle.key_for(user_id, ws)):
        await ws.close(code=WS_CLOSE_THROTTLED)  # 연결 폭주 차단(accept/DB 조회 이전).
        return

    # ── 1) accept(★전송계층 갭 봉합): 인증 거부 코드(4401)를 클라에 코드 그대로 전달하려면 반드시
    #   accept(handshake 완료) 이후에 close 해야 한다. accept 이전 close 는 uvicorn 0.42.0
    #   (websockets 16.0)이 handshake 거부(HTTP 4xx)로 변환해 Close 프레임을 보내지 않으므로
    #   실브라우저는 1006 만 받고 socialWs.ts 의 4401 분기가 미발화한다. throttle 이 앞단에서
    #   연결 폭주를 막으므로 accept 후 인증 비용은 제한된다.
    await ws.accept()

    # ── 2) 인증: 토큰 없으면/무효면 accept 후 close(4401) → 클라가 코드 4401 을 그대로 수신 ──
    if not user_id:
        await ws.close(code=WS_CLOSE_UNAUTHENTICATED)  # accept 후이므로 Close 코드가 그대로 전달됨.
        return

    # 인증 통과 후에만 소켓 등록(이미 accept 했으므로 already_accepted=True 로 이중 accept 방지).
    await social_ws_manager.connect(user_id, ws, already_accepted=True)
    # ── 3) 인바운드 rate-limit + 바이트 크기캡 + 타입 화이트리스트(주입/플러딩 방어) ──
    # ★소켓 해제(유령소켓 방지)는 try/finally 로 단일화한다. rate-limit close(4429) 후 break,
    #   정상 close, WebSocketDisconnect, 예기치 못한 예외 — 모든 종료 경로가 finally 를 거쳐
    #   disconnect 를 정확히 1회 호출한다.
    limiter = InboundLimiter()
    try:
        # 내 방 전체 구독 등록(메시지 라우팅용)
        async with async_session_factory() as db:
            await _ensure(db)
            rooms = (await db.execute(text(
                "SELECT room_id FROM chat_members WHERE user_id = :u"
            ), {"u": user_id})).scalars().all()
        social_ws_manager.set_rooms([str(r) for r in rooms], user_id)
        await ws.send_json({"type": "READY", "rooms": [str(r) for r in rooms]})
        while True:
            # 클라이언트 핑/구독갱신 수신(서버→클라 push 가 주, 클라 메시지는 PING·SUBSCRIBE 만).
            # ★receive_json 대신 receive_text 로 받아 바이트 크기캡을 먼저 적용한다(대형 페이로드 차단).
            raw = await ws.receive_text()
            # 최근 윈도 구간 메시지 수 초과 시 연결 종료(플러딩 차단).
            if limiter.over_rate():
                await ws.close(code=WS_CLOSE_THROTTLED)
                break
            # 과도한 페이로드 차단(바이트 길이 기준 — 멀티바이트 한글 과소측정 방지).
            if limiter.too_large(raw):
                continue  # 비정상 대형 메시지는 무시.
            # 허용 스키마만 수용 — 잘못된 JSON·비-dict·미허용 타입은 무시(서버 상태 변경 없음).
            msg = limiter.parse_allowed(raw, _SOCIAL_ALLOWED_CLIENT_TYPES)
            if msg is None:
                continue
            mtype = msg.get("type")
            if mtype == "SUBSCRIBE" and msg.get("room_id"):
                social_ws_manager.subscribe(str(msg["room_id"]), user_id)
            elif mtype == "PING":
                # 전송 실패(소켓 종료 중 등)는 무해 — 다음 루프/onclose 가 정리한다.
                with contextlib.suppress(Exception):
                    await ws.send_json({"type": "PONG"})
    except WebSocketDisconnect:
        pass  # 정상 종료 — 소켓 해제는 finally 에서 단일 수행.
    except Exception:  # noqa: BLE001 - 예기치 못한 오류도 finally 에서 반드시 소켓 해제(유령소켓 방지).
        pass
    finally:
        # ★모든 종료 경로 단일 소켓 해제(break/예외/정상 close 무관). 멱등(disconnect 가 set.discard 류).
        social_ws_manager.disconnect(user_id, ws)
