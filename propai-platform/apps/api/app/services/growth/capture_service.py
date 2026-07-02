"""자가성장 엔진 — 이벤트 수집 코어(논블로킹 큐 + 배치 적재).

설계서 §3.2/§4. 요청경로 지연을 최소화하기 위해 미들웨어/인터프리터는
record_event() 로 in-memory 큐에 push 만 하고(동기 INSERT 금지), 실제 적재는
Celery 태스크(또는 인프로세스 폴백)가 flush_batch() 로 배치 INSERT 한다.

프라이버시:
- user_id → HMAC-SHA256(GROWTH_HMAC_KEY) → user_hash. 원본 user_id 미저장.
  GROWTH_HMAC_KEY 미설정 시 APP_SECRET_KEY 파생 폴백(둘 다 없으면 익명 처리).
- payload 는 저장 전 PII 키/패턴 마스킹(이메일/전화/주민번호/주소 등).

멱등: event_id(uuid) 가 있으면 INSERT ... ON CONFLICT(event_id) DO NOTHING.
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import logging
import os
import re
from collections import deque
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# ── in-memory 큐(프로세스 로컬, 논블로킹). maxlen 으로 폭주 시 오래된 것부터 drop. ──
_MAX_QUEUE = 10_000
_QUEUE: deque[dict[str, Any]] = deque(maxlen=_MAX_QUEUE)

# 1회 배치 INSERT 상한(과도한 단일 트랜잭션 방지).
_FLUSH_LIMIT = 500

# user_hash 캐시(같은 user_id 반복 해시 비용 절감, 프로세스 로컬).
_HASH_CACHE: dict[str, str] = {}

# payload 에서 마스킹할 민감 키(부분일치, 소문자 비교).
_PII_KEYS = (
    "email", "phone", "tel", "mobile", "name", "addr", "address", "jumin",
    "ssn", "resident", "rrn", "owner", "contact", "birth", "passport",
)

# 값 내부 PII 패턴(문자열 값에 적용).
_RE_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_RE_PHONE = re.compile(r"\b01[0-9][-\s]?\d{3,4}[-\s]?\d{4}\b")
_RE_RRN = re.compile(r"\b\d{6}[-\s]?[1-4]\d{6}\b")  # 주민등록번호
_REDACTED = "[redacted]"

# 이벤트가 허용하는 화이트리스트 컬럼(그 외 키는 payload 로 흡수하지 않고 버림).
_EVENT_COLS = (
    "event_id", "tenant_id", "user_hash", "session_id", "event_type", "surface",
    "route", "status_code", "latency_ms", "severity", "service", "payload",
    "app_version", "created_at",
)


def _hmac_key() -> bytes | None:
    """HMAC 키 바이트. GROWTH_HMAC_KEY → APP_SECRET_KEY 파생 폴백 순."""
    raw = os.getenv("GROWTH_HMAC_KEY") or ""
    if not raw:
        app_secret = os.getenv("APP_SECRET_KEY") or ""
        if app_secret:
            # APP_SECRET_KEY 에서 도메인 분리 파생(전용 키와 충돌 방지).
            raw = hashlib.sha256(("growth:" + app_secret).encode("utf-8")).hexdigest()
    return raw.encode("utf-8") if raw else None


def hash_user_id(user_id: str | None) -> str | None:
    """user_id 를 HMAC-SHA256 으로 익명화. 키/입력 없으면 None(익명)."""
    if not user_id:
        return None
    cached = _HASH_CACHE.get(user_id)
    if cached is not None:
        return cached
    key = _hmac_key()
    if key is None:
        return None
    digest = hmac.new(key, user_id.encode("utf-8"), hashlib.sha256).hexdigest()
    if len(_HASH_CACHE) < 50_000:
        _HASH_CACHE[user_id] = digest
    return digest


def _mask_str(value: str) -> str:
    """문자열 값 내부의 이메일/전화/주민번호 패턴을 치환."""
    if not value:
        return value
    out = _RE_EMAIL.sub(_REDACTED, value)
    out = _RE_PHONE.sub(_REDACTED, out)
    out = _RE_RRN.sub(_REDACTED, out)
    return out


def mask_pii(obj: Any, _depth: int = 0) -> Any:
    """payload 의 PII 를 재귀 마스킹한다.

    - 민감 키(_PII_KEYS 부분일치)의 값은 통째로 [redacted].
    - 그 외 문자열 값은 내부 패턴(이메일/전화/주민번호)만 치환.
    - dict/list 재귀(과도한 깊이는 방어적으로 중단).
    """
    if _depth > 8:
        return _REDACTED
    if isinstance(obj, dict):
        masked: dict[str, Any] = {}
        for k, v in obj.items():
            key_l = str(k).lower()
            if any(p in key_l for p in _PII_KEYS):
                masked[k] = _REDACTED
            else:
                masked[k] = mask_pii(v, _depth + 1)
        return masked
    if isinstance(obj, (list, tuple)):
        return [mask_pii(v, _depth + 1) for v in obj]
    if isinstance(obj, str):
        return _mask_str(obj)
    return obj


def record_event(event_type: str, props: dict[str, Any] | None = None) -> None:
    """이벤트를 in-memory 큐에 논블로킹 push 한다(동기 INSERT 없음).

    props 에 user_id 가 있으면 즉시 user_hash 로 익명화하고 user_id 는 버린다.
    payload 는 PII 마스킹 후 저장. 어떤 예외도 호출경로로 전파하지 않는다.
    """
    try:
        props = dict(props or {})
        # user_id → user_hash 익명화(원본 미저장).
        uid = props.pop("user_id", None)
        if uid is not None and not props.get("user_hash"):
            props["user_hash"] = hash_user_id(str(uid))
        # payload PII 마스킹.
        if props.get("payload") is not None:
            props["payload"] = mask_pii(props["payload"])
        # 화이트리스트 컬럼만 보존.
        row = {k: props.get(k) for k in _EVENT_COLS}
        row["event_type"] = event_type
        if row.get("created_at") is None:
            row["created_at"] = datetime.now(UTC)
        _QUEUE.append(row)
    except Exception as e:  # noqa: BLE001 — 수집은 절대 호출경로를 깨뜨리면 안 됨.
        logger.debug("growth record_event 무시: %s", str(e)[:120])


def queue_size() -> int:
    """현재 큐 적재 건수(관측·테스트용)."""
    return len(_QUEUE)


def _drain(limit: int) -> list[dict[str, Any]]:
    """큐에서 최대 limit 건을 꺼낸다(FIFO)."""
    out: list[dict[str, Any]] = []
    while _QUEUE and len(out) < limit:
        out.append(_QUEUE.popleft())
    return out


_INSERT_SQL = """
INSERT INTO platform_events
    (event_id, tenant_id, user_hash, session_id, event_type, surface, route,
     status_code, latency_ms, severity, service, payload, app_version, created_at)
VALUES
    (:event_id, :tenant_id, :user_hash, :session_id, :event_type, :surface, :route,
     :status_code, :latency_ms, :severity, :service, CAST(:payload AS jsonb),
     :app_version, :created_at)
ON CONFLICT (event_id) DO NOTHING
"""


async def flush_batch(db, limit: int = _FLUSH_LIMIT) -> int:
    """큐의 이벤트를 platform_events 로 배치 INSERT 한다. 적재 건수 반환.

    event_id 멱등(ON CONFLICT DO NOTHING). best-effort: 실패 시 rollback 후 0.
    """
    import json

    from sqlalchemy import text

    rows = _drain(limit)
    if not rows:
        return 0
    params: list[dict[str, Any]] = []
    for r in rows:
        payload = r.get("payload")
        params.append({
            "event_id": str(r["event_id"]) if r.get("event_id") else None,
            "tenant_id": str(r["tenant_id"]) if r.get("tenant_id") else None,
            "user_hash": r.get("user_hash"),
            "session_id": r.get("session_id"),
            "event_type": r.get("event_type"),
            "surface": r.get("surface"),
            "route": r.get("route"),
            "status_code": r.get("status_code"),
            "latency_ms": r.get("latency_ms"),
            "severity": r.get("severity"),
            "service": r.get("service"),
            "payload": json.dumps(payload, ensure_ascii=False, default=str) if payload is not None else None,
            "app_version": r.get("app_version"),
            "created_at": r.get("created_at"),
        })
    try:
        await db.execute(text(_INSERT_SQL), params)
        await db.commit()
        return len(params)
    except Exception as e:  # noqa: BLE001
        logger.warning("growth flush_batch 실패(%d건 유실): %s", len(params), str(e)[:160])
        with contextlib.suppress(Exception):
            await db.rollback()
        return 0
