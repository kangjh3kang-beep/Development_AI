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

    return await analyze_terrain(
        address=(req.address or "").strip() or None,
        pnu=(req.pnu or "").strip() or None,
        target_level_m=req.target_level_m,
        section_bearing_deg=req.section_bearing_deg,
    )
