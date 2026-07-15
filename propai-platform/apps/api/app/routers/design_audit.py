"""설계심사(Design Audit) API 라우터 (U6/DA-5).

설계 개요(PDF/텍스트) 추출 → 심사 실행(U5 오케스트레이터 + DA-4 사각지대 AI) →
결과 조회 → 리포트 PDF(S0~S7, DA-6)까지의 표면.

  POST /design-audit/extract-brief   설계개요 결정론 추출(UploadFile PDF | 텍스트)
  POST /design-audit/run             심사 실행 + design_audits 저장
  GET  /design-audit/{audit_id}      저장된 심사 결과 조회(본인 것만)
  GET  /design-audit/{audit_id}/pdf  리포트 PDF 다운로드

prefix: /api/v1/design-audit — 전 엔드포인트 인증 필수(get_current_user).
저장: design_audits 런타임 DDL(design_reference_service.ensure_schema 관행 미러,
alembic 마이그레이션 대신 CREATE TABLE IF NOT EXISTS — 무중단·idempotent).
정직성: 심사 결과는 자동 점검 + AI 보조 참고자료이며 법적 효력이 없다.
U5 오케스트레이터(design_audit_orchestrator)는 지연 임포트 — 미배포 환경에서도
라우터 등록·다른 엔드포인트는 무중단(run만 503 정직 안내).
"""

from __future__ import annotations

import json
import uuid as _uuid
from datetime import UTC
from typing import Any

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser, get_current_user
from apps.api.database.session import get_db

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/design-audit", tags=["설계심사(Design Audit)"])

_MAX_PDF_BYTES = 25 * 1024 * 1024  # design_references와 동일 한도(도면 PDF 여유)
_MAX_DXF_BYTES = 20 * 1024 * 1024  # UP4(WI-6) — run-upload dxf_file 한도(설계 명시 20MB)

_DISCLAIMER = (
    "본 심사는 공개데이터·결정론 룰체크·AI 보조 기반 참고 자료이며 법적 효력이 없습니다. "
    "인허가 적합 여부의 최종 판단은 허가권자 소관이고, 구조상세·설비는 분야 기술사 확인이 필요합니다."
)


# ── 런타임 DDL(design_reference_service.ensure_schema 관행 미러) ─────────────

_DDL = [
    """CREATE TABLE IF NOT EXISTS design_audits (
        id uuid PRIMARY KEY,
        project_id text,
        user_id uuid,
        overall jsonb,
        inputs jsonb,
        findings jsonb,
        blindspot jsonb,
        sections jsonb,
        created_at timestamptz NOT NULL DEFAULT now()
    )""",
    # ★기존 테이블 무중단 마이그레이션(alembic 금지·런타임 DDL): CREATE TABLE IF NOT EXISTS는
    #   기존 테이블에 컬럼을 추가하지 못하므로 ADD COLUMN IF NOT EXISTS로 sections를 보강한다.
    #   sections 미영속 시 prior_comparison·s1_samples·인센티브가 재조회·PDF에서 소실되던 결함 수정.
    "ALTER TABLE design_audits ADD COLUMN IF NOT EXISTS sections jsonb",
    "CREATE INDEX IF NOT EXISTS idx_design_audits_user ON design_audits(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_design_audits_project ON design_audits(project_id)",
]


async def ensure_schema(db: AsyncSession) -> None:
    for ddl in _DDL:
        await db.execute(sa_text(ddl))
    await db.commit()


def _dump(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)


def _maybe_json(v: Any) -> Any:
    """jsonb 컬럼 값 복원 — asyncpg가 str로 줄 수 있어 양형(str/dict/list) 수용."""
    if isinstance(v, str):
        try:
            return json.loads(v)
        except ValueError:
            return v
    return v


async def _save_audit(
    db: AsyncSession,
    *,
    user_id: Any,
    project_id: str | None,
    overall: Any,
    inputs: Any,
    findings: Any,
    blindspot: Any,
    sections: Any = None,
) -> str:
    await ensure_schema(db)
    audit_id = str(_uuid.uuid4())
    await db.execute(
        sa_text(
            "INSERT INTO design_audits"
            "(id, project_id, user_id, overall, inputs, findings, blindspot, sections) "
            "VALUES (:i, :p, :u, CAST(:o AS jsonb), CAST(:inp AS jsonb), "
            "CAST(:f AS jsonb), CAST(:b AS jsonb), CAST(:s AS jsonb))"
        ),
        {
            "i": audit_id, "p": project_id, "u": str(user_id),
            "o": _dump(overall), "inp": _dump(inputs),
            "f": _dump(findings), "b": _dump(blindspot), "s": _dump(sections),
        },
    )
    await db.commit()
    return audit_id


async def _load_audit(db: AsyncSession, audit_id: str, *, user_id: Any) -> dict[str, Any] | None:
    """본인 소유 심사 1건 조회 — 타인 행·미존재·잘못된 ID 모두 None(404 정직)."""
    try:
        _uuid.UUID(audit_id)
    except (TypeError, ValueError):
        return None
    await ensure_schema(db)
    row = (
        await db.execute(
            sa_text(
                "SELECT id, project_id, user_id, overall, inputs, findings, blindspot, "
                "sections, created_at FROM design_audits WHERE id=:i AND user_id=:u"
            ),
            {"i": audit_id, "u": str(user_id)},
        )
    ).first()
    if row is None:
        return None
    return {
        "id": str(row[0]),
        "project_id": row[1],
        "overall": _maybe_json(row[3]),
        "inputs": _maybe_json(row[4]),
        "findings": _maybe_json(row[5]),
        "blindspot": _maybe_json(row[6]),
        "sections": _maybe_json(row[7]),
        "created_at": row[8].isoformat() if row[8] else None,
    }


# ── U5 오케스트레이터(지연 임포트 — 계약: run(db, site=, params=, geometry=,
#    ifc_file_url=, use_llm=, use_verification_retry=[, rooms=])) ─────────────
#    rooms 키워드는 UP3 확장 계약 — 제공 시에만 가산 전달(미제공 호출은 기존과
#    동일해 rooms 미지원 구버전 run()과도 하위호환). ───────────────────────────


def _get_orchestrator():
    """DesignAuditOrchestrator(U5) 지연 임포트.

    모듈 레벨 임포트를 피해 U5 미배포 환경에서도 라우터 등록은 무중단으로 유지하고,
    run 호출 시점에만 503 정직 안내를 낸다. 테스트에서는 본 함수를 모킹한다.
    """
    from app.services.design_audit.design_audit_orchestrator import DesignAuditOrchestrator

    return DesignAuditOrchestrator()


# ── 설계개요 추출(extract-brief) — 정본 brief_extractor 위임 ──────────────────
# ★DA-1 완성 추출기(brief_extractor.extract_brief: value·quote·confidence·평환산·
#   정규식 폴백, 오케스트레이터 표준 키 total_floor_area_sqm·building_height_m)를 위임
#   사용한다. 라우터 자체 정규식(gfa_sqm/height_m 등 비표준 키 + {ok,brief:{}} 반환)은
#   프론트 fields[] 계약과 절단돼 항상 0필드였던 결함을 제거하고, 응답을 프론트 계약
#   fields[{key,label,value,unit,quote,confidence,source}]로 직렬화한다.

# 표준 키 → 표시 단위(프론트 그리드 표기용, 추출 값에는 미포함 — 표기 단위만).
_BRIEF_UNITS: dict[str, str | None] = {
    "zone_type": None,
    "land_area_sqm": "㎡",
    "building_area_sqm": "㎡",
    "total_floor_area_sqm": "㎡",
    "bcr_pct": "%",
    "far_pct": "%",
    "building_height_m": "m",
    "floors_above": "층",
    "floors_below": "층",
    "units": "세대",
    "parking": "대",
    "building_use": None,
}


def _extract_pdf_text(data: bytes) -> str:
    """PDF 바이트 → 텍스트(PyMuPDF). 미설치·스캔본·암호화 등은 빈 문자열(정직 안내)."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return ""
    try:
        with fitz.open(stream=data, filetype="pdf") as doc:
            return "\n".join(page.get_text("text") for page in doc)
    except Exception:  # noqa: BLE001 — 추출 불가는 정직하게 빈 문자열
        return ""


def _serialize_brief_fields(extracted: dict[str, Any]) -> list[dict[str, Any]]:
    """brief_extractor.extract_brief 출력({fields:{key:{value,quote,confidence}|None}})을
    프론트 계약 fields[{key,label,value,unit,quote,confidence,source}]로 직렬화한다.

    원문 근거 없는 필드(None)는 생략한다(날조 금지 — 누락 필드는 프론트에서 직접 입력).
    """
    from app.services.design_audit.brief_extractor import BRIEF_FIELDS

    fields_map = extracted.get("fields") or {}
    out: list[dict[str, Any]] = []
    for key, label in BRIEF_FIELDS.items():
        rec = fields_map.get(key)
        if not isinstance(rec, dict) or rec.get("value") in (None, ""):
            continue
        out.append({
            "key": key,
            "label": label,
            "value": rec.get("value"),
            "unit": _BRIEF_UNITS.get(key),
            "quote": rec.get("quote"),
            "confidence": rec.get("confidence"),
            "source": "extracted",
        })
    return out


@router.post("/extract-brief")
async def extract_brief(
    file: UploadFile | None = File(None),
    text: str = Form(""),
    use_llm: bool = Form(True),
    current: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """설계개요(대지/연면적·건폐/용적률·층수·세대 등) 추출 — 정본 brief_extractor 위임.

    입력: PDF 파일(file) 또는 텍스트(text) — 둘 다 있으면 텍스트를 우선 결합.
    추출은 LLM 우선(원문 인용·confidence 동반) → 실패 시 한국어 라벨 정규식 폴백(가짜값 금지).
    응답은 프론트 계약 fields[{key,label,value,unit,quote,confidence,source}] — 원문에 없는
    필드는 생략(누락 필드는 프론트에서 직접 입력).
    """
    source_text = (text or "").strip()
    pdf_note: str | None = None
    if file is not None:
        data = await file.read()
        if data:
            if len(data) > _MAX_PDF_BYTES:
                raise HTTPException(status_code=413, detail="파일이 너무 큽니다(최대 25MB).")
            # ★공용 콘텐츠 검증(WP-H 세션2 전역 스윕·fail-closed) — PDF 텍스트 추출 전에 실행/스크립트
            # 위장·MIME 위장·경로순회·폴리글랏 압축폭탄을 차단한다. 실측 계열은 pdf 로 화이트리스트.
            from app.services.security.content_inspection import (
                http_status_for,
                inspect_upload,
            )

            _v = inspect_upload(data, file.filename or "", file.content_type, expected_kinds={"pdf"})
            if not _v.allowed:
                raise HTTPException(
                    status_code=http_status_for(_v.code),
                    detail=f"업로드가 거부되었습니다: {_v.reason}",
                )
            extracted_text = _extract_pdf_text(data)
            if extracted_text.strip():
                source_text = (source_text + "\n" + extracted_text).strip()
            else:
                pdf_note = "PDF 텍스트 추출 불가(스캔본·암호화 또는 추출기 미설치) — 텍스트로 직접 입력하세요."

    if not source_text:
        return {
            "ok": False,
            "message": pdf_note or "추출할 텍스트가 없습니다. PDF 파일 또는 텍스트를 입력하세요.",
            "fields": [],
        }

    from app.services.design_audit.brief_extractor import extract_brief as _extract_brief_fields

    extracted = await _extract_brief_fields(source_text, use_llm=use_llm)
    fields = _serialize_brief_fields(extracted)
    return {
        "ok": True,
        "fields": fields,
        "fields_found": len(fields),
        "source": extracted.get("source"),
        "text_chars": len(source_text),
        "note": extracted.get("note")
        or "원문에 없는 필드는 생략됩니다 — 누락 필드는 아래 그리드에서 직접 입력하세요.",
        **({"pdf_note": pdf_note} if pdf_note else {}),
    }


# ── 심사 실행(run) ───────────────────────────────────────────────────────────


class RunRequest(BaseModel):
    """설계심사 실행 요청 — U5 오케스트레이터 run() 계약과 1:1."""

    project_id: str | None = Field(None, description="프로젝트 ID(선택)")
    site: dict[str, Any] = Field(
        default_factory=dict, description="부지 정보(주소·용도지역·대지면적 등)"
    )
    params: dict[str, Any] = Field(
        default_factory=dict, description="설계 개요 파라미터(extract-brief 출력 등)"
    )
    geometry: dict[str, Any] | None = Field(None, description="설계 지오메트리(선택)")
    ifc_file_url: str | None = Field(None, description="IFC 파일 URL(선택)")
    # UP4(WI-7) additive — 실(室) 목록(UP1 extract_rooms 출력의 rooms 등).
    # 제공 시에만 orchestrator.run(rooms=...)으로 가산 전달(미제공 시 기존 호출 동일).
    rooms: list[dict[str, Any]] | None = Field(
        None, description="실(室) 목록(DXF rooms 역추출 등 — 선택, grammar 검증용)"
    )
    use_llm: bool = Field(True, description="AI 보조(사각지대 쟁점 생성) 사용 여부")
    use_verification_retry: bool = Field(True, description="검증관 1회 재생성 사용 여부")


@router.post("/run")
async def run_design_audit(
    req: RunRequest,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """설계심사 실행 — U5 오케스트레이터 + DA-4 사각지대 AI + design_audits 저장.

    blindspot(AI)·저장은 best-effort 무중단: 실패해도 결정론 심사 결과는 반환한다.
    """
    return await _execute_run(req, current, db)


async def _execute_run(
    req: RunRequest,
    current: CurrentUser,
    db: AsyncSession,
) -> dict[str, Any]:
    """/run·/run-upload 공용 실행 본체(계약 동일 — multipart 진입점만 분리)."""
    try:
        orchestrator = _get_orchestrator()
    except Exception as e:  # noqa: BLE001 — U5 미배포 등
        logger.warning("설계심사 오케스트레이터 로드 실패", error=str(e)[:120])
        raise HTTPException(
            status_code=503, detail="설계심사 엔진이 아직 준비되지 않았습니다. 잠시 후 다시 시도하세요."
        ) from e

    run_kwargs: dict[str, Any] = {
        "site": req.site,
        "params": req.params,
        "geometry": req.geometry,
        "ifc_file_url": req.ifc_file_url,
        "use_llm": req.use_llm,
        "use_verification_retry": req.use_verification_retry,
    }
    # UP4(WI-7) — rooms는 제공 시에만 키워드 가산(미제공 호출은 기존과 동일 —
    # rooms 미지원 구버전 run() 계약과 하위호환, TypeError 미유발).
    if req.rooms is not None:
        run_kwargs["rooms"] = req.rooms

    # Phase 1 성장루프: 직전 design_audit prior read(best-effort).
    # ★write(record_design_audit, 하단)가 site의 pnu/address를 원장 체인키로 담으므로
    #   read도 **동일 pnu/address**로 조회해야 같은 체인이 매칭된다(_chain_where: pnu 우선 →
    #   address_norm → 둘 다 없으면 NULL 체인). 과거엔 read가 tenant+project_id만 써서
    #   pnu 보유 심사(주경로 — 프론트가 site.pnu/address 전송)는 위쪽 write가 pnu 체인에 적재해도
    #   read는 계속 NULL 체인만 조회 → prior_comparison이 영구 미매칭(항상 공란)이었다.
    _run_site = req.site if isinstance(req.site, dict) else {}
    from app.services.ledger.prior_context import load_prior
    _prior = await load_prior(
        analysis_type="design_audit",
        tenant_id=str(getattr(current, "tenant_id", "") or "") or None,
        pnu=(_run_site.get("pnu") or None),
        address=(_run_site.get("address") or None),
        project_id=req.project_id,
    )
    if _prior:
        run_kwargs["prior_context"] = _prior

    try:
        result = await orchestrator.run(db, **run_kwargs)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        logger.warning("설계심사 실행 실패", error=str(e)[:160])
        raise HTTPException(status_code=502, detail=f"설계심사 실행 실패: {str(e)[:160]}") from e

    if not isinstance(result, dict):
        raise HTTPException(status_code=502, detail="설계심사 결과 형식 오류")

    overall = result.get("overall")
    findings = result.get("findings") or []
    sections_raw = result.get("sections") if isinstance(result.get("sections"), dict) else {}
    # ★오케스트레이터 정본 스키마 정렬(과거 라우터는 모킹 _FAKE_RESULT의 derived_signals/
    #   engine_status/zone_limits 키를 읽어 실엔진 산출과 절단됐다 — derived_signals 항상 {}).
    #   실 U5는 params_used·limits·sections·engines를 낸다. derived_signals는 이를 근거로 합성한다
    #   (blindspot citation_gate 수치 그라운딩 + PDF S7 효율지표 재구성). 무날조 — 실데이터만.
    derived_signals: dict[str, Any] = dict(result.get("params_used") or {})
    _eff = sections_raw.get("efficiency_metrics")
    if _eff is not None:
        derived_signals["efficiency_metrics"] = _eff
    verdict_str = overall.get("verdict") if isinstance(overall, dict) else None

    # DA-4 사각지대(AI) — 전체 실패 시 생략(무중단, blindspot=None).
    blindspot: dict[str, Any] | None = None
    if req.use_llm:
        try:
            from app.services.design_audit.blindspot_interpreter import generate_blindspot

            blindspot = await generate_blindspot(
                findings,
                derived_signals,
                context={"site": req.site, "params": req.params},
                use_verification_retry=req.use_verification_retry,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("blindspot 생성 실패 — 생략(무중단)", error=str(e)[:120])
            blindspot = None

    # 저장 페이로드 — derived_signals는 PDF(S1 비교표본·S7 지표) 재구성을 위해
    # inputs에 함께 보존(스키마 컬럼 추가 없이 jsonb 내 포함).
    inputs = {
        "project_id": req.project_id,
        "site": req.site,
        "params": req.params,
        "geometry_provided": req.geometry is not None,
        "rooms_provided": req.rooms is not None,  # UP4 additive(키 추가만)
        "ifc_file_url": req.ifc_file_url,
        "use_llm": req.use_llm,
        "use_verification_retry": req.use_verification_retry,
        "derived_signals": derived_signals,
    }

    audit_id: str | None = None
    try:
        audit_id = await _save_audit(
            db,
            user_id=current.user_id,
            project_id=req.project_id,
            overall=overall,
            inputs=inputs,
            findings=findings,
            blindspot=blindspot,
            # ★sections 영속(런타임 DDL 컬럼) — prior_comparison·s1_samples·인센티브가
            #   재조회·PDF 재구성에서 소실되던 결함 수정(조회 시 _load_audit이 함께 반환).
            sections=sections_raw or None,
        )
    except Exception as e:  # noqa: BLE001 — 저장 실패해도 결과 반환(무중단)
        logger.warning("design_audits 저장 실패 — 결과는 반환", error=str(e)[:120])

    # Phase 0 unit d: design_audit raw 결과를 원장 단일 SSOT에 best-effort 일원화(실패 무중단).
    # _save_audit가 commit하므로 audit_id 행은 영속 → backlink 안전.
    # ★원장 스코프: site의 pnu/address를 전달해 수동주소 심사가 단일 NULL 체인에 섞이는 것을 막는다
    #   (ledger_adapters.record_design_audit이 이미 pnu/address를 받게 설계됨 — 배선만 봉합).
    #   read(load_prior, 위쪽)와 동일 site(_run_site)를 재사용 — read/write 체인키 대칭 유지.
    ledger_wb: dict[str, Any] | None = None   # 성장루프 조인키(ledger_hash) 노출용 append 결과
    try:
        from app.services.ledger.ledger_adapters import record_design_audit

        ledger_wb = await record_design_audit(
            result=result, audit_id=audit_id,
            tenant_id=str(getattr(current, "tenant_id", "") or "") or None,
            project_id=req.project_id,
            pnu=(_run_site.get("pnu") or None),
            address=(_run_site.get("address") or None),
            created_by=str(getattr(current, "user_id", "") or "") or None,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("원장 배선 append 실패(design_audit)", err=str(e)[:160])

    # 중심엔진 수렴 관측(shadow, 기본 off·fire-and-forget·무중단): 종합 verdict + 체크별 current/limit를 엔진과 대조.
    try:
        from apps.api.config import get_settings

        if get_settings().deliberation_shadow_enabled:  # gate-first(off면 매퍼/스케줄 미발생)
            from app.services.deliberation import shadow_integration, shadow_mappers

            _tid = str(getattr(current, "tenant_id", "") or "") or None
            shadow_integration.observe(  # 비차단 — 엔진 RTT가 심사 응답을 막지 않음
                "design_audit", _tid, shadow_mappers.design_audit({"overall": overall, "findings": findings}))
    except Exception as e:  # noqa: BLE001 — 관측은 심사 흐름 절대 방해 금지
        logger.warning("shadow 관측 실패(design_audit)", err=str(e)[:120])

    # ★성장루프 조인키: 원장 content_hash 를 응답 최상위 `ledger_hash` 로 노출(공용 헬퍼 — 프론트 피드백 키잉).
    from app.services.ledger.analysis_ledger_service import attach_ledger_hash
    return attach_ledger_hash({
        "ok": True,
        "audit_id": audit_id,
        "saved": audit_id is not None,
        "overall": overall,
        # ★프론트(AuditReportView.verdict)는 문자열을 기대한다 — overall(dict)의 verdict만 표면화.
        "verdict": verdict_str,
        "findings": findings,
        "derived_signals": derived_signals,
        "blindspot": blindspot,
        # additive — 오케스트레이터 원자료(섹션 구성용, 미존재 시 None). ★실 U5 정본 키로 정렬:
        #   engine_status←engines, zone_limits←limits(과거 죽은 키를 실 산출과 봉합).
        "sections_raw": result.get("sections"),
        "engine_status": result.get("engines"),
        "zone_limits": result.get("limits"),
        "disclaimer": _DISCLAIMER,
    }, ledger_wb)


def _build_report_sections(resp: dict[str, Any]) -> list[dict[str, Any]]:
    """U7 프론트 AuditSection[] 구성 — 존재하는 원자료만(빈 섹션 미생성, 가짜값 0).

    UP4(WI-7) additive — sections_raw.grammar(UP3 결정론 문법검증 섹션) 존재 시:
      · S5 하위 grammar 핑거: ldk_open·connectivity·daylight 중 **실재 키만** 부착.
      · S6 grammar 경고: warnings|grammar_warnings(list)를 S6에 결합. blindspot
        없이 경고만 있으면 'AI 추정' 라벨 없이 정직 표기로 별도 생성.
    grammar 부재 시 기존 출력과 동일(회귀 0).
    """
    sections: list[dict[str, Any]] = []
    findings = resp.get("findings") or []
    raw = resp.get("sections_raw") or {}
    blindspot = resp.get("blindspot") or {}

    # UP4 — grammar 원자료(결정론 문법검증): 실재 키만 채택(가짜값 0)
    grammar = raw.get("grammar") if isinstance(raw, dict) else None
    g_finger: dict[str, Any] = {}
    g_warnings: list[Any] = []
    if isinstance(grammar, dict) and grammar:
        g_finger = {
            k: grammar[k]
            for k in ("ldk_open", "connectivity", "daylight")
            if grammar.get(k) is not None
        }
        gw = grammar.get("warnings")
        if not isinstance(gw, list):
            gw = grammar.get("grammar_warnings")
        if isinstance(gw, list) and gw:
            g_warnings = gw

    # design_review 원자료(파라미터 법규검토) — pass_rate 정직화(not_checked_items) surface.
    # ★design_review_service가 검사한 항목(건폐율·용적률)만 판정하고 나머지(일조·주차·피난 등)는
    #   not_checked로 분리해 반환한다(pass_rate 오도 제거) — 이 원자료를 s5에 실어 프론트에 전달.
    design_review_raw = raw.get("design_review") if isinstance(raw, dict) else None
    not_checked_items = (
        design_review_raw.get("not_checked_items")
        if isinstance(design_review_raw, dict)
        else None
    )

    if findings:
        s5: dict[str, Any] = {
            "id": "s5",
            "title": "공학·법규 검증 (8룰)",
            "status": resp.get("verdict"),
            "findings": findings,
        }
        if g_finger:
            s5["grammar"] = g_finger
        if not_checked_items:
            s5["not_checked_items"] = not_checked_items
        sections.append(s5)
    elif g_finger:
        # findings 없이 grammar 핑거만 실재 — S5를 grammar 전용으로 생성(빈 섹션 아님)
        sections.append({
            "id": "s5",
            "title": "공학·법규 검증 (8룰)",
            "status": resp.get("verdict"),
            "grammar": g_finger,
        })
    s1 = raw.get("s1_samples") if isinstance(raw, dict) else None
    if s1:
        # 프론트 CaseComparisonBlock 계약({available·sample_count·far/bcr_position·vs_median_pp·note})은
        # s1_samples.comparison(DesignReviewService.compare_with_nearby_cases 출력)에 담긴다 — 있으면 언랩.
        case_comparison = (
            s1.get("comparison") if isinstance(s1, dict) and s1.get("comparison") else s1
        )
        sections.append({
            "id": "s1",
            "title": "유사·인근 사례 비교",
            "case_comparison": case_comparison,
        })
    s4 = raw.get("s4_incentives") if isinstance(raw, dict) else None
    if s4:
        sections.append({
            "id": "s4",
            "title": "적용 가능 법규·정책 인센티브",
            "incentives": s4,
        })
    eff = raw.get("efficiency_metrics") if isinstance(raw, dict) else None
    if eff:
        sections.append({
            "id": "s7",
            "title": "설계 효율 지표",
            "evidence": eff,
        })
    # ★blindspot 정본 키는 items(generate_blindspot 출력) — 과거 'blindspots'를 읽어 S6가 항상 비었다.
    bs_items = (blindspot or {}).get("items") if isinstance(blindspot, dict) else None
    if bs_items:
        s6: dict[str, Any] = {
            "id": "s6",
            "title": "심의 예상 쟁점·사각지대 (AI 추정)",
            "blind_spots": bs_items,
        }
        if g_warnings:
            s6["grammar_warnings"] = g_warnings
            s6["grammar_note"] = "grammar 경고는 결정론 문법검증 결과(AI 추정 아님)"
        sections.append(s6)
    elif g_warnings:
        # blindspot 없이 grammar 경고만 실재 — 'AI 추정' 라벨 없이 정직 표기
        sections.append({
            "id": "s6",
            "title": "심의 예상 쟁점·사각지대",
            "grammar_warnings": g_warnings,
            "grammar_note": "결정론 문법검증(LDK 오픈·연결성·채광) 경고 — AI 추정 아님",
        })
    return sections


# ── UP4(WI-6) — run-upload DXF 수용(parse_dxf_to_shapes → cad_upload_hub) ────


def _rooms_list_of(hub_rooms: Any) -> list[dict[str, Any]] | None:
    """허브 rooms 산출({rooms:[...], warnings:[...]} dict | list)에서 실 dict 목록만 추출.

    UP2 허브의 rooms는 UP1 extract_rooms 출력(dict) 또는 미배포 시 None이다.
    빈 목록·비정형은 None — 가짜 실 금지(미제공과 동일 취급).
    """
    if isinstance(hub_rooms, dict):
        hub_rooms = hub_rooms.get("rooms")
    if not isinstance(hub_rooms, list):
        return None
    rooms = [r for r in hub_rooms if isinstance(r, dict)]
    return rooms or None


async def _ingest_dxf_upload(dxf_file: UploadFile) -> dict[str, Any] | None:
    """dxf_file 업로드 → parse_dxf_to_shapes → cad_upload_hub.distribute(UP2 허브).

    검증: .dxf 확장자(아니면 422) → 20MB 한도(초과 413 — PDF 25MB 관행 미러) →
    파싱 실패(ValueError — 손상/비DXF/ezdxf 미설치)는 422 정직(가짜 기하 금지).
    빈 파일은 None(미제공과 동일 — ifc_file 경로 관행 미러).
    """
    if not (dxf_file.filename or "").lower().endswith(".dxf"):
        raise HTTPException(
            status_code=422, detail="DXF 파일(.dxf 확장자)만 업로드할 수 있습니다."
        )
    data = await dxf_file.read()
    if not data:
        return None
    if len(data) > _MAX_DXF_BYTES:
        raise HTTPException(status_code=413, detail="DXF 파일이 너무 큽니다(최대 20MB).")

    # ★공용 콘텐츠 검증(WP-H 세션2 전역 스윕·fail-closed) — parse_dxf_to_shapes(공용 파서) 전에
    # 실행/스크립트 위장·MIME 위장·경로순회·폴리글랏 압축폭탄을 차단한다. ★expected_kinds
    # 미지정(WP-H 세션2 CI 회귀 수정 — CSV/parcel_excel과 동일 정책): DXF는 강한 매직바이트가
    # 없는 텍스트 포맷이라 정상 파일도 매직판별 실패로 415 과대거부될 수 있다. 형식 판정(손상/
    # 비DXF)은 parse_dxf_to_shapes 가 맡아 422 로 정직 거부한다(가짜 기하 금지) — 여기서는
    # exe/스크립트·활성콘텐츠·경로순회·압축폭탄만 차단한다.
    from app.services.security.content_inspection import http_status_for, inspect_upload

    _v = inspect_upload(data, dxf_file.filename or "", dxf_file.content_type)
    if not _v.allowed:
        raise HTTPException(
            status_code=http_status_for(_v.code),
            detail=f"업로드가 거부되었습니다: {_v.reason}",
        )

    from app.services.cad.dxf_import_service import parse_dxf_to_shapes

    try:
        parse_result = parse_dxf_to_shapes(data)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"DXF 파싱 실패: {str(e)[:160]}") from e

    from app.services.cad.cad_upload_hub import distribute

    return distribute(parse_result)


@router.post("/run-upload")
async def run_design_audit_upload(
    payload: str = Form(..., description="실행 페이로드 JSON 문자열(site/brief/drawing)"),
    ifc_file: UploadFile | None = File(None),
    dxf_file: UploadFile | None = File(None),
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """설계심사 실행(multipart) — 프론트 4단 스테퍼 진입점.

    /run(JSON)과 동일 본체를 공유하고, ①payload(JSON 문자열) 파싱
    ②brief.fields[{key,value}] → params dict 변환 ③IFC 업로드를 임시파일로
    저장해 ifc_file_url로 전달만 추가한다. 응답에 프론트 계약 별칭
    (id·verdict·sections)을 가산한다(/run 응답 키도 전부 포함 — additive).

    UP4(WI-6) additive — dxf_file 수용: parse_dxf_to_shapes(20MB·.dxf 검증,
    파싱 실패 422) → cad_upload_hub.distribute로 design_raw→geometry,
    rooms→RunRequest.rooms, params_hint→brief 미입력 항목만 보완(기존값 우선·
    덮어쓰기 금지). 적용 내역은 응답 dxf_import 키로 투명 보고(additive).
    payload의 geometry/rooms 직접 입력은 DXF보다 우선한다(덮어쓰기 금지).
    """
    import json as _json

    try:
        body = _json.loads(payload or "{}")
        if not isinstance(body, dict):
            raise ValueError("payload는 JSON 객체여야 합니다")
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=422, detail=f"payload JSON 파싱 실패: {str(e)[:80]}") from e

    site = body.get("site") if isinstance(body.get("site"), dict) else {}
    # brief.fields[{key,value,source}] → params dict (value null은 제외 — 날조 금지)
    params: dict[str, Any] = {}
    brief = body.get("brief") if isinstance(body.get("brief"), dict) else {}
    for f in brief.get("fields") or []:
        if isinstance(f, dict) and f.get("key") and f.get("value") is not None:
            params[str(f["key"])] = f["value"]
    # params를 직접 주는 호출(JSON /run 형태 페이로드)도 수용
    if isinstance(body.get("params"), dict):
        params.update({k: v for k, v in body["params"].items() if v is not None})

    ifc_file_url: str | None = body.get("ifc_file_url")
    if ifc_file is not None and ifc_file.filename:
        import tempfile

        data = await ifc_file.read()
        if data:
            # ★공용 콘텐츠 검증(WP-H 세션2 전역 스윕·fail-closed) — 신뢰 안 되는 바이트를 디스크
            # (tempfile)에 쓰기 전에 실행/스크립트 위장·MIME 위장·경로순회·폴리글랏 압축폭탄을
            # 차단한다. ★expected_kinds 미지정(WP-H 세션2 CI 회귀 수정 — CSV/parcel_excel과 동일
            # 정책): IFC(STEP)는 강한 매직바이트가 없는 텍스트 포맷이라("ISO-10303-21" 헤더
            # 휴리스틱만 존재) 정상 파일도 매직판별 실패로 415 과대거부될 수 있다. 형식 판정은
            # 다운스트림 IFC 파서가 맡고, 여기서는 exe/스크립트·활성콘텐츠·경로순회·압축폭탄만 차단.
            from app.services.security.content_inspection import (
                http_status_for,
                inspect_upload,
            )

            _v = inspect_upload(data, ifc_file.filename or "", ifc_file.content_type)
            if not _v.allowed:
                raise HTTPException(
                    status_code=http_status_for(_v.code),
                    detail=f"업로드가 거부되었습니다: {_v.reason}",
                )
            tmp = tempfile.NamedTemporaryFile(suffix=".ifc", delete=False)
            tmp.write(data)
            tmp.close()
            ifc_file_url = tmp.name

    # payload 직접 입력(geometry/rooms) — DXF 산출보다 우선(덮어쓰기 금지)
    geometry: dict[str, Any] | None = (
        body.get("geometry") if isinstance(body.get("geometry"), dict) else None
    )
    rooms: list[dict[str, Any]] | None = None
    if isinstance(body.get("rooms"), list):
        rooms = [r for r in body["rooms"] if isinstance(r, dict)] or None

    # UP4(WI-6) — DXF 업로드: parse → 허브 분배 → 심사 입력 배선(기존값 우선)
    dxf_import: dict[str, Any] | None = None
    if dxf_file is not None and dxf_file.filename:
        hub = await _ingest_dxf_upload(dxf_file)
        if hub is not None:
            applied: list[str] = []
            if geometry is None and isinstance(hub.get("design_raw"), dict):
                geometry = hub["design_raw"]
                applied.append("geometry")
            hub_rooms = _rooms_list_of(hub.get("rooms"))
            if rooms is None and hub_rooms:
                rooms = hub_rooms
                applied.append("rooms")
            # params_hint — brief 미입력 항목만 보완(기존값 우선·덮어쓰기 금지).
            # 'source'(출처 라벨)는 params에 혼입하지 않고 dxf_import로 투명 보고.
            hint = hub.get("params_hint")
            hint_applied: list[str] = []
            if isinstance(hint, dict):
                for k, v in hint.items():
                    if k == "source" or v is None or k in params:
                        continue
                    params[k] = v
                    hint_applied.append(k)
            dxf_import = {
                "filename": dxf_file.filename,
                "applied": applied,
                "params_hint_applied": sorted(hint_applied),
                "rooms_count": len(hub_rooms or []),
                "diagnostics": hub.get("diagnostics") or [],
            }
            if isinstance(hint, dict) and hint.get("source"):
                dxf_import["params_hint_source"] = hint["source"]

    req = RunRequest(
        project_id=body.get("project_id") or (site.get("project_id") if isinstance(site, dict) else None),
        site=site,
        params=params,
        geometry=geometry,
        ifc_file_url=ifc_file_url,
        rooms=rooms,
        use_llm=bool(body.get("use_llm", True)),
        use_verification_retry=bool(body.get("use_verification_retry", True)),
    )
    resp = await _execute_run(req, current, db)

    # 프론트(AuditReportView) 계약 별칭 — 기존 키 전부 유지(additive).
    # verdict는 _execute_run이 이미 문자열로 표면화했다(overall dict 재대입 금지 — .trim() 크래시 방지).
    from datetime import datetime

    resp["id"] = resp.get("audit_id")
    resp["sections"] = _build_report_sections(resp)
    resp["generated_at"] = datetime.now(UTC).isoformat()
    if dxf_import is not None:
        resp["dxf_import"] = dxf_import  # UP4 additive — DXF 적용 내역 투명 보고
    return resp


# ── 조회·PDF ─────────────────────────────────────────────────────────────────


@router.get("")
async def list_design_audits(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 20,
    project_id: str | None = None,
) -> dict[str, Any]:
    """본인 소유 설계심사 이력 목록(최신순) — 요약 필드만(overall·project_id·생성시각).

    project_id 지정 시 해당 프로젝트로 한정한다. 소유권(user_id) 필터로 타인 행은 제외.
    """
    await ensure_schema(db)
    clamped = max(1, min(limit, 100))
    sql = (
        "SELECT id, project_id, overall, created_at FROM design_audits WHERE user_id=:u "
        + ("AND project_id=:p " if project_id else "")
        + "ORDER BY created_at DESC LIMIT :l"
    )
    params: dict[str, Any] = {"u": str(current.user_id), "l": clamped}
    if project_id:
        params["p"] = project_id
    rows = (await db.execute(sa_text(sql), params)).fetchall()
    audits = [
        {
            "id": str(r[0]),
            "project_id": r[1],
            "overall": _maybe_json(r[2]),
            "created_at": r[3].isoformat() if r[3] else None,
        }
        for r in rows
    ]
    return {"ok": True, "audits": audits, "count": len(audits)}


@router.get("/{audit_id}")
async def get_design_audit(
    audit_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """저장된 설계심사 결과 조회 — 본인 소유만(타인·미존재 404 정직)."""
    audit = await _load_audit(db, audit_id, user_id=current.user_id)
    if audit is None:
        raise HTTPException(status_code=404, detail="심사 결과를 찾을 수 없습니다.")
    return {"ok": True, "audit": audit, "disclaimer": _DISCLAIMER}


@router.get("/{audit_id}/pdf")
async def get_design_audit_pdf(
    audit_id: str,
    format: str = "pdf",
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """설계심사 리포트(S0~S7 + 책임한계·면책) 다운로드(PDF/PPTX/DOCX) — 본인 소유만.

    통합 보고서 생성엔진 경유(format 으로 포맷 선택)."""
    audit = await _load_audit(db, audit_id, user_id=current.user_id)
    if audit is None:
        raise HTTPException(status_code=404, detail="심사 결과를 찾을 수 없습니다.")
    from app.services.report.render import build_report_model_from_design_audit, render_report

    data, media_type, ext = render_report(build_report_model_from_design_audit(audit), format)
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename=design_audit_{audit_id}.{ext}"},
    )
