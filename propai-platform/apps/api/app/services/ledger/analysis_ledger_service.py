"""분석 원장(블록체인-inspired) — 해시체인 append-only 변조방지 버전 원장.

간편분석(대시보드)·정식분석(프로젝트) 결과를 PNU/주소·프로젝트별로 영속 누적한다.
 - append-only: 덮어쓰지 않고 버전(version) 누적 → 전 버전 보존(감사추적).
 - 무결성: content_hash = sha256(정규화 payload), prev_hash = 같은 체인 직전 버전 해시.
 - 계보(provenance): 같은 PNU면 간편↔정식 분석이 한 체인으로 연결 → 프로젝트 승계·비교.
 - 검증: 체인을 따라 prev_hash 연속성 + content_hash 재계산으로 변조탐지.

진짜 분산원장(합의/P2P/토큰) 없이 블록체인의 유용한 속성(불변성·무결성·계보)만 DB로 구현.
(옵션: 향후 일배치 Merkle 루트 외부 앵커링으로 '블록체인급 증명' 확장 가능)
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_DDL = (
    "CREATE TABLE IF NOT EXISTS analysis_ledger ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  tenant_id text,"
    "  pnu text,"
    "  address_norm text,"
    "  project_id text,"
    "  analysis_type text NOT NULL,"
    "  version int NOT NULL,"
    "  payload jsonb NOT NULL,"
    "  content_hash text NOT NULL,"
    "  prev_hash text,"
    "  source text,"
    "  created_by text,"
    "  created_at timestamptz DEFAULT now()"
    ")"
)
_IDX = (
    "CREATE INDEX IF NOT EXISTS idx_ledger_chain "
    "ON analysis_ledger(tenant_id, pnu, project_id, analysis_type, version DESC)",
    "CREATE INDEX IF NOT EXISTS idx_ledger_addr "
    "ON analysis_ledger(tenant_id, address_norm, analysis_type, version DESC)",
)


def _norm_addr(s: str | None) -> str:
    return " ".join((s or "").split()).strip()


def _canonical(payload: Any) -> str:
    """결정적 직렬화(키 정렬) — 동일 내용 = 동일 해시."""
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def _content_hash(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _chain_where(pnu: str | None, address_norm: str, project_id: str | None) -> tuple[str, dict[str, Any]]:
    """체인 식별 조건. PNU 우선, 없으면 주소(정규화). project_id는 NULL 동등 비교."""
    params: dict[str, Any] = {"atype": None}  # atype는 호출부에서 채움
    if pnu:
        key_sql = "pnu = :pnu"
        params["pnu"] = pnu
    else:
        key_sql = "address_norm = :addr"
        params["addr"] = address_norm
    if project_id:
        key_sql += " AND project_id = :pid"
        params["pid"] = project_id
    else:
        key_sql += " AND project_id IS NULL"
    return key_sql, params


async def _ensure(db) -> None:
    from sqlalchemy import text
    await db.execute(text(_DDL))
    for ix in _IDX:
        await db.execute(text(ix))


async def append_analysis(
    *,
    analysis_type: str,
    payload: dict[str, Any],
    tenant_id: str | None = None,
    pnu: str | None = None,
    address: str | None = None,
    project_id: str | None = None,
    source: str = "quick",
    created_by: str | None = None,
) -> dict[str, Any]:
    """분석 1건을 원장에 append(버전+1, 해시체인). 직전과 동일 내용이면 append 생략(멱등)."""
    address_norm = _norm_addr(address)
    chash = _content_hash(payload)
    try:
        from sqlalchemy import text
        from app.core.database import async_session_factory

        async with async_session_factory() as db:
            await _ensure(db)
            key_sql, params = _chain_where(pnu, address_norm, project_id)
            params.update({"atype": analysis_type, "tid": tenant_id})
            tenant_sql = "tenant_id = :tid" if tenant_id else "tenant_id IS NULL"
            prev = (await db.execute(text(
                f"SELECT version, content_hash FROM analysis_ledger "
                f"WHERE {tenant_sql} AND {key_sql} AND analysis_type = :atype "
                f"ORDER BY version DESC LIMIT 1"), params)).first()

            if prev and prev[1] == chash:
                # 변경 없음 — 중복 버전 생성 방지(멱등)
                return {"ok": True, "unchanged": True, "version": int(prev[0]),
                        "content_hash": chash, "analysis_type": analysis_type}

            version = (int(prev[0]) + 1) if prev else 1
            prev_hash = prev[1] if prev else None
            await db.execute(text(
                "INSERT INTO analysis_ledger"
                "(tenant_id, pnu, address_norm, project_id, analysis_type, version, payload, content_hash, prev_hash, source, created_by)"
                " VALUES (:tid,:pnu,:addr,:pid,:atype,:ver,CAST(:pl AS jsonb),:ch,:ph,:src,:cb)"),
                {"tid": tenant_id, "pnu": pnu, "addr": address_norm or None, "pid": project_id,
                 "atype": analysis_type, "ver": version, "pl": _canonical(payload),
                 "ch": chash, "ph": prev_hash, "src": source, "cb": created_by})
            await db.commit()
            return {"ok": True, "unchanged": False, "version": version,
                    "content_hash": chash, "prev_hash": prev_hash, "analysis_type": analysis_type}
    except Exception as e:  # noqa: BLE001
        logger.warning("분석원장 append 실패", err=str(e)[:160])
        return {"ok": False, "message": str(e)[:160]}


async def get_latest(
    *, analysis_type: str | None = None, tenant_id: str | None = None,
    pnu: str | None = None, address: str | None = None, project_id: str | None = None,
) -> dict[str, Any] | None:
    """체인 최신 버전 payload 반환(analysis_type 미지정 시 타입별 최신 묶음)."""
    address_norm = _norm_addr(address)
    try:
        from sqlalchemy import text
        from app.core.database import async_session_factory
        async with async_session_factory() as db:
            await _ensure(db)
            key_sql, params = _chain_where(pnu, address_norm, project_id)
            params.update({"tid": tenant_id})
            tenant_sql = "tenant_id = :tid" if tenant_id else "tenant_id IS NULL"
            if analysis_type:
                params["atype"] = analysis_type
                row = (await db.execute(text(
                    f"SELECT payload, version, content_hash, created_at FROM analysis_ledger "
                    f"WHERE {tenant_sql} AND {key_sql} AND analysis_type = :atype "
                    f"ORDER BY version DESC LIMIT 1"), params)).first()
                if not row:
                    return None
                return {"analysis_type": analysis_type, "version": int(row[1]),
                        "content_hash": row[2], "created_at": str(row[3]), "payload": row[0]}
            # 타입별 최신 묶음(DISTINCT ON)
            rows = (await db.execute(text(
                f"SELECT DISTINCT ON (analysis_type) analysis_type, payload, version, content_hash, created_at "
                f"FROM analysis_ledger WHERE {tenant_sql} AND {key_sql} "
                f"ORDER BY analysis_type, version DESC"), params)).all()
            return {r[0]: {"version": int(r[2]), "content_hash": r[3], "created_at": str(r[4]), "payload": r[1]}
                    for r in rows} or None
    except Exception as e:  # noqa: BLE001
        logger.warning("분석원장 조회 실패", err=str(e)[:160])
        return None


async def get_history(
    *, analysis_type: str, tenant_id: str | None = None,
    pnu: str | None = None, address: str | None = None, project_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """체인 전체 버전 이력(최신순) — 버전 타임라인·비교용."""
    address_norm = _norm_addr(address)
    try:
        from sqlalchemy import text
        from app.core.database import async_session_factory
        async with async_session_factory() as db:
            await _ensure(db)
            key_sql, params = _chain_where(pnu, address_norm, project_id)
            params.update({"tid": tenant_id, "atype": analysis_type, "lim": limit})
            tenant_sql = "tenant_id = :tid" if tenant_id else "tenant_id IS NULL"
            rows = (await db.execute(text(
                f"SELECT version, content_hash, prev_hash, source, created_by, created_at "
                f"FROM analysis_ledger WHERE {tenant_sql} AND {key_sql} AND analysis_type = :atype "
                f"ORDER BY version DESC LIMIT :lim"), params)).all()
            return [{"version": int(r[0]), "content_hash": r[1], "prev_hash": r[2],
                     "source": r[3], "created_by": r[4], "created_at": str(r[5])} for r in rows]
    except Exception as e:  # noqa: BLE001
        logger.warning("분석원장 이력 실패", err=str(e)[:160])
        return []


async def verify_chain(
    *, analysis_type: str, tenant_id: str | None = None,
    pnu: str | None = None, address: str | None = None, project_id: str | None = None,
) -> dict[str, Any]:
    """체인 무결성 검증 — prev_hash 연속성 + content_hash 재계산(payload 변조탐지)."""
    address_norm = _norm_addr(address)
    try:
        from sqlalchemy import text
        from app.core.database import async_session_factory
        async with async_session_factory() as db:
            await _ensure(db)
            key_sql, params = _chain_where(pnu, address_norm, project_id)
            params.update({"tid": tenant_id, "atype": analysis_type})
            tenant_sql = "tenant_id = :tid" if tenant_id else "tenant_id IS NULL"
            rows = (await db.execute(text(
                f"SELECT version, payload, content_hash, prev_hash FROM analysis_ledger "
                f"WHERE {tenant_sql} AND {key_sql} AND analysis_type = :atype "
                f"ORDER BY version ASC"), params)).all()
            if not rows:
                return {"ok": True, "verified": False, "message": "원장에 해당 체인이 없습니다.", "length": 0}
            broken: list[dict[str, Any]] = []
            prev_hash = None
            for r in rows:
                ver, payload, stored_hash, ph = int(r[0]), r[1], r[2], r[3]
                recomputed = _content_hash(payload)
                if recomputed != stored_hash:
                    broken.append({"version": ver, "issue": "payload_tampered"})
                if ph != prev_hash:
                    broken.append({"version": ver, "issue": "chain_broken"})
                prev_hash = stored_hash
            return {"ok": True, "verified": not broken, "length": len(rows),
                    "head_version": int(rows[-1][0]), "broken": broken,
                    "message": "무결성 체인 정상(변조 없음)" if not broken else f"무결성 이상 {len(broken)}건 탐지"}
    except Exception as e:  # noqa: BLE001
        logger.warning("분석원장 검증 실패", err=str(e)[:160])
        return {"ok": False, "message": str(e)[:160]}
