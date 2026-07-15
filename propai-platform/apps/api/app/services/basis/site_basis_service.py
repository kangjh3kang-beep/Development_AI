"""부지기반(site basis) 조립자 — P0 게이트 집계 + 상태 영속화 + 원장 기록(명세 WP-G).

WP-A(P4 access_basis)·WP-B(P2 dev_act_permit_gate)·P3(권리 보수 게이트) 판정을 집계해
ADVISORY/AUTHORIZED를 분리한다. 상태 판정·전이 규칙 자체는 site_basis_state.py(순수 함수)가
전담하고, 이 파일은 그 결과를 (1) 가변 projection 테이블에 저장, (2) 불변 analysis_ledger에
append-only 감사기록을 남기는 async 조립만 담당한다.

★원장 무변이 설계(계획 R1 적대검증 확정 — 절대 제약)
------------------------------------------------------
analysis_ledger(해시체인 append-only) 테이블 정의는 이 파일에서 단 한 줄도 건드리지 않는다.
가변 상태(현재 artifact_status·basis_status)는 전용 projection 테이블(site_basis_state,
run_id 키)에만 저장하고, 그 변경 이력은 append-only 이벤트 테이블(site_basis_transition_event,
INSERT 전용·UPDATE/DELETE 없음)로 별도 남긴다. 두 신규 테이블 모두 growth/schema_guard.py 선례
(부팅 시 CREATE TABLE IF NOT EXISTS — alembic 신규 헤드 없이 멱등 보장)를 그대로 재사용한다.
analysis_ledger에는 append_analysis()로 "site_basis" 분석유형의 감사 스냅샷만 기존 방식대로
새 버전 append한다(㉔ 재사용 — 스키마 변경 0, 새 행 추가만).

★"인간승인 없는 AUTHORIZED 0": approve_site_basis()만이 APPROVED(→AUTHORIZED)로 전이시킬 수
있고, 그 함수는 approved_by(인간 승인자)가 비어있으면 site_basis_state.can_approve()가 거부한다.
assess_site_basis()·gate_design_entry()는 절대 APPROVED를 만들지 않는다(구조적 보장).
"""
from __future__ import annotations

import json
from typing import Any

import structlog

from app.services.basis import site_basis_state as sbs
from app.services.basis.site_basis_state import ArtifactStatus, GateResult

logger = structlog.get_logger(__name__)

# ── schema_guard 패턴(growth/schema_guard.py 선례) — 신규 alembic 헤드 없이 멱등 보장 ──
_STATE_DDL = (
    "CREATE TABLE IF NOT EXISTS site_basis_state ("
    "  run_id text PRIMARY KEY,"
    "  tenant_id text,"
    "  pnu text,"
    "  address_norm text,"
    "  project_id text,"
    "  artifact_status text NOT NULL,"
    "  basis_status text NOT NULL,"
    "  gates jsonb NOT NULL,"
    "  content_hash text,"
    "  approved_by text,"
    "  approved_at timestamptz,"
    "  created_at timestamptz NOT NULL DEFAULT now(),"
    "  updated_at timestamptz NOT NULL DEFAULT now()"
    ")"
)
# append-only 상태전이 이벤트 — INSERT만 수행(이 파일 어디에도 UPDATE/DELETE 없음).
_EVENT_DDL = (
    "CREATE TABLE IF NOT EXISTS site_basis_transition_event ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  run_id text NOT NULL,"
    "  from_status text,"
    "  to_status text NOT NULL,"
    "  action text NOT NULL,"
    "  actor text,"
    "  reason text,"
    "  content_hash text,"
    "  created_at timestamptz NOT NULL DEFAULT now()"
    ")"
)
_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_sbs_chain ON site_basis_state (tenant_id, pnu, project_id)",
    "CREATE INDEX IF NOT EXISTS idx_sbs_status ON site_basis_state (artifact_status)",
    "CREATE INDEX IF NOT EXISTS idx_sbte_run ON site_basis_transition_event (run_id, created_at)",
)

_SCHEMA_READY = False


async def _ensure_schema(db: Any, force: bool = False) -> None:
    """projection·이벤트 테이블 멱등 보장(부팅 대기 없이 최초 호출 시 lazy 생성)."""
    global _SCHEMA_READY
    if _SCHEMA_READY and not force:
        return
    from sqlalchemy import text

    await db.execute(text(_STATE_DDL))
    await db.execute(text(_EVENT_DDL))
    for ix in _INDEXES:
        await db.execute(text(ix))
    _SCHEMA_READY = True


# ── 결정론 run_id(⑦ provenance triad 패턴 재사용 — compute_input_hash) ──────────

def _fingerprint(
    access_status: str | None, dev_act_status: str | None, rights_confirmed: bool | None,
    pnu: str | None, address: str | None, project_id: str | None,
) -> dict[str, Any]:
    return {
        "access_status": access_status, "dev_act_status": dev_act_status,
        "rights_confirmed": rights_confirmed, "pnu": pnu, "address": address, "project_id": project_id,
    }


def _content_hash(fingerprint: dict[str, Any]) -> str:
    from app.services.cad.provenance import compute_input_hash
    return compute_input_hash(fingerprint)


def _run_id(content_hash: str) -> str:
    """basis_ 접두 + 입력해시 앞 16자 — 같은 입력이면 같은 run_id(멱등)."""
    return f"basis_{content_hash[:16]}"


def _gates_to_json(gates: list[GateResult]) -> str:
    return json.dumps([g.to_dict() for g in gates], ensure_ascii=False)


# ══════════════════════════════════════════════════════════════════════════
# 자동 조립 — assess (AUTHORIZED로는 절대 도달하지 않는다)
# ══════════════════════════════════════════════════════════════════════════

async def assess_site_basis(
    *,
    db: Any,
    tenant_id: str | None = None,
    pnu: str | None = None,
    address: str | None = None,
    project_id: str | None = None,
    access_status: str | None = None,
    dev_act_status: str | None = None,
    rights_confirmed: bool | None = None,
    created_by: str | None = None,
) -> dict[str, Any]:
    """P2·P3·P4 P0 게이트 자동집계 → ANALYZED/REVIEW_REQUIRED(원장 감사기록 포함).

    같은 체인(tenant/pnu/project_id)에 기존 APPROVED 행이 있고 이번 게이트 content_hash가
    다르면, 그 행을 STALE로 강등한다(STALE 전파 실경로 — evidence_changed 액션 경유).
    """
    all_clear, gates = sbs.aggregate_p0(
        access_status=access_status, dev_act_status=dev_act_status, rights_confirmed=rights_confirmed,
    )
    new_status = sbs.classify_after_assess(all_clear)
    fingerprint = _fingerprint(access_status, dev_act_status, rights_confirmed, pnu, address, project_id)
    content_hash = _content_hash(fingerprint)
    run_id = _run_id(content_hash)

    stale_propagated: list[str] = []
    ledger_result: dict[str, Any] | None = None
    try:
        await _ensure_schema(db)
        from sqlalchemy import text

        # ── STALE 전파: 같은 체인의 기존 APPROVED 행이 다른 content_hash면 강등 ──
        prior_rows = (await db.execute(text(
            "SELECT run_id, artifact_status, content_hash FROM site_basis_state "
            "WHERE tenant_id IS NOT DISTINCT FROM :tid AND pnu IS NOT DISTINCT FROM :pnu "
            "AND project_id IS NOT DISTINCT FROM :pid AND artifact_status = :approved"
        ), {"tid": tenant_id, "pnu": pnu, "pid": project_id, "approved": ArtifactStatus.APPROVED.value})).all()
        for prior_run_id, prior_status, prior_hash in prior_rows:
            if prior_run_id == run_id or not sbs.is_stale(prior_hash, content_hash):
                continue
            degraded = sbs.apply_transition(ArtifactStatus(prior_status), "evidence_changed")
            await db.execute(text(
                "UPDATE site_basis_state SET artifact_status = :st, basis_status = :bst, updated_at = now() "
                "WHERE run_id = :rid"
            ), {"st": degraded.value, "bst": sbs.basis_status_of(degraded).value, "rid": prior_run_id})
            await db.execute(text(
                "INSERT INTO site_basis_transition_event"
                "(run_id, from_status, to_status, action, actor, reason, content_hash) "
                "VALUES (:rid, :frm, :to, 'evidence_changed', 'system', :reason, :ch)"
            ), {"rid": prior_run_id, "frm": prior_status, "to": degraded.value,
                "reason": "의존 evidence content_hash 변경 감지(재분석 유입) — 기존 승인 결과 강등",
                "ch": content_hash})
            stale_propagated.append(prior_run_id)

        gates_json = _gates_to_json(gates)
        basis_status = sbs.basis_status_of(new_status)
        await db.execute(text(
            "INSERT INTO site_basis_state"
            "(run_id, tenant_id, pnu, address_norm, project_id, artifact_status, basis_status, "
            " gates, content_hash, updated_at) "
            "VALUES (:rid, :tid, :pnu, :addr, :pid, :ast, :bst, CAST(:gates AS jsonb), :ch, now()) "
            "ON CONFLICT (run_id) DO UPDATE SET "
            "  artifact_status = EXCLUDED.artifact_status, basis_status = EXCLUDED.basis_status, "
            "  gates = EXCLUDED.gates, updated_at = now()"
        ), {"rid": run_id, "tid": tenant_id, "pnu": pnu, "addr": address, "pid": project_id,
            "ast": new_status.value, "bst": basis_status.value, "gates": gates_json, "ch": content_hash})
        await db.execute(text(
            "INSERT INTO site_basis_transition_event"
            "(run_id, from_status, to_status, action, actor, reason, content_hash) "
            "VALUES (:rid, NULL, :to, 'assess', :actor, :reason, :ch)"
        ), {"rid": run_id, "to": new_status.value, "actor": created_by or "system",
            "reason": "; ".join(g.reason for g in gates), "ch": content_hash})
        await db.commit()

        # ㉔ 재사용 — analysis_ledger는 append_analysis 그대로(새 버전 append만, 스키마 무변이).
        from app.services.ledger.ledger_adapters import record_user_analysis

        ledger_result = await record_user_analysis(
            analysis_type="site_basis", kind="site_basis",
            summary={"run_id": run_id, "artifact_status": new_status.value,
                     "basis_status": basis_status.value, "gates": [g.to_dict() for g in gates],
                     "content_hash": content_hash},
            tenant_id=tenant_id, project_id=project_id, pnu=pnu, address=address,
            source="site_basis_assess", created_by=created_by,
        )
    except Exception as e:  # noqa: BLE001 — 영속 실패해도 판정 자체는 정직하게 반환(best-effort).
        logger.warning("site_basis 영속 실패", err=str(e)[:160])

    return {
        "run_id": run_id, "artifact_status": new_status.value,
        "basis_status": sbs.basis_status_of(new_status).value,
        "gates": [g.to_dict() for g in gates], "content_hash": content_hash,
        "stale_propagated": stale_propagated, "ledger": ledger_result,
    }


# ══════════════════════════════════════════════════════════════════════════
# 인간승인 액션 — approve (AUTHORIZED로 도달하는 유일한 경로)
# ══════════════════════════════════════════════════════════════════════════

async def approve_site_basis(
    *,
    db: Any,
    run_id: str,
    approved_by: str,
    access_status: str | None = None,
    dev_act_status: str | None = None,
    rights_confirmed: bool | None = None,
) -> dict[str, Any]:
    """인간승인 액션 — ANALYZED 상태 + 승인시점 P0 전건 재확인 충족일 때만 APPROVED(AUTHORIZED).

    ★TOCTOU 방지: 저장된 판정만 신뢰하지 않고, 호출측이 최신 게이트값을 넘기면 그 값으로 P0을
    재계산한다(승인 직전 괴리 차단). 값을 안 넘기면 저장 시점 gates 스냅샷을 재사용한다.
    """
    from sqlalchemy import text

    await _ensure_schema(db)
    row = (await db.execute(text(
        "SELECT artifact_status, gates, content_hash, tenant_id, pnu, project_id "
        "FROM site_basis_state WHERE run_id = :rid"
    ), {"rid": run_id})).first()
    if row is None:
        return {"ok": False, "message": f"run_id={run_id} 없음(먼저 /basis/assess 호출 필요)."}

    current = ArtifactStatus(row[0])
    stored_gates = row[1] or []

    recheck_provided = access_status is not None or dev_act_status is not None or rights_confirmed is not None
    if recheck_provided:
        all_clear, _ = sbs.aggregate_p0(
            access_status=access_status, dev_act_status=dev_act_status, rights_confirmed=rights_confirmed,
        )
    else:
        all_clear = bool(stored_gates) and all(bool(g.get("clear")) for g in stored_gates)

    ok, reason = sbs.can_approve(current, all_clear, approved_by)
    if not ok:
        return {"ok": False, "message": reason, "run_id": run_id, "artifact_status": current.value}

    new_status = sbs.apply_transition(current, "approve", approved_by=approved_by, all_p0_clear=all_clear)
    basis_status = sbs.basis_status_of(new_status)

    ledger_result: dict[str, Any] | None = None
    try:
        await db.execute(text(
            "UPDATE site_basis_state SET artifact_status = :st, basis_status = :bst, "
            "approved_by = :by, approved_at = now(), updated_at = now() WHERE run_id = :rid"
        ), {"st": new_status.value, "bst": basis_status.value, "by": approved_by, "rid": run_id})
        await db.execute(text(
            "INSERT INTO site_basis_transition_event"
            "(run_id, from_status, to_status, action, actor, reason) "
            "VALUES (:rid, :frm, :to, 'approve', :actor, :reason)"
        ), {"rid": run_id, "frm": current.value, "to": new_status.value, "actor": approved_by,
            "reason": "인간승인 — P0 전건 충족 확인됨"})
        await db.commit()

        from app.services.ledger.ledger_adapters import record_user_analysis

        ledger_result = await record_user_analysis(
            analysis_type="site_basis", kind="site_basis_approval",
            summary={"run_id": run_id, "artifact_status": new_status.value,
                     "basis_status": basis_status.value, "approved_by": approved_by},
            tenant_id=row[3], project_id=row[5], pnu=row[4],
            source="site_basis_approve", created_by=approved_by,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("site_basis 승인 영속 실패", err=str(e)[:160])

    return {
        "ok": True, "run_id": run_id, "artifact_status": new_status.value,
        "basis_status": basis_status.value, "approved_by": approved_by,
        "gates": stored_gates, "content_hash": row[2], "stale_propagated": [], "ledger": ledger_result,
    }


async def get_site_basis(*, db: Any, run_id: str) -> dict[str, Any] | None:
    """현재 상태 조회(projection 테이블 단건)."""
    from sqlalchemy import text

    await _ensure_schema(db)
    row = (await db.execute(text(
        "SELECT run_id, artifact_status, basis_status, gates, content_hash, approved_by "
        "FROM site_basis_state WHERE run_id = :rid"
    ), {"rid": run_id})).first()
    if row is None:
        return None
    return {
        "run_id": row[0], "artifact_status": row[1], "basis_status": row[2],
        "gates": row[3] or [], "content_hash": row[4], "approved_by": row[5],
        "stale_propagated": [], "ledger": None,
    }


# ══════════════════════════════════════════════════════════════════════════
# 하류(설계생성 진입) 게이트 자동 결선 — 순수·DB 불요(best-effort 부착용)
# ══════════════════════════════════════════════════════════════════════════

def gate_design_entry(
    *,
    access_status: str | None = None,
    dev_act_status: str | None = None,
    rights_confirmed: bool | None = None,
) -> dict[str, Any]:
    """설계생성 진입점(매스 SSOT 등) additive 부착용 — DB 불요 순수 자동판정 스냅샷.

    ★이 함수는 절대 AUTHORIZED를 반환하지 않는다(basis_status 고정 ADVISORY) — 인간승인 액션
    (POST /api/v1/basis/{run_id}/approve)을 거치지 않는 자동경로이기 때문이다. 설계생성 소비처는
    all_p0_clear=False일 때 정직 경고를 표시하고, AUTHORIZED 승격은 별도 승인 API로 유도한다.
    """
    all_clear, gates = sbs.aggregate_p0(
        access_status=access_status, dev_act_status=dev_act_status, rights_confirmed=rights_confirmed,
    )
    artifact_status = sbs.classify_after_assess(all_clear)
    return {
        "artifact_status": artifact_status.value,
        "basis_status": sbs.BasisStatus.ADVISORY.value,  # 자동경로 고정(승인 없이는 AUTHORIZED 불가).
        "all_p0_clear": all_clear,
        "gates": [g.to_dict() for g in gates],
        "note": ("자동판정(참고용) — AUTHORIZED 전이는 명시적 인간승인 API"
                 "(POST /api/v1/basis/{run_id}/approve)로만 가능합니다."),
    }
