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

# 구독자(테넌트)별 저장 용량 쿼터 — 기본값 + 관리자 상향(override) 테이블
_QUOTA_DDL = (
    "CREATE TABLE IF NOT EXISTS analysis_ledger_quota ("
    "  tenant_id text PRIMARY KEY, max_entries int NOT NULL, updated_at timestamptz DEFAULT now())"
)
_DEFAULT_QUOTA = 300         # 무설정 테넌트 기본 보관 한도(분석 버전 행 수)


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
    elif address_norm:  # 비어있지 않은 주소만 동등 비교
        key_sql = "address_norm = :addr"
        params["addr"] = address_norm
    else:  # pnu·address 모두 없음 → NULL 저장행과 정합(Phase 0 carve-out 버그픽스)
        key_sql = "address_norm IS NULL"
    if project_id:
        key_sql += " AND project_id = :pid"
        params["pid"] = project_id
    else:
        key_sql += " AND project_id IS NULL"
    return key_sql, params


async def _ensure(db) -> None:
    from sqlalchemy import text
    await db.execute(text(_DDL))
    await db.execute(text(_QUOTA_DDL))
    for ix in _IDX:
        await db.execute(text(ix))


async def _count_entries(db, tenant_id: str | None) -> int:
    from sqlalchemy import text
    tenant_sql = "tenant_id = :tid" if tenant_id else "tenant_id IS NULL"
    row = (await db.execute(text(
        f"SELECT count(*) FROM analysis_ledger WHERE {tenant_sql}"), {"tid": tenant_id})).first()
    return int(row[0]) if row else 0


async def _quota(db, tenant_id: str | None) -> int:
    from sqlalchemy import text
    if not tenant_id:
        return _DEFAULT_QUOTA
    row = (await db.execute(text(
        "SELECT max_entries FROM analysis_ledger_quota WHERE tenant_id = :tid"),
        {"tid": tenant_id})).first()
    return int(row[0]) if row else _DEFAULT_QUOTA


async def get_usage(tenant_id: str | None) -> dict[str, Any]:
    """테넌트 저장 사용량/한도 조회."""
    try:
        from app.core.database import async_session_factory
        async with async_session_factory() as db:
            await _ensure(db)
            used = await _count_entries(db, tenant_id)
            quota = await _quota(db, tenant_id)
            return {"ok": True, "used": used, "quota": quota,
                    "remaining": max(0, quota - used),
                    "usage_pct": round(used / quota * 100, 1) if quota else 0}
    except Exception as e:  # noqa: BLE001
        logger.warning("원장 사용량 조회 실패", err=str(e)[:160])
        return {"ok": False, "message": str(e)[:160]}


async def set_quota(tenant_id: str, max_entries: int) -> dict[str, Any]:
    """관리자: 테넌트 용량 한도 상향/조정(override)."""
    try:
        from sqlalchemy import text

        from app.core.database import async_session_factory
        async with async_session_factory() as db:
            await _ensure(db)
            await db.execute(text(
                "INSERT INTO analysis_ledger_quota(tenant_id, max_entries, updated_at) "
                "VALUES (:tid, :mx, now()) "
                "ON CONFLICT (tenant_id) DO UPDATE SET max_entries = EXCLUDED.max_entries, updated_at = now()"),
                {"tid": tenant_id, "mx": int(max_entries)})
            await db.commit()
            return {"ok": True, "tenant_id": tenant_id, "max_entries": int(max_entries)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": str(e)[:160]}


async def delete_chain(
    *, analysis_type: str, tenant_id: str | None = None,
    pnu: str | None = None, address: str | None = None, project_id: str | None = None,
) -> dict[str, Any]:
    """체인(특정 PNU/주소·프로젝트·타입) 전체 버전 삭제 — 용량 확보."""
    address_norm = _norm_addr(address)
    try:
        from sqlalchemy import text

        from app.core.database import async_session_factory
        async with async_session_factory() as db:
            await _ensure(db)
            key_sql, params = _chain_where(pnu, address_norm, project_id)
            params.update({"tid": tenant_id, "atype": analysis_type})
            tenant_sql = "tenant_id = :tid" if tenant_id else "tenant_id IS NULL"
            res = await db.execute(text(
                f"DELETE FROM analysis_ledger WHERE {tenant_sql} AND {key_sql} AND analysis_type = :atype"), params)
            await db.commit()
            return {"ok": True, "deleted": res.rowcount}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": str(e)[:160]}


async def prune_old_versions(tenant_id: str | None, keep_per_chain: int = 5) -> dict[str, Any]:
    """체인별 최신 N개만 남기고 옛 버전 삭제 — 용량 확보(최신·계보 유지)."""
    try:
        from sqlalchemy import text

        from app.core.database import async_session_factory
        async with async_session_factory() as db:
            await _ensure(db)
            tenant_sql = "tenant_id = :tid" if tenant_id else "tenant_id IS NULL"
            res = await db.execute(text(
                f"DELETE FROM analysis_ledger a USING ("
                f"  SELECT id, row_number() OVER ("
                f"    PARTITION BY tenant_id, pnu, address_norm, project_id, analysis_type "
                f"    ORDER BY version DESC) AS rn "
                f"  FROM analysis_ledger WHERE {tenant_sql}) r "
                f"WHERE a.id = r.id AND r.rn > :keep"), {"tid": tenant_id, "keep": keep_per_chain})
            await db.commit()
            return {"ok": True, "pruned": res.rowcount, "kept_per_chain": keep_per_chain}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": str(e)[:160]}


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

            # 용량 쿼터 — 신규 버전 적재 전 한도 확인(초과 시 삭제·상향 안내)
            used = await _count_entries(db, tenant_id)
            quota = await _quota(db, tenant_id)
            if used >= quota:
                return {"ok": False, "quota_exceeded": True, "used": used, "quota": quota,
                        "message": (f"저장 용량 한도({quota}건) 초과 — "
                                    "오래된 분석을 삭제하거나 관리자에게 용량 상향을 요청하세요.")}

            version = (int(prev[0]) + 1) if prev else 1
            prev_hash = prev[1] if prev else None
            await db.execute(text(
                "INSERT INTO analysis_ledger"
                "(tenant_id, pnu, address_norm, project_id, analysis_type, version, "
                "payload, content_hash, prev_hash, source, created_by)"
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


async def verify_all_chains(
    *, tenant_id: str | None = None, project_id: str | None = None,
) -> dict[str, Any]:
    """테넌트(옵션: 프로젝트)의 모든 체인을 일괄 무결성 검증.

    단일 패스 SELECT로 전 행을 읽어(N+1 라운드트립 제거) 파이썬에서 verify_chain과 '동일한 체인 키
    규칙'(_chain_where: pnu 있으면 pnu, 없으면 address_norm; +project_id, analysis_type)으로 그룹핑해
    검증한다 → 단건 verify_chain과 판정 일치. 검증은 prev_hash 연속성 + content_hash 재계산에 더해
    동일 version 중복(동시 append 경쟁조건 사후탐지)까지 본다. 기존 verify_chain은 불변(별도 함수).
    """
    try:
        from sqlalchemy import text

        from app.core.database import async_session_factory

        async with async_session_factory() as db:
            await _ensure(db)
            tenant_sql = "tenant_id = :tid" if tenant_id else "tenant_id IS NULL"
            params: dict[str, Any] = {"tid": tenant_id}
            proj_sql = ""
            if project_id:
                proj_sql = " AND project_id = :pid"
                params["pid"] = project_id
            rows = (await db.execute(text(
                f"SELECT pnu, address_norm, project_id, analysis_type, version, "
                f"payload, content_hash, prev_hash FROM analysis_ledger "
                f"WHERE {tenant_sql}{proj_sql}"), params)).all()

            # _chain_where와 동일한 체인 키(pnu 우선, 없으면 address_norm)로 그룹핑.
            chains: dict[tuple[Any, Any, Any], dict[str, Any]] = {}
            for r in rows:
                pnu_v, addr_v, pid_v, atype = r[0], r[1], r[2], r[3]
                pnu_key = pnu_v or None    # 빈문자열 pnu도 address 분기로(=_chain_where `if pnu:` 동형)
                key = (pnu_key if pnu_key is not None else f"@addr:{addr_v}", pid_v, atype)
                chains.setdefault(key, {
                    "pnu": pnu_v, "address_norm": addr_v, "project_id": pid_v,
                    "analysis_type": atype, "rows": [],
                })["rows"].append((int(r[4]), r[5], r[6], r[7]))

            broken_chains: list[dict[str, Any]] = []
            for ch in chains.values():
                broken: list[dict[str, Any]] = []
                prev_hash = None
                seen: set[int] = set()
                for ver, payload, stored_hash, ph in sorted(ch["rows"], key=lambda x: x[0]):
                    if ver in seen:
                        broken.append({"version": ver, "issue": "duplicate_version"})
                    seen.add(ver)
                    if _content_hash(payload) != stored_hash:
                        broken.append({"version": ver, "issue": "payload_tampered"})
                    if ph != prev_hash:
                        broken.append({"version": ver, "issue": "chain_broken"})
                    prev_hash = stored_hash
                if broken:
                    broken_chains.append({
                        "analysis_type": ch["analysis_type"], "pnu": ch["pnu"],
                        "address_norm": ch["address_norm"], "project_id": ch["project_id"],
                        "broken": broken,
                    })

            return {
                "ok": True, "verified": not broken_chains,
                "chains_checked": len(chains), "broken_chains": broken_chains,
                "message": ("전 체인 무결성 정상(변조 없음)" if not broken_chains
                            else f"무결성 이상 체인 {len(broken_chains)}건 탐지"),
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("분석원장 전체검증 실패", err=str(e)[:160])
        return {"ok": False, "message": str(e)[:160]}
