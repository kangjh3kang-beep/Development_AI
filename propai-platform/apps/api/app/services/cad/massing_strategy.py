"""건축유형별 매싱 목적함수 SSOT(공용 단일 출처) — 결정론·무날조·additive.

근본문제(코드감사): 기존 매싱은 building_use(3종)·massing_kind(형상4종)를 입력
파라미터로만 쓰고 '목적함수'가 없었다. compute_optimal_mass는 항상 건폐율 max(단일
전략), solar_envelope는 round(far/30~20) 하드코딩. 이 모듈은 건축유형을 결정론으로
추론(classify_building_type)하고, 한국 설계실무에 맞는 매싱 목적(MassingObjective)을
반환(resolve_massing_objective)한다.

실무 목적함수(한국 설계실무):
- 공동주택(아파트): 높이 최대·건폐율 최소(인동간격 0.5H·동지연속 2h 충족의 결과로
  고층저밀) → footprint를 건폐율 상한보다 작게 잡아 층수↑.
- 빌라/다가구/연립/도시형생활주택: 정북일조사선(10m↓1.5m / 초과 0.5H)이 층수를
  지배 → 건폐율 최대 + 사선 역산.
- 상업(일반/근린): 건폐율·용적률 둘 다 최대(포디움+타워).
- 주상복합/준주거: 주거용적률 최대 s.t. 지자체 비주거 의무비율(상업지=연면적 10%,
  준주거=용적률 트랙)·오피스텔 비주거 인정 지자체 편차 → commercial_podium_ratio.

이 모듈은 순수 함수(결정론·LLM 0). 기존 빌딩블록(design_change_predictor 상수·
design_geometry.ALLOWED_USES_BY_ZONE)을 재사용한다. 신규 의존성 0.

★무회귀: 본 모듈은 정보만 산출한다. 소비측(compute_optimal_mass·solar_envelope)은
목적함수를 '선택 kwargs'로만 받으며, 미전달 시 기존 동작이 완전히 보존된다.
"""

from __future__ import annotations

from typing import Any

# ── 기존 상수 재사용(DRY·단일 출처) ──────────────────────────────────────────
# 주거/상업 용도 키(세대 기반 vs 면적 기반 판정에 이미 쓰이는 표준 집합).
from app.services.design_risk.design_change_predictor import (
    _COMMERCIAL_TYPES,
    _RESIDENTIAL_TYPES,
)

# 정북일조 적용 용도지역 코드(건축법 61조 적용범위 — 전용·일반주거). auto_design_engine과
# 동일 frozenset을 재사용(이중 정의 방지). import 실패 시 보수 폴백(graceful).
try:
    from app.services.cad.auto_design_engine import SUNLIGHT_ZONES as _SUNLIGHT_ZONES
except Exception:  # noqa: BLE001
    _SUNLIGHT_ZONES = frozenset({"1R", "2R", "3R"})

# 용도지역(코드/한글) → 허용 건축물 목록(국토계획법 별표 확인분). 분류 보강용.
try:
    from app.services.design_ingest.design_geometry import allowed_uses as _allowed_uses
except Exception:  # noqa: BLE001
    def _allowed_uses(_zone: str | None) -> list[str] | None:  # type: ignore[misc]
        return None


# ── 건축유형 분류 결과값(결정론 5+종) ────────────────────────────────────────
TYPE_APARTMENT = "아파트"            # 공동주택(중·고층 분양·임대)
TYPE_MIXED_USE = "주상복합"          # 주거+상업 혼합(준주거·상업지)
TYPE_OFFICETEL = "오피스텔"          # 준주거/상업의 오피스텔
TYPE_VILLA = "빌라"                  # 다세대·다가구·연립(저층 정북일조 지배)
TYPE_ROWHOUSE = "연립주택"           # 연립(빌라와 동일 목적·법적 구분만)
TYPE_COMMERCIAL = "상업시설"         # 판매·업무·근생(포디움+타워)
TYPE_RESIDENTIAL_DEFAULT = "공동주택"  # 불명확 시 보수 기본

# 저층 정북일조 지배 유형(빌라·연립·다세대·다가구·도시형생활주택). 건폐율 최대 전략.
_LOW_RISE_RESIDENTIAL = frozenset({
    TYPE_VILLA, TYPE_ROWHOUSE, "다세대주택", "다가구주택", "연립", "도시형생활주택",
})

# 상업지·준주거 용도지역 코드(상업 분기 판정). auto_design ZONE_LIMITS 키 체계.
_COMMERCIAL_ZONE_CODES = frozenset({"GC", "NC", "CC", "QR"})

# 정북일조 적용 한글 용도지역 키워드(코드가 아닌 한글명으로 들어올 때 보강).
_NORTH_LIGHT_ZONE_KEYWORDS = ("전용주거", "일반주거", "1종", "2종", "3종", "제1종", "제2종", "제3종")

# 저층 판정 GFA·세대수 임계(추정·보수). 미만이면 저층 주거(빌라류)로 본다.
# 다세대주택 법적 정의: 1동 연면적 660㎡ 이하·4개층 이하. 이를 보수 기준으로 차용.
_VILLA_GFA_THRESHOLD_SQM = 660.0
_VILLA_UNIT_THRESHOLD = 19  # 다세대 통상 세대수 상한 근사(도시형생활 원룸형 30 미만)


def _norm(text: str | None) -> str:
    return str(text or "").replace(" ", "").strip()


def classify_building_type(
    zone_code: str,
    building_use: str | None = None,
    total_gfa_sqm: float | None = None,
    unit_count: int | None = None,
    allowed_uses: list[str] | None = None,
) -> str:
    """용도지역·용도·규모로 건축유형을 결정론 추론한다(무날조·보수 기본).

    우선순위:
    1) 명시 building_use가 상업(판매·업무·근생)이면 → 상업시설.
    2) building_use가 오피스텔이면 → 오피스텔.
    3) 상업지/준주거(GC/NC/CC/QR) + 주거 용도 → 주상복합(혼합)·단 순수상업은 상업시설.
    4) 주거 용도(공동주택·아파트류) + 저층 규모(GFA<660㎡ 또는 세대수<20) → 빌라/연립.
    5) 주거 용도 + 정북일조 적용 주거지역(1R/2R/3R) → 아파트.
    불명확하면 보수적으로 '공동주택'을 반환(가짜 단정 금지).

    Args:
        zone_code: 용도지역 코드(2R 등) 또는 한글명.
        building_use: 건축물 용도(공동주택·업무시설·오피스텔 등). None이면 용도지역으로 추론.
        total_gfa_sqm: 연면적(저층/고층 구분 보강). None이면 규모 미사용.
        unit_count: 세대수(저층/고층 구분 보강). None이면 규모 미사용.
        allowed_uses: 용도지역 허용 용도 목록(없으면 design_geometry로 자동 조회).
    """
    zc = _norm(zone_code)
    use = _norm(building_use)

    # 허용 용도 목록(주거 가능 여부 보강) — 미주입 시 자동 조회(graceful).
    if allowed_uses is None:
        allowed_uses = _allowed_uses(zone_code)

    is_commercial_zone = zc in _COMMERCIAL_ZONE_CODES or any(
        k in zc for k in ("상업", "준주거")
    )

    # (1) 명시 용도가 상업(판매·업무·근생·상가)이면 상업시설(주거 아님).
    commercial_use = bool(use) and (
        use in {_norm(t) for t in _COMMERCIAL_TYPES}
        or any(k in use for k in ("업무", "판매", "근린생활", "상가", "숙박"))
    ) and "오피스텔" not in use
    if commercial_use:
        return TYPE_COMMERCIAL

    # (2) 오피스텔 명시.
    if "오피스텔" in use:
        return TYPE_OFFICETEL

    # 주거 용도 판정(공동주택·아파트·다세대·다가구·연립 등).
    residential_use = (
        not use  # 용도 미상이면 주거로 보수 추론(주거지역 가정)
        or use in {_norm(t) for t in _RESIDENTIAL_TYPES}
        or any(k in use for k in ("주택", "공동주택", "아파트", "주거"))
    )

    # 명시적 거주 신호: building_use에 주거 키워드 포함, 또는 세대수/GFA가 주거 규모를 암시.
    # ★수정(오분류 정정): 상업지(일반/근린/중심/유통상업)에서 주상복합을 반환하려면
    # 반드시 거주 의도를 나타내는 명시적 신호가 있어야 한다. 신호 없는 순수 상업지역은
    # 상업시설(max_both)이 기본. 준주거(QR)는 주거 기본 성격이라 신호 없어도 주거 취급.
    explicit_residential_signal = bool(use) and residential_use
    is_jun_jugeo_zone = zc == "QR" or "준주거" in zc
    # 주상복합 판정: 준주거이거나 명시적 거주 신호가 있는 상업지.
    mixed_use_signal = is_jun_jugeo_zone or explicit_residential_signal

    # (3) 상업지/준주거 분기 — 거주 신호 있으면 주상복합, 없으면 상업시설.
    if is_commercial_zone:
        if mixed_use_signal:
            return TYPE_MIXED_USE
        # 거주 신호 없는 순수 상업지역(일반상업·근린상업 등) → 상업시설.
        return TYPE_COMMERCIAL

    # (4) 저층 주거 규모 → 빌라/연립(정북일조 사선이 층수 지배).
    if residential_use:
        small_gfa = total_gfa_sqm is not None and 0 < total_gfa_sqm <= _VILLA_GFA_THRESHOLD_SQM
        small_units = unit_count is not None and 0 < unit_count <= _VILLA_UNIT_THRESHOLD
        if "연립" in use:
            return TYPE_ROWHOUSE
        if "다세대" in use or "다가구" in use or "빌라" in use or "도시형생활" in use:
            return TYPE_VILLA
        if small_gfa or small_units:
            return TYPE_VILLA

        # (5) 정북일조 적용 주거지역(1R/2R/3R) → 아파트(고층저밀 전략).
        north_light_zone = zc in _SUNLIGHT_ZONES or any(
            k in zc for k in _NORTH_LIGHT_ZONE_KEYWORDS
        )
        if north_light_zone:
            return TYPE_APARTMENT

    # 불명확 → 보수 기본(공동주택). 무날조: 단정 금지.
    return TYPE_RESIDENTIAL_DEFAULT


# ── 매싱 목적(MassingObjective) ──────────────────────────────────────────────
# objective:
#   'max_height_min_coverage' — 공동주택(아파트): 높이 최대·건폐율 최소(고층저밀).
#   'max_coverage'            — 빌라/연립/다세대: 건폐율 최대 + 정북일조 사선 역산.
#   'max_both'                — 상업(일반/근린): 건폐율·용적률 둘 다 최대(포디움+타워).
#   'mixed_use_residential'   — 주상복합/준주거: 주거용적률 최대 s.t. 비주거 의무비율.
OBJ_MAX_HEIGHT_MIN_COVERAGE = "max_height_min_coverage"
OBJ_MAX_COVERAGE = "max_coverage"
OBJ_MAX_BOTH = "max_both"
OBJ_MIXED_USE_RESIDENTIAL = "mixed_use_residential"

# 공동주택 고층저밀 권장 건폐율 비율(상한 대비). 인동간격·일조의 결과로 통상 상한을 다
# 채우지 않는다. 0.55 = 상한의 55%까지만 깔고 나머지는 층수로(추정·보수·실무 통념).
_APARTMENT_BCR_RATIO = 0.55
# 1동 최대 길이(m) — 공동주택 판상 과장(超장변) 방지·피난/입면 통념(추정).
_APARTMENT_MAX_DONG_LEN_M = 90.0

# 주상복합 비주거 의무비율(연면적 대비). 상업지역 통상 10%(지자체 조례 편차) — 보수 기본.
# ★무날조: 지자체별 정확한 비율·오피스텔 비주거 인정 여부는 조례 확인 필요(honest 플래그).
_MIXED_COMMERCIAL_PODIUM_RATIO = 0.10


def resolve_massing_objective(
    building_type: str,
    zone_code: str,
    district: str | None = None,
) -> dict[str, Any]:
    """건축유형·용도지역으로 매싱 목적함수(MassingObjective)를 반환한다(결정론·근거 표기).

    반환 키:
      objective: 위 OBJ_* 중 하나.
      target_bcr_ratio: 건폐율 상한 대비 목표 점유율(0~1). 공동주택<1.0(고층저밀),
        빌라/상업/혼합=1.0(상한 만충). compute_optimal_mass가 footprint 축소에 사용.
      preferred_massing_kind: 권장 매스 형상(MASSING_FORMS 키). 미지정 시 None(auto).
      commercial_podium_ratio: 주상복합 비주거 의무비율(연면적 대비). 그 외 None.
      max_dong_length_m: 1동 최대 길이(m·통념). 미적용 시 None.
      daylight_mode: 'high_rise_low_density' | 'setback_envelope' | 'none'.
      basis: 법령·실무 근거(문자열).
      honest: 추정/보수 기본 사용 플래그 dict(무날조 정직 표기).

    ★district(지자체)는 비주거 의무비율·오피스텔 비주거 인정 편차 반영용. 현재는 미확인
      지자체 수치를 날조하지 않고 보수 기본(10%)+honest 플래그로 정직 처리한다.
    """
    bt = _norm(building_type)
    zc = _norm(zone_code)
    honest: dict[str, Any] = {}

    # ── 상업시설: 건폐율·용적률 둘 다 최대(포디움+타워) ──
    if bt == _norm(TYPE_COMMERCIAL):
        return {
            "objective": OBJ_MAX_BOTH,
            "target_bcr_ratio": 1.0,            # 건폐율 상한 만충(상업 포디움)
            "preferred_massing_kind": "tower",  # 상부 타워(작은 플로어플레이트로 고층)
            "commercial_podium_ratio": None,
            "max_dong_length_m": None,
            "daylight_mode": "none",            # 정북일조 미적용(상업지)
            "basis": (
                "상업지역 — 건폐율·용적률 둘 다 최대화(저층 포디움+상부 타워). "
                "정북일조 사선 미적용(건축법 61조 적용범위 외)."
            ),
            "honest": {},
        }

    # ── 주상복합/준주거: 주거용적률 최대 s.t. 비주거 의무비율 ──
    if bt == _norm(TYPE_MIXED_USE):
        is_jun_jugeo = zc == "QR" or "준주거" in zc
        # 상업지=연면적 10% 비주거 의무(보수 기본). 준주거=용적률 트랙(지자체 편차) — 미확인.
        honest = {
            "commercial_ratio_basis": (
                "준주거 용적률 트랙(지자체 조례 편차) — 정확 비율 미확인, 보수 기본 10% 적용"
                if is_jun_jugeo
                else "상업지역 비주거 의무 연면적 10%(지자체 조례 편차 가능) — 보수 기본"
            ),
            "officetel_nonresidential_recognition": (
                "오피스텔 비주거 인정 여부는 지자체 편차(서울/부천/하남 불인정·인천 50%·대전 인정) "
                "— 미확인, 자동 미반영(조례 확인 필요)"
            ),
            "district": district or "미상",
        }
        return {
            "objective": OBJ_MIXED_USE_RESIDENTIAL,
            "target_bcr_ratio": 1.0,            # 저층 상업 포디움은 건폐율 만충
            "preferred_massing_kind": "tower",  # 주거 타워 상부
            "commercial_podium_ratio": _MIXED_COMMERCIAL_PODIUM_RATIO,
            "max_dong_length_m": None,
            "daylight_mode": "none",            # 상업지/준주거 정북일조 미적용
            "basis": (
                "주상복합/준주거 — 주거 용적률 최대화. 단 비주거(상업) 의무비율 충족 필요. "
                "저층 포디움(비주거)+주거 타워 구성. 오피스텔 비주거 인정은 지자체 편차."
            ),
            "honest": honest,
        }

    # ── 빌라/연립/다세대/다가구/도시형생활: 건폐율 최대 + 정북일조 사선 역산 ──
    if bt in {_norm(t) for t in _LOW_RISE_RESIDENTIAL}:
        return {
            "objective": OBJ_MAX_COVERAGE,
            "target_bcr_ratio": 1.0,            # 건폐율 상한 만충(저층 고밀)
            "preferred_massing_kind": "slab",   # 판상(넓고 얕게)
            "commercial_podium_ratio": None,
            "max_dong_length_m": None,
            "daylight_mode": "setback_envelope",  # 정북일조 사선이 층수 지배 → 단계후퇴 권장
            "basis": (
                "빌라/연립/다세대 — 건폐율 최대화 후 정북일조 사선(건축법 61조·시행령 86조: "
                "10m 이하 1.5m·초과 높이/2)으로 층수 역산(저층 정북일조 지배)."
            ),
            "honest": {},
        }

    # ── 공동주택/아파트(및 보수 기본): 높이 최대·건폐율 최소(고층저밀) ──
    daylight_mode = (
        "high_rise_low_density"
        if (zc in _SUNLIGHT_ZONES or any(k in zc for k in _NORTH_LIGHT_ZONE_KEYWORDS))
        else "none"
    )
    return {
        "objective": OBJ_MAX_HEIGHT_MIN_COVERAGE,
        "target_bcr_ratio": _APARTMENT_BCR_RATIO,  # <1.0 — footprint 축소 → 층수↑(고층저밀)
        "preferred_massing_kind": "tower",         # 타워(작은 플로어플레이트)
        "commercial_podium_ratio": None,
        "max_dong_length_m": _APARTMENT_MAX_DONG_LEN_M,
        "daylight_mode": daylight_mode,
        "basis": (
            "공동주택(아파트) — 높이 최대·건폐율 최소(고층저밀). 인동간격 0.5H·동지 연속일조 "
            "2시간 충족의 결과로 footprint를 건폐율 상한보다 작게(약 55%) 깔고 층수를 높인다. "
            f"건폐율 목표={int(_APARTMENT_BCR_RATIO * 100)}%(상한 대비·추정·실무 통념)."
        ),
        "honest": {
            "bcr_ratio_basis": (
                f"고층저밀 권장 건폐율 비율 {_APARTMENT_BCR_RATIO}(상한 대비)은 인동간격·일조 "
                "충족의 결과적 통념 추정값 — 정확값은 단지 배치·일조 시뮬레이션 필요"
            ),
        },
    }
