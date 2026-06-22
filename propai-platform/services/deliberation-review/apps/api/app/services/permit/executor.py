"""INC-PD2 — 프로세스 실행기: 스펙을 읽어 단계별로 AnalysisResult를 소비·계측·검증(얇은 결정론).

INV-13: AnalysisResult를 read-only 소비(재계산·라이브 호출 없음). 검증은 엔진 게이트 산출(finding.gated_status)
재사용. 입력 결손은 NEEDS_INPUT로 표면화(무음 금지). 동일 입력+스펙 → 동일 결과(결정론).
"""
from __future__ import annotations

from app.contracts.analysis import AnalysisResult
from app.contracts.permit_process import PermitProcessSpec, StageSpec
from app.contracts.permit_result import PermitProcessResult, StageResult
from app.services.permit.measurement import measure, worst_conformance
from app.services.permit.spec_loader import applicable_stages

_VERIFY_RANK = {"CONFIRMED": 0, "NEEDS_REVIEW": 1, "BLOCKED": 2}


def _verify_stage(result: AnalysisResult) -> str:
    """단계 검증 — 엔진 게이트 산출(finding.gated_status) worst-of 재사용. finding 없으면 NEEDS_REVIEW(보수)."""
    statuses = [f.gated_status.value for f in result.findings]
    if not statuses:
        return "NEEDS_REVIEW"
    return max(statuses, key=lambda s: _VERIFY_RANK.get(s, 1))


def run_process(result: AnalysisResult, spec: PermitProcessSpec, *,
                dev_type: str | None = None, use_zone: str | None = None,
                provided_inputs: dict | None = None) -> PermitProcessResult:
    """AnalysisResult + 프로세스 스펙 → ProcessResult(로드맵+단계별 계측+대응+검증). 결정론·소비 read-only.

    프로세스-불문 — permit·design 등 어떤 ProcessSpec이든 구동(spec_id로 구분). provided_inputs는 단계 required_inputs
    충족 여부 판정용 컨텍스트(설계 라이프사이클의 완결성 — 기획/매스/평면 등 산출물 존재 표시). use_zone은 항상 포함."""
    from app.services.predict.outcome import overall_outcome, predict_stage

    stages = applicable_stages(spec, dev_type=dev_type, use_zone=use_zone)
    inputs = {"use_zone": use_zone, **(provided_inputs or {})}
    stage_verify = _verify_stage(result)
    stage_results: list[StageResult] = []
    for st in stages:
        sr = _run_stage(result, st, inputs, stage_verify, use_zone)
        if st.outcome_predictor:   # Phase 2a 슬롯 — 설정 단계만 승인 가능성 예측(결정론 휴리스틱)
            sr.outcome = predict_stage(sr, st.outcome_predictor)
        stage_results.append(sr)
    overall_c = worst_conformance([s.conformance for s in stage_results])
    overall_v = max((s.verification_status for s in stage_results),
                    key=lambda s: _VERIFY_RANK.get(s, 1), default="NEEDS_REVIEW")
    overall_o = overall_outcome([s.outcome.likelihood for s in stage_results if s.outcome])
    return PermitProcessResult(
        spec_id=spec.spec_id, spec_version=spec.version, run_id=result.run_id,
        roadmap=[s.stage_id for s in stages], stages=stage_results,
        overall_conformance=overall_c, overall_verification=overall_v,
        overall_outcome=overall_o,
    )


def _run_stage(result: AnalysisResult, st: StageSpec, inputs: dict,
               stage_verify: str, use_zone: str | None) -> StageResult:
    sr = StageResult(stage_id=st.stage_id, name=st.name, stage_type=st.stage_type,
                     authority=st.authority, submittals=list(st.submittals),
                     deliverables=list(st.deliverables))
    missing = [k for k in st.required_inputs if not inputs.get(k)]   # 선언된 모든 required_inputs 검사(완결성)
    if missing:
        sr.status = "NEEDS_INPUT"
        sr.issues = [f"필요 입력 결손: {', '.join(missing)}"]   # 무음 금지 — 표면화
        return sr
    crits = [measure(result, ref, use_zone) for ref in st.criteria_refs]
    sr.criteria = crits
    sr.conformance = worst_conformance([c.conformance for c in crits])
    sr.verification_status = stage_verify
    sr.remediation = [f"{c.criterion_id}: 보완 필요({c.basis_article or '근거조문 확인'})"
                      for c in crits if c.conformance in ("미흡", "조건부")]
    return sr


# 후방호환 별칭 — 기존 permit 경로 무파손(시스템1 동일 함수).
run_permit_process = run_process
