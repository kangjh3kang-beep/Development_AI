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

import hashlib
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


def _domain_rec_to_status(rec: str | None) -> str:
    """권고(recommendation) → 모순감지용 status. proceed=pass, 조건부=warning, 그 외(escalate/review)=fail."""
    r = (rec or "").lower()
    if r == "proceed":
        return "pass"
    if "condition" in r:
        return "warning"
    return "fail"


async def record_domain_agent_task(
    *, task: dict[str, Any], tenant_id: str | None = None,
    project_id: str | None = None, created_by: str | None = None,
) -> dict[str, Any]:
    # Phase 3.2 합류: 도메인별 체인(domain_agent_{domain}) + findings_brief(권고·신뢰도) 보강 +
    # prior 모순/lineage(_append_with_lineage). 기존 매퍼(domain_agent_task_to_ledger)·서비스 계약 불변.
    domain = task.get("domain") or "unknown"
    payload = domain_agent_task_to_ledger(task)
    payload["findings_brief"] = [{
        "check_id": "RECOMMENDATION",
        "status": _domain_rec_to_status(task.get("recommendation")),
        "current": task.get("confidence_score"), "limit": None,
    }]
    return await _append_with_lineage(
        analysis_type=f"domain_agent_{domain}", payload=payload,
        tenant_id=tenant_id, project_id=project_id, pnu=None, address=None,
        source="domain_agents", created_by=created_by)


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


async def _append_with_lineage(
    *, analysis_type: str, payload: dict[str, Any], tenant_id: str | None, project_id: str | None,
    pnu: str | None, address: str | None, source: str, created_by: str | None,
    abs_thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Phase 2: prior read → 결정론 모순 탐지 → append → 파생 lineage 엣지(best-effort).

    결정론 수치/판정 불변(모순은 비교·표면화 전용). 반환에 'contradictions' 가산(additive).
    """
    from app.services.ledger import lineage
    from app.services.ledger.contradiction import detect_contradictions
    try:
        prior = await ledger.get_latest(
            analysis_type=analysis_type, tenant_id=tenant_id,
            pnu=pnu, address=address, project_id=project_id)
    except Exception:  # noqa: BLE001 — prior read 실패는 무중단(정직 degrade)
        prior = None
    contradictions = detect_contradictions(prior, payload, abs_thresholds=abs_thresholds)
    wb = await ledger.append_analysis(
        analysis_type=analysis_type, payload=payload,
        tenant_id=tenant_id, project_id=project_id, pnu=pnu, address=address,
        source=source, created_by=created_by)
    if (isinstance(wb, dict) and wb.get("ok") and not wb.get("unchanged")
            and wb.get("content_hash") and prior and prior.get("content_hash")):
        await lineage.record_edge(
            child_hash=wb["content_hash"], child_type=analysis_type,
            parent_hash=prior["content_hash"], parent_type=prior.get("analysis_type", analysis_type),
            tenant_id=tenant_id,
            contradiction_count=len(contradictions["contradictions"]),
            max_severity=contradictions["max_severity"])
    out = {**wb, "contradictions": contradictions} if isinstance(wb, dict) else wb
    # Phase 4.2: append 이벤트 훅 — 위험평가 + 고위험 알림(best-effort, 이벤트 구동).
    if isinstance(out, dict):
        try:
            from app.services.ledger.risk_monitor import on_analysis_appended
            out["risk"] = await on_analysis_appended(
                analysis_type=analysis_type, tenant_id=tenant_id,
                pnu=pnu, address=address, project_id=project_id)
        except Exception:  # noqa: BLE001 — 위험 훅 실패가 append를 막지 않음
            pass
    return out


async def record_feasibility_result(
    *, result: dict[str, Any], tenant_id: str | None = None,
    project_id: str | None = None, pnu: str | None = None, address: str | None = None,
    created_by: str | None = None,
) -> dict[str, Any]:
    # analysis_type="feasibility" (VCS 메타 'feasibility_vcs'와 분리 — read 성장루프 재무 체인)
    # Phase 2: prior 대비 결정론 모순 + 파생 lineage(profit_rate 5%p 절대임계 포함).
    return await _append_with_lineage(
        analysis_type="feasibility", payload=feasibility_result_to_ledger(result),
        tenant_id=tenant_id, project_id=project_id, pnu=pnu, address=address,
        source="feasibility", created_by=created_by,
        abs_thresholds={"profit_rate_pct": 5.0})


def pricing_revenue_to_ledger(rev: dict[str, Any], *, round_id: str | None = None) -> dict[str, Any]:
    """분양가 산정 매출 산출 dict → 원장 payload(W1 미배선 합류 — sales_revenue 체인)."""
    return {
        "kind": "sales_revenue", "schema_version": "sales_revenue/v1",
        "round_id": rev.get("round_id") or round_id, "units_priced": rev.get("units_priced"),
        "total_revenue_10k": rev.get("total_revenue_10k"), "avg_unit_10k": rev.get("avg_unit_10k"),
        "by_type": rev.get("by_type") or {},
        "findings_brief": [
            {"check_id": "TOTAL_REVENUE", "status": "info", "current": rev.get("total_revenue_10k"), "limit": None},
        ],
    }


async def record_pricing_revenue(
    *, rev: dict[str, Any], round_id: str | None = None, tenant_id: str | None = None,
    project_id: str | None = None, created_by: str | None = None,
) -> dict[str, Any]:
    return await ledger.append_analysis(
        analysis_type="sales_revenue", payload=pricing_revenue_to_ledger(rev, round_id=round_id),
        tenant_id=tenant_id, project_id=project_id, source="sales_pricing", created_by=created_by,
    )


def cost_estimate_to_ledger(*, summary: dict[str, Any], header: dict[str, Any],
                            estimate_id: str | None = None) -> dict[str, Any]:
    """BOQ 원가추정 요약 → 원장 payload(W1 미배선 합류 — cost_estimate 체인)."""
    payload: dict[str, Any] = {
        "kind": "cost_estimate", "schema_version": "cost_estimate/v1",
        "building_type": header.get("building_type"), "structure_type": header.get("structure_type"),
        "total_gfa_sqm": header.get("total_gfa_sqm"), "confidence_grade": summary.get("confidence_grade"),
        "direct": summary.get("direct"), "indirect": summary.get("indirect"), "total": summary.get("total"),
        "findings_brief": [
            {"check_id": "TOTAL_COST", "status": "info", "current": summary.get("total"), "limit": None},
        ],
    }
    if estimate_id is not None:                  # 원본 cost_estimate 행 역추적(없으면 생략)
        payload["estimate_id"] = estimate_id
    return payload


async def record_cost_estimate(
    *, summary: dict[str, Any], header: dict[str, Any], estimate_id: str | None = None,
    tenant_id: str | None = None, project_id: str | None = None,
    pnu: str | None = None, address: str | None = None, created_by: str | None = None,
) -> dict[str, Any]:
    # W1-7: pnu/address 체인키 수용 — 미전달 시 project_id 없는 호출이 익명 체인으로
    # 적재돼 from-ledger 보고서·모순탐지가 cost 단계를 못 찾던 단선 해소.
    return await ledger.append_analysis(
        analysis_type="cost_estimate",
        payload=cost_estimate_to_ledger(summary=summary, header=header, estimate_id=estimate_id),
        tenant_id=tenant_id, project_id=project_id, pnu=pnu, address=address,
        source="cost_boq", created_by=created_by,
    )


# ── Phase 3: 계층3 SpecialistAgent 산출 → 원장 cite(W4 닫기) ──

async def record_specialist_result(
    *, analysis_type: str, payload: dict[str, Any], tenant_id: str | None = None,
    project_id: str | None = None, pnu: str | None = None, address: str | None = None,
    source: str = "specialist", created_by: str | None = None,
) -> dict[str, Any]:
    """Phase 3 계층3 SpecialistAgent 산출 → 원장 cite(prior 모순 + lineage). W4 닫기.

    payload는 SpecialistAgent가 만든 domain_agent/v2(findings_brief 포함). 기본 상대임계 모순탐지
    (도메인별 절대임계 필요 시 abs_thresholds 확장). 반환에 contradictions 가산(additive).
    """
    return await _append_with_lineage(
        analysis_type=analysis_type, payload=payload,
        tenant_id=tenant_id, project_id=project_id, pnu=pnu, address=address,
        source=source, created_by=created_by)


# ── 성장루프 조인키 폐합: 사용자대면 분석 공용 기록기 ──
#   프론트 화면(VerificationBadge 피드백)이 읽는 표시 엔드포인트가 원장에 적재되어야
#   피드백 content_hash ↔ 원장 등가조인(learning_loop.curate_few_shot)이 성립한다.
#   도메인별 매퍼를 일일이 만들지 않고, "요약·핵심 필드만" 규약(kind+schema_version)을
#   지키는 얕은 공용 매퍼 1개로 수렴한다(대용량 원시데이터는 각 도메인 테이블에 잔류).

def user_analysis_to_ledger(kind: str, summary: dict[str, Any]) -> dict[str, Any]:
    """사용자대면 분석 요약 → 원장 payload(kind+schema_version 규약, None 값은 생략=정직)."""
    payload: dict[str, Any] = {"kind": kind, "schema_version": f"{kind}/v1"}
    payload.update({k: v for k, v in summary.items() if v is not None})
    return payload


# ── 변동감지 계약: input_signature/signature_parts 단일 소유자 ────────────────
#   프론트(apps/web/lib/use-analysis-cache.ts: analysisSignature)는 여러 입력 파트를 "|"로
#   조인해 재분석 필요 여부(stale)를 판정한다. 과거엔 프론트가 이 파트를 자체 계산해 서버 산식과
#   3중 불일치가 나던 문제(design_ingest 계열과 동일 계보) — 서버가 동일 순서의 파트 배열
#   자체를 원장 summary에 실어(signature_parts) 프론트는 "|".join(parts)만 하면 되게 일원화한다.
#   순서 고정: [address_norm, pnu, parcel_count, use_llm, options_summary].

def _options_summary(options: dict[str, Any] | None) -> str:
    """옵션 dict → 결정적 요약 문자열(키 정렬 — 삽입 순서 무관, 중첩 dict/list 안전).

    비-dict·빈 dict는 빈 문자열(옵션 없음과 동일 취급 — 가짜 파트 금지).
    """
    if not isinstance(options, dict) or not options:
        return ""

    def _fmt(v: Any) -> str:
        if isinstance(v, dict):
            return "{" + ",".join(f"{k}:{_fmt(v2)}" for k, v2 in sorted(v.items())) + "}"
        if isinstance(v, (list, tuple)):
            return "[" + ",".join(_fmt(v2) for v2 in v) + "]"
        return str(v)

    return ",".join(f"{k}={_fmt(v)}" for k, v in sorted(options.items()))


def build_signature_parts(
    *, address: str | None, pnu: str | None = None,
    parcel_count: int | None = None, use_llm: Any = None,
    options: dict[str, Any] | None = None,
    extra_parts: list[str] | None = None,
) -> list[str]:
    """변동감지 파츠(순서 고정) — 프론트 analysisSignature(...).join('|')와 1:1 대응.

    호출부(market_report·regulation·permits 등)는 재료(address/pnu/parcel_count/use_llm/options)만
    넘기면 되고, 조합 산식은 여기 한 곳에서만 정의한다(단일 소유자 — 산식 불일치 근절).
    address 정규화는 analysis_ledger_service._norm_addr을 그대로 재사용(체인키 정규화와 동일 규칙).

    extra_parts(옵션·additive): 기본 5파트 뒤에 그대로 이어붙이는 호출부 전용 추가 파트(예:
    market_report의 필지세트 지문). 기본 계약 순서(0~4)는 불변 — 프론트 변동감지 비교는 이
    파트를 재계산할 수 없으므로 idx5+는 비교에서 제외한다(use-analysis-history.ts 계약 참고).
    """
    parts = [
        ledger._norm_addr(address),
        pnu or "",
        str(parcel_count or 0),
        str(bool(use_llm)),
        _options_summary(options),
    ]
    if extra_parts:
        parts.extend(extra_parts)
    return parts


def build_input_signature(parts: list[str]) -> str:
    """signature_parts → 짧은 결정적 해시(sha256 앞 16자, analysis_cache._key 관행과 동형)."""
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


async def record_user_analysis(
    *, analysis_type: str, summary: dict[str, Any], kind: str | None = None,
    tenant_id: str | None = None, project_id: str | None = None,
    pnu: str | None = None, address: str | None = None,
    source: str | None = None, created_by: str | None = None,
    parcel_count: int | None = None, use_llm: Any = None,
    options: dict[str, Any] | None = None,
    extra_parts: list[str] | None = None,
) -> dict[str, Any]:
    """표시 엔드포인트 응답 요약을 원장에 best-effort 적재(append_analysis가 예외 흡수·멱등).

    반환값을 attach_ledger_hash(response, wb)에 넘기면 응답 최상위 `ledger_hash`가 노출된다.

    parcel_count/use_llm/options 중 하나라도 전달되면(=호출부가 변동감지 재료를 넘기면) 표준키
    `input_signature`/`signature_parts`를 summary에 부착한다(additive — 미전달 기존 호출부는
    무회귀, 키 자체가 생기지 않는다). 이미 summary에 같은 키가 있으면 그대로 보존(setdefault).

    extra_parts: build_signature_parts에 그대로 위임(예: market_report 필지세트 지문 6번째 파트).
    """
    _summary = dict(summary)
    if parcel_count is not None or use_llm is not None or options is not None or extra_parts:
        parts = build_signature_parts(
            address=address, pnu=pnu, parcel_count=parcel_count, use_llm=use_llm, options=options,
            extra_parts=extra_parts)
        _summary.setdefault("signature_parts", parts)
        _summary.setdefault("input_signature", build_input_signature(parts))
    return await ledger.append_analysis(
        analysis_type=analysis_type,
        payload=user_analysis_to_ledger(kind or analysis_type, _summary),
        tenant_id=tenant_id, project_id=project_id, pnu=pnu, address=address,
        source=source or analysis_type, created_by=created_by,
    )
