"""프로젝트 파이프라인 API 라우터."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.billing_deps import enforce_llm_quota
from app.services.ledger import analysis_ledger_service as ledger
from app.services.pipeline.project_pipeline import (
    PipelineStage,
    PipelineStatus,
    ProjectPipeline,
)
from app.services.report.pipeline_report_service import (
    PipelineReport,
    PipelineReportService,
)
from apps.api.auth.jwt_handler import CurrentUser, get_current_user

router = APIRouter(prefix="/api/v2/pipeline", tags=["pipeline"])
logger = structlog.get_logger(__name__)


# ── Request / Response 모델 ──────────────────────────────────


class PipelineRunRequest(BaseModel):
    address: str
    project_id: str | None = None
    options: dict | None = None
    # 다필지 통합 개발 시 필지목록(2개 이상이면 site stage가 면적가중 통합면적·우세용도로 산출).
    #   행 계약은 /analysis/comprehensive와 동일(camelCase/snake 양형 수용 — build_integrated_context 정규화).
    #   미전달/1필지면 기존 단일주소 동작 그대로(무회귀).
    parcels: list[dict[str, Any]] | None = None


class StageRerunRequest(BaseModel):
    """특정 단계 재실행 요청."""

    address: str
    project_id: str | None = None
    stage: str  # "site_analysis" | "design" | "cost" | ...
    overrides: dict[str, Any] = Field(
        default_factory=dict,
        description="해당 단계에 주입할 사용자 수정값 (예: {\"max_far\": 250})",
    )
    # 다필지 통합 — run과 동일 계약(재실행도 통합면적 유지).
    parcels: list[dict[str, Any]] | None = None
    stage_overrides: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description=(
            "단계별 사용자 수정값 맵 (다단계, 예: {\"cost\": {\"total_construction_cost\": 1.2e9}, "
            "\"feasibility\": {\"avg_sale_price_per_pyeong\": 2200}}). "
            "기존 단일 overrides와 병합된다. 미전달 시 기존 동작과 동일(하위호환)."
        ),
    )
    previous_result: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "이전 파이프라인 실행 결과. stages는 list[{stage,data}] / {stage:{data}} 양형 모두 수용. "
            "미제공 시 skip 단계 payload 복원 없이 재실행."
        ),
    )


class PipelineStageStatusResponse(BaseModel):
    stage: str
    status: str
    duration_ms: int | None = None
    data: dict = {}
    error: str | None = None


class PipelineRunResponse(BaseModel):
    pipeline_id: str
    project_id: str
    status: str
    stages: list[PipelineStageStatusResponse]
    summary: dict = {}
    # 성장루프 조인키: 원장 write-back content_hash(sha256) — 프론트 피드백이 원장과 조인(미적재 시 None)
    ledger_hash: str | None = None


# ── 헬퍼 ──────────────────────────────────────────────────


def _build_stages_response(result) -> list[PipelineStageStatusResponse]:
    """PipelineState → PipelineStageStatusResponse 리스트 변환."""
    stages: list[PipelineStageStatusResponse] = []
    for stage_name, stage_result in result.stages.items():
        stages.append(
            PipelineStageStatusResponse(
                stage=stage_name,
                status=stage_result.status.value,
                duration_ms=stage_result.duration_ms,
                data=stage_result.data,
                error=stage_result.error,
            )
        )
    return stages


# ── 엔드포인트 ────────────────────────────────────────────


def _merge_parcels_into_options(options: dict | None, parcels: list | None) -> dict | None:
    """다필지목록을 options["parcels"]로 병합(하위호환·additive). parcels 없으면 원본 그대로."""
    if not parcels:
        return options
    merged = dict(options or {})
    merged["parcels"] = parcels
    return merged


@router.post(
    "/run",
    response_model=PipelineRunResponse,
    # ★전수감사 보강: 전체 파이프라인(LLM 단계 포함) — 익명 always-LLM 접근 차단 위해 인증도 부착.
    dependencies=[Depends(get_current_user), Depends(enforce_llm_quota)],
)
async def run_pipeline(req: PipelineRunRequest):
    """주소 입력으로 전체 파이프라인 실행."""
    pipeline = ProjectPipeline()
    result = await pipeline.run(
        address=req.address,
        project_id=req.project_id,
        options=_merge_parcels_into_options(req.options, req.parcels),
    )

    stages = _build_stages_response(result)

    # 서비스 사용료(LLM 별개): 이번 실행에서 실제로 수행된 단계마다 과금(로그인, best-effort).
    # duration_ms가 있는(=이번에 실행된) completed 단계만 → 재사용 단계 중복과금 방지.
    try:
        from app.core.request_context import get_current_user_id

        uid = get_current_user_id()
        if uid:
            ran = [s.stage for s in stages if s.status == "completed" and (s.duration_ms or 0) > 0]
            if ran:
                from app.core.database import async_session_factory
                from app.services.billing import billing_service

                async with async_session_factory() as _db:
                    for stage_name in ran:
                        await billing_service.charge_service(_db, uid, f"stage:{stage_name}")
    except Exception:  # noqa: BLE001
        pass

    # Fix #3: 결정론 cost/feasibility 산출을 분석원장에 적재(모순탐지·lineage·SSOT 합류).
    recorded = await _record_pipeline_ledger(result, req)

    # 최종 요약
    summary = {}
    report_data = result.stages.get("report")
    if report_data and report_data.data:
        summary = report_data.data.get("summary", {})

    # ★성장루프 조인키: write-back 성공분 중 대표 해시(feasibility 우선, 없으면 cost)를
    #   응답 `ledger_hash`로 노출 — 파이프라인 결과 화면의 피드백(👍/👎)이 원장과 조인된다.
    ledger_hash: str | None = None
    try:
        from app.services.ledger.analysis_ledger_service import extract_ledger_hash
        for _k in ("feasibility", "cost"):
            ledger_hash = extract_ledger_hash((recorded or {}).get(_k))
            if ledger_hash:
                break
    except Exception:  # noqa: BLE001 — 조인키 실패해도 파이프라인 응답 무손상
        ledger_hash = None

    return PipelineRunResponse(
        pipeline_id=result.pipeline_id,
        project_id=result.project_id,
        status=result.status.value,
        stages=stages,
        summary=summary,
        ledger_hash=ledger_hash,
    )


def _normalize_for_interpreter(stage: str, data: dict[str, Any]) -> dict[str, Any]:
    """파이프라인 stage 데이터 키 → 인터프리터 기대 키로 보강(해석 품질↑). 원본 키도 보존."""
    d = dict(data)

    def setdefault_from(target: str, *sources: str) -> None:
        if d.get(target) in (None, "") :
            for s in sources:
                if d.get(s) not in (None, ""):
                    d[target] = d[s]; return

    if stage == "design":
        setdefault_from("total_floor_area_sqm", "total_gfa_sqm")
        setdefault_from("num_floors", "floor_count", "floor_count_above")
        setdefault_from("building_use", "building_type")
        setdefault_from("bcr_pct", "bcr_used_pct", "bcr")
        setdefault_from("far_pct", "far_used_pct", "far")
        setdefault_from("max_bcr_pct", "max_bcr")
        setdefault_from("max_far_pct", "max_far")
        setdefault_from("zone_code", "zone_type")
        setdefault_from("building_footprint_sqm", "building_area_sqm")
    elif stage in ("appraisal", "avm"):
        # 예상시세 추정(desk_appraisal) 결과 → avm_interpreter 입력(estimated_value 등) 매핑.
        if not isinstance(d.get("estimated_value"), dict):
            rng = d.get("range_per_sqm") or {}
            d["estimated_value"] = {
                "value_won": d.get("appraised_total_won"),
                "value_per_sqm_won": d.get("appraised_price_per_sqm"),
                "confidence_score": d.get("confidence"),
                "confidence_interval_low": rng.get("low"),
                "confidence_interval_high": rng.get("high"),
            }
        if not isinstance(d.get("market_statistics"), dict) and isinstance(d.get("market_stats"), dict):
            d["market_statistics"] = d["market_stats"]
    elif stage == "esg":
        # esg_interpreter는 carbon_emissions 중첩을 기대 — 가용 탄소값으로 구성.
        if not isinstance(d.get("carbon_emissions"), dict):
            emb = d.get("embodied_carbon_kg"); op = d.get("operational_carbon_kg")
            per = d.get("total_carbon_per_sqm")
            if any(v is not None for v in (emb, op, per)):
                tot = ((emb or 0) + (op or 0)) / 1000 or None
                d["carbon_emissions"] = {
                    "total_emissions_tco2": round(tot, 2) if tot else None,
                    "emissions_per_sqm": per,
                    "scope1": round((emb or 0) / 1000, 2) if emb else None,
                    "scope3": round((op or 0) / 1000, 2) if op else None,
                }
    return d


def _make_interpreter(stage: str):
    """stage → 인터프리터 인스턴스. (재생성 피드백 주입을 위해 인스턴스 생성을 분리)

    report만 generate_report_narrative를, 나머지는 generate_interpretation을 쓰므로
    호출처가 hasattr로 분기한다. 미지원 stage는 None.
    """
    if stage == "site_analysis":
        from app.services.ai.site_analysis_interpreter import SiteAnalysisInterpreter
        return SiteAnalysisInterpreter()
    if stage == "design":
        from app.services.ai.design_interpreter import DesignInterpreter
        return DesignInterpreter()
    if stage == "cost":
        from app.services.ai.cost_interpreter import CostInterpreter
        return CostInterpreter()
    if stage == "feasibility":
        from app.services.ai.feasibility_interpreter import FeasibilityInterpreter
        return FeasibilityInterpreter()
    if stage == "tax":
        from app.services.ai.tax_interpreter import TaxInterpreter
        return TaxInterpreter()
    if stage == "esg":
        from app.services.ai.esg_interpreter import EsgInterpreter
        return EsgInterpreter()
    if stage in ("appraisal", "avm"):
        from app.services.ai.avm_interpreter import AvmInterpreter
        return AvmInterpreter()
    if stage == "report":
        from app.services.ai.report_interpreter import ReportInterpreter
        return ReportInterpreter()
    return None


async def _run_interpreter(interp, data: dict[str, Any]) -> dict[str, str]:
    """인터프리터 1회 실행(report/일반 분기)."""
    if hasattr(interp, "generate_report_narrative"):
        return await interp.generate_report_narrative(data)
    return await interp.generate_interpretation(data)


def _issues_text(verdict: dict[str, Any]) -> str:
    """검증 결과(verdict dict) → 재생성 프롬프트에 주입할 이슈 요약 문자열."""
    lines: list[str] = []
    for it in (verdict.get("issues") or [])[:8]:
        if not isinstance(it, dict):
            continue
        sev = it.get("severity", "?")
        typ = it.get("type", "이슈")
        claim = str(it.get("claim", ""))[:120]
        note = str(it.get("note", ""))[:160]
        lines.append(f"- [{sev}] {typ}: {claim} — {note}")
    summary = str(verdict.get("summary", ""))[:200]
    head = f"검증 요약: {summary}" if summary else ""
    return (head + "\n" + "\n".join(lines)).strip()


def _needs_retry(verdict: dict[str, Any]) -> bool:
    """fail 또는 high 심각도 이슈가 있으면 재생성 대상."""
    if not isinstance(verdict, dict):
        return False
    if verdict.get("verdict") == "fail":
        return True
    return any(
        isinstance(i, dict) and i.get("severity") == "high"
        for i in (verdict.get("issues") or [])
    )


async def _interpret_stage(
    stage: str, data: dict[str, Any], *, use_verification_retry: bool = False
) -> dict[str, Any]:
    """단계 AI 해석(정규화+캐시+인터프리터). interpret 엔드포인트·PDF 생성 공용.

    use_verification_retry=True면, 1차 생성 결과를 검증관(VerifierService)으로
    검증하여 fail(또는 high 이슈)일 때 이슈를 프롬프트에 주입해 **1회만** 재생성한다.
    재검증이 pass/warn이면 재생성본을 채택, 여전히 실패면 원본 + 경고배지를 반환한다.
    기본값(False)은 기존 동작과 완전히 동일(무파괴).
    """
    data = _normalize_for_interpreter(stage, data)
    from app.services.ai.interpretation_cache import cache_key, get_cached, put_cached
    ckey = cache_key(stage, data)
    # 검증루프 경로(use_verification_retry=True)는 캐시키를 분리(":verified" 접미사).
    # 무검증 경로가 저장해 둔 캐시를 검증 요구 경로가 영구 재사용하는 것을 막기 위함이다.
    # (캐시 테이블 구조는 건드리지 않는 보수적 접근 — 기존 무검증 경로 키는 그대로.)
    # TODO: 캐시 sections에 verified 메타를 통합해 두 경로가 검증본을 공유하도록 개선.
    if use_verification_retry:
        ckey = f"{ckey}:verified"
    cached = await get_cached(ckey)
    if cached:
        return {"ok": True, "stage": stage, "sections": cached, "cached": True}
    interp = _make_interpreter(stage)
    if interp is None:
        return {"ok": False, "stage": stage, "message": "지원하지 않는 단계입니다.", "sections": {}}
    try:
        sections = await _run_interpreter(interp, data)
        ok = isinstance(sections, dict) and bool(sections)
        if not ok:
            return {"ok": False, "stage": stage, "sections": {}}

        if use_verification_retry:
            retry_result = await _verify_and_maybe_retry(stage, data, interp, sections)
            sections = retry_result["sections"]
            extra = {k: retry_result[k] for k in ("verification", "regenerated", "verification_warning") if k in retry_result}
            # 검증을 통과하지 못한 결과(verification_warning 배지)는 캐시에 남기지 않는다 —
            # 실패본이 ":verified" 키에 영구 고착되지 않고, 다음 호출에서 재생성·재검증 기회를 남긴다.
            if "verification_warning" not in retry_result:
                await put_cached(ckey, stage, sections)
        else:
            extra = {}
            await put_cached(ckey, stage, sections)
        return {"ok": True, "stage": stage, "sections": sections, **extra}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "stage": stage, "message": str(e)[:160], "sections": {}}


async def _verify_and_maybe_retry(
    stage: str, data: dict[str, Any], interp, sections: dict[str, str]
) -> dict[str, Any]:
    """검증 → fail시 이슈주입 1회 재생성 → 재검증. 상한 1회(무한루프 금지).

    LLM 추가 호출은 1차 검증이 fail일 때만 발생(비용통제). 모든 실패는 best-effort로
    무중단(원본 채택). 반환 dict: sections + (verification, regenerated, verification_warning).
    """
    try:
        from app.services.verification.verifier_service import VerifierService
        verifier = VerifierService()
        v1 = await verifier.verify(stage, data, sections)
    except Exception:  # noqa: BLE001
        return {"sections": sections}

    if not _needs_retry(v1):
        return {"sections": sections, "verification": v1, "regenerated": False}

    # ── 재생성(상한 1) ── 이슈를 프롬프트에 주입해 1회만 재호출.
    try:
        interp.set_retry_feedback(_issues_text(v1))
        regen = await _run_interpreter(interp, data)
        interp.set_retry_feedback(None)
    except Exception:  # noqa: BLE001
        return {"sections": sections, "verification": v1, "regenerated": False,
                "verification_warning": "검증 실패 — 재생성 중 오류로 원본을 유지합니다."}

    if not (isinstance(regen, dict) and regen):
        return {"sections": sections, "verification": v1, "regenerated": False,
                "verification_warning": "검증 실패 — 재생성 결과가 비어 원본을 유지합니다."}

    # 재검증(2차) — 통과하면 채택, 여전히 실패면 원본 + 경고배지.
    try:
        v2 = await verifier.verify(stage, data, regen)
    except Exception:  # noqa: BLE001
        # 재검증 자체 실패 시: 재생성본은 채택하되 경고 표기.
        return {"sections": regen, "verification": v1, "regenerated": True,
                "verification_warning": "재생성본을 적용했으나 재검증은 일시적으로 수행되지 않았습니다."}

    if _needs_retry(v2):
        # 1회 상한 — 여전히 실패면 원본 + 경고배지 반환(무한루프 금지).
        return {"sections": sections, "verification": v2, "regenerated": False,
                "verification_warning": "검증에 실패했고 1회 재생성 후에도 통과하지 못해 원본을 유지합니다."}

    return {"sections": regen, "verification": v2, "regenerated": True}


async def _gather_report_narratives(
    result_dict: dict[str, Any], timeout: float = 28.0, *, use_verification_retry: bool = False
) -> dict[str, dict[str, str]]:
    """보고서 PDF용 — 단계별 AI 해석을 병렬 수집(캐시 우선, 미스는 생성). 타임아웃 내 완료분만.

    use_verification_retry=True면 각 단계 해석에 검증→이슈주입→1회 재생성 루프
    (_verify_and_maybe_retry)를 태운다 — 보고서는 동기 UI가 아니므로 품질우선 경로.
    기본 False는 기존 호출부(파이프라인 PDF 등) 동작과 완전히 동일(무회귀).
    """
    import asyncio

    stages_map = result_dict.get("stages") or {}
    summary = result_dict.get("summary") or {}
    site = (stages_map.get("site_analysis") or {})
    site_data = site.get("data") if isinstance(site, dict) else {}
    ctx = {
        "address": result_dict.get("address") or (site_data or {}).get("address"),
        "zone_type": (site_data or {}).get("zone_type") or ((site_data or {}).get("basic") or {}).get("zone_type"),
    }
    targets = ["site_analysis", "design", "cost", "feasibility", "tax", "esg"]
    jobs = []
    for stg in targets:
        s = stages_map.get(stg)
        d = s.get("data") if isinstance(s, dict) else None
        if not isinstance(d, dict) or not d:
            # summary 폴백
            d = summary.get(stg) if isinstance(summary.get(stg), dict) else None
        if isinstance(d, dict) and d:
            jobs.append((stg, _interpret_stage(
                stg, {**ctx, **d}, use_verification_retry=use_verification_retry)))
    if not jobs:
        return {}
    out: dict[str, dict[str, str]] = {}
    # 타임아웃 부분보존: 이전의 wait_for(gather(...))는 타임아웃이 나면 이미 완료된
    # 해석까지 전량 유실했다. asyncio.wait(timeout=)로 바꿔 제한시간 내 '완료된'
    # 내러티브는 보존하고, 미완료 단계만 생략한다(보고서는 있는 만큼이라도 싣는다).
    tasks = {asyncio.ensure_future(coro): stg for stg, coro in jobs}
    done, pending = await asyncio.wait(tasks.keys(), timeout=timeout)
    for t in pending:
        t.cancel()  # 미완료 태스크는 취소 정리(백그라운드 잔류·리소스 누수 방지)
    if pending:
        # 취소가 실제로 마무리될 때까지 회수(예외는 무시) — 'Task was destroyed' 경고 방지
        await asyncio.gather(*pending, return_exceptions=True)
    for t, stg in tasks.items():  # dict 삽입순 = jobs 순서 그대로 결과 수집(결정적)
        if t not in done:
            continue
        try:
            r = t.result()
        except Exception:  # noqa: BLE001 — 한 단계 실패가 다른 단계 보존을 막지 않는다
            continue
        if isinstance(r, dict) and r.get("ok") and isinstance(r.get("sections"), dict):
            out[stg] = r["sections"]
    return out


class InterpretRequest(BaseModel):
    """단계별 AI 해석(온디맨드) 요청 — 보고서 섹션 열람 시 호출."""
    stage: str
    data: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)  # 공통 맥락(주소·용도지역·면적·연면적 등)
    # 검증 실패 시 1회 재생성 피드백루프(기본 False=보수적·기존동작). True면 fail/high시 LLM 1회 추가호출.
    use_verification_retry: bool = False


async def _autoload_ledger(stage: str, data: dict[str, Any], sections: dict[str, Any]) -> None:
    """채택된 인터프리터 출력을 분석 원장에 자동 적재(best-effort, 무중단).

    tenant_id는 요청 컨텍스트의 user_id로 해소(없으면 None=익명 체인). pnu/address는
    data에서 가용분만 사용. content_hash 멱등이라 동일 출력은 버전을 늘리지 않는다.
    어떤 실패도 본 해석 흐름을 막지 않는다(try/except 전체 감쌈).
    """
    if not (isinstance(sections, dict) and sections):
        return
    try:
        pnu = data.get("pnu") or data.get("PNU")
        address = data.get("address")
        if not (pnu or address):
            return  # 체인 식별자가 없으면 적재 스킵(무의미한 익명 누적 방지)
        tenant_id = None
        try:
            from app.core.request_context import get_current_user_id
            uid = get_current_user_id()
            if uid:
                from sqlalchemy import text

                from app.core.database import async_session_factory
                async with async_session_factory() as db:
                    row = (await db.execute(
                        text("SELECT tenant_id FROM public.users WHERE id = :uid"),
                        {"uid": uid})).first()
                    if row and row[0]:
                        tenant_id = str(row[0])
        except Exception:  # noqa: BLE001
            pass
        await ledger.append_analysis(
            analysis_type=stage,
            payload=sections,
            tenant_id=tenant_id,
            pnu=str(pnu) if pnu else None,
            address=str(address) if address else None,
            project_id=str(data.get("project_id")) if data.get("project_id") else None,
            source="interpreter",
        )
    except Exception as e:  # noqa: BLE001 — 자동적재 실패는 본 흐름 무중단(정직표기)
        logger.warning("파이프라인 단계 원장 자동적재 실패 — skipped", stage=stage, err=str(e)[:200])


async def _resolve_tenant_id() -> str | None:
    """요청 컨텍스트 user_id → users.tenant_id 해소(없으면 None=익명 체인). best-effort."""
    try:
        from app.core.request_context import get_current_user_id

        uid = get_current_user_id()
        if not uid:
            return None
        from sqlalchemy import text

        from app.core.database import async_session_factory
        async with async_session_factory() as db:
            row = (await db.execute(
                text("SELECT tenant_id FROM public.users WHERE id = :uid"),
                {"uid": uid})).first()
            if row and row[0]:
                return str(row[0])
    except Exception as e:  # noqa: BLE001 — 해소 실패는 무중단(익명 체인)이나 관측가능해야 함(불변규칙3)
        logger.warning("tenant_id 해소 실패 — 익명 체인으로 진행", err=str(e)[:200])
    return None


async def _record_pipeline_ledger(result, req: PipelineRunRequest) -> dict[str, Any]:
    """Fix #3(감사 HIGH): 파이프라인 결정론 산출(cost/feasibility)을 분석원장에 적재.

    /run·/report 공용. 모순탐지·lineage·SSOT 단일출처에 합류시켜, 통합 파이프라인의 권위수치가
    별도 엔드포인트에서만 적재되던 단선을 닫는다. 결정론 수치는 변경하지 않고 '추가'로 일원화하며,
    어떤 실패도 응답을 막지 않는다(best-effort, 정직 degrade).
    반환: 성공 적재분 dict({"cost": wb, "feasibility": wb}) — 성장루프 조인키(ledger_hash) 노출용.
    """
    try:
        from app.services.pipeline.pipeline_ledger_writeback import record_pipeline_results

        tenant_id = await _resolve_tenant_id()
        recorded = await record_pipeline_results(
            stages=result.stages,
            address=getattr(result, "address", None) or req.address,
            project_id=getattr(result, "project_id", None) or req.project_id,
            tenant_id=tenant_id,
        )
        if recorded:
            logger.info("파이프라인 원장 write-back", recorded=list(recorded.keys()))
        return recorded or {}
    except Exception as e:  # noqa: BLE001 — write-back 실패는 본 흐름 무중단(정직표기)
        logger.warning("파이프라인 원장 write-back 실패 — skipped", err=str(e)[:200])
        return {}


@router.post(
    "/interpret",
    summary="단계 AI 해석 온디맨드 생성(타임아웃 안전)",
    # ★전수감사 보강: LLM(_interpret_stage) 직접 트리거인데 인증·쿼터가 전무했음(미인증·미과금
    #   비용남용 가능). 인증(get_current_user) + 한도게이트(enforce_llm_quota)를 함께 부착.
    dependencies=[Depends(get_current_user), Depends(enforce_llm_quota)],
)
async def interpret_stage(req: InterpretRequest) -> dict[str, Any]:
    """한 단계의 인터프리터를 단건 호출해 섹션별 서술 해석을 반환한다.

    파이프라인 동기 실행을 막지 않도록 보고서가 섹션을 볼 때 개별 호출(각 ~10초).
    공통 맥락(주소·용도지역·면적·연면적)을 단계 데이터에 병합해 해석 품질을 높인다.
    """
    stage = (req.stage or "").strip()
    # 맥락(context) → 데이터 병합(단계 data 우선). 인터프리터 공통 키 보강.
    data = {**(req.context or {}), **(req.data or {})}
    out = await _interpret_stage(stage, data, use_verification_retry=req.use_verification_retry)
    # B2(a): 채택된 출력 원장 자동적재(best-effort, 무중단).
    if isinstance(out, dict) and out.get("ok"):
        await _autoload_ledger(stage, data, out.get("sections") or {})
    return out


@router.post(
    "/report",
    response_model=PipelineReport,
    # ★전수감사 보강: 전체 파이프라인(LLM 포함) 실행 — 인증+한도게이트 부착(/run과 동일 계약).
    # ★잔여 백로그: /report/pdf·/rerun-stage 등 파이프라인 재실행 라우트도 동일 게이트 스윕 권장.
    dependencies=[Depends(get_current_user), Depends(enforce_llm_quota)],
)
async def generate_report(req: PipelineRunRequest):
    """파이프라인 실행 + 통합 보고서 생성.

    전체 파이프라인을 실행한 뒤, 결과를 10섹션 은행 PF 심사용
    통합 보고서로 변환하여 반환한다.
    """
    pipeline = ProjectPipeline()
    result = await pipeline.run(
        address=req.address,
        project_id=req.project_id,
        options=_merge_parcels_into_options(req.options, req.parcels),
    )

    # Fix #3: 결정론 cost/feasibility 산출을 분석원장에 적재(/run과 동일 경로·best-effort).
    await _record_pipeline_ledger(result, req)

    # PipelineState → dict 변환 (stages 내부의 StageResult도 직렬화)
    result_dict = result.model_dump()

    report_svc = PipelineReportService()
    report = report_svc.generate(result_dict)
    return report


class ReportPdfRequest(BaseModel):
    """통합 보고서 PDF 요청 — 이미 계산된 결과(result)를 보내면 재실행 없이 즉시 PDF."""
    address: str | None = None
    project_id: str | None = None
    result: dict[str, Any] | None = None   # {summary, stages} (프론트 보유분)


def _normalize_result(result: dict[str, Any]) -> dict[str, Any]:
    """프론트 result(stages=list) → PipelineReportService 기대형(stages=dict) 정규화."""
    out = dict(result or {})
    stages = out.get("stages")
    if isinstance(stages, list):
        out["stages"] = {s.get("stage"): s for s in stages if isinstance(s, dict) and s.get("stage")}
    return out


@router.post("/report/pdf", summary="통합 보고서 PDF 다운로드(결과 제공 시 재실행 없음)")
async def generate_report_pdf(req: ReportPdfRequest):
    """통합 분석 보고서를 PDF로 생성. result가 있으면 그것으로(즉시), 없으면 파이프라인 실행."""
    from fastapi.responses import Response

    from app.services.report.pipeline_report_pdf import build_pipeline_report_pdf

    if req.result:
        result_dict = _normalize_result(req.result)
        if req.address and not result_dict.get("address"):
            result_dict["address"] = req.address
    else:
        pipeline = ProjectPipeline()
        state = await pipeline.run(address=req.address or "", project_id=req.project_id, options=None)
        result_dict = state.model_dump()
        # W2-2: self-execution 경로도 결정론 cost/feasibility 산출을 분석원장에 적재
        #   (형제 /report :595와 동일 경로). _record_pipeline_ledger는 내부 try/except로
        #   어떤 실패도 응답을 막지 않는다(best-effort). 제공-result 경로는 무변경.
        await _record_pipeline_ledger(state, req)

    report = PipelineReportService().generate(result_dict)
    narratives = await _gather_report_narratives(result_dict)
    pdf = build_pipeline_report_pdf(report.model_dump(), narratives=narratives)
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=propai_report.pdf"},
    )


# ── 원장(ledger) 단일출처 직접 렌더 ──────────────────────────

# 원장 analysis_type → 파이프라인 stage 키 매핑.
# PipelineReportService.generate / _gather_report_narratives 가 읽는 stage 키
# (site_analysis, design, cost, feasibility, tax, esg)와 일치시킨다.
# appraisal/avm은 보고서 본문에서 직접 소비하지 않으나 계보 보존용으로 통과시킨다.
_LEDGER_TYPE_TO_STAGE: dict[str, str] = {
    "avm": "appraisal",
    "appraisal": "appraisal",
    "site_analysis": "site_analysis",
    "design": "design",
    "cost": "cost",
    # W1-7: 파이프라인 write-back은 "cost_estimate" 타입으로 적재(record_cost_estimate) —
    # 매핑 부재로 from-ledger 보고서가 cost 단계를 영원히 못 찾던 단선 해소.
    "cost_estimate": "cost",
    "feasibility": "feasibility",
    "tax": "tax",
    "esg": "esg",
    "permit": "permit",
}


class ReportFromLedgerRequest(BaseModel):
    """원장(ledger) 최신 버전 묶음을 단일출처로 통합 보고서 PDF를 직접 렌더."""
    pnu: str | None = None
    address: str | None = None
    project_id: str | None = None


@router.post("/report/pdf-from-ledger", summary="통합 보고서 PDF(분석 원장 단일출처 직접 렌더)")
async def generate_report_pdf_from_ledger(
    req: ReportFromLedgerRequest,
    current: CurrentUser = Depends(get_current_user),
):
    """분석 원장에 적재된 각 분석타입의 최신 버전 payload를 단일출처로
    PF 심사용 통합 보고서 PDF를 직접 생성한다(프론트 컨텍스트 경유 없이).

    pnu/address/project_id 중 하나로 체인을 식별하며, 원장이 비어 있으면
    빈 PDF 대신 안내 JSON을 반환한다.
    """
    from fastapi.responses import JSONResponse, Response

    from app.services.report.pipeline_report_pdf import build_pipeline_report_pdf

    if not (req.pnu or req.address or req.project_id):
        return JSONResponse(
            status_code=422,
            content={"ok": False, "message": "pnu/address/project_id 중 하나는 필수입니다."},
        )

    tid = str(getattr(current, "tenant_id", "") or "") or None
    bundle = await ledger.get_latest(
        analysis_type=None, tenant_id=tid,
        pnu=req.pnu, address=req.address, project_id=req.project_id,
    )
    if not bundle:
        return JSONResponse(
            status_code=200,
            content={"ok": False, "message": "원장에 분석 데이터가 없습니다. 먼저 분석을 실행/저장하세요."},
        )

    # 원장 묶음 → result_dict 조립(stages=dict). PipelineReportService 기대형.
    stages: dict[str, Any] = {}
    version_parts: list[str] = []
    for atype, entry in bundle.items():
        if not isinstance(entry, dict):
            continue
        stage = _LEDGER_TYPE_TO_STAGE.get(atype, atype)
        payload = entry.get("payload")
        stages[stage] = {
            "stage": stage,
            "data": payload if isinstance(payload, dict) else {},
            "ledger_version": entry.get("version"),
            "content_hash": entry.get("content_hash"),
        }
        version_parts.append(f"{stage}:v{entry.get('version')}")

    site_payload = (stages.get("site_analysis") or {}).get("data") or {}
    address = req.address or (site_payload.get("address") if isinstance(site_payload, dict) else None) or ""

    result_dict: dict[str, Any] = {"address": address, "stages": stages}

    report = PipelineReportService().generate(result_dict)
    narratives = await _gather_report_narratives(result_dict)
    pdf = build_pipeline_report_pdf(
        report.model_dump() if hasattr(report, "model_dump") else report,
        narratives=narratives,
    )
    # 헤더값은 ASCII 안전(콜론/쉼표만, 한글 금지).
    versions_header = ",".join(version_parts)[:300] or "none"
    return Response(
        content=pdf, media_type="application/pdf",
        headers={
            "Content-Disposition": "attachment; filename=propai_report_ledger.pdf",
            "X-Ledger-Versions": versions_header,
        },
    )


@router.post("/rerun-stage")
async def rerun_stage(req: StageRerunRequest):
    """특정 단계만 재실행.

    이전 결과를 유지하면서 지정된 단계부터 이후 단계를 연쇄 재계산한다.
    사용자가 입력값(overrides)을 수정한 후 해당 단계만 재분석할 수 있다.

    동작 방식:
    1. ``previous_result.stages`` 가 있으면 options["previous_stage_data"]로 전달되어
       파이프라인이 skip 단계 data와 단계간 payload 3종(SiteToDesign/DesignToCost/
       CostToFeasibility)을 복원한다 — 기본값(500㎡/60%/200%) 왜곡 없이 수정 지점부터
       정확히 재계산. (list[{stage,data}] / {stage:{data}} 양형 모두 수용)
    2. 지정 단계부터 파이프라인 끝까지 재실행한다.
    3. ``stage_overrides`` (다단계) 와 ``overrides`` (단일 — 하위호환) 는 병합되어
       options["stage_overrides"]로 주입, 각 단계 실행 시 참조된다.
    4. 응답은 PipelineRunResponse 호환 형상(stages + summary) + rerun_from/report.
    """
    # stage 유효성 검증
    valid_stages = [s.value for s in PipelineStage]
    if req.stage not in valid_stages:
        raise HTTPException(
            status_code=400,
            detail=f"유효하지 않은 단계: '{req.stage}'. 가능한 값: {valid_stages}",
        )

    target_idx = valid_stages.index(req.stage)

    # options 구성: 다단계 stage_overrides + 기존 단일 overrides 병합.
    # 동일 단계 키 충돌 시 기존 계약인 overrides가 우선(단일 필드 호출자의 의도 보존).
    merged_overrides: dict[str, dict[str, Any]] = {
        name: dict(ov)
        for name, ov in (req.stage_overrides or {}).items()
        if isinstance(ov, dict) and ov
    }
    if req.overrides:
        merged_overrides[req.stage] = {
            **merged_overrides.get(req.stage, {}),
            **req.overrides,
        }

    options: dict[str, Any] = {}
    if merged_overrides:
        options["stage_overrides"] = merged_overrides

    # skip_stages: 재실행 대상 이전 단계를 스킵 (이전 결과 유지)
    skip_before = valid_stages[:target_idx]
    options["skip_stages"] = skip_before

    # 이전 결과 → previous_stage_data 주입 (미제공 시 키 자체를 생략 — 하위호환)
    if req.previous_result:
        options["previous_stage_data"] = req.previous_result.get(
            "stages", req.previous_result
        )

    # ★다필지 통합(리뷰 HIGH): 재실행도 parcels를 흘려 site_analysis가 통합면적을 유지한다 —
    #   없으면 단계 재실행 시 대표필지 면적으로 조용히 회귀(원 버그 재현)한다.
    options = _merge_parcels_into_options(options, req.parcels) or options

    pipeline = ProjectPipeline()
    result = await pipeline.run(
        address=req.address,
        project_id=req.project_id,
        options=options,
    )

    # W2-2: 단계 재실행의 결정론 산출(cost/feasibility)도 분석원장에 적재
    #   (형제 /report :595와 동일 경로·시그니처). _record_pipeline_ledger는 내부
    #   try/except로 어떤 실패도 응답을 막지 않는다(best-effort). 상태 리매핑 전 적재해도
    #   record_pipeline_results는 stage.data만 읽으므로 결과는 동일.
    await _record_pipeline_ledger(result, req)

    # 하위호환: 이전 결과로 data가 복원된 skip 단계는 응답에서 completed로 표기
    # (기존 라우터가 prev data 채움+COMPLETED 처리하던 응답 계약 보존).
    if req.previous_result:
        for skipped_stage in skip_before:
            sr = result.stages.get(skipped_stage)
            if sr and sr.status == PipelineStatus.SKIPPED and sr.data:
                sr.status = PipelineStatus.COMPLETED

    stages = _build_stages_response(result)

    # 보고서도 함께 생성
    result_dict = result.model_dump()
    report_svc = PipelineReportService()
    report = report_svc.generate(result_dict)

    # 최종 요약 — run_pipeline과 동일 소스(report 단계 data.summary).
    # _run_report가 SKIPPED+data 단계도 포함하므로 미재계산 단계 결과가 유실되지 않는다.
    summary: dict[str, Any] = {}
    report_stage = result.stages.get("report")
    if report_stage and report_stage.data:
        summary = report_stage.data.get("summary", {})

    return {
        "pipeline_id": result.pipeline_id,
        "project_id": result.project_id,
        "status": result.status.value,
        "rerun_from": req.stage,
        "stages": [s.model_dump() for s in stages],
        "summary": summary,
        "report": report.model_dump(),
    }
