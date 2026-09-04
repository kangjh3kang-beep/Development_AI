"""Idempotency-Key — 뮤테이팅 커맨드 재전송 안전화(WP-L · A3).

이 파일이 푸는 문제(쉬운 설명):
- 네트워크가 끊겨 클라이언트가 같은 요청(예: 설계승인·제출번들 산출)을 두 번 보내면, 서버가
  두 번 실행해 이중 부작용·이중 과금이 날 수 있다. Idempotency-Key는 '이 요청은 이미 처리했다'를
  키로 기억해, **같은 키 재전송 = 처음 응답을 그대로 돌려주는(재실행 없이)** 계약을 만든다.
- 본 모듈은 응답을 키로 기억(저장)하고 재전송 시 되돌려주는(재생) 얇은 저장소다.

★영속 계약(WP-I outbox·WP-E design_run_store·WP-H 선례 동일 — 절대 제약):
- alembic 신규 헤드 없음. CREATE TABLE IF NOT EXISTS 기반 schema_guard(멱등·lazy·부팅안전)로만
  테이블을 보장한다(WP-M이 마이그레이션 WP 완료 후 5→1 병합을 최후단 격리 실행 — 그 전 헤드 분기 금지).
- 원장(analysis_ledger) 무접촉.

★멱등 계약(게이트):
- 같은 (tenant·endpoint·key) + 같은 요청지문(request_hash) → 저장된 응답을 그대로 재생(state=replay).
- 같은 키인데 요청지문이 다르면(다른 페이로드로 같은 키 재사용) → state=conflict → 호출부가
  422로 정직하게 거부한다(RFC 9457 problem+json). '한 키 = 한 요청'의 오사용을 무음 통과시키지 않는다.
- 저장은 INSERT ON CONFLICT DO NOTHING(경쟁 시 최초 1행만 확정 — 두 요청이 동시 실행돼도 첫 응답이 정본).

★테넌트 격리: 유니크 키는 (COALESCE(tenant_id,'')·endpoint·idempotency_key). 테넌트별로 키 공간이
  분리돼, 한 테넌트의 키가 다른 테넌트의 응답을 재생하지 않는다.

★best-effort: DB 장애 시 idempotency는 fail-open(기억 못 함=일반 실행)한다 — 저장 실패가 커맨드
  자체를 막지 않는다(WP-E persist 선례). 저장이 되면 재전송 안전이 활성화된다.
"""
from __future__ import annotations

import base64
import contextlib
from dataclasses import dataclass
from typing import Any

import structlog

from app.services.cad.provenance import compute_input_hash

logger = structlog.get_logger(__name__)

# 저장할 응답 본문 상한(바이트) — 이보다 크면 본문은 저장하지 않고 메타만 남긴다(대형 zip DB 적재 방지).
# 이 경우 재생은 본문이 없어(None) 호출부가 결정적 재계산으로 대체한다(deterministic 산출이라 동일).
_MAX_STORED_BODY_BYTES = 8 * 1024 * 1024  # 8MB
# Idempotency-Key 헤더 값 상한(과대입력 방어).
_MAX_KEY_LEN = 255

# lookup 상태.
STATE_MISS = "miss"        # 처음 보는 키 — 실행하고 저장하라.
STATE_REPLAY = "replay"    # 같은 키+같은 요청 — 저장된 응답을 그대로 돌려주라.
STATE_CONFLICT = "conflict"  # 같은 키, 다른 요청 — 422로 거부하라(키 오사용).


def normalize_key(raw: str | None) -> str | None:
    """Idempotency-Key 헤더 값을 정규화한다(공백 strip·길이 상한). 비면 None(=키 없음)."""
    if not raw:
        return None
    k = str(raw).strip()
    if not k:
        return None
    return k[:_MAX_KEY_LEN]


def compute_request_hash(payload: Any) -> str:
    """요청 페이로드의 결정적 지문(⑦ compute_input_hash 재사용 — 키순서·int/float 정규화).

    같은 논리 요청이면 같은 지문 → 재전송 판정의 기준. dict가 아니면 감싸서 정규화한다.
    """
    if isinstance(payload, dict):
        return compute_input_hash(payload)
    return compute_input_hash({"_payload": payload})


@dataclass
class StoredResponse:
    """저장된(또는 재생할) 응답 1건 — 상태·미디어타입·본문(bytes)·run_id."""

    response_status: int
    response_media_type: str
    body: bytes | None
    run_id: str | None = None

    def to_response(self):
        """FastAPI Response로 복원한다. 본문이 없으면(대형이라 미저장) None을 준다(호출부 재계산)."""
        if self.body is None:
            return None
        from fastapi.responses import Response

        return Response(
            content=self.body,
            status_code=int(self.response_status),
            media_type=self.response_media_type,
        )


@dataclass
class IdempotencyLookup:
    """lookup 결과 — state(miss/replay/conflict)와 재생할 응답(replay일 때만)."""

    state: str
    stored: StoredResponse | None = None


# ── 영속(schema_guard — CREATE TABLE IF NOT EXISTS, alembic 헤드 없음) ─────────
_SCHEMA_READY = False

_IDEMPOTENCY_DDL = (
    "CREATE TABLE IF NOT EXISTS idempotency_key ("
    "  id bigserial PRIMARY KEY,"
    "  idempotency_key text NOT NULL,"
    "  tenant_id text,"
    "  endpoint text NOT NULL,"
    "  request_hash text NOT NULL,"
    "  response_status integer NOT NULL,"
    "  response_media_type text NOT NULL DEFAULT 'application/json',"
    "  response_body_b64 text,"           # 응답 본문 base64(대형이면 NULL — 메타만)
    "  run_id text,"
    "  created_at timestamptz NOT NULL DEFAULT now()"
    ")"
)
_INDEXES = (
    # ★테넌트 스코프 유니크 — NULL 테넌트도 ''로 접어 '한 키 1행'을 보장(경쟁 시 최초 확정).
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_idempotency_scope "
    "ON idempotency_key (COALESCE(tenant_id, ''), endpoint, idempotency_key)",
)


async def ensure_schema(db: Any, force: bool = False) -> bool:
    """idempotency_key 테이블·인덱스를 멱등 보장. 실패는 graceful(rollback 후 False)."""
    global _SCHEMA_READY
    if _SCHEMA_READY and not force:
        return True
    from sqlalchemy import text

    try:
        await db.execute(text(_IDEMPOTENCY_DDL))
        for ix in _INDEXES:
            await db.execute(text(ix))
        await db.commit()  # DDL 즉시 확정(유령 ready 방지 — schema_guard 동형).
        _SCHEMA_READY = True
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("idempotency schema_guard 실패", err=str(e)[:160])
        with contextlib.suppress(Exception):
            await db.rollback()
        return False


async def lookup(
    *, db: Any, key: str, tenant_id: str | None, endpoint: str, request_hash: str
) -> IdempotencyLookup:
    """저장된 응답을 조회해 miss/replay/conflict를 판정한다(테넌트 스코프).

    - 없음 → miss(호출부: 실행 후 save).
    - 있고 요청지문 일치 → replay(저장 응답 재생).
    - 있고 요청지문 불일치 → conflict(호출부: 422 거부 — 키 오사용).
    """
    if not await ensure_schema(db):
        return IdempotencyLookup(state=STATE_MISS)  # fail-open(기억 못 함=일반 실행)
    from sqlalchemy import text

    try:
        row = (await db.execute(text(
            "SELECT request_hash, response_status, response_media_type, response_body_b64, run_id "
            "FROM idempotency_key "
            "WHERE COALESCE(tenant_id, '') = COALESCE(:tid, '') "
            "  AND endpoint = :ep AND idempotency_key = :key"
        ), {"tid": tenant_id, "ep": endpoint, "key": key})).first()
    except Exception as e:  # noqa: BLE001
        logger.warning("idempotency lookup 실패", err=str(e)[:160])
        with contextlib.suppress(Exception):
            await db.rollback()
        return IdempotencyLookup(state=STATE_MISS)

    if row is None:
        return IdempotencyLookup(state=STATE_MISS)
    stored_hash = row[0]
    if stored_hash != request_hash:
        return IdempotencyLookup(state=STATE_CONFLICT)
    body_b64 = row[3]
    body = None
    if body_b64:
        with contextlib.suppress(Exception):
            body = base64.b64decode(body_b64)
    return IdempotencyLookup(
        state=STATE_REPLAY,
        stored=StoredResponse(
            response_status=int(row[1]),
            response_media_type=str(row[2] or "application/json"),
            body=body,
            run_id=row[4],
        ),
    )


async def save(
    *,
    db: Any,
    key: str,
    tenant_id: str | None,
    endpoint: str,
    request_hash: str,
    response_status: int,
    body: bytes,
    media_type: str = "application/json",
    run_id: str | None = None,
    max_body_bytes: int = _MAX_STORED_BODY_BYTES,
) -> bool:
    """응답을 키로 기억한다(INSERT ON CONFLICT DO NOTHING — 경쟁 시 최초 1행만 정본).

    본문이 상한을 넘으면 body_b64는 NULL로 저장(메타만) — 재생 시 호출부가 결정적 재계산으로 대체.
    best-effort: 실패해도 예외를 던지지 않는다(idempotency는 fail-open).
    """
    if not await ensure_schema(db):
        return False
    from sqlalchemy import text

    body_b64: str | None = None
    if body is not None and len(body) <= int(max_body_bytes):
        body_b64 = base64.b64encode(body).decode("ascii")
    try:
        await db.execute(text(
            "INSERT INTO idempotency_key "
            "(idempotency_key, tenant_id, endpoint, request_hash, response_status, "
            " response_media_type, response_body_b64, run_id) "
            "VALUES (:key, :tid, :ep, :rh, :st, :mt, :body, :rid) "
            "ON CONFLICT (COALESCE(tenant_id, ''), endpoint, idempotency_key) DO NOTHING"
        ), {"key": key, "tid": tenant_id, "ep": endpoint, "rh": request_hash,
            "st": int(response_status), "mt": media_type, "body": body_b64, "rid": run_id})
        await db.commit()
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("idempotency save 실패", err=str(e)[:160])
        with contextlib.suppress(Exception):
            await db.rollback()
        return False
