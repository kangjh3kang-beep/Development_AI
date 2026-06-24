"""Flagship C-2 — 환경분석(일조·조망·스카이라인) 라우터.

POST /api/v1/environment/analyze: 주소/PNU → 좌표·필지·주변건물 →
  일조(태양궤적·일조시간·정북사선)·조망(개방도)·스카이라인(높이맥락).
산정 로직은 app/services/environment/environment_service.py에 있으며 본 라우터는 얇게 위임한다.
정밀 일조분석/측량이 아닌 약식 계산(참고용) — 정직성 비협상(badges 명시).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class DesignParams(BaseModel):
    """대상 건물 제원 — height_m 우선, 없으면 floors×floor_height_m."""

    floors: int | None = None
    height_m: float | None = None
    floor_height_m: float | None = None


class EnvironmentAnalyzeRequest(BaseModel):
    """환경분석 요청 — address/pnu 중 최소 1개 필수."""

    address: str | None = None
    pnu: str | None = None
    design_params: DesignParams | None = None
    season: str = "winter"  # winter(동지·기본)|summer(하지)|equinox(춘분)


@router.post("/analyze", summary="환경분석 — 일조(일조시간·정북사선)·조망(개방도)·스카이라인")
async def analyze(req: EnvironmentAnalyzeRequest) -> dict:
    """주소/PNU 기준 좌표·필지·주변 건물로 일조·조망·스카이라인을 약식 정량 분석한다.

    - solar: 위도·날짜·시각별 천문식 태양 고도/방위(3D 궤적), 동지 9~15시 약식 일조시간,
      주거지역 정북 일조사선(건축법 제61조) 이격 검토.
    - view: 건물 상부 8방위 개방도 점수(0~100)·가림율·양호 조망 방향.
    - skyline: 대상 높이 vs 주변 평균/최고 → 돌출/조화/매몰.

    정밀 일조분석/측량 아님(참고용) — badges에 약식 근거 명시.
    """
    if not (req.address and req.address.strip()) and not (req.pnu and req.pnu.strip()):
        raise HTTPException(status_code=422, detail="address 또는 pnu 중 하나는 필수입니다.")

    from app.services.environment.environment_service import analyze_environment

    dp = req.design_params.model_dump(exclude_none=True) if req.design_params else None
    result = await analyze_environment(
        address=(req.address or "").strip() or None,
        pnu=(req.pnu or "").strip() or None,
        design_params=dp,
        season=req.season or "winter",
    )

    # 표준 근거 블록(#5): 환경분석이 '실제 산출한 값'(일조시간·정북사선·개방도·스카이라인)과
    # 그 산식/근거만 가산한다(graceful·무목업 — 실값만, 빈/가짜 금지). 분석 실패(ok=False)면 skip.
    if isinstance(result, dict) and result.get("ok"):
        try:
            from app.services.data_validation.evidence_contract import build_evidence_block

            solar = result.get("solar") or {}
            view = result.get("view") or {}
            skyline = result.get("skyline") or {}
            north = solar.get("north_setback") or {}
            items: list[dict] = []

            # 일조시간(선택 계절 9~15시 약식) — 실제 표본 가림판정 결과
            if solar.get("sunlight_hours") is not None:
                season_label = solar.get("season_label") or "기준일"
                items.append({
                    "label": f"일조시간({season_label} 9~15시)",
                    "value": solar.get("sunlight_hours"),
                    "basis": "태양 천문 근사식(NOAA) + 주변 footprint 2D 평면투영 가림판정(약식)",
                })
            # 정북 일조사선(적용 대상일 때만 required_m 노출 — 비적용은 근거 키만)
            if north.get("applies") and north.get("required_m") is not None:
                items.append({
                    "label": "정북 일조사선 이격(약식)",
                    "value": north.get("required_m"),
                    "basis": north.get("detail") or "건축법 제61조·시행령 제86조 기본규정값(조례·완화 미반영)",
                    "legal_ref_key": "daylight_height",
                })
            # 조망 개방도(8방위 올려본각 약식)
            if view.get("openness_score") is not None:
                items.append({
                    "label": "조망 개방도(0~100)",
                    "value": view.get("openness_score"),
                    "basis": "건물 상부 8방위 섹터 최대 올려본각 → 개방도 정규화(수목·원경 미반영 약식)",
                })
            # 스카이라인(주변 평균/최고 대비 위치)
            if skyline.get("position"):
                items.append({
                    "label": "스카이라인 위치",
                    "value": skyline.get("position"),
                    "basis": f"대상 {skyline.get('subject_height_m')}m vs 주변 평균 "
                             f"{skyline.get('neighbor_avg_m')}m·최고 {skyline.get('neighbor_max_m')}m",
                })

            if items:
                # 주거지역(정북사선 적용)일 때만 시행령 위임조문도 함께 노출(verified 키만).
                legal_keys = ["daylight_height", "daylight_height_dec"] if north.get("applies") else []
                result["evidence"] = build_evidence_block(
                    items=items,
                    legal_ref_keys=legal_keys,
                    sources=["VWorld(국토교통부 공간정보)", "NOAA 태양위치 근사식"],
                )
        except Exception:  # noqa: BLE001 — 근거 블록 실패는 환경분석 결과를 막지 않음(가산·정직).
            pass

    return result
