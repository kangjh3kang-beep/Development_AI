"""INC-11 — 외부 1차출처 응답 캐시 계층(law.go.kr/MOLIT/VWORLD 등 어댑터 공용).

vision_cache(INC-8)의 분산/영속 확장. 두 계층:
- **L1 프로세스 인메모리**(sync): 어댑터의 동기 httpx 호출 경로가 사용. 적중 시 동일 입력→동일 출력
  (결정론 영향 0). 미스/만료→재호출, 실패→기존 graceful None(무음0, None 미캐시→재시도 허용).
- **L2 DB 영속**(`external_source_cache`, async): `warm_from_db`(분석 전 적재)/`flush_to_db`(분석 후 영속)를
  async 라우트 경계에서 호출 → 워커/재시작 간 공유·쿼터 절감. snapshot_id 결속(재현성).

cache_key=adapter+endpoint+정규화params 해시(**secret 파라미터 제외** — 키 회전 무관·시크릿 비유출).
payload에 ref(endpoint)/etag/fetched_at 보존(1차출처·설명가능성).
"""
from __future__ import annotations

import contextvars
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Any

# 캐시 항목 기본 수명(초). 운영 인프라 설정(법정/도메인 수치 아님, INV-3 비대상).
_DEFAULT_TTL_SECONDS = 86400
# L1 최대 항목 수 — 초과 시 가장 오래된 비-dirty 항목 회수(장수 워커 메모리 가드).
_MAX_ENTRIES = 10000

_store: dict[str, "SourceCacheEntry"] = {}
_dirty: set[str] = set()  # 라이브 fetch로 새로 채워진 키(flush 대상). warm 적재분은 비더티.
_lock = Lock()

# 현재 분석 snapshot_id — run_analysis가 설정(어댑터 시그니처 미변경으로 snapshot 결속).
_current_snapshot: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "source_cache_snapshot", default=None)


def set_snapshot(snapshot_id: str | None) -> None:
    """현재 분석의 snapshot_id 설정(캐시 항목 결속). run_analysis 진입 시 호출."""
    _current_snapshot.set(snapshot_id)


@dataclass
class SourceCacheEntry:
    cache_key: str
    adapter: str
    endpoint: str
    params_hash: str
    payload: Any
    content_hash: str | None = None
    etag: str | None = None
    fetched_at: datetime | None = None
    snapshot_id: str | None = None
    status: str | None = None


def _norm_params(params: dict) -> str:
    """정규화 직렬화(정렬 키, 결정론). secret 제외는 호출측에서 수행."""
    return json.dumps(params, sort_keys=True, ensure_ascii=False, default=str)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def cache_key(adapter: str, endpoint: str, params: dict) -> str:
    """동일 (adapter, endpoint, 정규화 params) → 동일 키(sha256). 설명가능성 위해 3요소 결합."""
    h = hashlib.sha256()
    for part in (adapter, endpoint, _norm_params(params)):
        h.update(part.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def _expired(entry: SourceCacheEntry, ttl_seconds: int) -> bool:
    if entry.fetched_at is None:
        return False  # 영속 항목(fetched_at 없으면 만료 판단 보류 — 결손 단정 금지)
    age = (datetime.now(timezone.utc) - entry.fetched_at).total_seconds()
    return age > ttl_seconds


def _evict_locked() -> None:
    """상한 초과 시 가장 오래된 비-dirty 항목부터 회수(dirty는 flush 전 보존). _lock 보유 전제."""
    for k in list(_store):
        if len(_store) <= _MAX_ENTRIES:
            break
        if k not in _dirty:
            _store.pop(k, None)


def _l1_get(key: str, ttl_seconds: int) -> SourceCacheEntry | None:
    with _lock:
        entry = _store.get(key)
        if entry is not None and _expired(entry, ttl_seconds):
            _store.pop(key, None)  # 만료 항목 회수(메모리 누적 방지)
            _dirty.discard(key)
            entry = None
    return entry


def _l1_put(key: str, entry: SourceCacheEntry, *, dirty: bool) -> None:
    with _lock:
        _store[key] = entry
        if dirty:
            _dirty.add(key)
        if len(_store) > _MAX_ENTRIES:
            _evict_locked()


def get(key: str, ttl_seconds: int | None = None) -> SourceCacheEntry | None:
    """L1 조회(만료 시 None). 테스트/조회용."""
    return _l1_get(key, ttl_seconds if ttl_seconds is not None else _DEFAULT_TTL_SECONDS)


def put(entry: SourceCacheEntry, *, dirty: bool = True) -> None:
    """L1 적재."""
    _l1_put(entry.cache_key, entry, dirty=dirty)


def clear() -> None:
    """캐시 비우기(테스트/스냅샷 경계용)."""
    with _lock:
        _store.clear()
        _dirty.clear()


def cached_get(
    adapter: str,
    url: str,
    params: dict,
    *,
    secret_param_keys: tuple[str, ...] = (),
    headers: dict | None = None,
    timeout: float = 15.0,
    ttl_seconds: int | None = None,
) -> Any:
    """캐시 경유 GET — 적중 시 저장 payload(동일 출력), 미스 시 httpx.get→파싱→적재.

    secret_param_keys(키/OC/serviceKey)는 cache_key에서 제외(시크릿 비유출·키 회전 무관), 실 호출엔 포함.
    실패(예외/ImportError)는 None(무음 단정 금지). None은 캐시 안 함(재시도 허용). 기존 어댑터 httpx 의미 동일.
    """
    ttl = ttl_seconds if ttl_seconds is not None else _DEFAULT_TTL_SECONDS
    key_params = {k: v for k, v in params.items() if k not in secret_param_keys}
    key = cache_key(adapter, url, key_params)

    hit = _l1_get(key, ttl)
    if hit is not None:
        return hit.payload

    try:
        import httpx
    except ImportError:
        return None
    # 헤더 없는 어댑터(molit/law)는 headers 미전달 — 원 httpx.get 호출 시그니처 보존(기존 동작·목 호환).
    kwargs: dict = {"params": params, "timeout": timeout}
    if headers is not None:
        kwargs["headers"] = headers
    try:
        r = httpx.get(url, **kwargs)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return None  # 라이브 실패 → degrade(상위 어댑터가 결손 처리). 미캐시(재시도 허용).
    # etag 추출 실패는 fetch를 무효화하지 않음(헤더 미보유 응답 호환).
    etag = None
    hdrs = getattr(r, "headers", None)
    if hdrs is not None:
        try:
            etag = hdrs.get("etag")
        except Exception:
            etag = None

    if data is None:
        return None
    payload_json = json.dumps(data, sort_keys=True, ensure_ascii=False, default=str)
    entry = SourceCacheEntry(
        cache_key=key, adapter=adapter, endpoint=url, params_hash=_sha(_norm_params(key_params)),
        payload=data, content_hash=_sha(payload_json), etag=etag,
        fetched_at=datetime.now(timezone.utc), snapshot_id=_current_snapshot.get(), status="OK",
    )
    _l1_put(key, entry, dirty=True)
    return data


async def warm_from_db(session, snapshot_id: str | None = None) -> int:
    """L2(DB) → L1 적재(분석 전). snapshot_id 주면 해당 스냅샷 항목만(재현성·범위 한정). 적재 수 반환."""
    from sqlalchemy import select

    from app.db.models.cache_models import ExternalSourceCacheModel as M

    stmt = select(M)
    if snapshot_id is not None:
        stmt = stmt.where(M.snapshot_id == snapshot_id)
    rows = (await session.execute(stmt)).scalars().all()
    for row in rows:
        _l1_put(row.cache_key, SourceCacheEntry(
            cache_key=row.cache_key, adapter=row.adapter, endpoint=row.endpoint,
            params_hash=row.params_hash, payload=row.payload, content_hash=row.content_hash,
            etag=row.etag, fetched_at=row.fetched_at, snapshot_id=row.snapshot_id, status=row.status,
        ), dirty=False)  # 영속분은 비더티(재flush 회피)
    await session.rollback()  # 읽기 전용 트랜잭션 즉시 종료(동기 run_analysis 동안 idle-in-transaction 방지)
    return len(rows)


async def flush_to_db(session) -> int:
    """L1의 라이브 신규 fetch분(dirty)을 L2(DB)로 upsert(분석 후). cache_key 충돌 시 갱신. 영속 수 반환."""
    import uuid

    from sqlalchemy import func
    from sqlalchemy.dialects.postgresql import insert

    from app.db.models.cache_models import ExternalSourceCacheModel as M

    with _lock:
        keys = [k for k in _dirty if k in _store]
        entries = [_store[k] for k in keys]
    if not entries:
        return 0
    for e in entries:
        stmt = insert(M).values(
            id=uuid.uuid4(), cache_key=e.cache_key, adapter=e.adapter, endpoint=e.endpoint,
            params_hash=e.params_hash, payload=e.payload, content_hash=e.content_hash,
            etag=e.etag, fetched_at=e.fetched_at, snapshot_id=e.snapshot_id, status=e.status,
        ).on_conflict_do_update(
            constraint="uq_external_source_cache_cache_key",
            set_={"payload": e.payload, "content_hash": e.content_hash, "etag": e.etag,
                  "fetched_at": e.fetched_at, "snapshot_id": e.snapshot_id, "status": e.status,
                  "updated_at": func.now()},
        )
        await session.execute(stmt)
    await session.commit()
    with _lock:
        for k in keys:
            _dirty.discard(k)  # commit 성공분만 해제(실패 시 보존 → 다음 분석 재flush)
    return len(entries)
