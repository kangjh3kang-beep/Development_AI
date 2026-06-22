"""Phase 2b — 매스 캐파 검증(생성 아닌 검증). 엔진 SSOT(용적/건폐) 한도로 최대 허용 규모 산정 + 제공 매스 대조.

design_gen의 생성형 capacity(comprehensive_analysis·solar_envelope·composition)와 비중복 — 본 모듈은 엔진의
reg SSOT(resolve_zone_limit)+대지면적(legal_quantities)으로 '최대 캐파'를 산정하고 제공 매스(proposed_gfa)의
적정성을 검증(부합/미흡/미상)한다. 정북일조·완화 등 추가 제약은 별도(caveat 표면화). 결정론·설명가능(근거+링크).
"""
from __future__ import annotations

from app.contracts.analysis import AnalysisResult
from app.contracts.permit_result import CapacityEnvelope
from app.services.permit.measurement import _legal_basis, _measured_for
from app.services.legal_calc.zone_limit_provider import resolve_zone_limit


def capacity_envelope(result: AnalysisResult, use_zone: str | None,
                      proposed_gfa: float | None = None) -> CapacityEnvelope:
    """최대 캐파(연면적/건축면적) = 대지면적 × 용적/건폐(SSOT). 제공 매스 대조(부합/미흡). 한도/대지 부재면 미상."""
    plot_area = _measured_for(result, "plot_area")
    far = resolve_zone_limit(use_zone, "far_floor_area") if use_zone else None
    bcr = resolve_zone_limit(use_zone, "building_area") if use_zone else None
    far_pct = far[0] if far else None
    bcr_pct = bcr[0] if bcr else None
    env = CapacityEnvelope(
        plot_area_sqm=plot_area, far_pct=far_pct, bcr_pct=bcr_pct,
        proposed_gfa_sqm=proposed_gfa,
        legal_basis=_legal_basis(None, ["국토계획법§78", "국토계획법§77"]),   # 용적률·건폐율 근거+링크
    )
    valid_plot = plot_area is not None and plot_area > 0
    if valid_plot and far_pct is not None:
        env.max_gfa_sqm = plot_area * far_pct / 100.0           # 연면적 한도(식 — 리터럴 할당 아님)
    if valid_plot and bcr_pct is not None:
        env.max_footprint_sqm = plot_area * bcr_pct / 100.0     # 건축면적 한도
    if proposed_gfa is not None and env.max_gfa_sqm is not None:
        env.margin_sqm = env.max_gfa_sqm - proposed_gfa
        env.conformance = "부합" if proposed_gfa <= env.max_gfa_sqm else "미흡"
    else:
        env.conformance = "미상"   # 제공 매스 부재 또는 캐파 산정 불가(대지/한도 부재) → 보류(날조 금지)
    return env
