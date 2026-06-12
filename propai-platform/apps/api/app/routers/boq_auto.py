"""BOQ 자동화 라우터 — 실적 공내역서 마스터 조회 + 파라메트릭 드래프트 + 개산공사비 연동.

prefix: /api/v1/boq-auto

구성(병렬 구현 격리 원칙):
- B1 마스터 조회: app.services.cost.boq_master_registry (랜딩 완료 — 지연 임포트 사용).
  실적 5공종(의정부동 424 주상복합, 3,997 고유항목 · 414 섹션 · 표본 n=1) 표준항목.
- B2 드래프트 생성기(generate_draft/build_xlsx): 병렬 구현 중 — 후보 모듈 지연 해석.
  미배포 시 503 정직 안내(가짜 결과 금지) — design_audit 라우터와 동일 규약.
- apply-cost: 기존 boq_builder.build_boq(무수정 재사용)의 summary.total_project_cost 를
  costData 후보로 동봉. DB 쓰기 없음(persisted=false) — 적용 여부는 호출측 책임.

원칙: 결정론(LLM 0) · additive · 출처/가정 정직 표기 · 기존 서비스 무수정.
"""

from __future__ import annotations

import importlib
import inspect
import io
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/boq-auto", tags=["BOQ 자동화"])

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_EXPORT_FILENAME = "boq_draft.xlsx"
_MAX_ITEMS_LIMIT = 500  # boq_master_registry._MAX_LIMIT 와 동일 클램프(이중 방어)

# B2(드래프트 생성기) 후보 모듈 — 병렬 구현 랜딩명 차이 흡수(첫 매칭 사용, 순서 고정).
_DRAFT_MODULE_CANDIDATES: tuple[str, ...] = (
    "app.services.cost.boq_parametric_engine",  # B2 실모듈(랜딩 확정 — 최우선)
    "app.services.cost.boq_draft_generator",
    "app.services.cost.boq_draft_service",
    "app.services.cost.boq_draft_builder",
    "app.services.cost.boq_draft",
)


# ── 지연 의존성 접근자(테스트 모킹 지점 — design_audit._get_orchestrator 규약) ──


def _get_master():
    """B1 마스터 레지스트리 모듈 — 미배포 시 503 정직(가짜 목록 금지)."""
    try:
        from app.services.cost import boq_master_registry
    except ImportError as exc:  # pragma: no cover — B1 랜딩 완료(방어용)
        raise HTTPException(
            status_code=503,
            detail=f"BOQ 마스터 레지스트리(B1) 미배포 — 조회 불가(정직 안내): {exc}",
        ) from exc
    return boq_master_registry


def _get_draft_module():
    """B2 드래프트 생성기 모듈(generate_draft + build_xlsx) — 후보 순회 해석.

    미배포/시그니처 불일치 시 503 정직 안내(가짜 드래프트 금지).
    """
    for name in _DRAFT_MODULE_CANDIDATES:
        try:
            mod = importlib.import_module(name)
        except ImportError:
            continue
        if callable(getattr(mod, "generate_draft", None)) and callable(
            getattr(mod, "build_xlsx", None)
        ):
            return mod
    raise HTTPException(
        status_code=503,
        detail=(
            "BOQ 드래프트 생성기(B2: generate_draft/build_xlsx) 미배포 — "
            "가짜 결과 대신 정직 안내. 후보 모듈: " + ", ".join(_DRAFT_MODULE_CANDIDATES)
        ),
    )


def _get_build_boq():
    """기존 적산 자산 boq_builder.build_boq(무수정 재사용) — 미배포 시 503 정직."""
    try:
        from app.services.cost.boq_builder import build_boq
    except ImportError as exc:  # pragma: no cover — 기존 자산(방어용)
        raise HTTPException(
            status_code=503,
            detail=f"boq_builder(기존 적산 자산) 미배포 — 개산 공사비 산정 불가: {exc}",
        ) from exc
    return build_boq


# ── 호출 어댑터(병렬 구현 모듈 간 느슨한 결합 — 결정론 유지) ──


def _call_adaptive(fn: Any, /, **kwargs: Any) -> Any:
    """시그니처에 없는 키워드는 제거하고 호출. **kwargs 수용 함수는 전체 전달."""
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return fn(**kwargs)
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return fn(**kwargs)
    return fn(**{k: v for k, v in kwargs.items() if k in params})


async def _invoke_draft_fn(fn: Any, req: "BoqDraftRequest") -> Any:
    """B2 함수(generate_draft/build_xlsx) 호출 — sync/async 모두 지원."""
    try:
        result = _call_adaptive(
            fn,
            params=req.params.model_dump(exclude_none=True),
            disciplines=req.disciplines,
        )
    except TypeError as exc:
        # 바인딩 불일치(병렬 구현 시그니처 차이) — 503 정직(원문 동봉).
        raise HTTPException(
            status_code=503,
            detail=f"BOQ 드래프트 생성기(B2) 호출 시그니처 불일치: {exc}",
        ) from exc
    if inspect.isawaitable(result):
        result = await result
    return result


def _as_xlsx_bytes(raw: Any) -> bytes:
    """build_xlsx 산출물을 bytes 로 정규화(bytes/BytesIO/file-like/Workbook/(bytes, mime))."""
    if isinstance(raw, tuple) and raw and isinstance(raw[0], (bytes, bytearray)):
        return bytes(raw[0])  # ExcelExportService 관례((file_bytes, content_type)) 흡수
    if isinstance(raw, (bytes, bytearray)):
        return bytes(raw)
    if hasattr(raw, "getvalue"):
        value = raw.getvalue()
        if isinstance(value, (bytes, bytearray)):
            return bytes(value)
    if hasattr(raw, "read"):
        value = raw.read()
        if isinstance(value, (bytes, bytearray)):
            return bytes(value)
    if hasattr(raw, "save"):  # openpyxl Workbook 호환
        buf = io.BytesIO()
        raw.save(buf)
        return buf.getvalue()
    raise HTTPException(
        status_code=500,
        detail=f"build_xlsx 산출물 형식 인식 실패(type={type(raw).__name__}) — 정직 안내",
    )


def _draft_summary_of(draft: Any) -> Optional[dict[str, Any]]:
    """드래프트 결과에서 summary 추출 — items 전체(최대 3,997행) 중복 동봉 방지."""
    if not isinstance(draft, dict):
        return None
    summary = draft.get("summary")
    if isinstance(summary, dict):
        return summary
    return {k: v for k, v in draft.items() if k != "items"}


# ── 요청 스키마 ──


class BoqDraftParams(BaseModel):
    """드래프트 생성 파라미터 — gfa_sqm 필수(>0), 나머지 선택."""

    gfa_sqm: float = Field(..., gt=0, description="연면적(㎡) — 필수, 0 초과")
    households: Optional[int] = Field(None, ge=0, description="세대수(선택)")
    site_area_sqm: Optional[float] = Field(None, gt=0, description="대지면적(㎡, 선택)")
    landscape_area_sqm: Optional[float] = Field(None, gt=0, description="조경면적(㎡, 선택)")


class BoqDraftRequest(BaseModel):
    """드래프트 생성/내보내기 요청."""

    params: BoqDraftParams
    disciplines: Optional[list[str]] = Field(
        None, description="대상 공종 목록(없으면 B2 기본 = 전체 5공종)")


class BoqApplyCostRequest(BoqDraftRequest):
    """드래프트 + 개산 공사비(costData 후보) 연동 요청 — DB 쓰기 없음."""

    project_id: str = Field(..., min_length=1, description="프로젝트 ID(응답 echo 용)")


# ── 엔드포인트 ──


@router.get("/master/summary", summary="공내역서 마스터 5공종 요약 + 출처(provenance)")
def master_summary() -> dict[str, Any]:
    """B1 list_disciplines 결과와 출처(provenance)를 반환한다(표본 n=1 정직 표기)."""
    reg = _get_master()
    return {
        "disciplines": reg.list_disciplines(),
        "provenance": reg.get_provenance(),
    }


@router.get("/master/items", summary="공종 표준항목 조회(섹션/검색/페이지네이션)")
def master_items(
    discipline: str = Query(..., description="공종 — 한글 canonical(건축 등) 또는 영문 stem(architecture 등)"),
    section_code: Optional[str] = Query(None, description="섹션 코드 필터"),
    q: Optional[str] = Query(None, description="name/spec 부분일치 검색어"),
    limit: int = Query(100, ge=1, description="페이지 크기(<=500 클램프)"),
    offset: int = Query(0, ge=0, description="페이지 오프셋"),
) -> dict[str, Any]:
    """B1 get_items 위임 — limit 은 500 으로 클램프(레지스트리와 동일 이중 방어)."""
    reg = _get_master()
    clamped = min(limit, _MAX_ITEMS_LIMIT)
    return reg.get_items(
        discipline,
        section_code=section_code,
        query=q,
        limit=clamped,
        offset=offset,
    )


@router.post("/draft", summary="공내역서 드래프트 생성(B2 — 단가 빈칸·물량 채움)")
async def create_draft(req: BoqDraftRequest) -> dict[str, Any]:
    """B2 generate_draft 위임 — gfa_sqm<=0 은 422(검증), B2 미배포는 503 정직."""
    mod = _get_draft_module()
    draft = await _invoke_draft_fn(mod.generate_draft, req)
    if isinstance(draft, dict):
        return draft
    return {"draft": draft}  # 방어적 래핑(B2 계약은 dict — 비파괴 통과)


@router.post("/draft/export", summary="공내역서 드래프트 XLSX 내보내기")
async def export_draft(req: BoqDraftRequest) -> StreamingResponse:
    """B2 build_xlsx 산출물을 XLSX 스트리밍으로 반환한다(RFC 5987 filename*)."""
    mod = _get_draft_module()
    raw = await _invoke_draft_fn(mod.build_xlsx, req)
    data = _as_xlsx_bytes(raw)
    headers = {
        "Content-Disposition": (
            f'attachment; filename="{_EXPORT_FILENAME}"; '
            f"filename*=UTF-8''{_EXPORT_FILENAME}"
        )
    }
    return StreamingResponse(io.BytesIO(data), media_type=XLSX_MEDIA_TYPE, headers=headers)


@router.post("/draft/apply-cost", summary="드래프트 + 개산 공사비(costData 후보) 연동 — DB 쓰기 없음")
async def apply_cost(req: BoqApplyCostRequest) -> dict[str, Any]:
    """드래프트 summary 와 기존 boq_builder 개산 총액(costData 후보)을 함께 반환한다.

    - boq_builder.build_boq(무수정 재사용) — summary.total_project_cost 를 후보로 동봉.
    - 건축개요(층수/구조 등) 미입력 — 기본 가정값으로 개산하고 assumptions 에 정직 표기.
    - DB 쓰기 없음(persisted=false) — 적용 여부는 호출측(프론트/상위 워크플로우) 책임.
    """
    mod = _get_draft_module()
    draft = await _invoke_draft_fn(mod.generate_draft, req)
    draft_summary = _draft_summary_of(draft)

    build_boq = _get_build_boq()
    assumptions = {
        "building_type": "apartment",
        "structure_type": "RC",
        "floor_count_above": 1,
        "floor_count_below": 0,
        "note": "건축개요(층수·구조) 미입력 — 기본 가정으로 개산(참고용). 개요 입력 시 /api/v1/cost 정밀 경로 권장.",
    }
    boq = build_boq(
        building_type=assumptions["building_type"],
        total_gfa_sqm=req.params.gfa_sqm,
        floor_count_above=assumptions["floor_count_above"],
        floor_count_below=assumptions["floor_count_below"],
        structure_type=assumptions["structure_type"],
        qto_source="derived",
    )
    if inspect.isawaitable(boq):
        boq = await boq
    boq_summary = boq.get("summary", {}) if isinstance(boq, dict) else {}
    total = boq_summary.get("total_project_cost", boq_summary.get("total"))
    if total is None:
        raise HTTPException(
            status_code=500,
            detail="boq_builder 결과에서 summary.total_project_cost 미발견 — 가짜 0원 대신 정직 안내",
        )

    return {
        "project_id": req.project_id,
        "boq_draft_summary": draft_summary,
        "cost_estimate": {
            "total_construction_cost_won": int(total),
            "source": "boq_builder 개산",
            "summary": boq_summary,
            "assumptions": assumptions,
            "builder_badges": boq.get("badges") if isinstance(boq, dict) else None,
        },
        "badges": [
            "공내역서 마스터: 실적 표본 1건(의정부동 424 주상복합) 기반 드래프트",
            "공사비: boq_builder 개산(확정가 아님) — 전문 적산사 검토 권장",
            "DB 미저장 — costData 후보 값(적용 여부는 사용자 확인)",
        ],
        "persisted": False,
    }
