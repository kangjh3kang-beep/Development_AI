"""건축법규 자동 검증 룰엔진.

RASE 방법론 기반: 각 법규 조항을 Requirement/Applicability/Selection/Exception으로 분해.
건축법, 건축법 시행령, 주차장법 핵심 조항을 논리식으로 인코딩.

검증 항목 8개:
  BL-001  건폐율        건축법 시행령 §84
  BL-002  용적률        건축법 시행령 §85
  BL-003  높이제한      건축법 §60, §61
  BL-004  건축선 후퇴   건축법 §46, §47
  BL-005  주차대수      주차장법 시행령 §6
  BL-006  일조권 사선   건축법 §61
  BL-007  피난/방화     건축법 시행령 §34, §46
  BL-008  장애인 편의   장애인등편의법 §4
"""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class ComplianceStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"
    NOT_APPLICABLE = "n/a"


class RuleCheckResult(BaseModel):
    rule_id: str
    rule_name: str
    legal_basis: str
    status: ComplianceStatus
    required_value: str
    actual_value: str
    message: str


# ── 용도지역별 법적 한도 기본값 ──────────────────────────────────────

ZONE_DEFAULTS: dict[str, dict[str, Any]] = {
    "제1종전용주거지역": {"max_bcr": 50, "max_far": 100, "max_height": 12, "setback_m": 3.0},
    "제2종전용주거지역": {"max_bcr": 50, "max_far": 150, "max_height": 18, "setback_m": 3.0},
    "제1종일반주거지역": {"max_bcr": 60, "max_far": 200, "max_height": 0, "setback_m": 2.0},
    "제2종일반주거지역": {"max_bcr": 60, "max_far": 250, "max_height": 0, "setback_m": 2.0},
    "제3종일반주거지역": {"max_bcr": 50, "max_far": 300, "max_height": 0, "setback_m": 2.0},
    "준주거지역": {"max_bcr": 70, "max_far": 500, "max_height": 0, "setback_m": 1.0},
    "일반상업지역": {"max_bcr": 80, "max_far": 1300, "max_height": 0, "setback_m": 0},
    "근린상업지역": {"max_bcr": 70, "max_far": 900, "max_height": 0, "setback_m": 0},
    "준공업지역": {"max_bcr": 70, "max_far": 400, "max_height": 0, "setback_m": 0},
    # ★녹지지역: 키 부재 시 ZONE_DEFAULTS.get()가 빈 dict→상위 폴백(주거 bcr60/far200)으로
    #   자연녹지를 주거한도로 오판정하던 문제를 차단. 건폐20·용적80~100·4층 이하(SSOT 정합).
    "보전녹지지역": {"max_bcr": 20, "max_far": 80, "max_height": 0, "max_floors": 4, "setback_m": 0},
    "생산녹지지역": {"max_bcr": 20, "max_far": 100, "max_height": 0, "max_floors": 4, "setback_m": 0},
    "자연녹지지역": {"max_bcr": 20, "max_far": 100, "max_height": 0, "max_floors": 4, "setback_m": 0},
}

# ── 주차대수 산정 기준 (주차장법 시행령 §6) ──────────────────────────

PARKING_REQUIREMENTS: dict[str, dict[str, Any]] = {
    "아파트": {"unit": "세대", "per_unit": 1.0, "additional_per_sqm": None},
    "공동주택": {"unit": "세대", "per_unit": 1.0, "additional_per_sqm": None},
    "다세대주택": {"unit": "세대", "per_unit": 0.7, "additional_per_sqm": None},
    "오피스텔": {"unit": "sqm", "per_unit": None, "additional_per_sqm": 150},
    "근린생활시설": {"unit": "sqm", "per_unit": None, "additional_per_sqm": 134},
}


class BuildingCodeRuleEngine:
    """건축법규 자동 검증 엔진."""

    def check_all(
        self,
        design_params: dict[str, Any],
        site_params: dict[str, Any],
    ) -> list[RuleCheckResult]:
        """설계안의 모든 법규 준수 여부를 검증한다.

        Args:
            design_params: 설계 파라미터 dict
                - building_area_sqm: 건축면적(㎡)
                - total_gfa_sqm: 연면적(㎡)
                - floor_count_above: 지상 층수
                - floor_count_below: 지하 층수
                - building_height_m: 건물 높이(m). 없으면 층수×3.3으로 추정.
                - unit_count: 세대/호수
                - building_type: 건물유형
                - setback_m: 건축선 후퇴거리(m). 없으면 0.
                - parking_count: 계획 주차대수. 없으면 0.
                - floor_area_per_floor_sqm: 층당 바닥면적(㎡). 피난/방화 검토용.
            site_params: 부지 파라미터 dict
                - land_area_sqm: 대지면적(㎡)
                - max_bcr: 허용 건폐율(%)
                - max_far: 허용 용적률(%)
                - max_height: 높이제한(m). 0이면 제한없음.
                - zone_type: 용도지역
                - north_boundary_m: 북측 인접대지 경계선까지 거리(m). 일조권용.
        """
        results: list[RuleCheckResult] = []
        results.append(self._check_bcr(design_params, site_params))
        results.append(self._check_far(design_params, site_params))
        results.append(self._check_height(design_params, site_params))
        results.append(self._check_setback(design_params, site_params))
        results.append(self._check_parking(design_params, site_params))
        results.append(self._check_daylighting(design_params, site_params))
        results.append(self._check_fire_escape(design_params, site_params))
        results.append(self._check_barrier_free(design_params, site_params))
        return results

    # ── BL-001: 건폐율 ──

    def _check_bcr(self, design: dict, site: dict) -> RuleCheckResult:
        max_bcr = site.get("max_bcr", 60)
        land_area = max(site.get("land_area_sqm", 1), 1)
        building_area = design.get("building_area_sqm", 0)
        actual_bcr = (building_area / land_area) * 100

        status = ComplianceStatus.PASS if actual_bcr <= max_bcr else ComplianceStatus.FAIL
        return RuleCheckResult(
            rule_id="BL-001",
            rule_name="건폐율 검증",
            legal_basis="건축법 시행령 제84조",
            status=status,
            required_value=f"{max_bcr}% 이하",
            actual_value=f"{actual_bcr:.1f}%",
            message=(
                f"건폐율 적합 ({actual_bcr:.1f}% ≤ {max_bcr}%)"
                if status == ComplianceStatus.PASS
                else f"건폐율 초과 ({actual_bcr:.1f}% > {max_bcr}%) — {actual_bcr - max_bcr:.1f}%p 초과"
            ),
        )

    # ── BL-002: 용적률 ──

    def _check_far(self, design: dict, site: dict) -> RuleCheckResult:
        max_far = site.get("max_far", 200)
        land_area = max(site.get("land_area_sqm", 1), 1)
        total_gfa = design.get("total_gfa_sqm", 0)
        actual_far = (total_gfa / land_area) * 100

        status = ComplianceStatus.PASS if actual_far <= max_far else ComplianceStatus.FAIL
        return RuleCheckResult(
            rule_id="BL-002",
            rule_name="용적률 검증",
            legal_basis="건축법 시행령 제85조",
            status=status,
            required_value=f"{max_far}% 이하",
            actual_value=f"{actual_far:.1f}%",
            message=(
                f"용적률 적합 ({actual_far:.1f}% ≤ {max_far}%)"
                if status == ComplianceStatus.PASS
                else f"용적률 초과 ({actual_far:.1f}% > {max_far}%) — {actual_far - max_far:.1f}%p 초과"
            ),
        )

    # ── BL-003: 높이제한 ──

    def _check_height(self, design: dict, site: dict) -> RuleCheckResult:
        max_height = site.get("max_height", 0)
        floor_count = design.get("floor_count_above", 1)
        actual_height = design.get("building_height_m", floor_count * 3.3)

        if max_height <= 0:
            return RuleCheckResult(
                rule_id="BL-003",
                rule_name="높이제한 검증",
                legal_basis="건축법 제60조, 제61조",
                status=ComplianceStatus.NOT_APPLICABLE,
                required_value="제한 없음",
                actual_value=f"{actual_height:.1f}m ({floor_count}층)",
                message="해당 용도지역에 높이제한 규정 없음",
            )

        status = ComplianceStatus.PASS if actual_height <= max_height else ComplianceStatus.FAIL
        return RuleCheckResult(
            rule_id="BL-003",
            rule_name="높이제한 검증",
            legal_basis="건축법 제60조, 제61조",
            status=status,
            required_value=f"{max_height}m 이하",
            actual_value=f"{actual_height:.1f}m ({floor_count}층)",
            message=(
                f"높이 적합 ({actual_height:.1f}m ≤ {max_height}m)"
                if status == ComplianceStatus.PASS
                else f"높이 초과 ({actual_height:.1f}m > {max_height}m)"
            ),
        )

    # ── BL-004: 건축선 후퇴 ──

    def _check_setback(self, design: dict, site: dict) -> RuleCheckResult:
        zone_type = site.get("zone_type", "")
        zone_defaults = ZONE_DEFAULTS.get(zone_type, {})
        required_setback = zone_defaults.get("setback_m", 0)
        actual_setback = design.get("setback_m", required_setback)

        if required_setback <= 0:
            return RuleCheckResult(
                rule_id="BL-004",
                rule_name="건축선 후퇴 검증",
                legal_basis="건축법 제46조, 제47조",
                status=ComplianceStatus.NOT_APPLICABLE,
                required_value="후퇴 의무 없음",
                actual_value=f"{actual_setback}m",
                message="해당 용도지역에 건축선 후퇴 의무 없음",
            )

        status = ComplianceStatus.PASS if actual_setback >= required_setback else ComplianceStatus.FAIL
        return RuleCheckResult(
            rule_id="BL-004",
            rule_name="건축선 후퇴 검증",
            legal_basis="건축법 제46조, 제47조",
            status=status,
            required_value=f"{required_setback}m 이상",
            actual_value=f"{actual_setback}m",
            message=(
                f"건축선 후퇴 적합 ({actual_setback}m ≥ {required_setback}m)"
                if status == ComplianceStatus.PASS
                else f"건축선 후퇴 미달 ({actual_setback}m < {required_setback}m)"
            ),
        )

    # ── BL-005: 주차대수 ──

    def _check_parking(self, design: dict, site: dict) -> RuleCheckResult:
        building_type = design.get("building_type", "아파트")
        unit_count = design.get("unit_count", 0)
        total_gfa = design.get("total_gfa_sqm", 0)
        actual_parking = design.get("parking_count", 0)

        req = PARKING_REQUIREMENTS.get(building_type, PARKING_REQUIREMENTS.get("아파트", {}))

        if req.get("per_unit") is not None:
            required_parking = math.ceil(unit_count * req["per_unit"])
            calc_basis = f"{unit_count}세대 × {req['per_unit']}대/세대"
        else:
            per_sqm = req.get("additional_per_sqm", 150)
            required_parking = math.ceil(total_gfa / per_sqm)
            calc_basis = f"연면적 {total_gfa:.0f}㎡ ÷ {per_sqm}㎡"

        # ── 법정 주차대수 하한·상한 산정 ──
        #  · 하한(lower) = 「주차장법 시행령 §6」 별표1 기준 설치 최소대수(조례가 강화하면 실효 하한↑).
        #  · 상한(upper): 「주차장법」상 부설주차장 *설치 상한 규정은 원칙적으로 없음*.
        #    다만 ① 지자체가 도심·상업지에 '부설주차장 설치 상한제'를 두거나(과밀억제),
        #         ② 친환경·교통수요관리로 완화(감면)할 수 있어 조례 별도 확인 필요.
        #    실무 권장 운영 상한 = 법정 하한 + 여유 10%(회전·방문차 대비). 정직 표기.
        lower_spaces = required_parking
        upper_spaces = math.ceil(required_parking * 1.1)
        bound_note = (
            f"법정 하한 {lower_spaces}대(조례 강화 시 ↑) · 실무 권장 상한 {upper_spaces}대(여유 10%) · "
            f"법정 설치 상한 규정 없음(지자체 상한제·완화 별도 확인) · {calc_basis}"
        )

        # 주차대수 미입력 시 — 자동 추정치 표시 경고
        if actual_parking == 0:
            return RuleCheckResult(
                rule_id="BL-005",
                rule_name="주차대수 검증",
                legal_basis="주차장법 시행령 제6조 별표1",
                status=ComplianceStatus.WARNING,
                required_value=bound_note,
                actual_value="미입력",
                message=(
                    f"주차대수 미입력 — 법정 최소(하한) {lower_spaces}대 확보 필요"
                    f"(권장 상한 {upper_spaces}대)"
                ),
            )

        status = ComplianceStatus.PASS if actual_parking >= required_parking else ComplianceStatus.FAIL
        return RuleCheckResult(
            rule_id="BL-005",
            rule_name="주차대수 검증",
            legal_basis="주차장법 시행령 제6조 별표1",
            status=status,
            required_value=bound_note,
            actual_value=f"{actual_parking}대",
            message=(
                f"주차 적합 ({actual_parking}대 ≥ 법정 하한 {lower_spaces}대 · 권장 상한 {upper_spaces}대 이내 권장)"
                if status == ComplianceStatus.PASS
                else f"주차 부족 ({actual_parking}대 < 법정 하한 {lower_spaces}대) — {lower_spaces - actual_parking}대 추가 필요"
            ),
        )

    # ── BL-006: 일조권 사선제한 ──

    def _check_daylighting(self, design: dict, site: dict) -> RuleCheckResult:
        """건축법 §61: 정북방향 인접대지경계선으로부터 높이의 1/2 이상 이격.

        9m 이하: 1.5m 이상
        9m 초과: 해당 건축물 각 부분 높이의 1/2 이상
        """
        floor_count = design.get("floor_count_above", 1)
        building_height = design.get("building_height_m", floor_count * 3.3)
        north_boundary = site.get("north_boundary_m", 0)
        zone_type = site.get("zone_type", "")

        # 상업지역은 일조권 사선제한 적용 제외
        if "상업" in zone_type:
            return RuleCheckResult(
                rule_id="BL-006",
                rule_name="일조권 사선제한 검증",
                legal_basis="건축법 제61조",
                status=ComplianceStatus.NOT_APPLICABLE,
                required_value="적용 제외 (상업지역)",
                actual_value=f"건물높이 {building_height:.1f}m",
                message="상업지역은 일조권 사선제한 적용 제외",
            )

        if north_boundary <= 0:
            # 거리 정보 없으면 경고만
            if building_height <= 9:
                required_distance = 1.5
            else:
                required_distance = building_height / 2
            return RuleCheckResult(
                rule_id="BL-006",
                rule_name="일조권 사선제한 검증",
                legal_basis="건축법 제61조",
                status=ComplianceStatus.WARNING,
                required_value=f"북측 이격 {required_distance:.1f}m 이상 필요",
                actual_value="북측 경계거리 미입력",
                message=f"건물높이 {building_height:.1f}m → 정북방향 최소 {required_distance:.1f}m 이격 필요 (확인 필요)",
            )

        if building_height <= 9:
            required_distance = 1.5
        else:
            required_distance = building_height / 2

        status = ComplianceStatus.PASS if north_boundary >= required_distance else ComplianceStatus.FAIL
        return RuleCheckResult(
            rule_id="BL-006",
            rule_name="일조권 사선제한 검증",
            legal_basis="건축법 제61조",
            status=status,
            required_value=f"북측 이격 {required_distance:.1f}m 이상",
            actual_value=f"북측 이격 {north_boundary:.1f}m",
            message=(
                f"일조권 적합 (이격 {north_boundary:.1f}m ≥ {required_distance:.1f}m)"
                if status == ComplianceStatus.PASS
                else f"일조권 위반 (이격 {north_boundary:.1f}m < {required_distance:.1f}m)"
            ),
        )

    # ── BL-007: 피난계단/방화구획 ──

    def _check_fire_escape(self, design: dict, site: dict) -> RuleCheckResult:
        """건축법 시행령 §34: 5층 이상 또는 바닥면적 200㎡ 초과 → 직통계단 2개소 이상.
        건축법 시행령 §46: 바닥면적 1,000㎡ 이상 → 방화구획.
        """
        floor_count = design.get("floor_count_above", 1)
        floor_area = design.get("floor_area_per_floor_sqm", 0)
        total_gfa = design.get("total_gfa_sqm", 0)

        if floor_area <= 0 and total_gfa > 0 and floor_count > 0:
            floor_area = total_gfa / floor_count

        issues: list[str] = []
        requirements: list[str] = []

        # 직통계단
        needs_dual_stair = floor_count >= 5 or floor_area > 200
        if needs_dual_stair:
            requirements.append("직통계단 2개소 이상 (시행령 §34)")

        # 방화구획
        needs_fire_compartment = floor_area >= 1000
        if needs_fire_compartment:
            requirements.append("방화구획 설치 (시행령 §46)")

        # 16층 이상 → 특별피난계단
        needs_special_stair = floor_count >= 16
        if needs_special_stair:
            requirements.append("특별피난계단 설치 (시행령 §35)")

        if not requirements:
            return RuleCheckResult(
                rule_id="BL-007",
                rule_name="피난계단/방화구획 검증",
                legal_basis="건축법 시행령 제34조, 제46조",
                status=ComplianceStatus.NOT_APPLICABLE,
                required_value="해당 없음",
                actual_value=f"{floor_count}층, 층당 {floor_area:.0f}㎡",
                message="소규모 건축물 — 피난/방화 특별규정 해당 없음",
            )

        return RuleCheckResult(
            rule_id="BL-007",
            rule_name="피난계단/방화구획 검증",
            legal_basis="건축법 시행령 제34조, 제46조",
            status=ComplianceStatus.WARNING,
            required_value="; ".join(requirements),
            actual_value=f"{floor_count}층, 층당 {floor_area:.0f}㎡",
            message=f"설계도서에서 확인 필요: {', '.join(requirements)}",
        )

    # ── BL-008: 장애인 편의시설 ──

    def _check_barrier_free(self, design: dict, site: dict) -> RuleCheckResult:
        """장애인등편의법 §4: 공동주택 20세대 이상, 근생 500㎡ 이상 → 편의시설 의무.

        의무 항목: 주출입구 경사로, 장애인 주차구획, 승강기(6층 이상), 장애인 화장실.
        """
        building_type = design.get("building_type", "")
        unit_count = design.get("unit_count", 0)
        total_gfa = design.get("total_gfa_sqm", 0)
        floor_count = design.get("floor_count_above", 1)

        is_residential = building_type in ("아파트", "공동주택", "다세대주택")
        is_commercial = building_type in ("근린생활시설", "오피스텔")

        obligations: list[str] = []
        applicable = False

        if is_residential and unit_count >= 20:
            applicable = True
            obligations.append("주출입구 경사로(BF)")
            obligations.append(f"장애인 주차구획 {max(1, unit_count // 50)}대 이상")
            if floor_count >= 6:
                obligations.append("승강기 의무 설치")

        if is_commercial and total_gfa >= 500:
            applicable = True
            obligations.append("주출입구 단차 제거")
            obligations.append("장애인 화장실 1개소 이상")
            if floor_count >= 6:
                obligations.append("승강기 의무 설치")

        if not applicable:
            return RuleCheckResult(
                rule_id="BL-008",
                rule_name="장애인 편의시설 검증",
                legal_basis="장애인등편의법 제4조",
                status=ComplianceStatus.NOT_APPLICABLE,
                required_value="해당 없음",
                actual_value=f"{building_type}, {unit_count}세대, {total_gfa:.0f}㎡",
                message="소규모 건축물 — 장애인 편의시설 의무 해당 없음",
            )

        return RuleCheckResult(
            rule_id="BL-008",
            rule_name="장애인 편의시설 검증",
            legal_basis="장애인등편의법 제4조",
            status=ComplianceStatus.WARNING,
            required_value="; ".join(obligations),
            actual_value=f"{building_type}, {unit_count}세대",
            message=f"설계도서에서 확인 필요: {', '.join(obligations)}",
        )
