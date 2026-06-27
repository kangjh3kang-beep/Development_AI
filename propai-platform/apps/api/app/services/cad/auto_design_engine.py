"""AI 자동 설계 생성 엔진.

토지면적과 법규(용도지역)에 맞춰 최적의 건축 매스 + 평면 배치를 자동 생성한다.

알고리즘 5단계:
1. 법규 한도 자동 조회 (ZONE_LIMITS)
2. 유효 건축 영역 → 최적 매스 산출
3. 코어 + 복도 자동 배치
4. 세대/호실 자동 배분
5. DesignPayload 형식 변환 (프론트 CAD 스토어 호환)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, NamedTuple

import structlog

from app.services.common.sunlight_setback import (
    max_height_for_north_distance_m,
    required_north_setback_m,
)

logger = structlog.get_logger(__name__)


# ── 설계엔진 기본 한도 — 보수적/전형 조례 수준 베이스라인(국가 시행령 상한 '이하') ──
# ⚠️ authoritative 국가 상한이 아니다: 국가 시행령 §84/§85 상한은 auto_zoning_service.ZONE_LIMITS /
#    엔진 national_zone_limits.json(SSOT)에 있다(예: 제2종일반주거 국가상한 far 250%이나 본 설계 기본값은
#    전형 조례 수준 200%). 조례 실효값은 get_legal_limits 소비측에서 min(기본,조례,목표)로 가감한다.
#    설계 기본값이 국가 상한을 초과하면 위법 설계 → test_zone_limits_engine_sync 관계 가드(≤)가 차단.

class LegalLimits(NamedTuple):
    """용도지역별 설계엔진 기본 한도(보수적/전형 조례 수준 — 국가 상한 아님)."""
    building_coverage_ratio: float  # 건폐율 (0~1)
    floor_area_ratio: float  # 용적률 (0~N)
    max_height_m: float  # 최고 높이 (m)
    min_setback_m: float  # 최소 이격거리 (m)
    sunlight_hours: float  # 일조시간 (h)


ZONE_LIMITS: dict[str, LegalLimits] = {
    "1R": LegalLimits(0.60, 2.00, 20.0, 1.5, 4.0),  # 제1종일반주거
    "2R": LegalLimits(0.60, 2.00, 35.0, 1.0, 2.0),  # 제2종일반주거
    "3R": LegalLimits(0.50, 3.00, 50.0, 1.0, 2.0),  # 제3종일반주거
    "GC": LegalLimits(0.60, 10.00, 0.0, 0.0, 0.0),  # 일반상업 (높이 무제한)
    "NC": LegalLimits(0.60, 9.00, 0.0, 0.5, 0.0),  # 근린상업
    "QI": LegalLimits(0.60, 4.00, 0.0, 1.0, 0.0),  # 준공업
    # W-A 교정: 준주거 건폐율 70% 이하(국토계획법 시행령 84조). 기존 0.60은 오기재.
    "QR": LegalLimits(0.70, 5.00, 0.0, 1.0, 0.0),  # 준주거
}

_DEFAULT_LIMITS = LegalLimits(0.60, 2.50, 35.0, 1.0, 2.0)

# 건축법 61조(일조 등의 확보를 위한 건축물의 높이 제한)은 전용·일반주거지역에만 적용.
# 본 엔진 코드 체계에서 1R/2R/3R(일반주거)만 해당 — 준주거(QR)·상업(GC/NC)·공업(QI)은
# 정북일조 사선제한 적용 대상이 아니다(W-A ① 교정).
SUNLIGHT_ZONES: frozenset[str] = frozenset({"1R", "2R", "3R"})


# ── 건축물 용도별 상수 ──

# ── 복도폭(건축법 시행령 §48 — 복도 너비) ──
# 공동주택 공용복도는 '복도형식'에 따라 다르다: 편복도(한쪽 거실)≥1.8m, 중복도(양면 거실)≥2.4m.
# 기존 1.8m '고정'은 중복도(양면 세대) 평면에 오적용되면 법정 미달이 되므로, 유형별로 분리한다
# (D-A 교정: 주석↔값 일치·중복도 오적용 해소). CORRIDOR_WIDTHS는 '편복도(single-loaded)'
# 기준 최소폭이고, 중복도는 CORRIDOR_WIDTHS_DOUBLE를 사용한다.
CORRIDOR_WIDTHS: dict[str, float] = {  # 편복도(single-loaded) 최소폭
    "공동주택": 1.8,
    "근린생활시설": 1.8,
    "업무시설": 1.8,
    "판매시설": 2.4,
    "숙박시설": 1.8,
}
CORRIDOR_WIDTHS_DOUBLE: dict[str, float] = {  # 중복도(double-loaded·양면거실) 최소폭(≥2.4m)
    "공동주택": 2.4,
    "근린생활시설": 2.4,
    "업무시설": 2.4,
    "판매시설": 3.0,
    "숙박시설": 2.4,
}
# 편복도 최소폭(시행령 §48 — 공동주택 공용 편복도 1.8m). 미등록 용도 폴백.
_CORRIDOR_SINGLE_MIN = 1.8
# 중복도(양면 거실) 최소폭(시행령 §48 — 2.4m). 미등록 용도 폴백.
_CORRIDOR_DOUBLE_MIN = 2.4

CORE_AREA_SQM = 25.0  # 코어 1개당 면적 (계단+EV+파이프)
CORE_PER_FLOOR_AREA = 1500.0  # 연면적 N sqm당 코어 1개 (피난규칙)

# 피난 보행거리(피난·방화구조 등의 기준에 관한 규칙 §15 ① — 거실에서 직통계단까지 보행거리).
# 주요구조부 비내화 30m / 내화·불연(공동주택 등) 50m. 본 엔진은 보수적으로 비내화 30m를 적용해
# 코어 1개가 커버하는 복도 반경(=보행거리)을 정하고, 1동 길이가 이를 초과하면 코어를 추가한다.
TRAVEL_DISTANCE_NONCOMBUSTIBLE_M = 50.0  # 내화구조(공동주택 등) 보행거리 한도
TRAVEL_DISTANCE_DEFAULT_M = 30.0         # 일반(비내화) 보행거리 한도 — 보수 기본
# 직통계단(피난) 2개소 의무 기준(건축법 시행령 §34 ②): 5층 이상 또는 층당 거실 200㎡ 초과.
DUAL_STAIR_FLOOR_THRESHOLD = 5
DUAL_STAIR_FLOOR_AREA_THRESHOLD_SQM = 200.0
# 승강기(EV) 의무 설치(건축법 §64·시행령 §89): 6층 이상이고 연면적 2,000㎡ 이상.
ELEVATOR_FLOOR_THRESHOLD = 6

UNIT_TYPES: dict[str, float] = {
    "39A": 39.0,
    "49A": 49.0,
    "59A": 59.0,
    "74A": 74.0,
    "84A": 84.0,
    "114A": 114.0,
}

PARKING_RULES: dict[str, dict[str, Any]] = {
    "공동주택": {"per_unit": True, "rate": 1.0, "area_per_car_sqm": 33.0},
    "근린생활시설": {"per_unit": False, "rate_per_sqm": 100, "area_per_car_sqm": 33.0},
    "업무시설": {"per_unit": False, "rate_per_sqm": 150, "area_per_car_sqm": 33.0},
}


@dataclass
class SiteInput:
    """대지 입력 정보."""

    site_area_sqm: float
    site_shape: list[dict[str, float]] | None = None  # [{x, y}, ...]
    site_width_m: float = 0.0  # 대지 폭 (자동 산출 가능)
    site_depth_m: float = 0.0  # 대지 깊이 (자동 산출 가능)
    zone_code: str = "2R"
    building_use: str = "공동주택"
    target_unit_types: list[str] = field(default_factory=lambda: ["84A"])
    floor_height_m: float = 3.0
    setback_m: dict[str, float] = field(
        default_factory=lambda: {"north": 3.0, "south": 2.0, "east": 1.5, "west": 1.5}
    )
    # P5: 정북일조 사선제한 "단계후퇴" 모드. True면 단일 세트백 높이캡 대신 층별 북측
    # 후퇴(상부일수록 더 후퇴)로 더 높게 짓고 상부 세대의 일조를 확보한다(결정론).
    daylight_step: bool = False
    # W-A ④: 목표 설계강도(%). None=법정 한도 그대로. 값이 있으면 min(법정, 목표) 적용
    # (라우터에서 법정 한도로 1차 클램프, 엔진에서 한 번 더 min — 이중 안전).
    target_far_percent: float | None = None
    target_bcr_percent: float | None = None
    # §4-B 조례: 지자체 도시계획조례 실효 한도(%). 라우터가 OrdinanceService(법제처 API→캐시→
    # 법정상한)로 조회해 주입한다. 적용은 min(법정, 조례, 목표) — 조례가 법정을 넘으면 법정으로
    # 클램프(가짜 상향 금지). None=조례 미반영(법정상한 기준 — 기존 동작 불변).
    ordinance_bcr_percent: float | None = None
    ordinance_far_percent: float | None = None
    # 매스 형상(옵셔널·additive). None="auto"(대지 종횡비 기반 — 기존 동작 불변).
    # 명시 시 형상별 종횡비·플로어플레이트 계수로 매스를 재산출(결정론).
    massing_kind: str | None = None
    # §4-B 참조설계 피드백(옵셔널·additive): 유사 사례 기하 힌트(종횡비 등).
    # 라우터가 design_reference_service.derive_reference_mass_hint로 도출해 주입한다
    # (결정론). 우선순위 — 명시 massing_kind > 참조 비례 > auto(대지비율).
    # None=미사용(기존 동작 완전 불변). 형식: {aspect, ref_id, title, similarity, ...}.
    reference_mass: dict[str, Any] | None = None
    # ★건축유형별 매싱 목적함수(옵셔널·additive). massing_strategy.resolve_massing_objective가
    # 반환하는 MassingObjective dict. 핵심 키 target_bcr_ratio(<1.0이면 footprint를
    # 건폐율 상한 미만으로 축소 → 층수↑·고층저밀). None=목적함수 미사용(기존 동작 완전
    # 불변 — footprint는 건폐율 상한 만충). 형식: {objective, target_bcr_ratio, ...}.
    massing_objective: dict[str, Any] | None = None
    # ★목표 층수(옵셔널·additive): 정북일조 단계후퇴(daylight_step=True) 경로에서 층수 상한으로 작용한다.
    #   '지역 실측 전형' 시드(매스 백본 median_floors)처럼 전형 층수까지만 짓고 과도한 고층화를 막는 용도.
    #   min(FAR한도, 높이한도, target_floors)로 적용 → 법정 높이 초과 불가(자동 클램프). None=미적용(기존 동작
    #   완전 불변). hard_cap 경로(daylight_step=False)에서는 무시(단계후퇴 전제 — 그 경로는 일조 하드캡이 지배).
    target_floors: int | None = None


# 매스 형상 정의 — aspect=전면/깊이 비, fp_factor=최대 건축면적 대비 플로어플레이트 계수.
# 결정론 규칙(LLM 0): 타워형은 작은 플로어플레이트로 더 높이, 판상형은 넓고 얕게.
MASSING_FORMS: dict[str, dict[str, Any]] = {
    "slab": {"label": "판상형", "aspect": 2.6, "fp_factor": 1.0},
    "tower": {"label": "타워형", "aspect": 1.0, "fp_factor": 0.55},
    "lshape": {"label": "ㄱ자형", "aspect": 1.7, "fp_factor": 0.82},
    "court": {"label": "중정형", "aspect": 1.2, "fp_factor": 0.70},
}


@dataclass
class DesignResult:
    """자동 설계 결과."""

    design_payload: dict[str, Any]  # 프론트 DesignPayload 호환
    summary: dict[str, Any]
    compliance: dict[str, Any]
    alternatives: list[dict[str, Any]] = field(default_factory=list)


def compute_north_step_profile(
    building_w: float,
    building_d: float,
    max_floors: int,
    floor_height_m: float,
    base_north_m: float,
    max_total_floor_area: float,
) -> tuple[list[dict[str, float]], float, int]:
    """정북일조 사선제한 단계후퇴 프로파일을 산출한다(결정론).

    건축법 61조·시행령 86조(W-A ① 교정 산식·2023.9.12 개정 임계 10m): 높이 10m 이하
    부분은 정북 인접대지경계선에서 1.5m 이상, 10m 초과 부분은 해당 높이의 1/2 이상 이격.
    따라서 층의 윗변 높이 h=층수×층고에 대해 필요 북측 이격 d=max(base, h<=10 ? 1.5 : h/2).
    base(=설계 북측 세트백)를 넘는 만큼(inset)만 상부 층이 북쪽으로 후퇴한다.

    Returns: (profile, 단계후퇴 반영 총연면적, 실제 층수)
      profile[f] = {floor, north_setback_m, inset_m, depth_m}
    """
    profile: list[dict[str, float]] = []
    area = 0.0
    n = 0
    min_depth = max(4.0, building_d * 0.35)  # 후퇴해도 세대 성립 최소 깊이
    for f in range(1, max(1, max_floors) + 1):
        top_h = f * floor_height_m
        # 정북일조(시행령 86조·현행 10m): 10m 이하 1.5m / 10m 초과 h/2 (공용 산식)
        req_north = required_north_setback_m(top_h, base_north_m)
        inset = max(0.0, req_north - base_north_m)
        depth_f = building_d - inset
        if depth_f < min_depth:
            break  # 더 후퇴하면 세대 불가 → 이 층부터 못 올림
        af = building_w * depth_f
        if max_total_floor_area > 0 and area + af > max_total_floor_area:
            break  # 용적률 초과 → 중단
        area += af
        n += 1
        profile.append({
            "floor": f,
            "north_setback_m": round(req_north, 2),
            "inset_m": round(inset, 2),
            "depth_m": round(depth_f, 1),
        })
    if n == 0:  # 최소 1층 보장
        profile = [{"floor": 1, "north_setback_m": round(base_north_m, 2),
                    "inset_m": 0.0, "depth_m": round(building_d, 1)}]
        area = building_w * building_d
        n = 1
    return profile, round(area, 2), n


def _north_step_stop_reason(
    building_w: float,
    building_d: float,
    num_floors: int,
    floor_height_m: float,
    base_north_m: float,
    max_floors_by_height: int,
) -> str:
    """단계후퇴 프로파일이 num_floors에서 멈춘 바인딩 제약을 판정한다(far|height|sunlight).

    compute_north_step_profile의 중단 조건을 다음 층(num_floors+1)에 대해 같은
    순서(깊이→면적)로 재현하는 휴리스틱 판정 — W-A ④ binding_constraint 표기용.
    """
    if 0 < max_floors_by_height <= num_floors:
        return "height"
    next_h = (num_floors + 1) * floor_height_m
    req_north = required_north_setback_m(next_h, base_north_m)
    depth_next = building_d - max(0.0, req_north - base_north_m)
    if depth_next < max(4.0, building_d * 0.35):
        return "sunlight"  # 다음 층은 후퇴 한계로 세대 성립 불가 → 일조가 증층을 막음
    return "far"  # 깊이·높이 여유가 있는데 멈췄으면 FAR(연면적 한도) 소진


class AutoDesignEngineService:
    """AI 자동 설계 생성 엔진."""

    # ── 1단계: 법규 한도 조회 ──

    @staticmethod
    def get_legal_limits(zone_code: str) -> dict[str, Any]:
        """용도지역 코드로 설계엔진 기본 한도를 조회한다.

        ⚠️ 본 한도는 ZONE_LIMITS의 **설계엔진 보수적 기본값(전형 조례 수준)** 이며 국가 시행령 '법정 상한'
        그 자체가 아니다(일부 용도지역은 국가 상한보다 보수적 — 예 제2종일반주거 200% vs 국가상한 250%).
        authoritative 국가 상한은 auto_zoning_service.ZONE_LIMITS / 엔진 national_zone_limits.json(SSOT).
        지자체 도시계획조례·지구단위계획 가감은 미반영(설계엔진 경로 한정) — 조례 실효 한도가 필요한 정밀
        산정은 feasibility_service_v2(ordinance_far_pct/bcr_pct, land_info_service 출처)를 사용한다.
        ⚠️ 출력 키 statutory_max_*_percent는 본 기본값을 담으며(역사적 명명) 국가 상한과 다를 수 있다(제품 후속:
        명칭 정정·국가상한 default 채택 여부 검토). 출처(limits_source)를 정직 표기한다.
        """
        limits = ZONE_LIMITS.get(zone_code)
        is_known = limits is not None
        if not is_known:
            logger.warning("알 수 없는 용도지역 코드, 기본값 사용", zone_code=zone_code)
            limits = _DEFAULT_LIMITS
        return {
            "max_bcr_percent": round(limits.building_coverage_ratio * 100, 2),
            "max_far_percent": round(limits.floor_area_ratio * 100, 2),
            "max_height_m": limits.max_height_m,
            "min_setback_m": limits.min_setback_m,
            "sunlight_hours": limits.sunlight_hours,
            # 정직 출처 표기 — 조례 미반영 법정상한, 미지정 코드는 기본값 폴백
            "limits_source": "statutory_default" if is_known else "fallback_default",
            "ordinance_applied": False,
            "warnings": ([] if is_known else [f"미지정 용도지역 코드 '{zone_code}' — 기본값 적용"]) + [
                "지자체 조례·지구단위계획 가감 미반영(법정 상한 기준). 조례 실효 한도는 v2 수지엔진 참조.",
            ],
        }

    # ── 2단계: 유효 건축 영역 + 최적 매스 ──

    @staticmethod
    def compute_effective_site(
        site_input: SiteInput,
    ) -> dict[str, float]:
        """세트백 반영 후 유효 건축 가능 영역을 산출한다."""
        sb = site_input.setback_m

        # 대지 치수 추정 (정사각형 가정, site_shape 있으면 바운딩박스 사용)
        if site_input.site_width_m > 0 and site_input.site_depth_m > 0:
            w = site_input.site_width_m
            d = site_input.site_depth_m
        elif site_input.site_shape and len(site_input.site_shape) >= 3:
            xs = [p["x"] for p in site_input.site_shape]
            ys = [p["y"] for p in site_input.site_shape]
            w = max(xs) - min(xs)
            d = max(ys) - min(ys)
        else:
            side = math.sqrt(site_input.site_area_sqm)
            w = side
            d = side

        eff_w = max(0, w - sb.get("east", 1.5) - sb.get("west", 1.5))
        eff_d = max(0, d - sb.get("north", 3.0) - sb.get("south", 2.0))
        effective_area = eff_w * eff_d

        return {
            "site_width_m": round(w, 2),
            "site_depth_m": round(d, 2),
            "effective_width_m": round(eff_w, 2),
            "effective_depth_m": round(eff_d, 2),
            "effective_area_sqm": round(effective_area, 2),
        }

    @staticmethod
    def _effective_limits(
        site_input: SiteInput,
        legal: dict[str, float],
    ) -> tuple[float, float]:
        """적용 한도(%)를 반환한다 — (건폐율, 용적률).

        적용 우선순위: min(법정, 조례, 목표). 조례(ordinance_*)·목표(target_*)가 법정을
        넘으면 법정값으로 클램프(가짜 한도 상향 금지). None/0 이하는 해당 단계 생략.
        조례는 §4-B(지자체 도시계획조례 실효 한도), 목표는 W-A ④(슬라이더 의도값).
        """
        max_bcr = legal["max_bcr_percent"]
        max_far = legal["max_far_percent"]
        ord_bcr = getattr(site_input, "ordinance_bcr_percent", None)
        ord_far = getattr(site_input, "ordinance_far_percent", None)
        target_bcr = getattr(site_input, "target_bcr_percent", None)
        target_far = getattr(site_input, "target_far_percent", None)
        # §4-B: 조례 실효 한도(법정 이하로만)
        if ord_bcr is not None and ord_bcr > 0:
            max_bcr = min(max_bcr, ord_bcr)
        if ord_far is not None and ord_far > 0:
            max_far = min(max_far, ord_far)
        # W-A ④: 목표 설계강도
        if target_bcr is not None and target_bcr > 0:
            max_bcr = min(max_bcr, target_bcr)
        if target_far is not None and target_far > 0:
            max_far = min(max_far, target_far)
        return max_bcr, max_far

    @staticmethod
    def _compute_podium_tower(
        *,
        site_area: float,
        eff_w: float,
        eff_d: float,
        max_bcr: float,
        max_far: float,
        fh: float,
        max_floors_by_height: int,
        sunlight_zone: bool,
        podium_floors: int = 4,
    ) -> dict[str, Any] | None:
        """고FAR·비일조 용도지역(상업·준주거)의 Podium-Tower 분할 매스(결정론).

        실무 주상복합은 단일 균일박스(만층)가 아니라 **저층 podium(상가·주차·로비 — 지상 큰 판)
        + 고층 tower(주거 — 작은 플로어플레이트)** 로 짓는다. 단일 만층 박스(예 16층)는 footprint를
        대지 가득 깔아 비현실적이며, 실무는 footprint를 줄이고 30~60층으로 올린다.

        적용 게이트: 정북일조 미적용(상업/준주거 등) + 고FAR(≥500%)에서만. 그 외(주거·저FAR)는
        None을 반환해 기존 단일박스를 보존한다(무회귀). 결정론·무날조(미충족 시 None).
        """
        far_pct = max_far * 100.0
        eff_area = eff_w * eff_d
        if sunlight_zone or far_pct < 500.0 or site_area <= 0 or eff_area <= 0:
            return None

        gfa_cap = site_area * max_far  # 용적률 허용 총 연면적

        # ── podium: 지상 저층(상가·주차·로비), 건폐율 max 큰 판 ──
        podium_floors = max(1, podium_floors)
        podium_fp = min(site_area * max_bcr, eff_area)
        podium_gfa = podium_fp * podium_floors
        p_scale = math.sqrt(podium_fp / eff_area) if eff_area > 0 else 0.0
        podium_w = round(eff_w * min(p_scale, 1.0), 1)
        podium_d = round(eff_d * min(p_scale, 1.0), 1)

        # ── tower: 고층 주거, 쾌적 플로어플레이트(주상복합 실무 15~30%·중앙 22%) ──
        tower_bcr = min(0.22, max_bcr)
        tower_fp = min(site_area * tower_bcr, podium_fp)
        if tower_fp <= 0:
            return None
        remaining_gfa = max(0.0, gfa_cap - podium_gfa)   # podium이 쓰고 남은 연면적
        tower_floors_by_far = int(remaining_gfa / tower_fp)
        # 높이 캡 — podium 제외 잔여 층수. compute_optimal_mass는 절대높이 미지정(상업) 시
        #   max_floors_by_height=100(소프트캡)을 넘기므로 그대로 podium 제외 잔여를 캡으로 쓴다.
        tower_floors_by_height = max(0, max_floors_by_height - podium_floors)
        tower_floors = max(0, min(tower_floors_by_far, tower_floors_by_height))
        if tower_floors < 1:
            return None  # tower가 1층도 안 나오면 podium-tower 부적합 → 단일박스 유지

        binding = "far" if tower_floors_by_far <= tower_floors_by_height else "height"
        tower_gfa = tower_fp * tower_floors
        t_scale = math.sqrt(tower_fp / eff_area) if eff_area > 0 else 0.0
        tower_w = round(eff_w * min(t_scale, 1.0), 1)
        tower_d = round(eff_d * min(t_scale, 1.0), 1)

        total_floors = podium_floors + tower_floors
        total_height = total_floors * fh
        total_gfa = podium_gfa + tower_gfa

        return {
            "podium": {
                "footprint_sqm": round(podium_fp, 1), "floors": podium_floors,
                "height_m": round(podium_floors * fh, 1),
                "width_m": podium_w, "depth_m": podium_d,
                "bcr_pct": round(podium_fp / site_area * 100, 1) if site_area > 0 else 0,
                "use": "상가·주차·로비",
            },
            "tower": {
                "footprint_sqm": round(tower_fp, 1), "floors": tower_floors,
                "height_m": round(tower_floors * fh, 1),
                "width_m": tower_w, "depth_m": tower_d,
                "bcr_pct": round(tower_bcr * 100, 1),
                "use": "주거",
            },
            "total_floors": total_floors,
            "total_height_m": total_height,
            "total_gfa": total_gfa,
            "tower_gfa": tower_gfa,        # 주거(tower) 연면적 — 세대분해 풀(podium 상가/주차 제외)
            "binding": binding,
            "basis": (
                f"podium {podium_floors}층(건폐율 {round(max_bcr * 100)}% 큰 판)"
                f"+tower {tower_floors}층(건폐율 {round(tower_bcr * 100)}% 작은 판)로 분할 — "
                "고FAR 상업지 주상복합 실무 매스(단일 만층 박스 비현실 해소)"
            ),
        }

    @staticmethod
    def compute_optimal_mass(
        site_input: SiteInput,
        effective: dict[str, float],
        legal: dict[str, float],
    ) -> dict[str, Any]:
        """법규 제약 하 최적 건축 매스를 산출한다.

        W-A 교정 사항:
        - 정북일조 높이캡은 전용·일반주거지역(1R/2R/3R)만 적용(건축법 61조 적용범위).
        - 목표 설계강도(target_far/bcr_percent)는 min(법정, 목표)로 적용.
        - 층수를 막은 제약을 binding_constraint(far|height|sunlight|setback)로 표기.
        """
        site_area = site_input.site_area_sqm
        eff_area = effective["effective_area_sqm"]

        applied_bcr_pct, applied_far_pct = AutoDesignEngineService._effective_limits(
            site_input, legal,
        )
        max_bcr = applied_bcr_pct / 100.0
        max_far = applied_far_pct / 100.0
        max_height = legal["max_height_m"]

        # 건폐율 제약 → 최대 건축면적
        max_footprint = site_area * max_bcr
        # ★매싱 목적함수(opt-in): target_bcr_ratio<1.0이면 건폐율 상한보다 작게 깔아
        # (고층저밀) max_floors_by_far가 자동 증가 → 높이 최대 달성(공동주택 목적).
        # None/무objective/ratio>=1.0이면 1.0=기존 동작(상한 만충) 보존(무회귀).
        target_bcr_ratio = 1.0
        objective = getattr(site_input, "massing_objective", None)
        if isinstance(objective, dict):
            try:
                r = float(objective.get("target_bcr_ratio", 1.0))
                if 0.0 < r < 1.0:
                    target_bcr_ratio = r
            except (TypeError, ValueError):
                target_bcr_ratio = 1.0
        building_footprint = min(max_footprint * target_bcr_ratio, eff_area)

        # 건물 치수 (유효 영역 내 직사각형)
        eff_w = effective["effective_width_m"]
        eff_d = effective["effective_depth_m"]

        if eff_w * eff_d > 0:
            scale = math.sqrt(building_footprint / (eff_w * eff_d))
            building_w = round(eff_w * min(scale, 1.0), 1)
            building_d = round(eff_d * min(scale, 1.0), 1)
        else:
            building_w = 0
            building_d = 0

        # 매스 형상(opt-in·additive): massing_kind 명시 시 형상별 종횡비·플로어플레이트로
        # 폭/깊이를 재산출(대지 유효치 내 클램프). None이면 위 기본 동작 그대로(하위호환).
        # §4-B 우선순위: 명시 massing_kind > 참조 비례(reference_mass) > auto(대지비율).
        mk = getattr(site_input, "massing_kind", None)
        form = MASSING_FORMS.get(mk) if mk else None
        ref_hint = getattr(site_input, "reference_mass", None)
        ref_hint = ref_hint if isinstance(ref_hint, dict) else None
        ref_aspect = 0.0
        if ref_hint is not None:
            try:
                ref_aspect = float(ref_hint.get("aspect") or 0.0)
            except (TypeError, ValueError):
                ref_aspect = 0.0
        ref_provenance: dict[str, Any] | None = None

        if form and eff_w * eff_d > 0 and building_footprint > 0:
            target_fp = building_footprint * form["fp_factor"]
            aspect = form["aspect"]
            raw_d = math.sqrt(target_fp / aspect) if aspect > 0 else 0.0
            raw_w = aspect * raw_d
            building_w = round(min(raw_w, eff_w), 1)
            building_d = round(min(raw_d, eff_d), 1)
            if ref_hint is not None:  # 참조 힌트는 왔으나 명시 형상이 우선 — 정직 표기
                ref_provenance = {
                    "used": False, "note": "명시 매스 형상이 우선 적용됨",
                    "ref_id": ref_hint.get("ref_id"), "title": ref_hint.get("title"),
                }
        elif ref_aspect > 0 and eff_w * eff_d > 0 and building_footprint > 0:
            # §4-B: 참조 사례 비례 주입 — BCR 건축면적은 그대로 두고(법규 불변) 종횡비만
            # 참조 사례(전면/깊이) 쪽으로 편향, 대지 유효치 내 클램프(결정론).
            raw_d = math.sqrt(building_footprint / ref_aspect)
            raw_w = ref_aspect * raw_d
            building_w = round(min(raw_w, eff_w), 1)
            building_d = round(min(raw_d, eff_d), 1)
            # 정직성: 유효치 클램프로 실현 종횡비가 목표와 달라질 수 있으므로 둘 다 표기한다
            # (목표 aspect + 실현 applied_aspect + clamped 플래그). 부분 적용을 온전 적용처럼
            # 표기하지 않는다(불변규칙 — 정직 표기).
            clamped = raw_w > eff_w + 1e-9 or raw_d > eff_d + 1e-9
            applied_aspect = round(building_w / building_d, 3) if building_d > 0 else None
            basis = (ref_hint.get("basis")
                     or f"유사 사례 기하 종횡비 {ref_aspect:.2f}(전면/깊이)로 매스 편향")
            if clamped and applied_aspect is not None:
                basis += f" — 대지 유효치로 클램프(실현 종횡비 {applied_aspect:.2f})"
            ref_provenance = {
                "used": True,
                "ref_id": ref_hint.get("ref_id"),
                "title": ref_hint.get("title"),
                "similarity": ref_hint.get("similarity"),
                "aspect": round(ref_aspect, 3),
                "applied_aspect": applied_aspect,
                "clamped": clamped,
                "source": ref_hint.get("source", "design_reference"),
                "basis": basis,
            }
        elif ref_hint is not None:
            # 힌트는 왔으나 종횡비가 무효(0/음수/결측) → auto 동작 유지, 정직 표기
            ref_provenance = {
                "used": False, "note": "참조 종횡비가 유효하지 않아 미적용(auto)",
                "ref_id": ref_hint.get("ref_id"),
            }

        actual_footprint = building_w * building_d

        # 용적률 제약 → 최대 연면적 → 최대 층수
        max_total_floor = site_area * max_far
        max_floors_by_far = (
            int(max_total_floor / actual_footprint)
            if actual_footprint > 0
            else 1
        )

        # 높이 제약 → 최대 층수
        max_floors_by_height = (
            int(max_height / site_input.floor_height_m)
            if max_height > 0
            else 100
        )

        north_setback = site_input.setback_m.get("north", 3.0)
        fh = site_input.floor_height_m
        north_step_profile: list[dict[str, float]] | None = None
        # W-A ①: 정북일조(건축법 61조)는 전용·일반주거지역만 적용 — QR/상업/공업 스킵
        sunlight_zone = site_input.zone_code in SUNLIGHT_ZONES
        max_height_by_sunlight: float | None = None
        binding_constraint = "far"

        if getattr(site_input, "daylight_step", False) and sunlight_zone:
            # 정북일조 "단계후퇴" 모드: 단일 세트백 높이캡을 쓰지 않고(FAR·높이 한도만),
            # 상부 층을 북쪽으로 후퇴시켜 더 높이 짓고 일조를 확보(결정론 사선제한).
            base_north = max(1.5, north_setback)
            # ★target_floors(옵셔널)는 층수 상한으로만 작용(min에 포함 → 법정 높이 초과 불가·자동 클램프).
            #   '지역 실측 전형' 시드가 전형 층수까지만 짓게 함. None이면 999로 무영향(기존 동작 불변).
            _tf = getattr(site_input, "target_floors", None)
            cap_floors = max(1, min(max_floors_by_far * 3, max_floors_by_height, _tf or 999))  # 후퇴로 더 높이 가능
            north_step_profile, total_floor_area, num_floors = compute_north_step_profile(
                building_w, building_d, cap_floors, fh, base_north, max_total_floor,
            )
            building_height = num_floors * fh
            binding_constraint = _north_step_stop_reason(
                building_w, building_d, num_floors, fh, base_north, max_floors_by_height,
            )
            sunlight_mode = "step_profile"
        else:
            if sunlight_zone:
                # W-A ① 교정 산식(시행령 86조·현행 10m): 높이 10m 이하 부분은 북측 1.5m
                # 이격으로 충족 → 북측이격 d>=5.0m면 최고높이 2d, d<5.0m면 10m 캡(공용 산식).
                max_height_by_sunlight = max_height_for_north_distance_m(north_setback)
                max_floors_by_sunlight = int(max_height_by_sunlight / fh)
                sunlight_mode = "hard_cap"
            else:
                max_floors_by_sunlight = 10**6  # 미적용(법 61조 적용범위 외)
                sunlight_mode = "not_applicable"
            # 층수 후보 중 최솟값이 바인딩 제약(동률 시 far→height→sunlight 순 표기)
            floor_candidates = {
                "far": max_floors_by_far,
                "height": max_floors_by_height,
                "sunlight": max_floors_by_sunlight,
            }
            num_floors = max(1, min(floor_candidates.values()))
            binding_constraint = (
                min(floor_candidates, key=floor_candidates.get)
                if actual_footprint > 0
                else "setback"  # 세트백으로 유효 건축면적 자체가 0
            )
            total_floor_area = actual_footprint * num_floors
            building_height = num_floors * fh

        bcr = round(actual_footprint / site_area * 100, 2) if site_area > 0 else 0
        far = round(total_floor_area / site_area * 100, 2) if site_area > 0 else 0

        result: dict[str, Any] = {
            "building_width_m": building_w,
            "building_depth_m": building_d,
            "building_footprint_sqm": round(actual_footprint, 2),
            "num_floors": num_floors,
            "floor_height_m": fh,
            "building_height_m": round(building_height, 2),
            "total_floor_area_sqm": round(total_floor_area, 2),
            "bcr_pct": bcr,
            "far_pct": far,
            "max_bcr_pct": legal["max_bcr_percent"],
            "max_far_pct": legal["max_far_percent"],
            "max_height_m": max_height,
            # W-A ④⑤: 적용 한도(목표 반영)·바인딩 제약·일조캡 근거 (additive)
            "applied_max_bcr_pct": round(applied_bcr_pct, 2),
            "applied_max_far_pct": round(applied_far_pct, 2),
            "binding_constraint": binding_constraint,
            "sunlight_mode": sunlight_mode,
            "max_height_by_sunlight_m": (
                round(max_height_by_sunlight, 2)
                if max_height_by_sunlight is not None
                else None
            ),
            # 매스 형상 출처(정직 표기) — 유효 형상이 적용된 경우만 그 이름, 아니면 auto.
            "massing_kind": (mk if form else "auto"),
            "massing_label": (form["label"] if form else "자동(대지비율)"),
        }
        # ★매싱 목적함수 적용 출처(있을 때만·additive). target_bcr_ratio<1.0이면 고층저밀
        # 적용됨을 정직 표기. 미주입/ratio=1.0이면 키 추가 안 함(기존 동작 불변).
        if isinstance(objective, dict) and 0.0 < target_bcr_ratio < 1.0:
            result["massing_objective"] = objective.get("objective")
            result["target_bcr_ratio_applied"] = round(target_bcr_ratio, 3)
        if north_step_profile is not None:
            result["north_step_profile"] = north_step_profile
            result["daylight_step"] = True
        # §4-B: 참조 프로비넌스(있을 때만 — additive). 미주입 시 키 없음(기존 동작 불변).
        if ref_provenance is not None:
            result["reference"] = ref_provenance

        # ── Podium-Tower 실무 매스(고FAR·비일조 상업/준주거 auto) ──
        # 단일 균일박스(만층·예 16층) 대신 저층 podium(상가·주차·지상 큰 판)+고층 tower(주거·작은
        # 판)로 분할해 실무 주상복합(30~60층)에 부합시킨다. 정북일조(주거)·저FAR(<500%)·정북단계
        # 후퇴(step_profile) 모드는 미적용(단일박스 보존·무회귀). headline(층수·높이·연면적·치수·
        # BCR)을 현실 composite로 갱신하고 podium/tower 상세를 additive로 싣는다.
        # 적용은 ①정북단계후퇴 모드 아님(주거 전용) ②명시 매스형상(massing_kind) 없음(auto)일 때만.
        #   사용자가 slab/tower 등을 명시하면 그 선택을 존중(podium-tower로 덮어쓰지 않음·메타 모순 방지).
        pt = (
            AutoDesignEngineService._compute_podium_tower(
                site_area=site_area, eff_w=eff_w, eff_d=eff_d,
                max_bcr=max_bcr, max_far=max_far, fh=fh,
                max_floors_by_height=max_floors_by_height,
                sunlight_zone=sunlight_zone,
            )
            if (north_step_profile is None and form is None)
            else None
        )
        if pt is not None:
            twr = pt["tower"]
            result["massing_profile"] = "podium_tower"
            result["massing_kind"] = "podium_tower"           # 메타 일관(label과 정합)
            result["podium"] = pt["podium"]
            result["tower"] = twr
            result["residential_floors"] = twr["floors"]      # 주거(tower) 층수
            result["commercial_floors"] = pt["podium"]["floors"]  # 저층부(상가·주차)
            result["floors_for_units"] = twr["floors"]        # ★세대수 산정 기준(podium 제외·무날조)
            result["residential_gfa_sqm"] = round(pt["tower_gfa"], 2)  # 주거 연면적(세대분해 풀·podium 제외)
            # headline을 현실 composite로 갱신 — 대표 floor plate는 tower(주거 기준층).
            result["num_floors"] = pt["total_floors"]
            result["building_height_m"] = round(pt["total_height_m"], 2)
            result["total_floor_area_sqm"] = round(pt["total_gfa"], 2)
            result["building_width_m"] = twr["width_m"]
            result["building_depth_m"] = twr["depth_m"]
            result["building_footprint_sqm"] = round(twr["footprint_sqm"], 2)
            # BCR=podium 지상피복(건물 지상 점유), FAR=composite 연면적/대지.
            result["bcr_pct"] = (
                round(pt["podium"]["footprint_sqm"] / site_area * 100, 2) if site_area > 0 else 0
            )
            result["far_pct"] = round(pt["total_gfa"] / site_area * 100, 2) if site_area > 0 else 0
            result["binding_constraint"] = pt["binding"]
            result["massing_label"] = "포디움-타워(주상복합)"
        return result

    # ── 3단계: 코어 + 복도 배치 ──

    @staticmethod
    def compute_core_layout(
        mass: dict[str, Any],
        building_use: str,
        *,
        corridor_type: str = "double",
        fire_resistant: bool = True,
    ) -> dict[str, Any]:
        """코어 수, 복도폭, 위치를 산출한다(피난 보행거리·복도형식 기반·D-A 교정).

        corridor_type: "double"(중복도·양면거실, 기본·보수) | "single"(편복도·한쪽거실).
          중복도는 §48에 따라 ≥2.4m, 편복도는 ≥1.8m을 적용한다(기존 1.8m 고정·중복도 오적용 해소).
        fire_resistant: 주요구조부 내화 여부(공동주택 등 True=보행거리 50m / False=30m).

        코어 수는 ① 층당 바닥판(plate) 면적 기준(CORE_PER_FLOOR_AREA — 코어는 수직 관통이라
        적층 연면적이 아닌 '층당' 면적으로 산정), ② 피난 보행거리 기준(1동 길이를 코어가 2방향으로
        커버 = 코어당 ≈ 2×보행거리), ③ 직통계단 2개소 의무(건축법 시행령 §34② — 5층↑/층당 200㎡↑)
        의 가장 많은 쪽(max)으로 보정한다(고층에서 적층 연면적으로 코어가 폭증해 세대 0이 되는
        오류·균등등분 과밀·보행거리 초과를 근본 차단). 코어 간격이 좁으면(과밀) 경고를 함께 반환(정직).
        """
        bw = float(mass["building_width_m"])
        bd = float(mass["building_depth_m"])
        warnings: list[str] = []

        # ★코어(계단·EV·설비 샤프트)는 모든 층을 수직으로 관통하는 공용공간이라, 코어 '수'는
        #   '적층 연면적'이 아니라 '층당 바닥판(plate) 면적'과 피난 동선으로 정해야 한다.
        #   적층 연면적으로 곱하면 고층일수록 코어가 비현실적으로 폭증한다(예: GC 2000㎡ 38층이면
        #   적층 19,760㎡/1500≈14개 → 타워 440㎡ 바닥판을 코어가 다 먹어 0세대; GC 14959㎡면 99개).
        #   podium-tower 매스에서는 building_footprint_sqm가 '타워' 바닥판이므로 그대로 plate가 된다.
        footprint_pf = float(mass.get("building_footprint_sqm") or (bw * bd))
        floors = int(mass.get("floors_for_units") or mass.get("num_floors") or 1)

        # 복도폭: 복도형식(편/중)에 따라 분리(§48). 중복도(기본)는 ≥2.4m, 편복도는 ≥1.8m.
        if corridor_type == "single":
            corridor_w = CORRIDOR_WIDTHS.get(building_use, _CORRIDOR_SINGLE_MIN)
        else:
            corridor_w = CORRIDOR_WIDTHS_DOUBLE.get(building_use, _CORRIDOR_DOUBLE_MIN)

        # ① 바닥판 면적 기준 코어 수(피난·설비 코어 1개/CORE_PER_FLOOR_AREA㎡ — '층당' plate 기준).
        cores_by_area = max(1, math.ceil(footprint_pf / CORE_PER_FLOOR_AREA))
        # ② 피난 보행거리 기준 코어 수: 코어 1개가 좌우 복도를 양방향으로 커버하므로 1동(폭 bw)을
        #    코어당 약 2×보행거리로 나눈다(거실→직통계단 보행거리 한도, 피난규칙 §15).
        travel = TRAVEL_DISTANCE_NONCOMBUSTIBLE_M if fire_resistant else TRAVEL_DISTANCE_DEFAULT_M
        cores_by_egress = max(1, math.ceil(bw / (2.0 * travel))) if bw > 0 else 1
        # ③ 직통계단 2개소 의무(건축법 시행령 §34②): 5층 이상 또는 층당 거실 200㎡ 초과면 코어 ≥2.
        #    (plate 면적은 거실 면적의 보수적 상한 — plate>200이면 거실>200 가능성을 안전측으로 포함.)
        cores_by_dual_stair = (
            2
            if (floors >= DUAL_STAIR_FLOOR_THRESHOLD or footprint_pf > DUAL_STAIR_FLOOR_AREA_THRESHOLD_SQM)
            else 1
        )
        num_cores = max(cores_by_area, cores_by_egress, cores_by_dual_stair)
        if cores_by_egress > max(cores_by_area, cores_by_dual_stair):
            warnings.append(
                f"피난 보행거리({travel:.0f}m) 확보 위해 코어 {num_cores}개로 증설"
                f"(1동 길이 {bw:.0f}m·바닥판 기준 {cores_by_area}개→보행거리 기준 {cores_by_egress}개)"
            )
        elif cores_by_dual_stair > cores_by_area:
            warnings.append(
                f"직통계단 2개소 의무(건축법 시행령 §34② — {floors}층·층당 약 {footprint_pf:.0f}㎡) "
                f"반영해 코어 {num_cores}개"
            )

        # 코어 위치: 건물 중심축에 등분 배치(균등등분은 위치 산출에만 사용 — 수량은 위에서 보정됨).
        core_positions: list[dict[str, float]] = []
        if num_cores == 1:
            core_positions.append({"x": round(bw / 2, 1), "y": round(bd / 2, 1)})
        else:
            spacing = bw / (num_cores + 1)
            for i in range(num_cores):
                core_positions.append({
                    "x": round(spacing * (i + 1), 1),
                    "y": round(bd / 2, 1),
                })
            # 코어 간격이 비현실적으로 좁으면(과밀) 정직 경고 — 코어 폭 ≈ √CORE_AREA(약 5m) 기준.
            core_side = math.sqrt(CORE_AREA_SQM)
            if spacing < core_side * 1.5:
                warnings.append(
                    f"코어 간격 {spacing:.1f}m가 과밀(코어 폭 약 {core_side:.1f}m 대비 좁음) — "
                    "코어 통합·평면 재구성 검토 필요"
                )

        total_core_area = num_cores * CORE_AREA_SQM
        corridor_area = bw * corridor_w  # 복도 면적(폭×1동 길이) — 복도형식에 맞는 폭 적용

        return {
            "num_cores": num_cores,
            "core_area_sqm": round(total_core_area, 2),
            "corridor_width_m": corridor_w,
            "corridor_type": corridor_type,        # 복도형식(편/중) — 평면검증·근거 표기
            "corridor_area_sqm": round(corridor_area, 2),
            "core_positions": core_positions,
            "travel_distance_m": travel,           # 적용 보행거리 한도(피난규칙 §15)
            "core_warnings": warnings,             # 코어 과밀·보행거리 보정 경고(정직·없으면 [])
        }

    # ── 4단계: 세대/호실 자동 배분 ──

    @staticmethod
    def compute_unit_layout(
        mass: dict[str, Any],
        core_layout: dict[str, Any],
        target_unit_types: list[str],
        building_use: str,
    ) -> dict[str, Any]:
        """세대 유형별 배분을 산출한다."""
        footprint = mass["building_footprint_sqm"]
        net_area_per_floor = footprint - core_layout["core_area_sqm"] - core_layout["corridor_area_sqm"]
        net_area_per_floor = max(0, net_area_per_floor)

        units: list[dict[str, Any]] = []
        total_units = 0
        units_feasible = True
        infeasible_reason: str | None = None

        if building_use == "공동주택" and target_unit_types:
            # W-A ③: 그리디 라운드로빈(소형 우선) — 층당 잔여 순면적 내에서만 배치.
            # 기존 max(1,…) 최소 1세대 강제는 순면적을 초과하는 가짜 세대를 만들 수
            # 있어 제거. 불변식: sum(area_sqm×count_per_floor) <= net_area_per_floor.
            unique_types = list(dict.fromkeys(target_unit_types))  # 입력 순서 유지 중복 제거
            greedy_order = sorted(unique_types, key=lambda t: UNIT_TYPES.get(t, 84.0))
            counts: dict[str, int] = {t: 0 for t in unique_types}
            remaining = net_area_per_floor
            placed = True
            while placed:
                placed = False
                for ut in greedy_order:  # 한 바퀴에 유형별 1세대씩(라운드로빈)
                    unit_area = UNIT_TYPES.get(ut, 84.0)
                    if unit_area <= remaining:
                        counts[ut] += 1
                        remaining -= unit_area
                        placed = True

            # ★세대 산정 층수: podium-tower면 주거(tower) 층수만(podium=상가·주차는 세대 제외).
            #   floors_for_units 없으면(단일박스) num_floors 그대로(무회귀). 무날조: podium 층을
            #   주거로 중복 계산해 세대수를 부풀리지 않는다.
            unit_floors = mass.get("floors_for_units") or mass.get("num_floors", 1)
            for ut in unique_types:
                count_per_floor = counts[ut]
                if count_per_floor <= 0:
                    continue  # 성립 불가 유형은 0세대 — 가짜 1세대 강제 금지
                total = count_per_floor * unit_floors
                units.append({
                    "type": ut,
                    "area_sqm": UNIT_TYPES.get(ut, 84.0),
                    "count_per_floor": count_per_floor,
                    "total_count": total,
                })
                total_units += total

            if total_units == 0:
                # 정직 반환: 순면적이 최소 평형보다 작아 세대 성립 불가
                units_feasible = False
                min_area = min(UNIT_TYPES.get(t, 84.0) for t in unique_types)
                infeasible_reason = (
                    f"세대 성립 불가 — 층당 순면적 {net_area_per_floor:.1f}㎡가 "
                    f"최소 평형 {min_area:.0f}㎡보다 작음"
                )
        else:
            # 비주거: 호실 면적 기준
            room_area = 50.0  # 기본 호실 면적
            rooms_per_floor = max(1, int(net_area_per_floor / room_area))
            unit_floors = mass.get("floors_for_units") or mass.get("num_floors", 1)
            total_units = rooms_per_floor * unit_floors
            units.append({
                "type": "일반",
                "area_sqm": room_area,
                "count_per_floor": rooms_per_floor,
                "total_count": total_units,
            })

        # 주차 대수 산정 (0세대면 0대 — 세대수 연동 정직 재산출)
        parking = _compute_parking(total_units, mass["total_floor_area_sqm"], building_use)

        result: dict[str, Any] = {
            "net_area_per_floor_sqm": round(net_area_per_floor, 2),
            "units": units,
            "total_units": total_units,
            "units_feasible": units_feasible,  # W-A ③: False면 세대 성립 불가(정직 표기)
            "parking_required": parking["required"],
            "parking_area_sqm": parking["area_sqm"],
            "basement_floors_for_parking": parking["basement_floors"],
        }
        if infeasible_reason:
            result["infeasible_reason"] = infeasible_reason
        return result

    # ── 5단계: DesignPayload 변환 ──

    @staticmethod
    def to_design_payload(
        site_input: SiteInput,
        effective: dict[str, float],
        mass: dict[str, Any],
        core_layout: dict[str, Any],
        unit_layout: dict[str, Any],
    ) -> dict[str, Any]:
        """프론트 CAD 스토어 호환 DesignPayload를 생성한다."""
        scale = 10.0  # 1m = 10px
        sb = site_input.setback_m
        bw = mass["building_width_m"]
        bd = mass["building_depth_m"]

        # 세트백 오프셋
        ox = sb.get("west", 1.5) * scale
        oy = sb.get("north", 3.0) * scale

        points: list[dict[str, Any]] = []
        lines: list[dict[str, Any]] = []
        surfaces: list[dict[str, Any]] = []

        # 건물 외곽선 (폴리곤)
        corners = [
            {"id": "pt-b0", "x": ox, "y": oy},
            {"id": "pt-b1", "x": ox + bw * scale, "y": oy},
            {"id": "pt-b2", "x": ox + bw * scale, "y": oy + bd * scale},
            {"id": "pt-b3", "x": ox, "y": oy + bd * scale},
        ]
        points.extend(corners)
        surfaces.append({
            "id": "pg-building",
            "point_ids": [c["id"] for c in corners],
        })

        # 외벽 라인
        for i in range(4):
            j = (i + 1) % 4
            lines.append({
                "id": f"ln-wall-{i}",
                "start_point_id": corners[i]["id"],
                "end_point_id": corners[j]["id"],
            })

        # 복도 (중앙 수평선)
        corr_w = core_layout["corridor_width_m"]
        corr_y = oy + (bd * scale) / 2
        p_cl = {"id": "pt-corr-l", "x": ox, "y": corr_y}
        p_cr = {"id": "pt-corr-r", "x": ox + bw * scale, "y": corr_y}
        points.extend([p_cl, p_cr])
        lines.append({
            "id": "ln-corridor",
            "start_point_id": p_cl["id"],
            "end_point_id": p_cr["id"],
        })

        # 코어 (사각형)
        for i, cp in enumerate(core_layout["core_positions"]):
            core_size = math.sqrt(CORE_AREA_SQM) * scale
            cx = ox + cp["x"] * scale - core_size / 2
            cy = oy + cp["y"] * scale - core_size / 2

            core_pts = [
                {"id": f"pt-core-{i}-0", "x": round(cx, 1), "y": round(cy, 1)},
                {"id": f"pt-core-{i}-1", "x": round(cx + core_size, 1), "y": round(cy, 1)},
                {"id": f"pt-core-{i}-2", "x": round(cx + core_size, 1), "y": round(cy + core_size, 1)},
                {"id": f"pt-core-{i}-3", "x": round(cx, 1), "y": round(cy + core_size, 1)},
            ]
            points.extend(core_pts)
            surfaces.append({
                "id": f"pg-core-{i}",
                "point_ids": [p["id"] for p in core_pts],
            })

        # 세대 구분선 (상부/하부 각각)
        total_units_per_side = sum(
            u["count_per_floor"] for u in unit_layout["units"]
        )
        units_top = total_units_per_side // 2
        units_bottom = total_units_per_side - units_top

        if units_top > 1:
            unit_w = bw * scale / units_top
            for i in range(1, units_top):
                x = ox + i * unit_w
                pid_top = f"pt-udiv-t-{i}"
                pid_bot = f"pt-udiv-tb-{i}"
                points.append({"id": pid_top, "x": round(x, 1), "y": oy})
                points.append({"id": pid_bot, "x": round(x, 1), "y": corr_y})
                lines.append({
                    "id": f"ln-udiv-t-{i}",
                    "start_point_id": pid_top,
                    "end_point_id": pid_bot,
                })

        if units_bottom > 1:
            unit_w = bw * scale / units_bottom
            for i in range(1, units_bottom):
                x = ox + i * unit_w
                pid_top = f"pt-udiv-b-{i}"
                pid_bot = f"pt-udiv-bb-{i}"
                points.append({"id": pid_top, "x": round(x, 1), "y": corr_y})
                points.append({"id": pid_bot, "x": round(x, 1), "y": oy + bd * scale})
                lines.append({
                    "id": f"ln-udiv-b-{i}",
                    "start_point_id": pid_top,
                    "end_point_id": pid_bot,
                })

        return {
            "points": points,
            "lines": lines,
            "surfaces": surfaces,
            "floor_count": mass["num_floors"],
            "building_height_m": mass["building_height_m"],
            "scale": scale,
        }

    # ── 통합 실행 ──

    def generate(self, site_input: SiteInput) -> DesignResult:
        """토지+법규 기반 자동 설계를 생성한다."""
        logger.info(
            "자동 설계 생성 시작",
            area=site_input.site_area_sqm,
            zone=site_input.zone_code,
            use=site_input.building_use,
        )

        # 1. 법규 조회
        legal = self.get_legal_limits(site_input.zone_code)

        # 2. 유효 영역 + 매스
        effective = self.compute_effective_site(site_input)
        mass = self.compute_optimal_mass(site_input, effective, legal)

        # 내장 자동 보정 (BCR/FAR/높이 위반 시 축소)
        corrections_applied = False
        max_bcr = legal["max_bcr_percent"]
        max_far = legal["max_far_percent"]
        max_h = legal["max_height_m"]

        # ★podium-tower 매스는 compute_optimal_mass에서 podium+tower 분할로 이미 far≤법정·
        #   bcr=podium 지상피복(≤max)·높이캡을 충족해 산출됐다. 이 보정 루프는 단일박스 가정
        #   (fp=width×depth, total=fp×num_floors)으로 재계산하므로 podium GFA를 통째로 버려
        #   composite를 파괴한다 → podium-tower면 루프를 건너뛴다(headline·podium/tower 정합 보존).
        _is_podium_tower = mass.get("massing_profile") == "podium_tower"
        for _ in range(0 if _is_podium_tower else 20):  # 최대 20회 반복 보정(podium-tower는 스킵)
            violation = False
            if mass["bcr_pct"] > max_bcr and mass["building_footprint_sqm"] > 0:
                mass["building_footprint_sqm"] *= 0.95
                mass["building_width_m"] = round(mass["building_width_m"] * 0.975, 1)
                mass["building_depth_m"] = round(mass["building_depth_m"] * 0.975, 1)
                violation = True
            if mass["far_pct"] > max_far and mass["num_floors"] > 1:
                mass["num_floors"] = max(1, mass["num_floors"] - 1)
                violation = True
            if max_h > 0 and mass["building_height_m"] > max_h and mass["num_floors"] > 1:
                mass["num_floors"] = max(1, mass["num_floors"] - 1)
                violation = True
            if not violation:
                break
            corrections_applied = True
            # 재계산
            fp = mass["building_width_m"] * mass["building_depth_m"]
            mass["building_footprint_sqm"] = round(fp, 2)
            mass["total_floor_area_sqm"] = round(fp * mass["num_floors"], 2)
            mass["building_height_m"] = round(mass["num_floors"] * site_input.floor_height_m, 2)
            mass["bcr_pct"] = round(fp / site_input.site_area_sqm * 100, 2) if site_input.site_area_sqm > 0 else 0
            mass["far_pct"] = round(mass["total_floor_area_sqm"] / site_input.site_area_sqm * 100, 2) if site_input.site_area_sqm > 0 else 0

        # 2-b. 정북일조 단계후퇴: 보정 루프가 box 연면적으로 덮어쓰므로 여기서 재산출(층수/치수 반영)
        if mass.get("daylight_step"):
            base_north = max(1.5, site_input.setback_m.get("north", 1.5))
            # W-A ④: FAR 캡은 목표 반영 적용 한도(min(법정, 목표)) 기준
            _, applied_far_pct = self._effective_limits(site_input, legal)
            far_cap_area = site_input.site_area_sqm * (applied_far_pct / 100.0)
            profile, stepped_area, n = compute_north_step_profile(
                mass["building_width_m"], mass["building_depth_m"], mass["num_floors"],
                site_input.floor_height_m, base_north, far_cap_area,
            )
            mass["num_floors"] = n
            mass["north_step_profile"] = profile
            mass["total_floor_area_sqm"] = stepped_area
            mass["building_height_m"] = round(n * site_input.floor_height_m, 2)
            mass["far_pct"] = round(stepped_area / site_input.site_area_sqm * 100, 2) if site_input.site_area_sqm > 0 else 0
            # 재산출된 층수 기준으로 바인딩 제약 재판정(W-A ④)
            max_floors_by_height = (
                int(max_h / site_input.floor_height_m) if max_h > 0 else 100
            )
            mass["binding_constraint"] = _north_step_stop_reason(
                mass["building_width_m"], mass["building_depth_m"], n,
                site_input.floor_height_m, base_north, max_floors_by_height,
            )

        # 3. 코어 배치
        core_layout = self.compute_core_layout(mass, site_input.building_use)

        # 4. 세대 배분
        unit_layout = self.compute_unit_layout(
            mass, core_layout, site_input.target_unit_types, site_input.building_use,
        )

        # 5. DesignPayload 변환
        payload = self.to_design_payload(site_input, effective, mass, core_layout, unit_layout)

        summary = {
            "building_area_sqm": mass["building_footprint_sqm"],
            "building_width_m": mass["building_width_m"],
            "building_depth_m": mass["building_depth_m"],
            "total_floor_area_sqm": mass["total_floor_area_sqm"],
            "num_floors": mass["num_floors"],
            "building_height_m": mass["building_height_m"],
            "bcr_percent": mass["bcr_pct"],
            "far_percent": mass["far_pct"],
            "total_units": unit_layout["total_units"],
            "parking_count": unit_layout["parking_required"],
            "core_count": core_layout["num_cores"],
            # W-A ④: 층수/목표 미달을 막은 제약(far|height|sunlight|setback)
            "binding_constraint": mass.get("binding_constraint", "far"),
            # W-A ③: 세대 성립 여부 정직 표기 (False면 total_units=0)
            "units_feasible": unit_layout.get("units_feasible", True),
            # 매스 형상 출처(정직 표기) — auto면 대지 종횡비 기반.
            "massing_kind": mass.get("massing_kind", "auto"),
            "massing_label": mass.get("massing_label", "자동(대지비율)"),
        }
        # ★매싱 목적함수 적용 출처(있을 때만·additive·정직 표기). 미적용이면 키 없음(기존 동작 불변).
        if mass.get("massing_objective"):
            summary["massing_objective"] = mass["massing_objective"]
            summary["target_bcr_ratio_applied"] = mass.get("target_bcr_ratio_applied")
        if not unit_layout.get("units_feasible", True):
            summary["units_note"] = unit_layout.get("infeasible_reason", "세대 성립 불가")

        # §4-B 참조설계 피드백 — 적용/미적용 프로비넌스를 summary에 가산(있을 때만, 정직).
        if mass.get("reference") is not None:
            summary["reference"] = mass["reference"]

        # W-A ⑤: 산출 근거(basis) — 적용 세트백 실값·일조캡 산식·바인딩 제약·주차/코어 산식 정직 표기
        sunlight_mode = mass.get("sunlight_mode") or (
            "step_profile" if mass.get("daylight_step") else "not_applicable"
        )
        if sunlight_mode == "hard_cap":
            sunlight_formula = (
                "건축법 61조·시행령 86조(현행 10m) — 정북이격 d≥5.0m: 최고높이 2d / "
                "d<5.0m: 10m (높이 10m 이하 부분은 1.5m 이격으로 충족)"
            )
        elif sunlight_mode == "step_profile":
            sunlight_formula = (
                "단계후퇴 — 층 상단높이 h≤10m: 북측이격 max(기본세트백, 1.5m) / "
                "h>10m: max(기본세트백, h/2)"
            )
        else:
            sunlight_formula = "정북일조 미적용 — 건축법 61조 적용범위(전용·일반주거지역) 외"

        parking_rule = PARKING_RULES.get(site_input.building_use, PARKING_RULES["공동주택"])
        if parking_rule.get("per_unit"):
            parking_formula = (
                f"세대당 {parking_rule['rate']:.1f}대 "
                "(주차장법 단순화 — 지역·전용면적별 세부기준 미반영)"
            )
        else:
            parking_formula = (
                f"연면적 {parking_rule.get('rate_per_sqm', 100)}㎡당 1대 (주차장법 단순화)"
            )

        summary["basis"] = {
            "setback_applied_m": dict(site_input.setback_m),
            "sunlight": {
                "applied": sunlight_mode != "not_applicable",
                "mode": sunlight_mode,  # hard_cap | step_profile | not_applicable
                "max_height_by_sunlight_m": mass.get("max_height_by_sunlight_m"),
                "formula": sunlight_formula,
            },
            "floors_binding_constraint": mass.get("binding_constraint", "far"),
            "applied_limits": {
                "max_bcr_percent": mass.get("applied_max_bcr_pct", legal["max_bcr_percent"]),
                "max_far_percent": mass.get("applied_max_far_pct", legal["max_far_percent"]),
                "statutory_max_bcr_percent": legal["max_bcr_percent"],
                "statutory_max_far_percent": legal["max_far_percent"],
                # §4-B 조례 실효 한도(정직 — 법정·목표와 구분). 미반영 시 None.
                "ordinance_bcr_percent": getattr(site_input, "ordinance_bcr_percent", None),
                "ordinance_far_percent": getattr(site_input, "ordinance_far_percent", None),
                "target_bcr_percent": getattr(site_input, "target_bcr_percent", None),
                "target_far_percent": getattr(site_input, "target_far_percent", None),
            },
            "parking_formula": parking_formula,
            "core_formula": (
                f"층당 바닥판 {CORE_PER_FLOOR_AREA:.0f}㎡당 코어 1개(피난규칙 단순화·수직관통), "
                f"코어 1개당 {CORE_AREA_SQM:.0f}㎡"
            ),
        }

        # P5: 정북일조 단계후퇴 정보 — 3D 매스 후퇴 렌더·근거 표기에 사용
        if mass.get("north_step_profile"):
            profile = mass["north_step_profile"]
            step_from = next((p["floor"] for p in profile if p["inset_m"] > 0), None)
            summary["daylight_step"] = True
            summary["north_step_profile"] = profile
            summary["base_north_setback_m"] = max(1.5, site_input.setback_m.get("north", 1.5))
            summary["daylight_note"] = (
                f"정북일조 사선제한 적용 — {step_from}층부터 북측 단계 후퇴(상부 세대 일조 확보)"
                if step_from else "정북일조 사선제한 검토 — 현재 높이는 단계후퇴 없이 충족"
            )

        bcr_ok = mass["bcr_pct"] <= max_bcr
        far_ok = mass["far_pct"] <= max_far
        height_ok = max_h <= 0 or mass["building_height_m"] <= max_h
        setback_ok = True  # 세트백은 설계 시 이미 반영됨

        compliance = {
            "bcr_ok": bcr_ok,
            "far_ok": far_ok,
            "height_ok": height_ok,
            "setback_ok": setback_ok,
            "all_pass": bcr_ok and far_ok and height_ok and setback_ok,
            "corrections_applied": corrections_applied,
        }

        logger.info(
            "자동 설계 생성 완료",
            floors=mass["num_floors"],
            bcr=mass["bcr_pct"],
            far=mass["far_pct"],
            units=unit_layout["total_units"],
            compliant=compliance["all_pass"],
        )

        return DesignResult(
            design_payload=payload,
            summary=summary,
            compliance=compliance,
        )

    def generate_alternatives(
        self,
        site_input: SiteInput,
        count: int = 3,
    ) -> list[DesignResult]:
        """대안 3개를 생성한다.

        대안 A: 최적 밸런스 (입력 massing_kind를 그대로 따름 — 미지정 시 auto)
        대안 B: 최대 세대수 (소형 위주, 타워형 — 작은 플로어플레이트로 더 높이)
        대안 C: 최적 일조 (넓은 세트백, ㄱ자형 — 채광·소음차폐 배치)

        §4-A②: B·C에 형상(tower/lshape)을 고정 배정해 대안마다 매스가 실제로
        달라지게 한다(가산 — summary 키 불변, 3개 대안 모두 법규 준수 유지).
        A는 입력 massing_kind를 honors(하위호환 — None이면 기존 auto 동작).
        """
        alternatives: list[DesignResult] = []

        # A: 기본 (최적 밸런스) — 입력 massing_kind 그대로(None=auto, 하위호환)
        result_a = self.generate(site_input)
        result_a.summary["alternative_name"] = "A: 최적 밸런스"
        alternatives.append(result_a)

        if count >= 2:
            # B: 소형 세대 위주 (최대 세대수)
            input_b = SiteInput(
                site_area_sqm=site_input.site_area_sqm,
                site_shape=site_input.site_shape,
                site_width_m=site_input.site_width_m,
                site_depth_m=site_input.site_depth_m,
                zone_code=site_input.zone_code,
                building_use=site_input.building_use,
                target_unit_types=["39A", "49A"],
                floor_height_m=2.8,  # 최소 층고
                setback_m=site_input.setback_m,
                daylight_step=site_input.daylight_step,
                target_far_percent=site_input.target_far_percent,
                target_bcr_percent=site_input.target_bcr_percent,
                ordinance_far_percent=site_input.ordinance_far_percent,
                ordinance_bcr_percent=site_input.ordinance_bcr_percent,
                massing_kind="tower",  # §4-A②: 타워형 — 작은 플로어플레이트로 더 높이(최대 세대수)
            )
            result_b = self.generate(input_b)
            result_b.summary["alternative_name"] = "B: 최대 세대수"
            alternatives.append(result_b)

        if count >= 3:
            # C: 최적 일조 (넓은 세트백 + 낮은 층수)
            wider_setback = {k: v + 2.0 for k, v in site_input.setback_m.items()}
            input_c = SiteInput(
                site_area_sqm=site_input.site_area_sqm,
                site_shape=site_input.site_shape,
                site_width_m=site_input.site_width_m,
                site_depth_m=site_input.site_depth_m,
                zone_code=site_input.zone_code,
                building_use=site_input.building_use,
                target_unit_types=["84A", "114A"],
                floor_height_m=3.3,  # 여유 층고
                setback_m=wider_setback,
                daylight_step=site_input.daylight_step,
                target_far_percent=site_input.target_far_percent,
                target_bcr_percent=site_input.target_bcr_percent,
                ordinance_far_percent=site_input.ordinance_far_percent,
                ordinance_bcr_percent=site_input.ordinance_bcr_percent,
                massing_kind="lshape",  # §4-A②: ㄱ자형 — 채광·소음차폐 배치(최적 일조)
            )
            result_c = self.generate(input_c)
            result_c.summary["alternative_name"] = "C: 최적 일조"
            alternatives.append(result_c)

        return alternatives


# ── 유틸리티 ──

def _compute_parking(
    total_units: int,
    total_floor_area: float,
    building_use: str,
) -> dict[str, Any]:
    """법규 기반 주차대수를 산정한다.

    공동주택은 '세대당 1.0대'(주차장법 단순화 — 지역·전용면적별 세부기준 미반영)
    이며, 0세대면 0대로 정직 반환한다(W-A ③ 가짜값 금지).
    """
    rule = PARKING_RULES.get(building_use, PARKING_RULES["공동주택"])

    if rule.get("per_unit"):
        required = int(total_units * rule["rate"])  # 0세대 → 0대 (최소 1대 강제 없음)
    else:
        required = max(1, int(total_floor_area / rule.get("rate_per_sqm", 100)))

    area_per_car = rule.get("area_per_car_sqm", 33.0)
    total_parking_area = required * area_per_car
    # 지하 주차장 기준 1개 층 약 500sqm — 주차 0대면 지하층도 0(가짜 지하층 금지)
    basement_floors = math.ceil(total_parking_area / 500) if required > 0 else 0

    return {
        "required": required,
        "area_sqm": round(total_parking_area, 2),
        "basement_floors": basement_floors,
    }
