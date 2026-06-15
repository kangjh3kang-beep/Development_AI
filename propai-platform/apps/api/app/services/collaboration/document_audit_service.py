"""SP3-4 회의방 자료교환 8엔진 투입 — 업로드된 설계파일(DXF/IFC)을 실제 자동검증(정직 type-routing).

DXF는 parse_dxf_to_shapes→cad_upload_hub.distribute로 내부 기하(design_raw)로 변환 후, IFC는 임시파일
경로로 DesignAuditOrchestrator.run(db, geometry=/ifc_file_url=)에 투입한다. orchestrator.run은 use_llm을
폐기하는 결정론 전용이라 LLM=0이 자동 보장된다(불변규칙 #4). 문서(PDF 등)는 8엔진이 입력으로 받을 수
없어 "unsupported"로 정직 표기한다(사람 심의자 review_state로 처리 — 과대표기 금지).

변환기·오케스트레이터는 주입 가능 — 테스트는 ezdxf/실엔진 없이 결정론 검증한다.
"""

from __future__ import annotations

from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


def summarize_audit(result: dict) -> dict:
    """orchestrator.run 결과 → 자료교환 문서에 부착할 8엔진 요약(결정론·LLM 0).

    overall.verdict/verdict_en, 지적(findings) 수, ok/실패 엔진 수, 상태별 카운트만 추린다.
    """
    overall = result.get("overall") if isinstance(result.get("overall"), dict) else {}
    findings = result.get("findings") or []
    engines = result.get("engines") if isinstance(result.get("engines"), dict) else {}
    engines_run = sum(1 for v in engines.values() if v == "ok")
    engines_skipped = sum(1 for v in engines.values() if v != "ok")
    return {
        "verdict": overall.get("verdict"),
        "verdict_en": overall.get("verdict_en"),
        "counts": overall.get("counts") or {},
        "findings_count": len(findings),
        "engines_run": engines_run,
        "engines_skipped": engines_skipped,
    }


def _design_ext(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if filename and "." in filename else ""


def _convert_dxf(data: bytes):
    """DXF 바이트 → (geometry=design_raw, rooms) — run-upload 변환경로와 동일(멱등·외부호출 0)."""
    from app.services.cad.dxf_import_service import parse_dxf_to_shapes
    from app.services.cad.cad_upload_hub import distribute

    hub = distribute(parse_dxf_to_shapes(data))
    geometry = hub.get("design_raw") if isinstance(hub.get("design_raw"), dict) else None
    rooms = hub.get("rooms") if isinstance(hub.get("rooms"), list) else None
    return geometry, rooms


def parse_design_shapes(data: bytes) -> dict:
    """저장된 DXF 바이트 → CAD2.0 셰이프(읽기전용 뷰어용). parse_dxf_to_shapes 위임(결정론).

    반환: {shapes, bounds_px, scale_px_per_m, ...}. 빈/무효 DXF는 ValueError(가짜 기하 금지).
    """
    from app.services.cad.dxf_import_service import parse_dxf_to_shapes

    return parse_dxf_to_shapes(data)


def _default_orchestrator():
    from app.services.design_audit.design_audit_orchestrator import DesignAuditOrchestrator

    return DesignAuditOrchestrator()


async def run_design_document_audit(
    db: Any,
    *,
    filename: str,
    data: bytes,
    convert_dxf=None,
    orchestrator=None,
    project_id: Optional[str] = None,    # Phase 0 unit d: 원장 backlink context(호출처 thread-through)
    tenant_id: Optional[str] = None,
    created_by: Optional[str] = None,
) -> tuple[str, Optional[dict]]:
    """설계파일(DXF/IFC) 8엔진 투입 → (audit_status, audit_summary).

    - dxf/ifc가 아니면 ("unsupported", None) — 8엔진은 문서를 입력으로 받지 못한다(정직).
    - site/params 미상이면 해당 엔진은 orchestrator 내장 정직 degrade로 skipped 처리된다.
    예외는 호출측이 "failed"로 표기한다(업로드는 이미 성공 — best-effort).
    """
    ext = _design_ext(filename)
    if ext not in ("dxf", "ifc"):
        return ("unsupported", None)

    orch = orchestrator or _default_orchestrator()
    if ext == "dxf":
        geometry, rooms = (convert_dxf or _convert_dxf)(data)
        result = await orch.run(db, geometry=geometry, rooms=rooms)
    else:  # ifc — 임시파일 경로로 전달 후 예외에도 반드시 정리(디스크 누수 방지)
        import os
        import tempfile

        tmp = tempfile.NamedTemporaryFile(suffix=".ifc", delete=False)
        try:
            tmp.write(data)
            tmp.close()
            result = await orch.run(db, ifc_file_url=tmp.name)
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass

    # Phase 0 unit d: design_audit raw 결과를 원장 단일 SSOT에 best-effort 일원화(실패 무중단).
    try:
        from app.services.ledger.ledger_adapters import record_design_audit

        await record_design_audit(
            result=result, tenant_id=tenant_id, project_id=project_id,
            created_by=created_by,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("원장 배선 append 실패(design_audit/document)", err=str(e)[:160])

    return ("completed", summarize_audit(result))
