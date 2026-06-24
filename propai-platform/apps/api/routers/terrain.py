"""Flagship C-1 — 지형분석(경사도·토공량·지형단면) 라우터.

POST /api/v1/terrain/analyze: 주소/PNU → DEM 격자 → 경사도·토공량·지형단면.
산정 로직은 app/services/terrain/terrain_service.py에 있으며 본 라우터는 얇게 위임한다.
표고는 OpenTopoData SRTM 30m(무료) 기반 — 정밀 측량/검증된 토목설계가 아님(참고용).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class TerrainAnalyzeRequest(BaseModel):
    """지형분석 요청 — address/pnu 중 최소 1개 필수."""

    address: str | None = None
    pnu: str | None = None
    target_level_m: float | None = None  # 토공 기준고(계획고). 미제공시 평균표고.
    section_bearing_deg: float | None = None  # 단면 진행 방위(북=0, 시계방향). 미제공시 최대경사방향.


@router.post("/analyze", summary="지형분석 — 경사도·토공량·지형단면(DEM 기반)")
async def analyze(req: TerrainAnalyzeRequest) -> dict:
    """필지 표고 격자(SRTM 30m)로 경사도·토공량·지형단면을 산정한다.

    - slope: 격자 표고차/거리 → 평균·최대 경사율(%), 사면 향(aspect), 등급(평지/완경사/경사/급경사).
    - earthwork: base_level(target_level_m 또는 평균표고) 기준 셀별 절토/성토/순량.
    - cross_section: 중심 통과 직선(section_bearing_deg 또는 최대경사방향) 표고 프로필.
    - confidence/note: 필지면적 대비 DEM 해상도로 신뢰도 산정 — 소형 필지/저해상도는 낮음.
    """
    if not (req.address and req.address.strip()) and not (req.pnu and req.pnu.strip()):
        raise HTTPException(status_code=422, detail="address 또는 pnu 중 하나는 필수입니다.")

    from app.services.terrain.terrain_service import analyze_terrain

    result = await analyze_terrain(
        address=(req.address or "").strip() or None,
        pnu=(req.pnu or "").strip() or None,
        target_level_m=req.target_level_m,
        section_bearing_deg=req.section_bearing_deg,
    )

    # 표준 근거 블록(#5): DEM으로 실제 산출한 경사도·토공량·기복 값과 그 산식·출처만
    # items로 가산(graceful·무목업). 지형분석은 물리계산이라 법령근거(legal_ref)는 없고,
    # 표고 원천(SRTM 30m·VWorld)을 evidence basis로 명시한다. ok:false면 부착하지 않는다.
    if isinstance(result, dict) and result.get("ok"):
        try:
            from app.services.data_validation.evidence_contract import build_evidence_block

            slope = result.get("slope") or {}
            earthwork = result.get("earthwork") or {}
            section = result.get("cross_section") or {}
            src_note = result.get("elevation_source") or "OpenTopoData SRTM 30m"
            ev_items: list[dict] = []

            # 경사도(평균·최대) — _compute_slope 중앙차분 산출값
            if slope.get("mean_pct") is not None:
                ev_items.append({
                    "label": "평균 경사율",
                    "value": f"{slope.get('mean_pct')}% ({slope.get('class', '')})",
                    "basis": f"DEM 격자 중앙차분 기울기 평균 — {src_note}",
                })
            if slope.get("max_pct") is not None:
                ev_items.append({
                    "label": "최대 경사율",
                    "value": f"{slope.get('max_pct')}%",
                    "basis": f"DEM 격자 셀별 기울기 최대 — {src_note}",
                })
            # 토공량(절토/성토/순량) — _compute_earthwork base_level 기준
            if earthwork.get("cut_volume_m3") is not None:
                ev_items.append({
                    "label": "절토/성토/순(토공)",
                    "value": (
                        f"절토 {earthwork.get('cut_volume_m3'):,}㎥ / "
                        f"성토 {earthwork.get('fill_volume_m3'):,}㎥ / "
                        f"순 {earthwork.get('net_m3'):,}㎥ ({earthwork.get('balance', '')})"
                    ),
                    "basis": (
                        f"기준고 {earthwork.get('base_level_m')}m 대비 셀별 (표고-기준고)×셀면적 합산 — "
                        f"개략추정, 다짐/팽창률 미반영"
                    ),
                })
            # 지형 기복(단면 최고-최저)
            if section.get("relief_m") is not None:
                ev_items.append({
                    "label": "지형 기복(단면)",
                    "value": f"{section.get('relief_m')}m",
                    "basis": f"중심 통과 단면 프로필 최고-최저 표고차 — {src_note}",
                })

            if ev_items:
                result["evidence"] = build_evidence_block(
                    items=ev_items,
                    legal_ref_keys=None,  # 물리(DEM)계산 — 법령근거 없음(정직표기)
                    sources=["vworld_land_info"],  # 좌표·필지 원천(레지스트리 등록 소스만)
                )
        except Exception:  # noqa: BLE001 — 근거 블록 실패는 기존 결과를 막지 않음.
            pass

    return result
