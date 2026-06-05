"""D3 — 설계변경 사전예측 + 보완방안 (착공 전 리스크 예측).

비전문가 보호 목적: 착공 전에 설계변경을 유발할 리스크(법규초과·필수요소 누락·
정량 정합성 모순)를 미리 예측하고 보완방안을 제시해, 공사 중 추가공사·공사비
증대를 미연에 방지한다. 역으로 최적 보완으로 절감안을 제시한다.

정직성 원칙(최우선):
- 본 결과는 "사전 예측·경고"이며 확정이 아니다. 전문가(건축사·구조기술사) 검토가
  반드시 필요하다.
- 룰기반을 우선(결정적)하고 AI는 보조(use_llm시만)로 사용한다.
- 3D clash(간섭) 검출은 범위 외다. 본 모듈은 정량 정합성만 점검하며 그 한계를
  결과(badges)에 정직히 표기한다.
- 데이터가 없으면 "데이터 없음"으로 명시하고 추측은 추측으로 표기한다.

재사용:
- 용도지역별 법적 한도: building_code_rules.ZONE_DEFAULTS,
  auto_zoning_service.ZONE_LIMITS(권위 소스 보조).
- 주차 산정 기준: building_code_rules.PARKING_REQUIREMENTS.
- 설계변경 추가비율 계수: cost_monte_carlo.RISK["design_chg"].
"""

from __future__ import annotations

import math
from typing import Any, Optional

# 법정 한도·주차 기준 재사용(룰 단일 출처).
from app.services.permit.building_code_rules import (
    PARKING_REQUIREMENTS,
    ZONE_DEFAULTS,
)
from app.services.zoning.auto_zoning_service import ZONE_LIMITS

Severity = str  # "high" | "warn" | "info"

# 설계변경 추가비율(monte carlo design_chg 최빈/최대)을 정성 표기에 사용.
# RISK["design_chg"] = (0.00, 0.05, 0.15) → 최빈 +5%, 최대 +15%.
_DESIGN_CHG_TYPICAL_PCT = 5
_DESIGN_CHG_MAX_PCT = 15

# 법규 근접(초과 직전) 경고 임계: 한도의 95% 이상이면 근접 경고.
_NEAR_LIMIT_RATIO = 0.95

# 주거 용도(세대 기반 주차·장애인 편의 판정).
_RESIDENTIAL_TYPES = ("아파트", "공동주택", "다세대주택", "주상복합")
_COMMERCIAL_TYPES = ("근린생활시설", "오피스텔", "상가")


def _zone_limits(zone_type: str) -> dict[str, Any]:
    """용도지역 → 법정 한도(max_bcr/max_far/max_height_m). 미매핑이면 빈 dict.

    building_code_rules.ZONE_DEFAULTS를 1차, auto_zoning.ZONE_LIMITS를 2차로 본다.
    height는 ZONE_LIMITS(max_height_m: None=무제한)를 우선 신뢰한다.
    """
    out: dict[str, Any] = {}
    d = ZONE_DEFAULTS.get(zone_type)
    if d:
        out["max_bcr"] = d.get("max_bcr")
        out["max_far"] = d.get("max_far")
        # ZONE_DEFAULTS의 max_height는 0=무제한 관행 → None으로 정규화.
        h = d.get("max_height", 0)
        out["max_height_m"] = h if h and h > 0 else None
    z = ZONE_LIMITS.get(zone_type)
    if z:
        out.setdefault("max_bcr", z.get("max_bcr"))
        out.setdefault("max_far", z.get("max_far"))
        # height는 ZONE_LIMITS를 우선(None=명시적 무제한).
        out["max_height_m"] = z.get("max_height_m")
    return out


def _mk_risk(
    category: str,
    item: str,
    severity: Severity,
    detail: str,
    remedy: str,
    *,
    current: Any = None,
    limit: Any = None,
    est_impact: Optional[str] = None,
) -> dict[str, Any]:
    return {
        "category": category,
        "item": item,
        "severity": severity,
        "current": current,
        "limit": limit,
        "detail": detail,
        "remedy": remedy,
        "est_impact": est_impact,
    }


class DesignChangePredictor:
    """설계변경 사전예측 룰엔진(법규초과·누락·간섭정합 3종)."""

    # ── 1) 법규초과 예측 ──────────────────────────────────────────────
    def _predict_overrun(
        self, design: dict[str, Any], limits: dict[str, Any], zone_type: str
    ) -> list[dict[str, Any]]:
        """현 설계(건폐율/용적률/높이/주차/세대) vs 법정 한도 → 초과/근접 위험."""
        risks: list[dict[str, Any]] = []

        bcr = design.get("bcr")
        far = design.get("far")
        height = design.get("height_m")
        max_bcr = limits.get("max_bcr")
        max_far = limits.get("max_far")
        max_height = limits.get("max_height_m")

        # 건폐율
        if bcr is not None and max_bcr:
            if bcr > max_bcr:
                risks.append(_mk_risk(
                    "법규초과", "건폐율 초과", "high",
                    f"계획 건폐율 {bcr:.1f}%가 법정 한도 {max_bcr}%를 초과합니다"
                    f"({bcr - max_bcr:.1f}%p 초과). 인허가 반려·면적 축소 설계변경 위험.",
                    f"건축면적을 약 {(1 - max_bcr / bcr) * 100:.0f}% 축소하거나, 필로티·"
                    f"공개공지로 산정 제외 면적을 활용해 {max_bcr}% 이내로 조정하세요. "
                    f"착공 전 조정 시 추가공사 없이 흡수 가능.",
                    current=f"{bcr:.1f}%", limit=f"{max_bcr}%",
                    est_impact=f"미조정 시 인허가 단계 재설계 → 설계변경비 약 +{_DESIGN_CHG_TYPICAL_PCT}%",
                ))
            elif bcr >= max_bcr * _NEAR_LIMIT_RATIO:
                risks.append(_mk_risk(
                    "법규초과", "건폐율 한도 근접", "warn",
                    f"계획 건폐율 {bcr:.1f}%가 법정 한도 {max_bcr}%에 근접합니다"
                    f"(여유 {max_bcr - bcr:.1f}%p). 측량 오차·발코니 산정 변동 시 초과 위험.",
                    "건축면적에 5% 내외 안전마진을 두거나, 측량 확정 후 재검토하세요. "
                    "착공 후 발견 시 구조변경을 동반할 수 있어 사전 확보가 유리합니다.",
                    current=f"{bcr:.1f}%", limit=f"{max_bcr}%",
                ))

        # 용적률
        if far is not None and max_far:
            if far > max_far:
                risks.append(_mk_risk(
                    "법규초과", "용적률 초과", "high",
                    f"계획 용적률 {far:.1f}%가 법정 한도 {max_far}%를 초과합니다"
                    f"({far - max_far:.1f}%p 초과). 연면적·층수 축소 설계변경 위험.",
                    f"연면적을 약 {(1 - max_far / far) * 100:.0f}% 축소(상층부 1~2개층 감축 또는 "
                    f"기준층 면적 축소)하거나, 용적률 완화 인센티브(공공기여·친환경)를 검토하세요.",
                    current=f"{far:.1f}%", limit=f"{max_far}%",
                    est_impact=f"미조정 시 층수 감축 재설계 → 설계변경비 최대 +{_DESIGN_CHG_MAX_PCT}%·분양면적 손실",
                ))
            elif far >= max_far * _NEAR_LIMIT_RATIO:
                risks.append(_mk_risk(
                    "법규초과", "용적률 한도 근접", "warn",
                    f"계획 용적률 {far:.1f}%가 법정 한도 {max_far}%에 근접합니다"
                    f"(여유 {max_far - far:.1f}%p). 면적 확정 변동 시 초과 위험.",
                    "기준층 면적·서비스면적 산정을 확정해 여유를 확인하세요. "
                    "한도 근접 설계는 인허가 협의 단계 변동에 취약합니다.",
                    current=f"{far:.1f}%", limit=f"{max_far}%",
                ))

        # 높이제한(상업지역 등 None=무제한이면 미적용)
        if height is not None and max_height:
            if height > max_height:
                risks.append(_mk_risk(
                    "법규초과", "높이제한 초과", "high",
                    f"계획 높이 {height:.1f}m가 법정 높이제한 {max_height}m를 초과합니다. "
                    f"층수 감축 설계변경 위험.",
                    f"최상층을 감축하거나 층고를 조정해 {max_height}m 이내로 맞추세요. "
                    f"일조권 사선·가로구역 높이제한도 함께 확인 필요.",
                    current=f"{height:.1f}m", limit=f"{max_height}m",
                    est_impact=f"미조정 시 층수 감축 → 분양세대 손실·설계변경비 +{_DESIGN_CHG_MAX_PCT}%",
                ))
            elif height >= max_height * _NEAR_LIMIT_RATIO:
                risks.append(_mk_risk(
                    "법규초과", "높이제한 근접", "warn",
                    f"계획 높이 {height:.1f}m가 법정 한도 {max_height}m에 근접합니다"
                    f"(여유 {max_height - height:.1f}m). 층고·옥탑 산정 변동 시 초과 위험.",
                    "옥탑·파라펫 높이 산정을 확정하고 층고 여유를 확인하세요.",
                    current=f"{height:.1f}m", limit=f"{max_height}m",
                ))

        return risks

    # ── 2) 누락 예측 (필수요소 체크리스트) ────────────────────────────
    def _predict_missing(
        self, design: dict[str, Any], limits: dict[str, Any], zone_type: str
    ) -> list[dict[str, Any]]:
        """용도·규모별 필수요소(법정주차·피난계단·승강기·장애인편의 등) 대비 누락 경고."""
        risks: list[dict[str, Any]] = []

        building_type = str(design.get("building_type") or "")
        floors = design.get("floors")
        gfa = design.get("gfa")
        units = design.get("units")
        parking = design.get("parking")

        is_resi = building_type in _RESIDENTIAL_TYPES
        is_comm = building_type in _COMMERCIAL_TYPES

        # (a) 법정주차 누락/부족
        required_parking = self._required_parking(building_type, units, gfa)
        if required_parking is not None:
            if parking is None:
                risks.append(_mk_risk(
                    "누락", "주차대수 미계획", "high",
                    f"법정 최소 주차 약 {required_parking}대가 필요하나 계획 주차대수가 "
                    f"입력되지 않았습니다(데이터 없음). 착공 후 부족 발견 시 지하층 추가 등 "
                    f"대규모 설계변경 위험.",
                    f"주차계획을 확정하고 최소 {required_parking}대를 확보하세요. "
                    f"부족 시 기계식 주차·지하층 추가를 사전 검토(착공 후 추가는 공사비 급증).",
                    current="미입력", limit=f"최소 {required_parking}대",
                    est_impact="착공 후 부족 시 지하주차 추가 → 공사비·공기 대폭 증가",
                ))
            elif parking < required_parking:
                short = required_parking - parking
                risks.append(_mk_risk(
                    "누락", "법정주차 부족", "high",
                    f"계획 주차 {parking}대가 법정 최소 {required_parking}대에 {short}대 부족합니다. "
                    f"인허가 반려 또는 세대수 축소 설계변경 위험.",
                    f"{short}대 추가 확보(기계식·필로티·지하 1개층 추가) 또는 세대수·연면적을 "
                    f"법정주차 충족 수준으로 조정하세요. 착공 전 조정이 비용 최소.",
                    current=f"{parking}대", limit=f"최소 {required_parking}대",
                    est_impact=f"미해소 시 세대 축소 또는 주차층 추가 → 설계변경비 +{_DESIGN_CHG_TYPICAL_PCT}~{_DESIGN_CHG_MAX_PCT}%",
                ))

        # (b) 피난계단(직통계단 2개소) — 5층 이상 또는 층당 200㎡ 초과
        if floors is not None:
            floor_area = None
            if gfa and floors:
                floor_area = gfa / floors
            needs_dual_stair = (floors >= 5) or (floor_area is not None and floor_area > 200)
            if needs_dual_stair:
                risks.append(_mk_risk(
                    "누락", "직통계단 2개소 확인 필요", "warn",
                    f"{floors}층 규모(또는 층당 면적 초과)는 직통계단 2개소 이상이 필요합니다"
                    f"(건축법 시행령 §34). 설계도서에서 피난계단 개소·이격을 확인하세요.",
                    "피난계단 2개소와 보행거리(피난거리)를 코어 계획에 반영하세요. "
                    "착공 후 계단 추가는 코어 재구성을 동반해 매우 고비용입니다.",
                    current=f"{floors}층",
                    est_impact="누락 시 코어 재설계 → 평면 전면 변경 위험",
                ))
            # 16층 이상 → 특별피난계단
            if floors >= 16:
                risks.append(_mk_risk(
                    "누락", "특별피난계단 확인 필요", "warn",
                    f"{floors}층(16층 이상)은 특별피난계단이 필요합니다(건축법 시행령 §35). "
                    f"부속실(전실)·제연설비 계획 누락 시 인허가 보완 발생.",
                    "특별피난계단 부속실과 제연설비를 코어에 반영하세요.",
                    current=f"{floors}층",
                ))

        # (c) 승강기 누락 — 6층 이상
        if floors is not None and floors >= 6:
            risks.append(_mk_risk(
                "누락", "승강기 설치 확인 필요", "info",
                f"{floors}층(6층 이상)은 승강기 설치가 의무입니다(건축법 §64). "
                f"설계에 EV 대수·규격이 반영됐는지 확인하세요.",
                "층수·세대수에 맞는 승강기 대수·정원을 코어에 반영하세요.",
                current=f"{floors}층",
            ))

        # (d) 장애인 편의시설 — 공동주택 20세대↑ / 근생 500㎡↑
        if is_resi and units is not None and units >= 20:
            risks.append(_mk_risk(
                "누락", "장애인 편의시설 확인 필요", "warn",
                f"공동주택 {units}세대(20세대 이상)는 장애인 편의시설이 의무입니다"
                f"(장애인등편의법 §4): 주출입구 경사로·장애인 주차구획 등.",
                "BF(무장애) 경사로, 장애인 주차구획, 점자블록을 설계에 반영하세요. "
                "준공 후 보완은 외부공간 재시공을 동반합니다.",
                current=f"{units}세대",
            ))
        elif is_comm and gfa is not None and gfa >= 500:
            risks.append(_mk_risk(
                "누락", "장애인 편의시설 확인 필요", "warn",
                f"{building_type} 연면적 {gfa:.0f}㎡(500㎡ 이상)는 장애인 편의시설이 의무입니다"
                f"(장애인등편의법 §4): 주출입구 단차제거·장애인 화장실 등.",
                "주출입구 단차제거, 장애인 화장실, 승강기(6층↑)를 반영하세요.",
                current=f"{gfa:.0f}㎡",
            ))

        # (e) 부대복리시설(공동주택 일정 세대 이상) — 정성 안내
        if is_resi and units is not None and units >= 150:
            risks.append(_mk_risk(
                "누락", "부대복리시설 확인 필요", "info",
                f"공동주택 {units}세대는 관리사무소·경로당·어린이놀이터 등 부대복리시설이 "
                f"규모별로 요구됩니다(주택건설기준). 면적 누락 시 인허가 보완 발생.",
                "세대수 구간별 부대복리시설 의무면적을 배치계획에 반영하세요.",
                current=f"{units}세대",
            ))

        return risks

    # ── 3) 간섭/정합 예측 (정량 정합성) ───────────────────────────────
    def _predict_consistency(
        self, design: dict[str, Any], limits: dict[str, Any], zone_type: str
    ) -> list[dict[str, Any]]:
        """정량 정합성(층수×층고 vs 높이, 세대수 vs 전용면적합 vs GFA, 건폐 vs 대지)."""
        risks: list[dict[str, Any]] = []

        floors = design.get("floors")
        height = design.get("height_m")
        floor_height = design.get("floor_height_m") or 3.0
        gfa = design.get("gfa")
        units = design.get("units")
        avg_unit_sqm = design.get("avg_unit_area_sqm")
        land_area = design.get("land_area_sqm")
        building_area = design.get("building_area_sqm")
        bcr = design.get("bcr")

        # (a) 층수×층고 vs 입력 높이 정합
        if floors is not None and height is not None:
            implied = floors * floor_height
            # 옥탑·기초 여유 고려해 10% 허용오차. 입력 높이가 층수×층고보다 크게 작으면 모순.
            if height < implied * 0.9:
                risks.append(_mk_risk(
                    "간섭정합", "높이-층수 불일치", "warn",
                    f"입력 높이 {height:.1f}m가 층수×층고({floors}×{floor_height:.1f}="
                    f"{implied:.1f}m)보다 작아 정합성이 맞지 않습니다. 층고 또는 층수 입력 오류 "
                    f"가능성(추정).",
                    "실제 층고와 층수, 옥탑 포함 여부를 확정해 높이를 재산정하세요. "
                    "높이 산정 오류는 일조권·높이제한 검토를 무력화합니다.",
                    current=f"높이 {height:.1f}m / {floors}층",
                    limit=f"층수×층고 ≈ {implied:.1f}m",
                ))

        # (b) 세대수 × 평균전용 vs 연면적 정합
        if units is not None and avg_unit_sqm and gfa:
            net_total = units * avg_unit_sqm
            # 전용면적합은 연면적보다 작아야 정상(공용·코어 포함). 전용합 > GFA면 모순.
            if net_total > gfa:
                risks.append(_mk_risk(
                    "간섭정합", "세대-면적 모순", "high",
                    f"세대수×평균전용({units}×{avg_unit_sqm:.0f}={net_total:.0f}㎡)이 "
                    f"연면적 {gfa:.0f}㎡를 초과합니다. 공용·코어 면적이 음수가 되는 물리적 모순"
                    f"(전용률 >100%). 세대수·전용면적·연면적 중 하나가 잘못 입력됨.",
                    "세대수·평균전용면적·연면적을 재확인하세요. 통상 전용률은 70~85%이며 "
                    "전용합이 연면적을 넘을 수 없습니다. 모순 방치 시 분양면적·수지 전면 오류.",
                    current=f"전용합 {net_total:.0f}㎡ / GFA {gfa:.0f}㎡",
                    limit="전용합 < 연면적",
                    est_impact="방치 시 분양면적·사업수지 전면 재산정",
                ))
            else:
                eff = net_total / gfa * 100 if gfa else 0
                if eff > 90:
                    risks.append(_mk_risk(
                        "간섭정합", "전용률 과다", "warn",
                        f"전용률(전용합/연면적)이 {eff:.0f}%로 통상 범위(70~85%)를 초과합니다. "
                        f"코어·공용면적이 과소 계상됐을 가능성(추정).",
                        "코어(계단·EV·복도)와 공용면적을 실치수로 재검토하세요. "
                        "공용면적 과소는 착공 후 면적 증가 설계변경을 유발합니다.",
                        current=f"전용률 {eff:.0f}%",
                        limit="통상 70~85%",
                    ))

        # (c) 건폐(건축면적/대지) vs 입력 건폐율 정합
        if building_area and land_area and bcr is not None:
            implied_bcr = building_area / land_area * 100
            if abs(implied_bcr - bcr) > 5:  # 5%p 이상 괴리면 입력 불일치
                risks.append(_mk_risk(
                    "간섭정합", "건폐율-면적 불일치", "warn",
                    f"입력 건폐율 {bcr:.1f}%와 건축면적/대지({building_area:.0f}/{land_area:.0f}="
                    f"{implied_bcr:.1f}%)가 {abs(implied_bcr - bcr):.1f}%p 차이납니다. "
                    f"건축면적·대지면적·건폐율 입력 정합 오류 가능성(추정).",
                    "건축면적과 대지면적을 측량 확정값으로 맞추고 건폐율을 재계산하세요.",
                    current=f"입력 {bcr:.1f}% / 산정 {implied_bcr:.1f}%",
                ))

        return risks

    # ── 주차 산정(building_code_rules 기준 재사용) ─────────────────────
    @staticmethod
    def _required_parking(
        building_type: str, units: Optional[float], gfa: Optional[float]
    ) -> Optional[int]:
        req = PARKING_REQUIREMENTS.get(building_type)
        if req is None:
            # 미등록 용도: 주거형이면 아파트 기준 폴백, 아니면 산정 불가.
            if building_type in _RESIDENTIAL_TYPES:
                req = PARKING_REQUIREMENTS.get("아파트")
            else:
                return None
        if req.get("per_unit") is not None:
            if units is None:
                return None
            return math.ceil(units * req["per_unit"])
        per_sqm = req.get("additional_per_sqm")
        if per_sqm and gfa:
            return math.ceil(gfa / per_sqm)
        return None

    # ── 공개 진입점: 룰기반 3종 예측 ──────────────────────────────────
    def predict(
        self, design: dict[str, Any], zone_type: str
    ) -> dict[str, Any]:
        """설계 파라미터와 용도지역으로 3종 리스크를 예측한다(룰기반·결정적).

        Args:
            design: {bcr, far, height_m, floors, floor_height_m, gfa, units,
                     parking, building_type, avg_unit_area_sqm, land_area_sqm,
                     building_area_sqm}
            zone_type: 용도지역명(예: "제2종일반주거지역")

        Returns:
            {risks, summary, limits_used, data_gaps}
        """
        limits = _zone_limits(zone_type)
        data_gaps: list[str] = []
        if not limits:
            data_gaps.append(
                f"용도지역 '{zone_type or '미상'}'의 법정 한도를 자동 매핑할 수 없어 "
                f"법규초과 예측 정확도가 제한됩니다(데이터 없음)."
            )
        for k, label in (
            ("bcr", "건폐율"), ("far", "용적률"), ("height_m", "높이"),
            ("parking", "주차대수"), ("units", "세대수"),
        ):
            if design.get(k) is None:
                data_gaps.append(f"{label} 미입력 — 해당 항목 예측 제한")

        risks: list[dict[str, Any]] = []
        risks += self._predict_overrun(design, limits, zone_type)
        risks += self._predict_missing(design, limits, zone_type)
        risks += self._predict_consistency(design, limits, zone_type)

        high = sum(1 for r in risks if r["severity"] == "high")
        warn = sum(1 for r in risks if r["severity"] == "warn")
        info = sum(1 for r in risks if r["severity"] == "info")

        if high:
            impact_note = (
                f"고위험 {high}건 — 미조치 시 인허가 반려·재설계로 설계변경비 "
                f"+{_DESIGN_CHG_TYPICAL_PCT}~{_DESIGN_CHG_MAX_PCT}% 및 공기 지연 가능(정성·추정)."
            )
        elif warn:
            impact_note = (
                f"주의 {warn}건 — 착공 전 확정·보완 시 추가공사 없이 흡수 가능(정성·추정)."
            )
        else:
            impact_note = "현 설계 기준 예측된 고위험·주의 리스크 없음(입력 데이터 범위 내)."

        return {
            "risks": risks,
            "summary": {
                "high": high,
                "warn": warn,
                "info": info,
                "total_predicted_impact_note": impact_note,
            },
            "limits_used": limits,
            "data_gaps": data_gaps,
        }


# ── AI 보완방안(use_llm시만, base_interpreter 패턴, 실패시 룰 폴백) ──────

_AI_SYSTEM_PROMPT = """\
당신은 한국 건축사이자 건설 VE(가치공학)·설계변경 관리 전문가입니다.

역할:
착공 전에 식별된 설계변경 유발 리스크(법규초과·필수요소 누락·정량 정합성 모순)에
대해, 어떻게 보완하면 공사 중 설계변경·추가공사·공사비 증대를 피할 수 있는지,
가능하면 절감 효과까지 실무 관점에서 제시합니다.

출력 규칙:
1. 모든 판단은 제공된 리스크 데이터에서만 근거. 수치를 지어내지 않음(없으면 "데이터 없음").
2. 본 의견은 사전 예측·권고이며 확정이 아님을 전제(건축사·구조기술사 검토 필요).
3. 보완방안은 착공 전 조치(저비용)와 착공 후 발견 시 위험(고비용)을 대비해 제시.
4. 반드시 JSON 형식으로만 응답(마크다운·설명문 금지).
"""

_AI_USER_TEMPLATE = """\
아래 사전예측된 설계변경 리스크를 바탕으로 통합 보완 전략을 JSON으로 작성하세요.

## 용도지역
{zone_type}

## 예측 리스크 요약
- 고위험: {high}건, 주의: {warn}건, 참고: {info}건

## 리스크 상세
{risks_json}

## 요구 출력 (JSON, 각 값은 문자열)
{{
  "priority_actions": "착공 전 즉시 조치할 우선순위 보완 1~3개(고위험 중심)",
  "savings_opportunity": "최적 보완으로 기대되는 설계변경비·공사비 절감 효과(정성·추정, 근거 명시)",
  "expert_review_note": "전문가(건축사·구조기술사) 검토가 필요한 항목과 한계"
}}
"""


async def generate_ai_remedies(
    prediction: dict[str, Any], zone_type: str, *, timeout_sec: float = 90.0
) -> dict[str, str]:
    """use_llm시 통합 보완 전략을 LLM으로 생성. 실패시 룰기반 폴백 dict.

    base_interpreter(_invoke: asyncio.wait_for·90초·캐시·그라운딩) 패턴을 그대로 사용.
    """
    summary = prediction.get("summary", {})
    risks = prediction.get("risks", [])

    # 룰기반 폴백(LLM 없이도 항상 유효한 보완 전략).
    high_items = [r["item"] for r in risks if r.get("severity") == "high"]
    fallback = {
        "priority_actions": (
            "착공 전 우선 조치: " + ", ".join(high_items[:3])
            if high_items
            else "고위험 항목 없음 — 주의·참고 항목을 인허가 협의 전 확인하세요."
        ),
        "savings_opportunity": (
            f"착공 전 보완 시 설계변경비 +{_DESIGN_CHG_TYPICAL_PCT}~{_DESIGN_CHG_MAX_PCT}%"
            f"(공사비 대비) 및 공기 지연을 회피할 수 있습니다(정성·추정)."
        ),
        "expert_review_note": (
            "본 예측은 정량 룰기반이며 확정이 아닙니다. 법규초과·구조·피난 항목은 "
            "건축사·구조기술사 검토가 필요합니다. 3D 간섭(clash)은 본 모듈 범위 외입니다."
        ),
    }

    try:
        from app.services.ai.base_interpreter import BaseInterpreter
    except Exception:  # noqa: BLE001
        return fallback

    class _RemedyInterpreter(BaseInterpreter):
        name = "design_risk_remedy"
        expected_keys = [
            "priority_actions",
            "savings_opportunity",
            "expert_review_note",
        ]
        fallback_key = "priority_actions"
        max_tokens = 2048
        system_prompt = _AI_SYSTEM_PROMPT

    try:
        import json as _json

        interp = _RemedyInterpreter(timeout_sec=timeout_sec)
        compact = {
            "zone_type": zone_type,
            "summary": summary,
            "risks": [
                {"category": r.get("category"), "item": r.get("item"),
                 "severity": r.get("severity"), "detail": r.get("detail")}
                for r in risks
            ],
        }
        prompt = _AI_USER_TEMPLATE.format(
            zone_type=zone_type or "미상",
            high=summary.get("high", 0),
            warn=summary.get("warn", 0),
            info=summary.get("info", 0),
            risks_json=_json.dumps(compact["risks"], ensure_ascii=False, indent=2),
        )
        result = await interp._invoke(prompt, cache_data=compact)
        if result:
            # 누락 키는 폴백으로 채움(부분 성공 보호).
            for k, v in fallback.items():
                result.setdefault(k, v)
            return result
    except Exception:  # noqa: BLE001
        pass
    return fallback
