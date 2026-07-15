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

★테넌트 격리(분리 리뷰 HIGH-1 교정 — §13 IDOR 재발 패턴 방지): 심층방어 2중화.
  ①run_id 자체가 tenant_id를 해시 입력에 포함해 테넌트별로 분할된다(_fingerprint) — 서로 다른
    테넌트가 동일 게이트값을 신고해도 다른 run_id가 나온다.
  ②그와 별개로 조회·승인 쿼리는 항상 `tenant_id IS NOT DISTINCT FROM :tid`로 스코프한다 —
    ①이 우회되거나 tenant_id가 비어있는 경계 케이스에도 교차테넌트 조회/승인을 차단한다.

★게이트 status 신뢰경계(분리 리뷰 MEDIUM-3 교정): assess_site_basis()의 access_status/
dev_act_status는 기본적으로 caller 자기신고(요청 본문)다 — 이는 위조 가능한 입력이다.
site_context(부지분석 result와 동형 dict)가 함께 오면, 권위 서비스(access_basis_service.
assess_access·dev_act_permit_gate.assess_dev_act_permit)로 서버측 재도출한 뒤 caller 신고값과
교차검증한다(reconcile_status) — 불일치 시 더 보수적인(차단쪽) 값을 채택하고 그 사실을
gates[].source에 "server_derived_conflict_resolved"로 남긴다. site_context가 없으면
"caller_declared"로 정직하게 표기하고, 그 경우엔 cap_status_by_trust가 자동판정을 ANALYZED로
승격시키지 않는다(REVIEW_REQUIRED 상한 — 미검증 자기신고만으로 인간승인 대기자격을 얻지 못한다).
"""
from __future__ import annotations

import contextlib
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
    """projection·이벤트 테이블 멱등 보장(부팅 대기 없이 최초 호출 시 lazy 생성).

    ★권고②(공용 패턴 교정 — growth/schema_guard.py 선례 정합·design_run_store와 동일 방식):
      _SCHEMA_READY는 DDL '커밋 성공 후'에만 세팅한다. 커밋 전에 세팅하면 이후 데이터 트랜잭션이
      롤백될 때 DDL도 되돌려지는데 플래그는 ready로 남아 다음 호출이 생성을 건너뛴다('유령 ready').
      DDL을 즉시 확정(commit)하면 이후 DML이 실패해도 스키마는 남는다.
    """
    global _SCHEMA_READY
    if _SCHEMA_READY and not force:
        return
    from sqlalchemy import text

    await db.execute(text(_STATE_DDL))
    await db.execute(text(_EVENT_DDL))
    for ix in _INDEXES:
        await db.execute(text(ix))
    await db.commit()  # ★DDL 즉시 확정 — 커밋 성공 후에만 ready 세팅(유령 ready 방지·schema_guard 동형).
    _SCHEMA_READY = True


async def _safe_rollback(db: Any) -> None:
    """오염된 세션이 get_db 티어다운 commit을 깨지 않도록 best-effort rollback(LOW-5 교정).

    growth/schema_guard.py 선례(contextlib.suppress) 재사용 — rollback 자체의 실패도 흡수한다.
    """
    with contextlib.suppress(Exception):
        await db.rollback()


# ── 결정론 run_id(⑦ provenance triad 패턴 재사용 — compute_input_hash) ──────────

def _fingerprint(
    tenant_id: str | None, access_status: str | None, dev_act_status: str | None,
    rights_confirmed: bool | None, pnu: str | None, address: str | None, project_id: str | None,
) -> dict[str, Any]:
    """run_id 해시 입력 — tenant_id 포함(HIGH-1 교정: run_id 자체를 테넌트별로 분할)."""
    return {
        "tenant_id": tenant_id, "access_status": access_status, "dev_act_status": dev_act_status,
        "rights_confirmed": rights_confirmed, "pnu": pnu, "address": address, "project_id": project_id,
    }


def _content_hash(fingerprint: dict[str, Any]) -> str:
    from app.services.cad.provenance import compute_input_hash
    return compute_input_hash(fingerprint)


def _run_id(content_hash: str) -> str:
    """basis_ 접두 + 입력해시 앞 16자 — 같은 입력(테넌트 포함)이면 같은 run_id(멱등)."""
    return f"basis_{content_hash[:16]}"


def _gates_to_json(gates: list[GateResult]) -> str:
    return json.dumps([g.to_dict() for g in gates], ensure_ascii=False)


async def _reconcile_gate_statuses(
    *, access_status: str | None, dev_act_status: str | None, site_context: dict[str, Any] | None,
) -> tuple[str | None, str, str | None, str]:
    """MEDIUM-3 교정 — site_context가 있으면 권위 서비스로 재도출해 caller 신고값과 교차검증.

    반환: (effective_access_status, access_source, effective_dev_act_status, dev_act_source).
    재도출 자체가 실패(예외)해도 caller 신고값으로 정직 폴백한다(주 경로를 깨지 않음, best-effort).
    """
    if not site_context:
        return access_status, "caller_declared", dev_act_status, "caller_declared"

    authoritative_access: str | None = None
    try:
        from app.services.access.access_basis_service import assess_access
        authoritative_access = assess_access(dict(site_context)).status
    except Exception as e:  # noqa: BLE001 — 재도출 실패는 caller 신고로 폴백(주 경로 무손상).
        logger.warning("access 권위 재도출 실패 — caller 신고값으로 폴백", err=str(e)[:120])

    authoritative_dev_act: str | None = None
    try:
        from app.services.permit.dev_act_permit_gate import assess_dev_act_permit
        dev_result = assess_dev_act_permit(dict(site_context))
        authoritative_dev_act = (dev_result or {}).get("status")
    except Exception as e:  # noqa: BLE001
        logger.warning("dev_act_permit 권위 재도출 실패 — caller 신고값으로 폴백", err=str(e)[:120])

    eff_access, access_source = sbs.reconcile_status(access_status, authoritative_access)
    eff_dev_act, dev_act_source = sbs.reconcile_status(dev_act_status, authoritative_dev_act)
    return eff_access, access_source, eff_dev_act, dev_act_source


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
    site_context: dict[str, Any] | None = None,
    created_by: str | None = None,
) -> dict[str, Any]:
    """P2·P3·P4 P0 게이트 자동집계 → ANALYZED/REVIEW_REQUIRED(원장 감사기록 포함).

    - site_context(선택) 제공 시 access/dev_act status를 권위 서비스로 재도출·교차검증한다
      (MEDIUM-3). 미제공 시 caller 신고값을 쓰되, ANALYZED 승격은 REVIEW_REQUIRED로 상한된다.
    - 같은 체인(tenant/pnu/project_id)에 기존 APPROVED 행이 있고 이번 게이트 content_hash가
      다르면, 그 행을 STALE로 강등한다(STALE 전파 실경로 — evidence_changed 액션 경유).
    - ★MEDIUM-2 교정: 이번 호출의 run_id(=content_hash)와 정확히 같은 기존 행이 이미 APPROVED
      (=동일 내용 재제출)면, 인간승인을 무음 취소하지 않고 그 상태를 그대로 반환한다(no-op).
    """
    all_clear_declared, _ = sbs.aggregate_p0(
        access_status=access_status, dev_act_status=dev_act_status, rights_confirmed=rights_confirmed,
    )
    # DB·재도출 모두 실패해도 정직한 판정을 반환하기 위한 폴백 기본값(아래 try에서 갱신됨).
    new_status = sbs.classify_after_assess(all_clear_declared)
    gates: list[GateResult] = []
    content_hash = _content_hash(
        _fingerprint(tenant_id, access_status, dev_act_status, rights_confirmed, pnu, address, project_id)
    )
    run_id = _run_id(content_hash)

    stale_propagated: list[str] = []
    ledger_result: dict[str, Any] | None = None
    try:
        eff_access, access_source, eff_dev_act, dev_act_source = await _reconcile_gate_statuses(
            access_status=access_status, dev_act_status=dev_act_status, site_context=site_context,
        )
        all_clear, gates = sbs.aggregate_p0(
            access_status=eff_access, dev_act_status=eff_dev_act, rights_confirmed=rights_confirmed,
            access_source=access_source, dev_act_source=dev_act_source,
        )
        # 재도출로 실효 게이트값이 바뀔 수 있으므로 content_hash·run_id를 실효값 기준으로 재계산.
        content_hash = _content_hash(
            _fingerprint(tenant_id, eff_access, eff_dev_act, rights_confirmed, pnu, address, project_id)
        )
        run_id = _run_id(content_hash)

        await _ensure_schema(db)
        from sqlalchemy import text

        # ── 이 run_id(=이번 content_hash) 자체의 기존 행 확인(HIGH-1: 테넌트 스코프) ──
        self_row = (await db.execute(text(
            "SELECT artifact_status, content_hash, basis_status, gates "
            "FROM site_basis_state WHERE run_id = :rid AND tenant_id IS NOT DISTINCT FROM :tid"
        ), {"rid": run_id, "tid": tenant_id})).first()

        existing_status: ArtifactStatus | None = None
        if self_row is not None:
            existing_status = ArtifactStatus(self_row[0])
            if existing_status == ArtifactStatus.APPROVED:
                # run_id는 content_hash 유래라 자기 자신과는 절대 stale일 수 없다(동일 입력=동일
                # 해시). 그럼에도 명시 비교해 방어한다(해시 함수를 맹신하지 않는 이중 안전장치).
                if not sbs.is_stale(self_row[1], content_hash):
                    # ★MEDIUM-2 — 동일 내용 재분석이 기존 인간승인(APPROVED)을 무음 취소하지
                    #   않도록 no-op으로 현재 상태를 그대로 반환한다(재기록·재강등 없음).
                    return {
                        "run_id": run_id, "artifact_status": existing_status.value,
                        "basis_status": self_row[2], "gates": self_row[3] or [],
                        "content_hash": self_row[1], "stale_propagated": [], "ledger": None,
                        "noop_preserved_approval": True,
                    }
                # 이론상 도달 불가(같은 run_id는 같은 content_hash)지만, 방어적으로 evidence_changed
                # 경로를 태워 STALE로 강등한 뒤 계속 진행한다(조용한 무단 강등 대신 이벤트 기록).
                degraded = sbs.apply_transition(existing_status, "evidence_changed")
                await db.execute(text(
                    "UPDATE site_basis_state SET artifact_status = :st, basis_status = :bst, updated_at = now() "
                    "WHERE run_id = :rid"
                ), {"st": degraded.value, "bst": sbs.basis_status_of(degraded).value, "rid": run_id})
                await db.execute(text(
                    "INSERT INTO site_basis_transition_event"
                    "(run_id, from_status, to_status, action, actor, reason, content_hash) "
                    "VALUES (:rid, :frm, :to, 'evidence_changed', 'system', :reason, :ch)"
                ), {"rid": run_id, "frm": existing_status.value, "to": degraded.value,
                    "reason": "자기 run_id 내 content_hash 불일치 감지(방어적 강등)", "ch": content_hash})
                existing_status = degraded

        source_status = existing_status if existing_status is not None else ArtifactStatus.DRAFT
        new_status = sbs.apply_transition(source_status, "assess", all_p0_clear=all_clear)
        # ★MEDIUM-3 — 미검증(caller_declared) P0만으로는 ANALYZED(인간승인 대기자격) 승격 금지.
        new_status = sbs.cap_status_by_trust(new_status, gates)

        # ── STALE 전파: 같은 체인(tenant/pnu/project_id, 테넌트 스코프)의 '다른' run_id APPROVED
        #    행이 다른 content_hash면 강등 ──
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
        # ★MEDIUM-2 — from_status에 실제 이전 상태 기록(기존엔 항상 NULL이었음).
        await db.execute(text(
            "INSERT INTO site_basis_transition_event"
            "(run_id, from_status, to_status, action, actor, reason, content_hash) "
            "VALUES (:rid, :frm, :to, 'assess', :actor, :reason, :ch)"
        ), {"rid": run_id, "frm": (existing_status.value if existing_status else None),
            "to": new_status.value, "actor": created_by or "system",
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
        await _safe_rollback(db)

    if not gates:
        # 재도출·집계 단계에서 예외가 나 gates가 비었으면(극히 드묾), caller 신고값 기준으로
        # 최소한의 정직한 게이트 스냅샷을 채워 반환한다(빈 배열로 무날조 응답하지 않음).
        _, gates = sbs.aggregate_p0(
            access_status=access_status, dev_act_status=dev_act_status, rights_confirmed=rights_confirmed,
        )

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
    tenant_id: str | None = None,
    access_status: str | None = None,
    dev_act_status: str | None = None,
    rights_confirmed: bool | None = None,
) -> dict[str, Any]:
    """인간승인 액션 — ANALYZED 상태 + 승인시점 P0 전건 재확인 충족일 때만 APPROVED(AUTHORIZED).

    ★TOCTOU 방지: 저장된 판정만 신뢰하지 않고, 호출측이 최신 게이트값을 넘기면 그 값으로 P0을
    재계산한다(승인 직전 괴리 차단). 값을 안 넘기면 저장 시점 gates 스냅샷을 재사용한다.
    ★HIGH-1(테넌트 격리): run_id 조회를 tenant_id로 스코프한다 — 다른 테넌트의 run_id는
    "없음"과 동일하게 취급(존재 여부 자체를 노출하지 않는 정직한 404류 응답, IDOR 오라클 방지).
    ★후속 결정 필요(제품 정책, 코드 변경 없음): 현재 승인 권한은 get_current_user(인증)만
    요구한다 — "승인 가능 역할/티어"(예: 관리자·특정 직무)를 별도로 강제할지는 RBAC 계층의
    제품 결정 사항으로 이 WP 범위 밖이다(라우터 basis.py docstring에도 동일 명시).
    """
    from sqlalchemy import text

    await _ensure_schema(db)
    row = (await db.execute(text(
        "SELECT artifact_status, gates, content_hash, tenant_id, pnu, project_id "
        "FROM site_basis_state WHERE run_id = :rid AND tenant_id IS NOT DISTINCT FROM :tid"
    ), {"rid": run_id, "tid": tenant_id})).first()
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
        await _safe_rollback(db)

    return {
        "ok": True, "run_id": run_id, "artifact_status": new_status.value,
        "basis_status": basis_status.value, "approved_by": approved_by,
        "gates": stored_gates, "content_hash": row[2], "stale_propagated": [], "ledger": ledger_result,
    }


async def get_site_basis(*, db: Any, run_id: str, tenant_id: str | None = None) -> dict[str, Any] | None:
    """현재 상태 조회(projection 테이블 단건) — HIGH-1: tenant_id 스코프(교차테넌트 조회 차단)."""
    from sqlalchemy import text

    await _ensure_schema(db)
    row = (await db.execute(text(
        "SELECT run_id, artifact_status, basis_status, gates, content_hash, approved_by "
        "FROM site_basis_state WHERE run_id = :rid AND tenant_id IS NOT DISTINCT FROM :tid"
    ), {"rid": run_id, "tid": tenant_id})).first()
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

    dev_act_status는 이 진입점에서 항상 권위 서비스(build_dev_act_permit_gate)의 실 산출값이므로
    source="server_derived"로 표기한다(caller 자기신고가 아님 — 호출측이 API 요청 본문이 아니라
    design_v61 내부에서 직접 그 서비스를 호출한 결과를 넘기기 때문).

    ★WP-A 배선(항목1) 이후 access_status도 design_v61이 build_access_basis_gate(권위 서비스)를
    직접 호출한 산출값을 넘긴다 — 하지만 그 호출부(design_v61._attach_special_parcel_gate)에는
    도로 실데이터(road_contact·road_width_m 등)가 없어 대부분 "신호 없음" 기본값으로만 판정되므로,
    여기서는 계속 source 기본값(caller_declared 상당의 보수 취급)을 유지해 P0 청산을 과신하지
    않는다(cap_status_by_trust가 ANALYZED 승격을 REVIEW_REQUIRED로 막는 기존 보수 정책 그대로).
    access_status를 실제로 뒷받침하는 도로 실데이터가 이 진입점에 흐르게 되면(후속 WP) 그때
    source="server_derived"로 승격하는 것이 맞다 — 지금은 과신을 피한다.

    ★이 함수는 절대 AUTHORIZED를 반환하지 않는다(basis_status 고정 ADVISORY) — 인간승인 액션
    (POST /api/v1/basis/{run_id}/approve)을 거치지 않는 자동경로이기 때문이다. 설계생성 소비처는
    all_p0_clear=False일 때 정직 경고를 표시하고, AUTHORIZED 승격은 별도 승인 API로 유도한다.
    """
    all_clear, gates = sbs.aggregate_p0(
        access_status=access_status, dev_act_status=dev_act_status, rights_confirmed=rights_confirmed,
        dev_act_source="server_derived",
    )
    artifact_status = sbs.classify_after_assess(all_clear)
    artifact_status = sbs.cap_status_by_trust(artifact_status, gates)
    return {
        "artifact_status": artifact_status.value,
        "basis_status": sbs.BasisStatus.ADVISORY.value,  # 자동경로 고정(승인 없이는 AUTHORIZED 불가).
        "all_p0_clear": all_clear,
        "gates": [g.to_dict() for g in gates],
        "note": ("자동판정(참고용) — AUTHORIZED 전이는 명시적 인간승인 API"
                 "(POST /api/v1/basis/{run_id}/approve)로만 가능합니다."),
    }
