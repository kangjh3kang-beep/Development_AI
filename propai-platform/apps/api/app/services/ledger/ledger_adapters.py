"""산출물 → 분석원장 어댑터(Phase 0 unit d + payload 규약).

design_audit(8엔진)·feasibility 커밋·domain_agent 태스크의 산출물을 원장 append payload로
정규화하는 순수 매퍼 + best-effort 기록 래퍼. 기존 테이블/모델은 그대로 두고(불변) 원장에
'추가로' 일원화한다(요약·핵심 필드만 — 원시 대용량은 기존 테이블에 잔류).

payload 규약(반복루프 read 전제): 모든 payload는 schema_version+kind 포함. design_audit는
비교·재계산 핵심(check_id/status/current/limit)을 findings_brief로 보존하고, 원본 행은
backlink(audit_id/task_id)로 역추적. analysis_type은 read 성장루프 키(feasibility 등)와
충돌하지 않게 분리(feasibility_vcs).
"""
from __future__ import annotations

from typing import Any

from app.services.ledger import analysis_ledger_service as ledger


# ── 순수 매퍼(무DB·결정적) ──

def design_audit_to_ledger(result: dict[str, Any], *, audit_id: str | None = None) -> dict[str, Any]:
    """8엔진 design_audit 결과 dict → 원장 payload(핵심 요약 + 비교용 findings_brief)."""
    overall = result.get("overall") or {}
    findings = result.get("findings") or []
    payload: dict[str, Any] = {
        "kind": "design_audit",
        "schema_version": result.get("schema_version") or "design_audit/v1",
        "zone_type": result.get("zone_type"),
        "sigungu": result.get("sigungu"),
        "verdict": overall.get("verdict"),
        "counts": overall.get("counts") or {},
        "engines": result.get("engines") or {},
        "findings_count": len(findings),
        # 비교·재계산 핵심만 보존(대용량 legal_refs/improvement 본문 제외).
        "findings_brief": [
            {"check_id": f.get("check_id"), "status": f.get("status"),
             "current": f.get("current"), "limit": f.get("limit")}
            for f in findings
        ],
    }
    if audit_id is not None:                 # 원본 design_audits 행 역추적(없으면 키 생략 — 정직)
        payload["audit_id"] = audit_id
    return payload


def feasibility_commit_to_ledger(commit: dict[str, Any]) -> dict[str, Any]:
    """version_control_db.commit() 반환 dict → 원장 payload."""
    return {
        "kind": "feasibility_commit",
        "schema_version": "feasibility_vcs/v1",
        "sha": commit.get("sha"),
        "parent_sha": commit.get("parent_sha"),
        "message": commit.get("message"),
        "author": commit.get("author"),
        "timestamp": commit.get("timestamp"),
    }


def domain_agent_task_to_ledger(task: dict[str, Any]) -> dict[str, Any]:
    """domain_agent 태스크 요약 dict → 원장 payload."""
    payload: dict[str, Any] = {
        "kind": "domain_agent_task",
        "schema_version": "domain_agent/v1",
        "domain": task.get("domain"),
        "task_type": task.get("task_type"),
        "status": task.get("status"),
        "confidence_score": task.get("confidence_score"),
        "recommendation": task.get("recommendation"),
        "requires_approval": task.get("requires_approval"),
    }
    if task.get("id") is not None:           # 원본 domain_agent_tasks 행 역추적(없으면 생략)
        payload["task_id"] = task.get("id")
    return payload


# ── best-effort 기록 래퍼(원장 append) ──

async def record_design_audit(
    *, result: dict[str, Any], audit_id: str | None = None,
    tenant_id: str | None = None, project_id: str | None = None,
    pnu: str | None = None, address: str | None = None, created_by: str | None = None,
) -> dict[str, Any]:
    return await ledger.append_analysis(
        analysis_type="design_audit", payload=design_audit_to_ledger(result, audit_id=audit_id),
        tenant_id=tenant_id, project_id=project_id, pnu=pnu, address=address,
        source="design_audit", created_by=created_by,
    )


async def record_feasibility_commit(
    *, commit: dict[str, Any], tenant_id: str | None = None,
    project_id: str | None = None, created_by: str | None = None,
) -> dict[str, Any]:
    # ⚠️ analysis_type="feasibility_vcs" (NOT "feasibility") — read 루프의 재무 키와 분리.
    return await ledger.append_analysis(
        analysis_type="feasibility_vcs", payload=feasibility_commit_to_ledger(commit),
        tenant_id=tenant_id, project_id=project_id,
        source="feasibility_vcs", created_by=created_by,
    )


async def record_domain_agent_task(
    *, task: dict[str, Any], tenant_id: str | None = None,
    project_id: str | None = None, created_by: str | None = None,
) -> dict[str, Any]:
    return await ledger.append_analysis(
        analysis_type="domain_agent", payload=domain_agent_task_to_ledger(task),
        tenant_id=tenant_id, project_id=project_id,
        source="domain_agents", created_by=created_by,
    )


# ── Phase 1: read 성장루프용 매퍼+래퍼(write/read 쌍 신설·SSOT 합류) ──

def feasibility_result_to_ledger(result: dict[str, Any]) -> dict[str, Any]:
    """수지분석 결과(ModuleOutput dict) → 원장 payload(재무 성장루프 read 대상)."""
    return {
        "kind": "feasibility", "schema_version": "feasibility/v1",
        "development_type": result.get("development_type"),
        "total_revenue_won": result.get("total_revenue_won"),
        "net_profit_won": result.get("net_profit_won"),
        "profit_rate_pct": result.get("profit_rate_pct"),
        "npv_won": result.get("npv_won"), "grade": result.get("grade"),
        "findings_brief": [
            {"check_id": "PROFIT_RATE", "status": "info",
             "current": result.get("profit_rate_pct"), "limit": None},
            {"check_id": "NPV", "status": "info", "current": result.get("npv_won"), "limit": None},
        ],
    }


async def record_feasibility_result(
    *, result: dict[str, Any], tenant_id: str | None = None,
    project_id: str | None = None, pnu: str | None = None, address: str | None = None,
    created_by: str | None = None,
) -> dict[str, Any]:
    # analysis_type="feasibility" (VCS 메타 'feasibility_vcs'와 분리 — read 성장루프 재무 체인)
    return await ledger.append_analysis(
        analysis_type="feasibility", payload=feasibility_result_to_ledger(result),
        tenant_id=tenant_id, project_id=project_id, pnu=pnu, address=address,
        source="feasibility", created_by=created_by,
    )
