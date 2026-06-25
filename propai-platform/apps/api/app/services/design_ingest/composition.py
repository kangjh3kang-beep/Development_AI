"""설계안 조합(composition) 엔진 — 검색된 도면을 부지 법적 한도에 맞춰 선택·스케일·검증.

'검색+조합'의 조합 절반(v1 토대). 실제 폴리곤 배치(CAD 기하)는 후속이며, 본 단계는
**선택 + 법적 envelope 스케일 + 세대/주차 추정 + 인허가(한도) 게이트 + 랭킹**으로
buildable·compliant 한 Top-N 설계 초안을 만든다. 모든 추정은 warnings로 정직 고지하며,
법적 한도 미상이면 compliant=False(추정 금지). 용적률은 실효(조례) 우선 — far_source 표기.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from app.services.design_ingest.design_spec import DRAWING_TYPE_META

# 건물 설계 권장 핵심 분야 — 이 분야 도면이 없으면 세트 불완전(정직 고지·업로드 유도).
_CORE_DISCIPLINES = ("건축", "구조", "전기", "기계설비", "급배수위생", "소방")

# content_hash(SHA-256 hex) 형식 가드 — object_store/search_service와 동일 계약(오염값 차단).
_HEX_HASH = re.compile(r"[0-9a-f]{16,128}")


def _valid_hash(v: object) -> str | None:
    return v if isinstance(v, str) and _HEX_HASH.fullmatch(v) else None

# 세대수 추정 시 전용률(연면적→전용 환산, 대략) — 추정치임을 명시.
_DEFAULT_EFFICIENCY = 0.75
# 연면적 활용률 정직고지 임계 — est_gfa가 법적 최대연면적의 이 비율 미만이면 '보수추정' 경고.
_GFA_UNDERUSE_RATIO = 0.7
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
    zone_name: str | None = None         # 한글 용도지역명(23종 fail-closed 한도 조회 키)
    width_m: float | None = None
    depth_m: float | None = None
    legal_bcr_pct: float | None = None   # 건폐율 한도(%)
    legal_far_pct: float | None = None   # 용적률 한도(%)
    legal_setback_m: float | None = None # 최소 이격거리(m) — 건물 배치 폴리곤 산출용
    legal_height_m: float | None = None  # 절대 높이한도(m) — 매스 층수 캡(미상 None=무캡)
    height_source: str = "unknown"       # ordinance(조례) | statutory(법정) | unknown
    bcr_source: str = "unknown"          # 건폐율 출처(far_source와 분리 표기)
    far_source: str = "unknown"          # ordinance(실효) | statutory(법정) | unknown
    floor_height_m: float = 3.0
    avg_unit_area_sqm: float = 84.0      # 세대 추정용 평균 평형(전용 기준 입력)
    unit_types: list[str] | None = None  # 평형 믹스(예: ["59A","84A"]) — 평형별 분해 산출용
    reference_mass: dict | None = None    # 유사사례 매스 힌트(derive_reference_mass_hint·{aspect,...})
    building_use_kr: str = "공동주택"     # 주차 산정용 표준 분류(PARKING_RULES 키)
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
    def max_floors_by_height(self) -> int | None:
        """절대 높이한도(m) → 최대 층수. 높이한도 미상이면 None(무캡·정직)."""
        if self.legal_height_m is None or self.legal_height_m <= 0 or self.floor_height_m <= 0:
            return None
        return max(1, int(self.legal_height_m // self.floor_height_m))

    @property
    def max_floors_est(self) -> int | None:
        fp = self.buildable_footprint_sqm
        gfa = self.max_gfa_sqm
        if not fp or not gfa:
            return None
        far_floors = max(1, int(gfa // fp))
        h_floors = self.max_floors_by_height
        # 높이한도가 있으면 FAR·높이 중 더 제약적인 쪽(min)으로 캡(일조/절대높이 준수·정직).
        return min(far_floors, h_floors) if h_floors else far_floors


@dataclass
class CompositionCandidate:
    """조합 결과 1건(설계 초안)."""

    selected: dict[str, str]            # drawing_type -> point_id
    sources: list[dict] = field(default_factory=list)  # 조합 출처(근거) — 종류·유사도·hash·면적
    primary_drawing_type: str = "unknown"
    primary_content_hash: str | None = None  # 주 도면 content_hash — 피드백(👍👎) 신호 연결키(down율 식별)
    scale_factor: float | None = None
    estimated_gfa_sqm: float | None = None       # 참조평면 기준 보수추정(achievable 하한 쪽)
    max_envelope_gfa_sqm: float | None = None    # 법적 최대 envelope 연면적(상한) — 부지 잠재력 명시
    estimated_floors: int | None = None
    estimated_units: int | None = None
    unit_breakdown: list[dict] | None = None  # 평형별 분해(type·area·count_per_floor·total·ratio_pct)
    unit_efficiency: float | None = None       # 적용 전용률(평형/유형 기반·상수 탈피 시 산출 근거)
    sunlight_profile: dict | None = None       # 정북일조 단계후퇴 envelope(층별 북측후퇴·일조준수 연면적)
    reference_hint: dict | None = None         # 유사사례 매스 힌트(종횡비·근거) — 검색 환류(피드백 시딩)
    estimated_parking: int | None = None    # = parking_required(하위호환 별칭)
    parking_required: int | None = None     # 법정 부설주차 대수(주차장법 단순화)
    parking_area_sqm: float | None = None   # 소요 주차면적(대당 33㎡)
    parking_basement_floors: int | None = None  # 지하주차 추정 층수(부지 footprint 기준 우선)
    parking_feasible: bool | None = None    # 주차 배치 현실성(지하층 과다 아님). 미상 None
    parking_layout: dict | None = None      # 주차 자동배치도(스키매틱 — 층당대수·소요층수·좌표)
    placement: dict | None = None           # 건물 배치 폴리곤(부지경계 내 이격 적용·중앙 배치 좌표)
    disciplines_covered: list[str] = field(default_factory=list)  # 도면 세트가 포함한 분야
    missing_disciplines: list[str] = field(default_factory=list)  # 권장 핵심분야 중 미확보(정직 갭)
    compliant: bool = False
    score: float = 0.0
    score_breakdown: dict | None = None  # 점수 산출 근거(적합도·완성도·적법 가중) — 랭킹 투명성(근거)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "selected": self.selected,
            "sources": list(self.sources),
            "primary_drawing_type": self.primary_drawing_type,
            "primary_content_hash": self.primary_content_hash,
            "disciplines_covered": list(self.disciplines_covered),
            "missing_disciplines": list(self.missing_disciplines),
            "scale_factor": self.scale_factor,
            "estimated_gfa_sqm": self.estimated_gfa_sqm,
            "max_envelope_gfa_sqm": self.max_envelope_gfa_sqm,
            "estimated_floors": self.estimated_floors,
            "estimated_units": self.estimated_units,
            "unit_breakdown": self.unit_breakdown,
            "unit_efficiency": self.unit_efficiency,
            "sunlight_profile": self.sunlight_profile,
            "reference_hint": self.reference_hint,
            "estimated_parking": self.estimated_parking,
            "parking_required": self.parking_required,
            "parking_area_sqm": self.parking_area_sqm,
            "parking_basement_floors": self.parking_basement_floors,
            "parking_feasible": self.parking_feasible,
            "parking_layout": self.parking_layout,
            "placement": self.placement,
            "compliant": self.compliant,
            "score": self.score,
            "score_breakdown": self.score_breakdown,
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


# 주차 배치 가능성 — 지하주차 추정 층수가 이보다 많으면 비현실(지상주차·필로티·대지 재검토).
_MAX_REASONABLE_BASEMENT = 5


def map_building_use_kr(building_use: str | None) -> str:
    """건축 용도 문자열 → 주차장법 산정용 표준 분류(PARKING_RULES 키). 미상이면 공동주택."""
    s = (building_use or "").strip().lower()
    if any(k in s for k in ("apt", "housing", "공동주택", "아파트", "주거", "resid")):
        return "공동주택"
    if any(k in s for k in ("근린", "근생", "retail", "commerc", "상가", "판매")):
        return "근린생활시설"
    if any(k in s for k in ("업무", "office", "오피스")):
        return "업무시설"
    return "공동주택"


def compute_parking_design(
    site: SiteContext, est_units: int | None, est_gfa: float | None
) -> dict:
    """법정 부설주차 산정 + 부지 footprint 기준 지하주차 층수·배치 가능성.

    주차 대수/면적은 AutoDesignEngine 정본(`_compute_parking`, 주차장법 단순화·대당 33㎡)을
    재사용한다(DRY). 지하주차 층수는 일반 기준(500㎡/층)과 부지 footprint 기준을 함께 내고,
    footprint 기준(지하 1개 층 ≈ 건축면적)으로 배치 현실성을 판정한다. 미상값은 None(정직).
    반환: {required, area_sqm, basement_floors, basement_floors_site, feasible, warnings}
    """
    out: dict = {
        "required": None, "area_sqm": None, "basement_floors": None,
        "basement_floors_site": None, "feasible": None, "warnings": [],
    }
    if est_gfa is None and not est_units:
        return out  # 산정 근거 없음(추정 금지)
    try:
        from app.services.cad.auto_design_engine import _compute_parking
    except Exception:  # noqa: BLE001
        out["warnings"].append("주차 산정 엔진 미연동 — 주차 미산정")
        return out

    pk = _compute_parking(int(est_units or 0), float(est_gfa or 0.0), site.building_use_kr)
    out["required"] = pk["required"]
    out["area_sqm"] = pk["area_sqm"]
    out["basement_floors"] = pk["basement_floors"]  # 일반 500㎡/층 기준

    fp = site.buildable_footprint_sqm
    if pk["required"] > 0 and fp and fp > 0:
        bf_site = math.ceil(pk["area_sqm"] / fp)  # 부지 건축면적 기준 지하 층수
        out["basement_floors_site"] = bf_site
        out["feasible"] = bf_site <= _MAX_REASONABLE_BASEMENT
        if not out["feasible"]:
            out["warnings"].append(
                f"주차 확보에 지하 {bf_site}층 필요 — 비현실(지상주차·필로티·대지 재검토)"
            )
    elif pk["required"] == 0:
        out["feasible"] = True  # 주차 0대 = 배치 부담 없음(정직)
    else:
        # 주차 필요하나 건폐율 한도(footprint) 미상 → 배치 현실성 미판정(정직 고지·None 유지).
        out["warnings"].append("건폐율 한도 미상 — 주차 배치 현실성 미판정(지하주차 층수 미산)")
    return out


# 표준 직각주차 모듈(주차장법 일반형) — 단위 m.
_STALL_W = 2.5          # 주차구획 폭(일반형)
_STALL_L = 5.0          # 주차구획 길이
_AISLE = 6.0            # 직각주차 차로 너비
_BAY_DEPTH = _STALL_L * 2 + _AISLE   # 복렬(양면주차+중앙차로) 베이 깊이 = 16.0m
_LAYOUT_STALL_CAP = 300              # 배치 좌표 페이로드 상한(시각화용)


def compute_parking_layout(site: SiteContext, required_stalls: int | None) -> dict | None:
    """footprint에 표준 직각주차 모듈을 자동 패킹 → 층당 대수·소요층수·대표층 배치 좌표(스키매틱).

    rectangular footprint 가정(부지 width/depth 비율 반영, 미상 시 정사각). 램프·기둥·구조·경사
    미반영의 개략 자동배치다(정직 고지). footprint/대수 미상이면 None.
    """
    fp = site.buildable_footprint_sqm
    if not fp or fp <= 0 or not required_stalls or required_stalls <= 0:
        return None
    if site.width_m and site.depth_m and site.width_m > 0 and site.depth_m > 0:
        fw = round(math.sqrt(fp * (site.width_m / site.depth_m)), 1)
    else:
        fw = round(math.sqrt(fp), 1)
    fd = round(fp / fw, 1) if fw > 0 else 0.0

    # 폭 방향 끝단 동선(진입·회전) 1개 차감해 보수화(과대산정 방지·개략 상한).
    stalls_per_row = max(0, int((fw - _AISLE) // _STALL_W))
    bays = int(fd // _BAY_DEPTH)
    stalls_per_floor = bays * 2 * stalls_per_row
    note = "스키매틱 자동배치(직각주차 2.5×5.0m·차로 6.0m) — 램프·기둥·구조 미반영(개략)"
    if stalls_per_floor <= 0:
        return {
            "stalls_per_floor": 0, "floors_for_parking": None,
            "footprint_w_m": fw, "footprint_d_m": fd, "stalls": [],
            "total_required": required_stalls,
            "note": "footprint이 주차 1베이(약 16m)보다 작아 자동배치 불가 — 기계식/지하 검토",
        }

    floors = math.ceil(required_stalls / stalls_per_floor)
    # 대표 1개 층 배치 좌표(상한 캡).
    cap = min(required_stalls, stalls_per_floor, _LAYOUT_STALL_CAP)
    stalls: list[dict] = []
    for b in range(bays):
        y0 = b * _BAY_DEPTH
        for side in (0, 1):  # 베이 양쪽 2열(복렬)
            y = round(y0 + (0.0 if side == 0 else _STALL_L + _AISLE), 1)
            for c in range(stalls_per_row):
                if len(stalls) >= cap:
                    break
                stalls.append({"x": round(c * _STALL_W, 1), "y": y, "w": _STALL_W, "l": _STALL_L})
    return {
        "stalls_per_floor": stalls_per_floor,
        "floors_for_parking": floors,
        "footprint_w_m": fw, "footprint_d_m": fd,
        "stalls": stalls, "total_required": required_stalls, "note": note,
    }


# 다동(단지) 배치 추정 상수 — 스키매틱(동수·동간거리·일조 정밀계획은 별도).
_MAX_BLOCK_FP_SQM = 1200.0   # 동 1개 표준 plate 면적 상한(板상형 대형동 가정) — 초과 시 분동
_MAX_DONG = 12               # 동수 상한(스키매틱 과밀 방지)
# D-A 교정: 동간거리 6m '고정'은 채광 인동간격(건축법 시행령 §86② 0.8H) 미달이 잦다.
# 동간거리는 건물 높이 기반(0.8H)으로 산출하되, 최소 6m는 하한으로 둔다(소형·저층 폴백).
_DONG_GAP_MIN_M = 6.0        # 동간거리 하한(저층·높이 미상 폴백)
_DONG_GAP_RATIO = 0.8        # 채광 인동간격 비율(건축법 시행령 §86② 0.8H)
# D-A 교정: 1동(板상형) 최대 길이 게이트. 80m 초과 단일 매스는 비현실(피난·구조·일조) →
# 길이 초과 시 분동(동수 증가)으로 강제한다(149m 단일매스 근본 차단).
_MAX_DONG_LENGTH_M = 80.0
_DONG_PLATE_RATIO = 2.5      # 동 板상형 폭:깊이 비(개략)


def _dong_gap_m(building_height_m: float | None) -> float:
    """동간거리(채광 인동간격) — 건축법 시행령 §86② 0.8H. 높이 미상이면 하한 6m(정직 폴백).

    solar_envelope_service의 0.8H 산식과 동일(드리프트 방지·DRY). 결과는 최소 6m로 클램프.
    """
    if not building_height_m or building_height_m <= 0:
        return _DONG_GAP_MIN_M
    return round(max(_DONG_GAP_MIN_M, _DONG_GAP_RATIO * building_height_m), 1)


def _layout_dong_blocks(
    origin: float, region_w: float, region_d: float, total_fp: float, n: int, gap: float
) -> list[dict] | None:
    """가용영역(원점 offset=origin·크기 region_w×region_d)에 n개 동을 그리드 배치(부지 좌표계).

    동 합계 footprint=total_fp(건폐율 보존), 동간거리 gap. 板상형 비율로 셀 내 중앙 배치.
    동간거리·동크기가 셀에 안 들어가면 None(호출자 단일동 폴백). n<=1이면 None(단일 경로 사용).
    """
    if n <= 1 or region_w <= 0 or region_d <= 0 or total_fp <= 0:
        return None
    cols = max(1, math.ceil(math.sqrt(n)))
    rows = max(1, math.ceil(n / cols))
    cell_w = (region_w - (cols - 1) * gap) / cols
    cell_d = (region_d - (rows - 1) * gap) / rows
    if cell_w <= 0 or cell_d <= 0:
        return None
    per_fp = total_fp / n
    bd = min(cell_d, max(2.0, math.sqrt(per_fp / _DONG_PLATE_RATIO)))
    bw = min(cell_w, (per_fp / bd) if bd > 0 else cell_w)
    if bw <= 0 or bd <= 0:
        return None
    right = origin + region_w   # 가용영역 우변/상변 — 라운딩 후 초과 방지(이격선 보장).
    top = origin + region_d
    blocks: list[dict] = []
    for i in range(n):
        r, c = divmod(i, cols)
        cx = origin + c * (cell_w + gap)
        cy = origin + r * (cell_d + gap)
        bxr = round(cx + (cell_w - bw) / 2, 1)
        byr = round(cy + (cell_d - bd) / 2, 1)
        blocks.append({
            "x": bxr, "y": byr,
            "w": round(min(bw, right - bxr), 1),   # 영역 경계 클램프(라운딩 드리프트 제거)
            "d": round(min(bd, top - byr), 1),
        })
    return blocks


def compute_placement(site: SiteContext) -> dict | None:
    """부지 경계 내 이격 적용 건물 배치 폴리곤(스키매틱·좌표). 원점 (0,0)=부지 좌하단.

    부지 치수(width/depth) 알려지면 사용, 미상이면 면적√ 정사각 가정(개략 고지). 이격거리만큼
    경계에서 안으로 들인 가용영역에 건폐율(BCR) footprint 크기의 건물 사각형을 중앙 배치한다.
    ★이격이 건폐율보다 배치를 더 제약하면(가용영역<BCR footprint) 실배치<BCR로 정직 플래그.
    램프/건축선/대지형상/맹지 미반영의 개략 배치다(정직 고지). 면적 미상이면 None.
    """
    area = site.area_sqm
    if not area or area <= 0:
        return None
    notes: list[str] = []
    if site.width_m and site.depth_m and site.width_m > 0 and site.depth_m > 0:
        site_w, site_d = round(site.width_m, 1), round(site.depth_m, 1)
        # 입력 치수(폭×깊이)와 대지면적이 크게 어긋나면 정직 고지(경고 오귀속 방지).
        if abs(site_w * site_d - area) / area > 0.15:
            notes.append(
                f"입력 부지치수(폭×깊이={round(site_w * site_d)}㎡)와 "
                f"대지면적({round(area)}㎡) 불일치 — 치수 확인 필요"
            )
    else:
        side = round(math.sqrt(area), 1)
        site_w = site_d = side
        notes.append("부지 치수 미상 — 면적 기준 정사각 가정(개략)")

    _sb = site.legal_setback_m
    has_setback = _sb is not None and _sb > 0
    setback = round(_sb, 2) if (_sb is not None and _sb > 0) else 1.0
    if not has_setback:
        notes.append("이격거리 미상 — 1.0m 가정(정밀 확인 필요)")

    region_w = round(max(0.0, site_w - 2 * setback), 1)
    region_d = round(max(0.0, site_d - 2 * setback), 1)
    region_area = round(region_w * region_d, 1)
    base = {"site": {"w": site_w, "d": site_d}, "setback_m": setback,
            "buildable_region_sqm": region_area, "notes": notes}
    if region_w <= 0 or region_d <= 0:
        return {**base, "building": None, "setback_binds": True,
                "note": "이격 적용 시 가용영역 없음 — 부지 과소 또는 이격 과대(배치 불가)"}

    target_fp = site.buildable_footprint_sqm  # BCR footprint(한도 미상이면 None)
    actual_fp = min(target_fp, region_area) if (target_fp and target_fp > 0) else region_area
    setback_binds = bool(target_fp and target_fp > region_area + 0.5)
    if setback_binds:
        notes.append(
            f"이격거리가 건폐율보다 배치 제약 — 실배치 {round(region_area)}㎡ "
            f"< BCR {round(target_fp or 0)}㎡"
        )

    # 가용영역 비율 유지하며 actual_fp 크기로 축소, 가용영역 중앙 배치.
    scale = min(1.0, math.sqrt(actual_fp / region_area)) if region_area > 0 else 0.0
    bldg_w = round(region_w * scale, 1)
    bldg_d = round(region_d * scale, 1)
    if bldg_w <= 0 or bldg_d <= 0:   # 극소 부지 — 라운딩 후 0크기면 0면적 '가짜 건물' 금지(정직)
        return {**base, "building": None, "setback_binds": True,
                "note": "이격 적용 시 유효 배치영역 없음(배치 불가·극소 부지)"}
    bx = round((site_w - bldg_w) / 2, 1)   # 부지 중앙 배치
    by = round((site_d - bldg_d) / 2, 1)

    # 동간거리(채광 인동간격 0.8H·건축법 시행령 §86②) — 건물 높이 기반. 높이는 site의
    # 추정 층수×층고로 산출(미상이면 하한 6m 폴백·정직). solar 0.8H 산식과 동일(DRY).
    est_floors_for_h = site.max_floors_est or 0
    bldg_height_m = (est_floors_for_h * site.floor_height_m) if est_floors_for_h > 0 else None
    dong_gap = _dong_gap_m(bldg_height_m)

    # 다동(단지) 배치 추정 — 공동주택이고 ① footprint가 1동 상한 초과 ② 또는 1동 板상형 길이가
    # 80m 초과(D-A 게이트)면 분동(板상형 그리드). 그 외(비주거·소형)는 단일 동(=building rect).
    use_kr = site.building_use_kr or ""
    n_dong = 1
    if use_kr == "공동주택" and actual_fp > 0:
        # ① 면적 기준 분동
        n_by_fp = math.ceil(actual_fp / _MAX_BLOCK_FP_SQM) if actual_fp > _MAX_BLOCK_FP_SQM else 1
        # ② 1동 길이(板상형 폭=√(per_fp×ratio)) ≤ 80m 게이트 → 초과 시 동수 증가.
        #    per_fp = actual_fp/n, 폭 = √(per_fp×ratio) ≤ MAX → n ≥ actual_fp×ratio / MAX².
        n_by_len = math.ceil(actual_fp * _DONG_PLATE_RATIO / (_MAX_DONG_LENGTH_M ** 2))
        n_dong = min(_MAX_DONG, max(1, n_by_fp, n_by_len))
    blocks = _layout_dong_blocks(setback, region_w, region_d, actual_fp, n_dong, dong_gap)
    if not blocks:                          # 단일 동(또는 그리드 불가 폴백)
        blocks = [{"x": bx, "y": by, "w": bldg_w, "d": bldg_d}]
        n_dong = 1
    else:
        # 분동 후에도 단일 동 길이가 80m를 넘으면(그리드 셀 제약으로 분동 불가) 정직 경고.
        _max_len = max((blk.get("w", 0.0) for blk in blocks), default=0.0)
        if _max_len > _MAX_DONG_LENGTH_M:
            notes.append(
                f"1동 길이 {_max_len:.0f}m가 권장 상한 {_MAX_DONG_LENGTH_M:.0f}m 초과 — "
                "피난·구조·일조상 추가 분동 권장(가용영역 제약으로 자동 분동 한계)"
            )
    if n_dong > 1:
        notes.append(
            f"단지 배치 개략 추정: {n_dong}개 동·동간거리 {dong_gap}m"
            f"(채광 인동간격 0.8H·건축법 시행령 §86②·동수·일조 정밀계획 별도)"
            " — blocks는 시각 스키매틱(동간공지로 합계<건폐율 가능)·면적/GFA는 건폐율 기준"
        )
    return {
        **base,
        # area_sqm은 BCR footprint(actual_fp)로 캡 — w·d 개별 반올림이 곱에서 BCR을 초과(드리프트)
        # 하지 않게 정직 클램프(스키매틱 rect는 유지, 보고 면적은 법적 footprint 이내).
        "building": {"x": bx, "y": by, "w": bldg_w, "d": bldg_d,
                     "area_sqm": round(min(bldg_w * bldg_d, actual_fp), 1)},
        "blocks": blocks,                   # 동별 배치 사각형(단일동이면 1개=building)
        "dong_count": n_dong,
        "gap_m": dong_gap if n_dong > 1 else 0.0,
        "max_dong_length_m": round(max((blk.get("w", 0.0) for blk in blocks), default=0.0), 1),
        "setback_binds": setback_binds,
        "note": "스키매틱 배치(이격 적용·중앙) — 건축선/대지형상/맹지/램프 미반영(개략)",
    }


# 세대 순면적률(전용+공용 분배 추정) — 연면적 중 세대 배치 가능 순면적 비율(코어·복도 차감 근사).
# 평형 분해 시 층면적이 아닌 '연면적×이 비율'을 세대 배치 풀로 본다(상수 0.75 탈피의 보조 근거).
_NET_AREA_RATIO = 0.82


def compute_unit_breakdown(
    per_floor_net_sqm: float | None, floors: int | None, unit_types: list[str] | None
) -> dict | None:
    """평형 믹스를 cad UNIT_TYPES 그리디 라운드로빈으로 분해(정본 재사용·DRY).

    AutoDesignEngine.compute_unit_layout의 세대 배분 알고리즘(소형 우선 라운드로빈·층당 순면적
    내에서만 배치, 가짜 1세대 강제 금지)과 동일한 산식으로 평형별 세대수·구성%를 낸다.
    전용률은 평형 면적 가중 평균(공급=전용/전용률 가정)으로 산출 → 상수 0.75 탈피.
    per_floor_net/층수/평형 미상이거나 세대 0이면 None(무가짜세대·정직).
    반환: {units:[{type,area_sqm,count_per_floor,total_count,ratio_pct}], total_units, efficiency}
    """
    if not per_floor_net_sqm or per_floor_net_sqm <= 0 or not floors or floors <= 0:
        return None
    try:
        from app.services.cad.auto_design_engine import UNIT_TYPES
    except Exception:  # noqa: BLE001 — 정본 미연동 시 평형 분해 생략(정직)
        return None
    types = [t for t in (unit_types or []) if t in UNIT_TYPES]
    if not types:
        return None  # 인식 가능한 평형 없음 — 분해 생략(상수 폴백은 호출자 책임)

    unique_types = list(dict.fromkeys(types))                              # 입력순 중복제거
    greedy_order = sorted(unique_types, key=lambda t: UNIT_TYPES[t])       # 소형 우선
    counts: dict[str, int] = {t: 0 for t in unique_types}
    remaining = float(per_floor_net_sqm)
    placed = True
    while placed:                                                          # 라운드로빈 1세대씩
        placed = False
        for ut in greedy_order:
            if UNIT_TYPES[ut] <= remaining:
                counts[ut] += 1
                remaining -= UNIT_TYPES[ut]
                placed = True

    units: list[dict] = []
    total_units = 0
    for ut in unique_types:
        cpf = counts[ut]
        if cpf <= 0:
            continue  # 성립 불가 유형은 0세대(가짜 1세대 강제 금지)
        total = cpf * int(floors)
        units.append({
            "type": ut, "area_sqm": UNIT_TYPES[ut],
            "count_per_floor": cpf, "total_count": total,
        })
        total_units += total
    if total_units == 0:
        return None  # 순면적이 최소 평형보다 작아 세대 성립 불가 — 무가짜세대(정직)
    # 구성%(전용 면적 가중) 부착.
    total_area = sum(u["area_sqm"] * u["total_count"] for u in units) or 1.0
    for u in units:
        u["ratio_pct"] = round(u["area_sqm"] * u["total_count"] / total_area * 100, 1)
    # 전용률 = 전용면적 가중 평균 / (가정 공급면적). 평형 면적 자체가 전용 기준 입력이므로,
    # 공급 환산 효율은 평형이 클수록 소폭 높다는 통상 패턴을 반영(소형 0.72 ~ 대형 0.80 선형 근사).
    avg_unit = total_area / sum(u["total_count"] for u in units)
    efficiency = round(min(0.82, max(0.70, 0.70 + (avg_unit - 39.0) / 75.0 * 0.12)), 3)
    return {"units": units, "total_units": total_units, "efficiency": efficiency}


# 정북일조(건축법 61조) 적용 용도지역 — 전용·일반주거지역만(준주거·상업·공업 제외).
# 입력이 한글 용도지역명·코드 어느 쪽이든 '주거' 식별로 판정(detect_special_parcel류 토큰).
_SUNLIGHT_ZONE_CODES = frozenset({"1R", "2R", "3R"})


def _is_sunlight_zone(site: SiteContext) -> bool:
    """정북일조 사선제한(건축법 61조) 적용 대상 — 전용·일반주거지역. 준주거·상업·공업 제외."""
    code = (site.zone_code or "").strip()
    if code in _SUNLIGHT_ZONE_CODES:
        return True
    name = (site.zone_name or "").replace(" ", "")
    # '준주거'·상업·공업은 제외, '전용주거'·'일반주거'만 일조 대상(국토계획법 체계).
    if "준주거" in name:
        return False
    return ("전용주거" in name) or ("일반주거" in name)


def _sunlight_envelope(
    site: SiteContext,
    *,
    bldg_w: float,
    bldg_d: float,
    far_floors: int,
    max_gfa: float,
) -> dict | None:
    """정북일조 단계후퇴(건축법 61조)를 매스 GFA/층수에 반영(cad 정본 재사용·DRY).

    AutoDesignEngine의 `compute_north_step_profile`(시행령 86조 현행 10m/h2 산식)을 그대로 호출해,
    참조평면 footprint(폭×깊이) 기준 상부층 북측 후퇴로 줄어든 '일조 준수 연면적·층수'를 산출한다.
    주거지역(일조 대상)에서만 호출하며, 그 결과 연면적·층수가 단순 FAR 산정보다 작으면(일조가
    binding) 그 값으로 매스를 보정한다(근거: 건축법 일조 정북사선). 비주거·산정불가는 None.
    반환: {floors, gfa, profile, base_north_m, binding} 또는 None(미적용·산정불가).
    """
    if not _is_sunlight_zone(site) or bldg_w <= 0 or bldg_d <= 0 or far_floors <= 0:
        return None
    try:
        from app.services.cad.auto_design_engine import compute_north_step_profile
    except Exception:  # noqa: BLE001 — 엔진 미연동 시 일조 미반영(정직·무캡)
        return None
    # 설계 북측 세트백 = 법정 최소 이격(없으면 정북 기본 1.5m). cad와 동일 base 의미.
    base_north = max(1.5, site.legal_setback_m or 0.0)
    profile, sun_gfa, sun_floors = compute_north_step_profile(
        building_w=bldg_w, building_d=bldg_d, max_floors=far_floors,
        floor_height_m=site.floor_height_m, base_north_m=base_north,
        max_total_floor_area=max_gfa,
    )
    binding = sun_floors < far_floors  # 일조가 FAR 산정 층수보다 더 제약하면 binding
    return {
        "floors": sun_floors,
        "gfa": round(min(sun_gfa, max_gfa), 2),
        "profile": profile,
        "base_north_m": round(base_north, 2),
        "binding": binding,
    }


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

    # 건물 배치 폴리곤은 부지 단위(모든 후보 공유) — 1회 산출 후 각 후보에 부착.
    placement = compute_placement(site)

    candidates: list[CompositionCandidate] = []
    for fp in primaries[: max(1, top_n)]:
        warnings: list[str] = list(site.warnings)  # 부지/한도 경고 승계(정직 전파)
        primary_type = _g(fp, "drawing_type") or "unknown"
        selected = {primary_type: str(_g(fp, "point_id") or "")}
        source_matches: dict[str, dict] = {primary_type: fp}  # 조합 출처(근거) — 종류별 채택 도면
        # ★분야별 도면 세트 조합 — 매칭된 모든 도면종류의 최고점 1건씩 첨부(by_type 이미 점수 정렬).
        #   건축 평면뿐 아니라 구조·전기·기계·위생·소방·토목·조경·통신 도면을 코퍼스에서 끌어모은다.
        for t, lst in by_type.items():
            if t and t != "unknown" and t not in selected and lst:
                selected[t] = str(_g(lst[0], "point_id") or "")
                source_matches[t] = lst[0]
        # 조합 출처 목록(어느 코퍼스 도면에서 왔는지) — 전역 '근거 제공' 원칙(provenance)
        sources = [
            {
                "drawing_type": t,
                "point_id": str(_g(m, "point_id") or ""),
                "score": round(float(_g(m, "score") or 0.0), 4),  # 검색 유사도
                "content_hash": _valid_hash(_g(m, "content_hash")),
                "area_sqm": _g(m, "total_area_sqm"),
            }
            for t, m in source_matches.items()
        ]

        # 분야 커버리지 — 세트가 포함한 분야 + 권장 핵심분야 중 미확보(정직 갭 고지).
        disciplines = sorted({
            DRAWING_TYPE_META.get(t, {}).get("discipline", "기타")
            for t in selected if t != "unknown"
        })
        missing_disc = [d for d in _CORE_DISCIPLINES if d not in disciplines]
        if missing_disc:
            warnings.append(
                f"분야별 도면 미확보: {', '.join(missing_disc)} — 해당 분야 도면 업로드 시 세트 보강"
            )

        fp_area = _g(fp, "total_area_sqm")
        scale = _scale_factor(float(fp_area) if fp_area else None, footprint)
        per_floor = None
        if fp_area and footprint:
            per_floor = min(float(fp_area), footprint)
        elif footprint:
            per_floor = footprint
            warnings.append("평면 면적 미상 — 부지 footprint로 층면적 추정")

        # ★유사사례 피드백 시딩(P0-2) — derive_reference_mass_hint(orchestrator가 주입)의 종횡비를
        #   매스 footprint 형상에 환류한다. 검색결과가 매스 생성에 실제로 영향(아래 일조 envelope의
        #   폭/깊이 산출에 사용)을 미치게 해, 코사인 검색이 '조회'에 그치지 않고 매스에 시딩되게 한다.
        reference_hint = None
        _ref = site.reference_mass if isinstance(site.reference_mass, dict) else None
        _ref_aspect = None
        if _ref and _ref.get("used") and isinstance(_ref.get("hint"), dict):
            try:
                _a = float(_ref["hint"].get("aspect") or 0.0)
                if _a > 0:
                    _ref_aspect = _a
                    reference_hint = _ref["hint"]
                    _basis = reference_hint.get("basis") or f"유사사례 종횡비 {_a:.2f} 매스 시딩"
                    warnings.append(f"유사사례 피드백 반영 — {_basis}(검색 환류)")
            except (TypeError, ValueError):
                reference_hint = None

        # 층수·연면적(법적 한도 클램프).
        est_floors = est_gfa = est_units = max_envelope_gfa = None
        sunlight_profile = unit_breakdown = unit_efficiency = None
        if per_floor and max_gfa:
            est_floors = max(1, int(max_gfa // per_floor))
            if site.max_floors_est:
                est_floors = min(est_floors, site.max_floors_est)
            est_gfa = round(min(max_gfa, per_floor * est_floors), 2)

            # ★정북일조(건축법 61조) 매스 envelope 반영 — 주거지역에서 상부층 북측 단계후퇴로
            #   줄어드는 일조 준수 연면적/층수를 cad 정본(compute_north_step_profile)으로 산출.
            #   일조가 binding이면(FAR 산정보다 작으면) GFA·층수를 일조 준수치로 보정(정직).
            #   매스 footprint 폭/깊이는 ①유사사례 종횡비(시딩) ②배치 폴리곤 ③per_floor 정사각 순.
            _bldg = (placement or {}).get("building") if placement else None
            if _ref_aspect and per_floor > 0:
                # 유사사례 종횡비(전면/깊이) 적용 — depth=√(면적/aspect), width=aspect×depth.
                _bd = round(math.sqrt(per_floor / _ref_aspect), 1)
                _bw = round(per_floor / _bd, 1) if _bd > 0 else round(math.sqrt(per_floor), 1)
            elif _bldg and _bldg.get("w") and _bldg.get("d"):
                _bw, _bd = float(_bldg["w"]), float(_bldg["d"])
            else:
                _side = math.sqrt(per_floor) if per_floor > 0 else 0.0
                _bw = _bd = round(_side, 1)
            sun = _sunlight_envelope(
                site, bldg_w=_bw, bldg_d=_bd, far_floors=est_floors, max_gfa=max_gfa
            )
            if sun:
                sunlight_profile = sun
                # 일조가 층수를 더 제약하면(binding) 층수를 보정. 그리고 상부층 북측 단계후퇴로
                # 줄어든 일조준수 연면적(sun["gfa"])이 평탄 추정(est_gfa)보다 작으면 GFA도 보정
                # — 사선한도를 매스 GFA에 실제로 반영(근거: 건축법 일조 정북사선·정직).
                _gfa_before, _floors_before = est_gfa, est_floors
                if sun["binding"]:
                    est_floors = sun["floors"]
                if sun["gfa"] < est_gfa:
                    est_gfa = round(sun["gfa"], 2)
                if est_floors != _floors_before or est_gfa < _gfa_before:
                    warnings.append(
                        f"정북일조 사선제한(건축법 61조) 반영 — 상부층 북측 단계후퇴로 {est_floors}층·"
                        f"연면적 {est_gfa:,.0f}㎡(일조 준수 envelope·근거: 건축법 일조 정북사선)"
                    )

            # ★평형별 분해(cad UNIT_TYPES 그리디 라운드로빈 재사용) — 연면적 순면적 풀에서 평형
            #   믹스 배치. 평형 미상이면 종전 단일 전용률 추정(상수)으로 폴백(정직 표기).
            _net_pool = est_gfa * _NET_AREA_RATIO if est_gfa else None
            _per_floor_net = (_net_pool / est_floors) if (_net_pool and est_floors) else None
            ub = compute_unit_breakdown(_per_floor_net, est_floors, site.unit_types)
            if ub:
                unit_breakdown = ub["units"]
                unit_efficiency = ub["efficiency"]
                est_units = ub["total_units"]
                warnings.append(
                    f"세대수는 평형 믹스({'/'.join(u['type'] for u in ub['units'])}) 그리디 배치 추정"
                    f"(전용률 {ub['efficiency']:.0%}·실 평면 세대분할과 다를 수 있음)"
                )
            elif site.avg_unit_area_sqm > 0:
                est_units = int(est_gfa * _DEFAULT_EFFICIENCY / site.avg_unit_area_sqm)
                warnings.append("세대수는 연면적×전용률 추정치(실제 평면 세대분할과 다를 수 있음)")
            # ★법적 최대 envelope 연면적(상한) — buildable footprint를 최대 활용(다동/타일링 가정)
            #   했을 때의 법적 상한. 보수추정(est_gfa·참조평면 기준)과 '나란히' 제시해 부지의 법적
            #   잠재력을 명시 산출 → 단일분석 대비 조용한 저평가를 근본 제거(실효 패리티·정직).
            #   상한은 '법적 최대 가능치'이지 확정 산출이 아님(실제는 코어/계단/이격으로 낮아짐).
            if footprint:
                _floors_cap = site.max_floors_est or est_floors or 1
                max_envelope_gfa = round(min(max_gfa, footprint * _floors_cap), 2)
            # 보수추정이 법적 상한 대비 현저히 낮으면(작은 참조평면·높이한도) 정직 고지.
            if max_envelope_gfa and est_gfa < max_envelope_gfa * _GFA_UNDERUSE_RATIO:
                _util = round(est_gfa / max_envelope_gfa * 100)
                warnings.append(
                    f"추정 연면적은 참조평면 기준 보수치(법적 상한 약 {max_envelope_gfa:,.0f}㎡의 "
                    f"약 {_util}%) — 작은 참조평면·높이한도 제약. 더 큰 평면/다동 설계로 상한까지 "
                    "상향 여지(상한은 법적 최대 가능치·확정 아님)."
                )

        # 주차: 법정 부설주차 산정(주차장법 단순화, 정본 _compute_parking 재사용) +
        # 부지 footprint 기준 지하주차 층수·배치 가능성.
        pk = compute_parking_design(site, est_units, est_gfa)
        est_parking = pk["required"]
        warnings.extend(pk["warnings"])
        if est_parking and est_parking > 0:
            bf = pk["basement_floors_site"]  # footprint 기준(미상이면 None)
            warnings.append(
                f"주차 {est_parking}대·면적 {pk['area_sqm']}㎡(주차장법 단순 산정·대당 33㎡)"
                + (f" — 지하 약 {bf}층 필요" if bf else "")
            )
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
        # ★score는 미반올림 factor로 계산(기존 단일식과 비트단위 동일 — 행위보존). 반올림은 표시용만.
        completeness_factor = 0.6 + 0.4 * completeness
        compliance_factor = 1.0 if compliant else 0.6
        score = round(fitness * completeness_factor * compliance_factor, 4)
        # 랭킹 근거(왜 이 안이 상위인지 투명 공개) — 전역 '근거 제공' 원칙
        cf_disp = round(completeness_factor, 4)  # breakdown·explanation 표시용 반올림
        score_breakdown = {
            "fitness": round(fitness, 4),                  # 부지 적합도(면적 적합·도면종류 가중)
            "completeness": round(completeness, 4),        # 도면세트 완성도(분야 수/3)
            "completeness_factor": cf_disp,                # 완성도 가중(0.6~1.0)
            "compliance_factor": compliance_factor,        # 적법 1.0 / 미확정·부적합 0.6
            "formula": "score = 적합도 × (0.6 + 0.4×완성도) × 적법가중",
            "explanation": (
                f"적합도 {fitness:.2f} · 완성도 {completeness:.0%}(×{cf_disp}) · "
                f"{'적법' if compliant else '적법성 미확정/부적합'}(×{compliance_factor}) → 종합 {score}"
            ),
        }

        candidates.append(CompositionCandidate(
            selected=selected,
            sources=sources,
            primary_drawing_type=_g(fp, "drawing_type") or "unknown",
            primary_content_hash=_valid_hash(_g(fp, "content_hash")),  # 피드백 신호 연결키(hex 검증)
            disciplines_covered=disciplines,
            missing_disciplines=missing_disc,
            scale_factor=scale,
            estimated_gfa_sqm=est_gfa,
            max_envelope_gfa_sqm=max_envelope_gfa,
            estimated_floors=est_floors,
            estimated_units=est_units,
            unit_breakdown=unit_breakdown,        # 평형별 분해(없으면 None — 평형 미상/세대 0)
            unit_efficiency=unit_efficiency,      # 적용 전용률(평형 기반·상수 탈피 근거)
            sunlight_profile=sunlight_profile,    # 정북일조 단계후퇴 envelope(주거·미적용 None)
            reference_hint=reference_hint,        # 유사사례 매스 힌트(검색 환류·없으면 None)
            estimated_parking=est_parking,  # 하위호환 별칭(=parking_required)
            parking_required=pk["required"],
            parking_area_sqm=pk["area_sqm"],
            parking_basement_floors=pk["basement_floors_site"],  # footprint 기준(미상 None)
            parking_feasible=pk["feasible"],
            parking_layout=compute_parking_layout(site, est_parking),  # 주차 자동배치도(스키매틱)
            placement=placement,                                       # 건물 배치 폴리곤(부지 공유)
            compliant=compliant,
            score=score,
            score_breakdown=score_breakdown,
            warnings=warnings,
        ))

    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates[:top_n]


def site_context_from_zone(
    zone_code: str,
    area_sqm: float,
    *,
    zone_name: str | None = None,
    ordinance_far_pct: float | None = None,
    ordinance_bcr_pct: float | None = None,
    ordinance_height_m: float | None = None,
    ordinance_setback_m: float | None = None,
    width_m: float | None = None,
    depth_m: float | None = None,
    avg_unit_area_sqm: float = 84.0,
    unit_types: list[str] | None = None,
    reference_mass: dict | None = None,
    building_use_kr: str = "공동주택",
) -> SiteContext:
    """용도지역 법정한도로 SiteContext 구성(best-effort). 조례(실효) 값이 오면 우선.

    한도 출처 우선순위(P1-4 zone 23종 확충):
      1. zone_name(한글)이 있으면 23종 fail-closed 계약(resolve_zone_limits)으로 확정/미확정 판정.
         미인식 zone은 max_*_pct=None(fail-closed) — 무근거 한도 폴백 금지(정직 경고).
      2. zone_code(7종)는 AutoDesignEngine 법정표로 보완 — height/setback 등 계약 미보유 필드,
         그리고 23종 미매칭 시 코드 기반 폴백(legacy 동작 보존). statutory_fallback 정직 표기.
      3. 조례(실효) far/bcr/height/setback가 명시되면 최우선(전역규칙: 용적률은 실효 우선).

    far_source: ordinance(실효) | statutory(법정확정) | statutory_fallback(코드 폴백) | unknown(미확정).
    height_source/bcr_source 동일 패턴으로 분리 표기.
    """
    far_pct = bcr_pct = height_m = setback_m = None
    far_source = bcr_source = height_source = "unknown"
    ctx_warnings: list[str] = []

    # 1) zone_name 기반 23종 fail-closed 계약(권위 한도). 미인식이면 확정 한도 None(fail-closed).
    if zone_name:
        try:
            from app.services.zoning.zone_limit_contract import resolve_zone_limits

            res = resolve_zone_limits(zone_name)
            if res.matched:
                far_pct, bcr_pct = res.max_far_pct, res.max_bcr_pct
                far_source = bcr_source = "statutory"
                # 절대 높이한도(m) — 23종 SSOT(legal_zone_limits) 보유분만(주거 전용 등). 없으면 None.
                try:
                    from app.services.zoning.legal_zone_limits import legal_limits_for

                    _ll = legal_limits_for(zone_name)
                    if _ll and _ll.get("max_height_m"):
                        height_m = float(_ll["max_height_m"])
                        height_source = "statutory"
                except Exception:  # noqa: BLE001
                    pass
            else:
                ctx_warnings.append(
                    f"용도지역 한도 미확정({res.fallback_reason or zone_name}) — "
                    "확정 한도 없음(fail-closed). 조례/코드 보완 또는 정밀 확인 필요."
                )
        except Exception:  # noqa: BLE001
            pass

    # 2) zone_code(7종) 법정표 — height/setback 보완 + 23종 미매칭 시 far/bcr 폴백(legacy 보존).
    try:
        from app.services.cad.auto_design_engine import AutoDesignEngineService

        legal = AutoDesignEngineService.get_legal_limits(zone_code)
        code_fallback = legal.get("limits_source") == "fallback_default"
        if far_pct is None and legal.get("max_far_percent") is not None:
            far_pct = legal.get("max_far_percent")
            far_source = "statutory_fallback" if code_fallback else "statutory"
        if bcr_pct is None and legal.get("max_bcr_percent") is not None:
            bcr_pct = legal.get("max_bcr_percent")
            bcr_source = "statutory_fallback" if code_fallback else "statutory"
        if setback_m is None and legal.get("min_setback_m") is not None:
            setback_m = legal.get("min_setback_m")  # 이격거리(배치 폴리곤·일조 base)
        # 코드 절대 높이한도(m>0만 — 0은 '무제한' 신호). 23종에서 못 채웠을 때만 보완.
        if height_m is None and legal.get("max_height_m"):
            height_m = float(legal["max_height_m"])
            height_source = "statutory_fallback" if code_fallback else "statutory"
        if code_fallback and not zone_name:
            ctx_warnings.append(f"미지정 용도지역 '{zone_code}' — 법정 기본값 폴백(정밀 확인 필요)")
        for w in (legal.get("warnings") or [])[:2]:
            ctx_warnings.append(str(w))
    except Exception:  # noqa: BLE001
        pass

    # 3) 조례(실효) 최우선(전역규칙). far_source는 FAR 출처만 표기.
    if ordinance_far_pct is not None:
        far_pct = ordinance_far_pct
        far_source = "ordinance"
    if ordinance_bcr_pct is not None:
        bcr_pct = ordinance_bcr_pct
        bcr_source = "ordinance"
    # 조례 height/setback 주입(P2-5) — 있으면 매스 높이캡·이격에 반영(없으면 법정/코드값 유지).
    if ordinance_height_m is not None and ordinance_height_m > 0:
        height_m = ordinance_height_m
        height_source = "ordinance"
    if ordinance_setback_m is not None and ordinance_setback_m > 0:
        setback_m = ordinance_setback_m

    return SiteContext(
        area_sqm=area_sqm,
        zone_code=zone_code,
        zone_name=zone_name,
        width_m=width_m,
        depth_m=depth_m,
        legal_bcr_pct=bcr_pct,
        legal_far_pct=far_pct,
        legal_setback_m=setback_m,
        legal_height_m=height_m,
        height_source=height_source,
        bcr_source=bcr_source,
        far_source=far_source,
        avg_unit_area_sqm=avg_unit_area_sqm,
        unit_types=unit_types,
        reference_mass=reference_mass,
        building_use_kr=building_use_kr,
        warnings=ctx_warnings,
    )
