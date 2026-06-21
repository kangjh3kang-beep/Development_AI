"""설계안 조합(composition) 엔진 — 검색된 도면을 부지 법적 한도에 맞춰 선택·스케일·검증.

'검색+조합'의 조합 절반(v1 토대). 실제 폴리곤 배치(CAD 기하)는 후속이며, 본 단계는
**선택 + 법적 envelope 스케일 + 세대/주차 추정 + 인허가(한도) 게이트 + 랭킹**으로
buildable·compliant 한 Top-N 설계 초안을 만든다. 모든 추정은 warnings로 정직 고지하며,
법적 한도 미상이면 compliant=False(추정 금지). 용적률은 실효(조례) 우선 — far_source 표기.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# 세대수 추정 시 전용률(연면적→전용 환산, 대략) — 추정치임을 명시.
_DEFAULT_EFFICIENCY = 0.75
# 참조도면을 부지에 맞추는 최소 허용 스케일 — 이보다 더 축소해야 하면(도면이 부지의 4배 초과)
# 현실적 조합 불가로 보아 부적합 처리(정직).
_MIN_SCALE = 0.5
# 도면 종류별 조합 가중(검색 적합도 외 완성도 점수용).
_TYPE_WEIGHT = {"floor_plan": 1.0, "site_plan": 0.8, "parking": 0.6, "section": 0.4, "elevation": 0.4}


@dataclass
class SiteContext:
    """조합 입력 — 부지 + 법적 한도(실효 조례 우선)."""

    area_sqm: float
    zone_code: str = "2R"
    width_m: float | None = None
    depth_m: float | None = None
    legal_bcr_pct: float | None = None   # 건폐율 한도(%)
    legal_far_pct: float | None = None   # 용적률 한도(%)
    far_source: str = "unknown"          # ordinance(실효) | statutory(법정) | unknown
    floor_height_m: float = 3.0
    avg_unit_area_sqm: float = 84.0      # 세대 추정용 평균 평형(전용 기준 입력)
    warnings: list[str] = field(default_factory=list)  # 부지/한도 산출 경고(예: 미지정 zone 폴백)

    @property
    def buildable_footprint_sqm(self) -> float | None:
        if self.legal_bcr_pct is None or self.area_sqm <= 0:
            return None
        return round(self.area_sqm * self.legal_bcr_pct / 100.0, 2)

    @property
    def max_gfa_sqm(self) -> float | None:
        if self.legal_far_pct is None or self.area_sqm <= 0:
            return None
        return round(self.area_sqm * self.legal_far_pct / 100.0, 2)

    @property
    def max_floors_est(self) -> int | None:
        fp = self.buildable_footprint_sqm
        gfa = self.max_gfa_sqm
        if not fp or not gfa:
            return None
        return max(1, int(gfa // fp))


@dataclass
class CompositionCandidate:
    """조합 결과 1건(설계 초안)."""

    selected: dict[str, str]            # drawing_type -> point_id
    primary_drawing_type: str
    scale_factor: float | None = None
    estimated_gfa_sqm: float | None = None
    estimated_floors: int | None = None
    estimated_units: int | None = None
    estimated_parking: int | None = None
    compliant: bool = False
    score: float = 0.0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "selected": self.selected,
            "primary_drawing_type": self.primary_drawing_type,
            "scale_factor": self.scale_factor,
            "estimated_gfa_sqm": self.estimated_gfa_sqm,
            "estimated_floors": self.estimated_floors,
            "estimated_units": self.estimated_units,
            "estimated_parking": self.estimated_parking,
            "compliant": self.compliant,
            "score": self.score,
            "warnings": list(self.warnings),
        }


def _g(match: dict, key: str, default=None):
    """검색결과(dict) 안전 접근."""
    return match.get(key, default) if isinstance(match, dict) else default


def fit_score(match: dict, site: SiteContext) -> float:
    """도면이 부지에 맞는 정도(0~1) — 면적 적합 + 도면종류 가중."""
    area = _g(match, "total_area_sqm")
    target = site.buildable_footprint_sqm or site.area_sqm
    if area is None or not target or target <= 0:
        area_fit = 0.5  # 면적 미상 — 중립(추정 금지, 가점/감점 안 함)
    else:
        area_fit = max(0.0, 1.0 - min(1.0, abs(float(area) - target) / target))
    type_w = _TYPE_WEIGHT.get(_g(match, "drawing_type") or "", 0.3)
    # 검색 유사도(score)가 있으면 약하게 반영.
    sim = float(_g(match, "score") or 0.0)
    return round(0.5 * area_fit + 0.3 * type_w + 0.2 * min(1.0, sim), 4)


def _scale_factor(fp_area: float | None, footprint: float | None) -> float | None:
    """평면 면적을 부지 footprint에 맞추는 선형 스케일(면적비의 제곱근). 부족정보면 None."""
    if not fp_area or fp_area <= 0 or not footprint or footprint <= 0:
        return None
    if fp_area <= footprint:
        return 1.0  # 그대로 들어감
    return round(math.sqrt(footprint / fp_area), 4)


def compose(site: SiteContext, matches: list[dict], top_n: int = 3) -> list[CompositionCandidate]:
    """검색된 도면들로 부지 맞춤 설계 초안 Top-N을 조합한다.

    floor_plan을 주(primary)로, 같은 부지에 맞는 site_plan/parking을 동반 선택한다.
    면적은 법적 한도(footprint·max_gfa)로 클램프하고, 한도 미상이면 compliant=False(정직).
    """
    if not matches:
        return []

    # 도면종류별 그룹(검색 점수 내림차순).
    by_type: dict[str, list[dict]] = {}
    for m in matches:
        by_type.setdefault(_g(m, "drawing_type") or "unknown", []).append(m)
    for lst in by_type.values():
        lst.sort(key=lambda x: float(_g(x, "score") or 0.0), reverse=True)

    footprint = site.buildable_footprint_sqm
    max_gfa = site.max_gfa_sqm
    # 주 후보 = floor_plan 우선, 없으면 site_plan, 그래도 없으면 가중·검색점수 최상 종류
    # (next(iter())의 등장순서 의존 제거).
    primaries = by_type.get("floor_plan") or by_type.get("site_plan")
    if not primaries:
        primaries = max(
            by_type.values(),
            key=lambda lst: (
                _TYPE_WEIGHT.get(_g(lst[0], "drawing_type") or "", 0.3),
                float(_g(lst[0], "score") or 0.0),
            ),
        )

    candidates: list[CompositionCandidate] = []
    for fp in primaries[: max(1, top_n)]:
        warnings: list[str] = list(site.warnings)  # 부지/한도 경고 승계(정직 전파)
        selected = {(_g(fp, "drawing_type") or "unknown"): str(_g(fp, "point_id") or "")}
        # 동반 도면(있으면) 1건씩 첨부.
        for comp_type in ("site_plan", "parking"):
            if comp_type not in selected and by_type.get(comp_type):
                selected[comp_type] = str(_g(by_type[comp_type][0], "point_id") or "")

        fp_area = _g(fp, "total_area_sqm")
        scale = _scale_factor(float(fp_area) if fp_area else None, footprint)
        per_floor = None
        if fp_area and footprint:
            per_floor = min(float(fp_area), footprint)
        elif footprint:
            per_floor = footprint
            warnings.append("평면 면적 미상 — 부지 footprint로 층면적 추정")

        # 층수·연면적(법적 한도 클램프).
        est_floors = est_gfa = est_units = None
        if per_floor and max_gfa:
            est_floors = max(1, int(max_gfa // per_floor))
            if site.max_floors_est:
                est_floors = min(est_floors, site.max_floors_est)
            est_gfa = round(min(max_gfa, per_floor * est_floors), 2)
            if site.avg_unit_area_sqm > 0:
                est_units = int(est_gfa * _DEFAULT_EFFICIENCY / site.avg_unit_area_sqm)
            warnings.append("세대수는 연면적×전용률 추정치(실제 평면 세대분할과 다를 수 있음)")

        # 주차: 세대당 1대 규칙 추정(주차도면 실제 대수는 검색 페이로드에 미포함 — 후속 연동).
        est_parking = est_units if (est_units and est_units > 0) else None
        if est_units and est_units > 0:
            warnings.append("주차대수는 세대당 1대 규칙 추정")
        elif est_units == 0:
            warnings.append("추정 세대수 0 — 평형 대비 연면적 과소(설계 재검토 필요)")

        # 인허가(한도) 게이트 — 면적은 footprint/max_gfa로 클램프되므로 한도 내(스케일로 맞춤).
        # 한도 미상이면 미확정(정직), 참조도면이 부지 대비 과대(축소<_MIN_SCALE)면 비현실=부적합.
        compliant = False
        if max_gfa is None or footprint is None:
            warnings.append(f"법적 한도 미상(zone={site.zone_code}, far_source={site.far_source}) — 적법성 미확정")
        else:
            aggressive = scale is not None and scale < _MIN_SCALE
            compliant = not aggressive
            if aggressive:
                warnings.append(f"참조도면이 부지 대비 과대(축소 {scale}) — 부적합, 다른 도면 권장")
            if site.far_source == "statutory":
                warnings.append("용적률 법정상한 기준 — 조례 실효한도 확인 필요(실효 우선)")

        # 점수 = 적합도 × 완성도(동반 도면 수) × 적법.
        fitness = fit_score(fp, site)
        completeness = min(1.0, len(selected) / 3.0)
        score = round(fitness * (0.6 + 0.4 * completeness) * (1.0 if compliant else 0.6), 4)

        candidates.append(CompositionCandidate(
            selected=selected,
            primary_drawing_type=_g(fp, "drawing_type") or "unknown",
            scale_factor=scale,
            estimated_gfa_sqm=est_gfa,
            estimated_floors=est_floors,
            estimated_units=est_units,
            estimated_parking=est_parking,
            compliant=compliant,
            score=score,
            warnings=warnings,
        ))

    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates[:top_n]


def site_context_from_zone(
    zone_code: str,
    area_sqm: float,
    *,
    ordinance_far_pct: float | None = None,
    ordinance_bcr_pct: float | None = None,
    width_m: float | None = None,
    depth_m: float | None = None,
    avg_unit_area_sqm: float = 84.0,
) -> SiteContext:
    """AutoDesignEngine 법정한도로 SiteContext 구성(best-effort). 조례(실효) 값이 오면 우선.

    실효(조례) 한도가 주어지면 far_source='ordinance'(전역규칙: 용적률은 실효 우선),
    아니면 법정상한 'statutory', 조회 실패 시 'unknown'.
    """
    far_pct = bcr_pct = None
    source = "unknown"
    ctx_warnings: list[str] = []
    try:
        from app.services.cad.auto_design_engine import AutoDesignEngineService

        legal = AutoDesignEngineService.get_legal_limits(zone_code)
        far_pct = legal.get("max_far_percent")
        bcr_pct = legal.get("max_bcr_percent")
        source = "statutory"
        # 미지정 zone 폴백·엔진 경고를 정직 전파(SiteContext.warnings → 후보 warnings로 승계).
        if legal.get("limits_source") == "fallback_default":
            source = "statutory_fallback"
            ctx_warnings.append(f"미지정 용도지역 '{zone_code}' — 법정 기본값 폴백(정밀 확인 필요)")
        for w in (legal.get("warnings") or [])[:2]:
            ctx_warnings.append(str(w))
    except Exception:  # noqa: BLE001
        pass

    # 용적률(FAR) 실효 우선(전역규칙). far_source는 FAR 출처만 표기 — BCR 출처는 v1 미추적.
    if ordinance_far_pct is not None:
        far_pct = ordinance_far_pct
        source = "ordinance"
    if ordinance_bcr_pct is not None:
        bcr_pct = ordinance_bcr_pct

    return SiteContext(
        area_sqm=area_sqm,
        zone_code=zone_code,
        width_m=width_m,
        depth_m=depth_m,
        legal_bcr_pct=bcr_pct,
        legal_far_pct=far_pct,
        far_source=source,
        avg_unit_area_sqm=avg_unit_area_sqm,
        warnings=ctx_warnings,
    )
