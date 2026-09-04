"""design_run 실행상태(job) 상태머신 — QUEUED/RUNNING/SUCCEEDED/CANCELLED/FAILED (WP-L · A3).

이 파일이 푸는 문제(쉬운 설명):
- 설계 실행(design_run)에는 **두 개의 서로 다른 차원**이 있다.
  ① 승인차원(status): DRAFT/APPROVED — "사람이 이 설계를 인가했는가"(WP-E design_run_store가 소유).
  ② 실행차원(job_status): QUEUED/RUNNING/SUCCEEDED/CANCELLED/FAILED — "계산 작업이 지금 어디까지
     돌았는가"(worker·큐 상태). 본 모듈이 소유.
- 둘은 **완전히 독립된 축**이다. 예: 실행이 SUCCEEDED여도 승인은 아직 DRAFT일 수 있고, 승인이
  APPROVED여도 재실행 job은 QUEUED일 수 있다. 그래서 **하나의 컬럼에 섞으면 안 된다**(계획서 §4
  WP-L ★). WP-E가 design_runs에 job_status **예약 컬럼**을 이미 두었고(미사용), 본 WP가 그 컬럼만
  활성화한다.

★차원 분리(불변식 — 이 모듈의 존재 이유):
- 이 모듈은 **job_status만** 읽고 쓴다. 승인차원 status(DRAFT/APPROVED)는 **한 줄도 건드리지 않는다**.
- 반대로 design_run_store(승인차원)는 job_status를 건드리지 않는다(WP-E 테스트가 이미 강제).
- 두 축이 각자 자기 컬럼만 전이하므로 '혼용 금지'가 모듈 경계로 구조적으로 보장된다.

★영속 계약(WP-E design_run_store 선례 — 절대 제약):
- alembic 신규 헤드 없음. 기반 테이블은 design_run_store._ensure_schema(CREATE TABLE IF NOT EXISTS)를
  **재사용**하고(중복 DDL 금지), 오래된 테이블 대비 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS job_status`로
  컬럼만 멱등 보강한다. 원장(analysis_ledger) 무접촉.
- 테넌트 격리: 조회·전이 쿼리는 항상 tenant_id IS NOT DISTINCT FROM으로 스코프(IDOR 차단).

★상태전이 규칙(터미널 재취소=409):
- 비터미널(None·QUEUED·RUNNING)에서만 취소 가능. 터미널(SUCCEEDED·CANCELLED·FAILED) 재취소는 거부(409).
- 낙관적 잠금: UPDATE는 `job_status IS NOT DISTINCT FROM :expected` 가드로 lost-update를 막는다.
"""
from __future__ import annotations

import contextlib
from typing import Any

import structlog

from app.services.cad import design_run_store

logger = structlog.get_logger(__name__)

# ── 실행차원(job) 상태 — 승인차원(DRAFT/APPROVED)과 완전히 다른 축 ──
JOB_QUEUED = "QUEUED"
JOB_RUNNING = "RUNNING"
JOB_SUCCEEDED = "SUCCEEDED"
JOB_CANCELLED = "CANCELLED"
JOB_FAILED = "FAILED"

VALID_JOB_STATUSES: frozenset[str] = frozenset(
    {JOB_QUEUED, JOB_RUNNING, JOB_SUCCEEDED, JOB_CANCELLED, JOB_FAILED}
)
# 터미널(더 이상 전이 없음) — 재취소·재전이 시 409.
TERMINAL_JOB_STATUSES: frozenset[str] = frozenset({JOB_SUCCEEDED, JOB_CANCELLED, JOB_FAILED})

# 허용 전이표. 키 None = 아직 job이 시작 전(job_status 컬럼 NULL) 상태.
_TRANSITIONS: dict[str | None, frozenset[str]] = {
    None: frozenset({JOB_QUEUED, JOB_RUNNING, JOB_CANCELLED}),
    JOB_QUEUED: frozenset({JOB_RUNNING, JOB_CANCELLED, JOB_FAILED}),
    JOB_RUNNING: frozenset({JOB_SUCCEEDED, JOB_CANCELLED, JOB_FAILED}),
    JOB_SUCCEEDED: frozenset(),
    JOB_CANCELLED: frozenset(),
    JOB_FAILED: frozenset(),
}


# ══════════════════════════════════════════════════════════════════════════
# 순수 규칙 — 정규화·터미널·전이·취소 가능여부(DB 불요·결정적·단위테스트 대상)
# ══════════════════════════════════════════════════════════════════════════

def normalize_job_status(value: Any) -> str | None:
    """job_status 후보를 정규화한다. None/'' → None(=미시작). 나머지는 대문자 문자열."""
    if value is None:
        return None
    s = str(value).strip().upper()
    return s or None


def is_terminal(job_status: Any) -> bool:
    """터미널(SUCCEEDED/CANCELLED/FAILED) 여부. None·QUEUED·RUNNING은 False."""
    return normalize_job_status(job_status) in TERMINAL_JOB_STATUSES


def can_transition(current: Any, target: Any) -> tuple[bool, str]:
    """current → target 전이가 규칙상 허용인지(순수). target은 유효 상태여야 한다."""
    cur = normalize_job_status(current)
    tgt = normalize_job_status(target)
    if tgt not in VALID_JOB_STATUSES:
        return False, f"유효하지 않은 실행상태: {target}"
    if cur is not None and cur not in VALID_JOB_STATUSES:
        return False, f"유효하지 않은 현재 실행상태: {current}"
    if cur in TERMINAL_JOB_STATUSES:
        return False, f"터미널 상태({cur})에서는 더 이상 전이할 수 없습니다."
    allowed = _TRANSITIONS.get(cur, frozenset())
    if tgt not in allowed:
        return False, f"허용되지 않은 전이: {cur} → {tgt}"
    return True, "ok"


def can_cancel(current: Any) -> tuple[bool, str]:
    """취소 가능여부(순수) — 비터미널(None·QUEUED·RUNNING)만 취소 가능. 터미널은 거부(409 사상)."""
    cur = normalize_job_status(current)
    if cur in TERMINAL_JOB_STATUSES:
        return False, f"이미 종료된 실행({cur})은 취소할 수 없습니다."
    if cur is not None and cur not in VALID_JOB_STATUSES:
        return False, f"유효하지 않은 현재 실행상태: {current}"
    return True, "ok"


# ══════════════════════════════════════════════════════════════════════════
# 영속 — 스키마 보강(job_status 컬럼만·기반 테이블은 WP-E 재사용)
# ══════════════════════════════════════════════════════════════════════════
_JOB_SCHEMA_READY = False


async def _ensure_job_schema(db: Any) -> None:
    """design_runs 기반 테이블 보장(WP-E 재사용) + job_status 컬럼·인덱스 멱등 보강.

    ★그린필드 금지: 테이블 DDL을 다시 쓰지 않고 design_run_store._ensure_schema를 호출한다.
      오래된 배포에서 컬럼이 없을 수 있으므로 ADD COLUMN IF NOT EXISTS로만 방어적으로 보강한다.
    """
    global _JOB_SCHEMA_READY
    if _JOB_SCHEMA_READY:
        return
    from sqlalchemy import text

    await design_run_store._ensure_schema(db)  # 기반 테이블(멱등) — 중복 DDL 없음
    await db.execute(text(
        "ALTER TABLE design_runs ADD COLUMN IF NOT EXISTS job_status text"
    ))
    await db.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_design_runs_job_status ON design_runs (job_status)"
    ))
    await db.commit()
    _JOB_SCHEMA_READY = True


async def _read_job(db: Any, run_id: str, tenant_id: str | None) -> tuple[bool, str | None]:
    """(존재여부, 현재 job_status) 조회 — 테넌트 스코프. 존재하지 않으면 (False, None)."""
    from sqlalchemy import text

    row = (await db.execute(text(
        "SELECT job_status FROM design_runs WHERE run_id = :rid "
        "AND tenant_id IS NOT DISTINCT FROM :tid"
    ), {"rid": run_id, "tid": tenant_id})).first()
    if row is None:
        return False, None
    return True, normalize_job_status(row[0])


async def get_job(
    *, db: Any, run_id: str, tenant_id: str | None = None
) -> dict[str, Any] | None:
    """실행차원(job_status) 단건 조회 — 테넌트 스코프. 존재하지 않으면 None.

    ★승인차원 status는 여기서 읽지 않는다(차원 분리) — 결합 뷰는 라우터가 store.get_design_run과 합성.
    """
    await _ensure_job_schema(db)
    exists, cur = await _read_job(db, run_id, tenant_id)
    if not exists:
        return None
    return {"run_id": run_id, "job_status": cur}


async def set_job_status(
    *,
    db: Any,
    run_id: str,
    target: str,
    tenant_id: str | None = None,
    expected_current: str | None = None,
    require_expected: bool = False,
) -> dict[str, Any]:
    """실행차원 전이 — 규칙(can_transition) 통과 시에만 job_status를 갱신한다(낙관 잠금).

    반환 dict의 code: ok(성공)·not_found(run 없음)·conflict(불법 전이·버전 충돌).
    require_expected=True면 expected_current와 현재가 다를 때 conflict(If-Match 의미론).
    ★status(승인차원) 컬럼은 절대 건드리지 않는다.
    """
    tgt = normalize_job_status(target)
    if tgt not in VALID_JOB_STATUSES:
        return {"ok": False, "code": "conflict", "run_id": run_id,
                "message": f"유효하지 않은 실행상태: {target}"}
    await _ensure_job_schema(db)
    exists, current = await _read_job(db, run_id, tenant_id)
    if not exists:
        return {"ok": False, "code": "not_found", "run_id": run_id,
                "message": f"run_id={run_id} 없음(먼저 설계 실행 persist 필요)."}
    if require_expected and normalize_job_status(expected_current) != current:
        return {"ok": False, "code": "conflict", "run_id": run_id, "job_status": current,
                "message": f"버전 충돌: 기대 {expected_current} ≠ 현재 {current}."}
    ok, reason = can_transition(current, tgt)
    if not ok:
        return {"ok": False, "code": "conflict", "run_id": run_id, "job_status": current,
                "message": reason}
    from sqlalchemy import text

    try:
        res = await db.execute(text(
            # ★낙관 잠금: 현재값이 그대로일 때만 갱신(동시 전이 lost-update 방지). status 무접촉.
            "UPDATE design_runs SET job_status = :tgt, updated_at = now() "
            "WHERE run_id = :rid AND tenant_id IS NOT DISTINCT FROM :tid "
            "  AND job_status IS NOT DISTINCT FROM :cur"
        ), {"tgt": tgt, "rid": run_id, "tid": tenant_id, "cur": current})
        if int(getattr(res, "rowcount", 0) or 0) == 0:
            await db.rollback()
            return {"ok": False, "code": "conflict", "run_id": run_id, "job_status": current,
                    "message": "동시 전이로 상태가 변경되었습니다(재시도 필요)."}
        await db.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("job_status 전이 실패", err=str(e)[:160])
        with contextlib.suppress(Exception):
            await db.rollback()
        return {"ok": False, "code": "conflict", "run_id": run_id, "message": f"전이 저장 실패: {str(e)[:120]}"}

    return {"ok": True, "code": "ok", "run_id": run_id, "job_status": tgt, "previous": current}


async def cancel_job(
    *, db: Any, run_id: str, tenant_id: str | None = None
) -> dict[str, Any]:
    """실행 취소 — 비터미널만 CANCELLED로 전이. 터미널 재취소는 code=conflict(라우터 409).

    ★status(승인차원) 무접촉 — 실행 취소는 승인 여부와 독립이다(APPROVED여도 job은 CANCELLED 가능).
    """
    await _ensure_job_schema(db)
    exists, current = await _read_job(db, run_id, tenant_id)
    if not exists:
        return {"ok": False, "code": "not_found", "run_id": run_id,
                "message": f"run_id={run_id} 없음."}
    ok, reason = can_cancel(current)
    if not ok:
        return {"ok": False, "code": "conflict", "run_id": run_id, "job_status": current,
                "message": reason}
    from sqlalchemy import text

    try:
        res = await db.execute(text(
            "UPDATE design_runs SET job_status = :cancel, updated_at = now() "
            "WHERE run_id = :rid AND tenant_id IS NOT DISTINCT FROM :tid "
            "  AND job_status IS NOT DISTINCT FROM :cur"
        ), {"cancel": JOB_CANCELLED, "rid": run_id, "tid": tenant_id, "cur": current})
        if int(getattr(res, "rowcount", 0) or 0) == 0:
            await db.rollback()
            return {"ok": False, "code": "conflict", "run_id": run_id, "job_status": current,
                    "message": "동시 전이로 상태가 변경되었습니다(재시도 필요)."}
        await db.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("job 취소 실패", err=str(e)[:160])
        with contextlib.suppress(Exception):
            await db.rollback()
        return {"ok": False, "code": "conflict", "run_id": run_id, "message": f"취소 저장 실패: {str(e)[:120]}"}

    return {"ok": True, "code": "ok", "run_id": run_id, "job_status": JOB_CANCELLED, "previous": current}
