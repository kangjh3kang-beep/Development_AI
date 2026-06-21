"""P2 — 분석 실행 영속화/조회. AnalysisResult ↔ analysis_run(JSONB blob, 권위 조회본). run_id = 조회 키.

★per-field fan-out: legal_quantities/findings를 discrete 행(legal_quantity/finding, analysis_id=run_id FK)으로도
동시 영속 — blob은 조회/재현 SSOT, per-field 행은 '필드별 데이터' 쿼리가능 granularity(run/프로젝트 역참조·집계).
blob과 동일 트랜잭션(원자성: 둘이 항상 일치·부분상태 없음). 매핑은 검증된 계약에서만 와 안전.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contracts.analysis import AnalysisResult
from app.contracts.project_data import ProjectFieldData, ProjectFinding, ProjectQuantity
from app.db.models.analysis_models import AnalysisRunModel
from app.db.models.r1_5_models import LegalQuantityModel
from app.db.models.r3_models import FindingModel

_MAX_PROJECT_ROWS = 1000  # 프로젝트 per-field 조회 행 상한(거대 응답 방어). 운영 상수 — 법정 파라미터 아님(INV-3 무관).


def _enum(v: Any) -> Any:
    """Enum→value, 그 외 그대로(verdict/status/gated_status가 Enum이든 str이든 컬럼은 문자열)."""
    return getattr(v, "value", v)


def _per_field_rows(result: AnalysisResult, run_id: uuid.UUID,
                    tenant_id: uuid.UUID | None, project_id: uuid.UUID | None) -> list[Any]:
    """AnalysisResult의 legal_quantities/findings → per-field ORM 행(analysis_id=run_id). 쿼리가능 granularity.
    calc_trace(provenance·INV-10)는 JSONB로 그대로 영속(도출이유 보존). 검증된 계약 매핑이라 결손 위험 없음.
    organization_id=tenant_id(#8a 격리)·project_id(프로젝트 귀속)를 blob과 동일하게 적재 — per-field 직접
    쿼리 시에도 교차테넌트 격리·프로젝트 스코프가 blob과 일관(필드별 행을 프로젝트로 집계 가능)."""
    rows: list[Any] = []
    for lq in result.legal_quantities:
        rows.append(LegalQuantityModel(
            analysis_id=run_id, organization_id=tenant_id, project_id=project_id,
            snapshot_id=(lq.snapshot_id or result.snapshot_id),  # quantity별 snapshot 우선, 없으면 run-level
            variable_id=lq.variable_id, value=lq.value, unit=_enum(lq.unit),
            status=_enum(lq.status), confidence=lq.confidence,
            calc_trace=(lq.calc_trace.model_dump(mode="json") if lq.calc_trace is not None else None),
            calc_rule_version=lq.calc_rule_version,
        ))
    for f in result.findings:
        rows.append(FindingModel(
            analysis_id=run_id, organization_id=tenant_id, project_id=project_id,
            snapshot_id=result.snapshot_id,
            rule_id=f.rule_id, verdict=_enum(f.verdict),
            conditional_relaxations=list(f.conditional_relaxations),
            requires_committee=f.requires_committee,
            composite_confidence=f.composite_confidence,
            gated_status=_enum(f.gated_status), conflicts=list(f.conflicts),
            basis_article=f.basis_article,
            measured_value=f.measured_value, limit_value=f.limit_value,
        ))
    return rows


async def save_analysis(session: AsyncSession, result: AnalysisResult,
                        input_payload: dict | None = None,
                        *, tenant_id: uuid.UUID | None = None,
                        project_id: uuid.UUID | None = None) -> AnalysisResult:
    """결과 저장 → run_id 부여한 결과 반환(저장본도 run_id 포함). blob(권위) + per-field 행(쿼리가능) 원자 영속.

    input_payload(원시 입력)는 INC-14 reconcile 불일치 시 동일입력 재실행(결정론)에 사용 — 미전달 시 None
    (재실행 불가로 표면화). 결과 JSON엔 원시 입력이 없어 별도 컬럼에 보존.
    tenant_id(#8a): BFF가 X-Tenant-Id로 전달 시 organization_id로 적재 → get_analysis 소유 필터의 격리 키.
    project_id: BFF가 X-Project-Id로 전달 시 적재 → 분석 결과를 프로젝트에 귀속(프로젝트 단위 데이터베이스).
    테넌트(보안 격리 경계) 내부의 스코프 — blob·per-field 행에 동일 적재해 프로젝트별 쿼리/집계 일관.
    """
    run_id = uuid.uuid4()
    stored = result.model_copy(update={"run_id": str(run_id)})
    session.add(AnalysisRunModel(
        id=run_id,
        organization_id=tenant_id,
        project_id=project_id,
        snapshot_id=result.snapshot_id,
        input_hash=result.input_hash,
        status="DONE",
        result=stored.model_dump(mode="json"),
        input_payload=input_payload,
    ))
    # blob과 동일 트랜잭션·격리키·프로젝트키 — 필드별 행 동시 적재(원자성: 셋이 항상 일치)
    for r in _per_field_rows(result, run_id, tenant_id, project_id):
        session.add(r)
    await session.commit()
    return stored


async def get_analysis(session: AsyncSession, run_id: str,
                       *, tenant_id: uuid.UUID | None = None) -> AnalysisResult | None:
    """run_id로 조회. tenant_id 제공 시 소유 필터(#8a 심층방어) — 행이 organization_id를 가졌고 불일치면 None
    (교차테넌트 차단). 레거시(organization_id NULL) 행은 후방호환 허용(BFF binding이 1차 소유 게이트)."""
    try:
        uid = uuid.UUID(run_id)
    except ValueError:
        return None
    row = await session.get(AnalysisRunModel, uid)
    if row is None or row.result is None:
        return None
    if tenant_id is not None and row.organization_id is not None and row.organization_id != tenant_id:
        return None  # 교차테넌트 조회 차단(엔진측 2차 방어선)
    return AnalysisResult.model_validate(row.result)


def _f(v: Any) -> float | None:
    """Numeric(Decimal)→float(JSON 직렬화·계약 정규화). None은 그대로."""
    return float(v) if v is not None else None


async def get_project_field_data(session: AsyncSession, project_id: uuid.UUID, *,
                                 tenant_id: uuid.UUID | None = None,
                                 max_rows: int = _MAX_PROJECT_ROWS) -> ProjectFieldData:
    """프로젝트에 귀속된 분석들의 per-field 값(legal_quantity/finding) 집계 조회 — '필드별 데이터 제공'의 읽기 측.

    테넌트 격리(#8a): tenant_id 제공 시 organization_id 일치 행만(교차테넌트 차단). run_count는 distinct 분석 run
    수(AnalysisRunModel 직접 count — per-field 캡과 무관하게 정확). per-field 행은 max_rows로 상한(거대 응답 방어);
    상한 도달 시 truncated=True로 표면화(무음 절단 금지). 결정론 정렬(created_at, id 타이브레이크)."""
    def _scope(model: Any):
        stmt = select(model).where(model.project_id == project_id)
        if tenant_id is not None:
            stmt = stmt.where(model.organization_id == tenant_id)
        # max_rows+1 fetch로 절단 감지(별도 count 불필요)
        return stmt.order_by(model.created_at, model.id).limit(max_rows + 1)

    lq_rows = (await session.execute(_scope(LegalQuantityModel))).scalars().all()
    fnd_rows = (await session.execute(_scope(FindingModel))).scalars().all()
    truncated = len(lq_rows) > max_rows or len(fnd_rows) > max_rows
    lq_rows, fnd_rows = lq_rows[:max_rows], fnd_rows[:max_rows]

    run_stmt = select(func.count()).select_from(AnalysisRunModel).where(AnalysisRunModel.project_id == project_id)
    if tenant_id is not None:
        run_stmt = run_stmt.where(AnalysisRunModel.organization_id == tenant_id)
    run_count = int((await session.execute(run_stmt)).scalar_one())

    quantities = [ProjectQuantity(
        analysis_id=(str(r.analysis_id) if r.analysis_id is not None else None),
        snapshot_id=r.snapshot_id, variable_id=r.variable_id, value=_f(r.value),
        unit=r.unit, status=r.status, confidence=r.confidence, calc_rule_version=r.calc_rule_version,
    ) for r in lq_rows]
    findings = [ProjectFinding(
        analysis_id=(str(r.analysis_id) if r.analysis_id is not None else None),
        snapshot_id=r.snapshot_id, rule_id=r.rule_id, verdict=r.verdict, gated_status=r.gated_status,
        basis_article=r.basis_article, measured_value=_f(r.measured_value), limit_value=_f(r.limit_value),
        composite_confidence=r.composite_confidence, requires_committee=r.requires_committee,
    ) for r in fnd_rows]
    return ProjectFieldData(project_id=str(project_id), run_count=run_count, truncated=truncated,
                            quantities=quantities, findings=findings)
