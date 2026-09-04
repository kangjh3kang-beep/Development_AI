"""Flagship A — 90초 AI PreCheck + 조닝 시그널 라우터.

규칙기반 즉시 룰체크(/instant)와 주변 기회필지 시그널(/zoning-signals)을 제공한다.
산정 로직은 app/services/precheck/precheck_service.py에 있으며 본 라우터는 얇게 위임한다.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, model_validator

from app.services.auth.auth_service import get_current_user_optional

router = APIRouter()


class PreCheckInstantRequest(BaseModel):
    """즉시 룰체크 요청."""

    address: str
    pnu: str | None = None
    area_sqm: float | None = None
    use_llm: bool = False


class ZoningSignalsRequest(BaseModel):
    """조닝 시그널(기회필지) 요청 — address/pnu 중 최소 1개 필수."""

    address: str | None = None
    pnu: str | None = None
    radius_m: int = 300

    @model_validator(mode="after")
    def _require_locator(self) -> ZoningSignalsRequest:
        if not (self.address and self.address.strip()) and not (self.pnu and self.pnu.strip()):
            raise ValueError("address 또는 pnu 중 하나는 필수입니다.")
        return self


@router.post("/instant", summary="90초 AI PreCheck — 개발방식 즉시 룰체크")
async def precheck_instant(
    req: PreCheckInstantRequest,
    current_user=Depends(get_current_user_optional),
) -> dict:
    """주소(+선택 면적)로 용도지역을 감지해 M01~M15 개발방식의 인허가 신호등을 산정한다.

    signal: 용도지역 불허→fail / 허용+복잡도≤3→pass / 허용+복잡도4~5→warn.
    면적 있으면 건폐율·용적률 개략 안내, 없으면 해당 check는 warn(면적 미입력).
    use_llm=true면 summary.llm_note 1줄만 LLM(타임아웃시 null).

    응답은 기존 필드(ok/zone_type/area_sqm/legal_limits/methods/summary/sources 등)를
    전부 유지하며, 신뢰 레이어 5블록을 additive로 가산한다(선택적 렌더):
      - inputs: 필드별 provenance(zone_type/area_sqm/official_price/pnu).
      - data_quality: confidence_level/quantitative_reliable/warnings/sources_meta/disclaimer.
      - legal_refs: 한도·조례 법령 원문링크(law.go.kr, 레지스트리 출력만).
      - evidence: 한도·면적·수지 산출 트레이스(EvidencePanel 소비 구조).
      - feasibility_band: best 후보 1건의 최저/기본/최대 3시나리오(검증된 수지엔진).

    인증은 선택(비로그인 체험 퍼널 무회귀) — 로그인 사용자에 한해 결과를 분석원장에
    best-effort 적재한다(비로그인 트래픽까지 전부 적재하면 90초진단 퍼널 최상단이
    원장에 과적재되므로 의도적으로 skip).
    ★P3(R1 REVISE): 성공(ok=True) 결과만 적재한다 — zone/pnu 미확인 early-return(ok=False)은
    zone_type/legal_limits/summary가 전부 결측이라 그대로 기록하면 "빈 요약" 히스토리 항목만
    쌓인다(실패 진단은 히스토리 대상에서 제외 — 재현·감사가 필요하면 별도 로그로 추적).
    """
    if not req.address or not req.address.strip():
        raise HTTPException(status_code=422, detail="address가 필요합니다.")

    from app.services.precheck.precheck_service import run_instant_precheck

    result = await run_instant_precheck(
        address=req.address.strip(),
        pnu=req.pnu,
        area_sqm=req.area_sqm,
        use_llm=req.use_llm,
    )

    # ★히스토리 확산(관례 미러 — permits.py/avm.py와 동일 try/except best-effort).
    #   ★P3(R1 REVISE): ok=False(zone/pnu 미확인 early-return)는 기록 제외 — 핵심 필드 결측인
    #   빈 요약이 히스토리에 쌓이는 것을 막는다.
    if current_user is not None and result.get("ok"):
        try:
            from app.services.ledger.analysis_ledger_service import attach_ledger_hash
            from app.services.ledger.ledger_adapters import record_user_analysis

            legal = result.get("legal_limits") or {}
            far_effective_pct = legal.get("applied_far_pct")
            if far_effective_pct is None:
                far_effective_pct = legal.get("far_pct")
            bcr_effective_pct = legal.get("applied_bcr_pct")
            if bcr_effective_pct is None:
                bcr_effective_pct = legal.get("bcr_pct")
            summ = result.get("summary") or {}

            wb = await record_user_analysis(
                analysis_type="precheck",
                summary={
                    "zone_type": result.get("zone_type"),
                    "area_sqm": result.get("area_sqm"),
                    "far_effective_pct": far_effective_pct,
                    "bcr_effective_pct": bcr_effective_pct,
                    "best": summ.get("best"),
                    "pass_count": summ.get("pass"),
                },
                tenant_id=str(current_user.tenant_id),
                pnu=result.get("pnu") or req.pnu, address=req.address.strip(),
                source="precheck",
                # ★변동감지 표준키(input_signature/signature_parts) 재료 — 단일 소유자(ledger_adapters).
                parcel_count=1, use_llm=req.use_llm,
            )
            result = attach_ledger_hash(result, wb)
        except Exception:  # noqa: BLE001 — 원장 적재 실패해도 90초진단 결과 무손상
            pass

    return result


@router.post("/zoning-signals", summary="조닝 시그널 — 주변 기회필지 탐지")
async def precheck_zoning_signals(req: ZoningSignalsRequest) -> dict:
    """대상 부지 주변(radius_m) 필지를 분석해 통합개발·용도상향·역세권·저밀재건축
    기회 시그널을 산정한다. 주변 필지 0이면 signals=[] + note를 반환한다.
    """
    from app.services.precheck.precheck_service import run_zoning_signals

    return await run_zoning_signals(
        address=req.address.strip() if req.address else None,
        pnu=req.pnu,
        radius_m=req.radius_m,
    )
