"""다각도 개발방식 시뮬레이션.

단일/다필지 부지에 대해 관련 개발정책의 적용요건을 판정하고, 정책별 예상 용적률·
적정 기부채납·실현성을 산정해 최적 사업방안을 제안한다. 어떤 정책도 적용되지 않으면
단순 건축(현 용도지역 한도 내) 추진방안으로 폴백한다.

대상 정책: 단순건축 / 지구단위계획 연계 / 도시개발사업(도시개발법) / 가로주택정비사업 /
모아주택(소규모주택정비) / 소규모재건축 / 역세권 활성화사업 / 역세권 장기전세주택 /
재개발·재건축(정비사업).

요건·수치는 일반 기준 기반 추정이며 정밀 산정은 지구단위계획·심의 단계 확인이 필요하다.
규칙기반 후보 생성 + LLM 종합·검증(하이브리드).
"""

import json
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

PYEONG_SQM = 3.305785

# 정책별 매도청구권 — 동의요건 충족 시 미동의자(잔여)에 매도청구 가능.
# consent_pct=사업 추진 동의 임계, claimable_remainder=임계 충족 시 매도청구 가능한 잔여(=100-임계),
# basis=근거 법령. (실제 적용은 소유관계·동의현황·보유기간 등 현장확인 필요)
#
# ★★`governing_act`(근거 법령 계열)는 **명시 필드**다 — `basis` 문자열에서 추론하지 않는다.
#   추론이 왜 틀리는지 실증: "역세권 활성화사업"의 basis 에는 "주택법"이 들어 있지만 그 문장이
#   스스로 *"사업방식에 따라 정비/소규모정비 준용"* 이라고 적는다. 문자열 매칭으로 주택법이라
#   단정하면 **보유기간 10년 요건을 동의율 기반 사업에 잘못 적용**하게 된다(실제 결함).
#   → 그래서 그 방식만 `governing_act=None` + `requires_track_input=True` 로 두고, 트랙(정비/
#     소규모정비 준용)이 입력되기 전에는 보유기간 판정을 **하지 않는다**.
#
# ★★`instrument`(강제취득 수단)도 명시한다. 보유기간 10년 요건(주택법 §22①2호)은
#   **주택법 계열에만** 있다. 도정법 §64·소규모정비특례법 §35 는 **동의율** 기반이라 보유기간
#   요건이 아예 없고, 도시개발법 §22 는 매도청구가 아니라 **수용**(토지보상법 준용: 협의→재결→
#   보상)이라 절차 자체가 다르다.
MAGDO_RULES: dict[str, dict[str, Any]] = {
    "재개발·재건축(정비사업)": {
        "consent_required": "조합설립: 토지등소유자 3/4 이상 + 토지면적 1/2 이상(재건축은 각 동 과반·전체 3/4·면적 3/4)",
        "consent_pct": 75,
        "consent_basis": "owner_count",
        "basis": "도시 및 주거환경정비법 제64조(매도청구)",
        "governing_act": "도정법",
        "instrument": "매도청구",
        "note": "조합설립 동의 후 미동의 조합원·토지등소유자에게 매도청구",
    },
    # ★★소규모정비특례법 §35 **본문 단서**: 「제35조의2 에 따라 수용·사용할 수 있는 경우는
    #   **제외**」. 소규모재개발·관리지역 가로주택을 **공공이 시행**하면 §35의2 수용이 되어
    #   **매도청구 대상이 아니다**(법령 대조 2026-08-13 · 계획서 §5). 즉 이 두 방식은
    #   `scheme` **하나만으로 갈리지 않는다** — 시행자 유형(민간/공공)·관리지역 여부가 분류를
    #   뒤집는다. 그래서 "역세권 활성화사업"과 **같은 기제**(`requires_track_input`)를 쓴다:
    #   트랙이 입력되기 전에는 강제취득 수단을 **단정하지 않는다**.
    #   ★`instrument` 는 민간시행 기본 트랙 값이며 **이 값만 보고 단정하면 안 된다**
    #     (`requires_track_input` 이 그 사실을 실어 나른다 — 역세권 활성화와 동일 계약).
    "가로주택정비사업": {
        "consent_required": "토지등소유자 80% 이상 + 토지면적 2/3 이상(공동주택 각 동 과반)",
        "consent_pct": 80,
        "consent_basis": "owner_count",
        "basis": "빈집 및 소규모주택 정비에 관한 특례법 제35조(매도청구) — 제35조의2 수용 대상은 제외",
        "governing_act": "소규모정비특례법",
        "requires_track_input": True,
        "instrument": "매도청구",
        "note": (
            "민간시행: 동의요건 충족 후 미동의자에게 매도청구. "
            "★관리지역 가로주택을 공공이 시행하면 §35의2 수용이라 매도청구가 아니다 — "
            "시행자 유형·관리지역 여부가 입력되기 전에는 수단을 확정하지 않는다."
        ),
    },
    "모아주택/모아타운": {
        "consent_required": "소규모재건축: 전체 3/4 이상 + 각 동 과반 + 토지면적 3/4 이상",
        "consent_pct": 75,
        "consent_basis": "owner_count",
        "basis": "빈집 및 소규모주택 정비에 관한 특례법 제35조(매도청구) — 제35조의2 수용 대상은 제외",
        "governing_act": "소규모정비특례법",
        "requires_track_input": True,
        "instrument": "매도청구",
        "note": (
            "민간시행: 동의요건 충족 후 미동의자 매도청구(모아타운 내 개별 소규모정비). "
            "★소규모재개발·공공시행 트랙은 §35의2 수용이라 매도청구 대상이 아니다."
        ),
    },
    "도시개발사업(도시개발법)": {
        "consent_required": "수용·사용방식: 토지면적 2/3 이상 + 토지소유자 총수 1/2 이상 동의",
        "consent_pct": 67,
        "consent_basis": "land_area",
        "basis": "도시개발법 제22조(토지등의 수용·사용) · 토지보상법",
        "governing_act": "도시개발법",
        # ★"매도청구에 준함"이라는 종전 note 문구는 **부정확**해서 삭제했다(법령 대조 2026-08-13).
        #   수용은 토지보상법 준용(협의→재결→보상)이라 매도청구와 절차·기한·보상기준이 다르다.
        "instrument": "수용",
        "note": "수용방식은 미동의 토지를 수용(토지보상법 준용: 협의→재결→보상). 환지방식은 환지처분으로 갈음",
    },
    "역세권 장기전세주택(시프트)": {
        "consent_required": "대지 사용권원 95% 이상 확보(주택건설사업)",
        "consent_pct": 95,
        "consent_basis": "use_right_area",
        "basis": "주택법 제22조·제23조(매도청구)",
        "governing_act": "주택법",
        "instrument": "매도청구",
        "note": "95%↑ 확보→잔여 전부 매도청구 / 80~95%→10년 미만 보유 토지에 매도청구",
    },
    "지구단위계획 연계": {
        "consent_required": "주택건설사업: 대지 사용권원 95% 이상 확보",
        "consent_pct": 95,
        "consent_basis": "use_right_area",
        "basis": "주택법 제22조(매도청구)",
        "governing_act": "주택법",
        "instrument": "매도청구",
        "note": "지구단위 내 주택건설사업 시 95%↑ 확보→잔여 매도청구(80~95%는 10년 미만 보유분)",
    },
    "역세권 활성화사업": {
        "consent_required": "주택건설사업 준용: 대지 사용권원 95% 이상 확보",
        "consent_pct": 95,
        "consent_basis": "use_right_area",
        "basis": "주택법 제22조(매도청구) — 사업방식에 따라 정비/소규모정비 준용",
        # ★모호 — basis 에 "주택법"이 있지만 같은 문장이 정비/소규모정비 준용도 함께 적는다.
        #   근거법령을 확정하지 못하므로 None. 트랙 입력 전에는 보유기간 판정을 하지 않는다.
        "governing_act": None,
        "requires_track_input": True,
        # instrument 는 정비/소규모정비 준용 시 매도청구가 되지만, 확정은 트랙 입력 후다
        # (requires_track_input 이 그 사실을 실어 나른다 — 이 값만 보고 단정하면 안 된다).
        "instrument": "매도청구",
        "note": "용도상향 복합개발. 주택 포함 시 95%↑ 확보→잔여 매도청구",
    },
}

# 보유기간(지구단위계획구역 결정고시일 기준 10년) 요건이 존재하는 **유일한** 법령 계열.
# 도정법 §64·소규모정비특례법 §35 는 동의율 기반이라 보유기간 조건이 없고, 도시개발법 §22 는
# 수용이라 매도청구 자체가 성립하지 않는다.
HOLDING_PERIOD_ACT = "주택법"


def scheme_legal_profile(scheme: str | None) -> dict[str, Any] | None:
    """사업방식 → {governing_act, instrument, requires_track_input, basis, consent_*}.

    ★MAGDO_RULES 를 읽는 **공용 통로**다. 소비처가 직접 dict 를 뒤지면 키 이름이 갈라지고
      `basis` 문자열에서 법령을 추론하는 결함이 다시 생긴다(P2 가 실제로 그 결함을 고쳤다).
    미등록 방식(단순 건축 등)은 None — 매도청구·수용 제도가 적용되지 않는다는 뜻이다.

    ★소비처가 없는 필드는 싣지 않는다("정의는 했는데 소비처 0"은 이 저장소가 반복해서 데인
      패턴이다 — 변이로 지워도 아무도 모른다). 여기 여섯은 전부 소비된다: 앞 셋은 보유기간
      게이트(`parcel_rights_survey_service._judge_owner`)가, 뒤 셋은 P2 판정표의 `legal`
      블록이 쓴다(동의율 기반 방식은 동의요건이 곧 판정 근거다).
    """
    r = MAGDO_RULES.get(scheme or "")
    if not r:
        return None
    return {
        "governing_act": r.get("governing_act"),
        "instrument": r.get("instrument"),
        "requires_track_input": bool(r.get("requires_track_input")),
        "basis": r.get("basis"),
        "consent_required": r.get("consent_required"),
        "consent_threshold_pct": r.get("consent_pct"),
        # ★임계의 **기준 축**을 명시한다 — 이 값이 없으면 소비처가 면적 임계를
        #   필지 개수에 곱하는 축 오류를 낸다(실제로 `_magdo_summary` 가 그랬다).
        "consent_basis": r.get("consent_basis"),
    }


def _magdo(scheme: str) -> dict[str, Any] | None:
    """정책별 **강제취득 수단** 분석(수단·동의요건·잔여 비율·근거).

    ★★2026-08-16 일원화 — 이 함수는 `MAGDO_RULES` 를 **두 번째로** 직접 읽던 통로였고,
      `scheme_legal_profile()` 이 신설한 `instrument`·`requires_track_input` 을 **읽지 않아
      화면과 판정이 갈라져 있었다.** 실측(프로덕션 배포 중이던 값):

          도시개발사업      화면 "매도청구 가능 잔여 33%"  ← 실제 instrument=**수용**
          가로주택정비사업   화면 "매도청구 가능 잔여 20%"  ← 실제 판정보류(트랙 미정)

      수용과 매도청구는 **절차**(협의→재결→보상 vs 3개월협의→소)도 **보상기준**
      (공시지가·개발이익 배제 vs **시가**)도 다르다. 사용자가 잘못된 트랙을 준비한다.
    → 이제 **`scheme_legal_profile()` 을 경유**한다. `MAGDO_RULES` 직접 조회는 그 함수 하나뿐이며
      새 필드가 생겨도 이쪽이 자동으로 따라온다(같은 판정이 두 곳에 살면 반드시 갈라진다).

    ★`claimable_remainder_pct` 는 **수단이 확정된 경우에만** 낸다. 트랙 미정인데 잔여 비율을
      숫자로 내면 그 단정 자체가 거짓이므로 `None` 이다.
    """
    prof = scheme_legal_profile(scheme)
    if not prof:
        return None  # 단순건축 등 단일 사업주체/소유 → 강제취득 불요
    r = MAGDO_RULES.get(scheme) or {}
    thr = prof.get("consent_threshold_pct")
    undetermined = bool(prof.get("requires_track_input"))
    return {
        "governing_act": prof.get("governing_act"),
        # ★"매도청구"라고 단정하지 않는다 — 도시개발은 **수용**이다.
        "instrument": None if undetermined else prof.get("instrument"),
        "instrument_undetermined": undetermined,
        "consent_required": prof.get("consent_required"),
        "consent_threshold_pct": thr,
        "consent_basis": prof.get("consent_basis"),
        "claimable_remainder_pct": (
            None if (undetermined or thr is None) else round(100 - thr, 1)
        ),
        "basis": prof.get("basis"),
        "note": r.get("note"),
    }


# ── 사업방식 → 근거법령 키(legal_reference_registry) 매핑 ──
#   시나리오↔규범 일치(가산)용. 소규모정비특례법(가로주택·소규모재건축·자율주택·소규모재개발),
#   정비법(재개발·재건축·주거환경개선·공공정비), 도시개발법, 국토계획법(지구단위·입지규제최소),
#   결합건축(건축법), 리모델링(주택법) 등. 미매핑 방식은 빈 리스트(무해).
_SCHEME_LEGAL_KEYS: dict[str, list[str]] = {
    "단순 건축": ["building_permit", "zone_use"],
    "지구단위계획 연계": ["district_unit_plan"],
    "도시개발사업(도시개발법)": ["urban_dev_replot"],
    "가로주택정비사업": ["small_housing_overview", "small_housing_road_project", "small_housing_sell_claim"],
    "모아주택/모아타운": ["small_housing_overview", "small_housing_road_project", "small_housing_sell_claim"],
    "재개발·재건축(정비사업)": ["redev_impl", "redev_mgmt"],
    "자율주택정비사업": ["small_housing_overview", "small_housing_road_project"],
    "소규모재개발사업": ["small_housing_overview", "small_housing_road_project", "small_housing_sell_claim"],
    "소규모재건축사업": ["small_housing_overview", "small_housing_road_project", "small_housing_sell_claim"],
    "주거환경개선사업": ["redev_impl"],
    "공공재개발·공공재건축": ["redev_impl", "redev_mgmt"],
    "공동주택 리모델링": ["housing_approval"],
    "결합건축": ["bldg_far"],
    "입지규제최소구역": ["zone_use"],
    "도심복합개발사업": ["urban_complex"],
    "역세권 장기전세주택(시프트)": ["housing_approval"],
    "지구단위계획": ["district_unit_plan"],
    "대지조성사업": ["housing_approval"],
}


def _scheme_legal_refs(scheme: str) -> list[dict]:
    """사업방식별 근거법령(verified 딥링크) — 가산 필드. 미매핑/실패 시 빈 리스트(무해)."""
    keys = _SCHEME_LEGAL_KEYS.get(scheme or "")
    if not keys:
        return []
    try:
        from app.services.legal.legal_reference_registry import get_legal_refs

        return get_legal_refs(keys)
    except Exception:  # noqa: BLE001
        return []


ZONE_BASIS_AREA_WEIGHTED = "area_weighted"
ZONE_BASIS_SINGLE = "single_zone"
ZONE_BASIS_NO_AREA = "first_parcel_no_area"
ZONE_BASIS_NONE = "none"
#: 동률(±5%)·규제성격 상이로 **단일화를 거부**한 상태. `special_parcel` 이 쓰는 그 값이고
#  `app/utils/withheld.py` 의 **표준 보류 어휘**이며, 프론트 `lib/zoning/dominant-zone.ts` 가 안다.
ZONE_BASIS_MIXED_REVIEW = "mixed_review_required"
MIXED_REVIEW_SENTINEL = "mixed_review_required"


#: 현 용도지역만으로는 **아파트를 지을 수 없는** 용도지역(국토계획법 시행령 009419 §71).
#  · 제1종일반주거 → [별표 4] 1호 나목 *"공동주택(**아파트를 제외한다**)"* · 4층 이하
#  · 전용주거(1·2종) → [별표 2]·[별표 3] — 단독·저층 공동주택 중심
#: `buildable_types` 안에 넣지 않는다 — 프론트가 그 리스트의 **모든 원소를 「건축 가능」 칩**으로
#  같은 악센트 색에 그린다(`DevelopmentScenarioCard.tsx`). 경고를 상품명 자리에 넣으면
#  **서로 모순되는 두 칩이 나란히** 서고, 그건 결함을 고친 것이 아니라 **문구로 덮은 것**이다.
#  → 전용 필드 `zone_use_constraint` 로 내보내고 **카드가 경고 스타일로 렌더**한다
#    (`DevelopmentScenarioCard.tsx` · 프론트 락 3건).
#  ★`cons` 에도 싣지만 **화면 소비처는 0** 이다(형제 필드 `pros`·`requirements`·`notes` 는 렌더됨).
#    한때 이 주석이 *"소비되기 전까지는 `cons` 에도 싣는다"* 고 적었는데 **그 임시 경로도 죽어
#    있었다** — 정직 신호를 만들어 놓고 **도달을 확인하지 않은** 것이다(적대 리뷰 3차).
#    지금 `cons` 를 유지하는 이유는 **다른 소비처**(PDF·LLM 요약)가 그 필드를 읽기 때문이다.
APARTMENT_PROHIBITED_MARK = "현 용도지역은 아파트 불허 — 용도지역 변경(종상향) 등 별도 절차 전제"
#: 아파트가 **불허**임을 말하는 부정 라벨(검출기가 자기 라벨을 「아파트 제안」으로 세면 위양성).
_APARTMENT_NEGATIVE_MARKERS = ("아파트 불가", "아파트 불허")


def proposes_apartment(items: list[str]) -> bool:
    """목록이 **아파트를 제안**하는가 — ★부정 라벨은 제외한다.

    적대 리뷰 실측: `any("아파트" in t …)` 가 **자기가 심은** `"(4층 이하 — 아파트 불가)"` 에 걸려
    21종 중 **9종이 위양성**이었다(CLAUDE.md §검증 규율 8 — *"주석에 예시를 적으면 그 예시가
    다음 검사의 위양성이 된다"* 와 같은 형태).
    """
    return any(
        "아파트" in t and not any(m in t for m in _APARTMENT_NEGATIVE_MARKERS)
        for t in (items or [])
    )


def zone_prohibits_apartment(zone: str | None) -> bool:
    """현 용도지역 그대로는 아파트가 **법정 불허**인가."""
    z = zone or ""
    if "전용주거" in z:
        return True
    return ("제1종일반주거" in z) or ("1종일반주거" in z)


#: 평면 도(degree) 거리를 미터로 옮기는 **근사 상수**(북위 37° 부근의 경도 1도 ≈ 88.8km).
#
#  ★★**주의 — 이 값은 「거리 판정」에 쓰면 안 된다.** 처음 이 자리에 쓴 주석은
#    *"이 값이 100m 를 넘으면 **어느 방위든** 넘는다"* 고 단정했는데 **거짓이다.**
#    적대 리뷰가 WGS84 로 실측해 반증했다(서울시청 37.5666°):
#
#        동서 실거리 100.0m → 100.5m 로 **과대보고**(거짓 차단)
#        남북 실거리 125.0m → 100.0m 로 **과소보고**(거짓 허용)
#
#    경도 1도의 실거리는 위도 37.00°에서 89,012m · 37.57°에서 88,343m · 38.00°에서 87,833m 다.
#    **위도 37.06° 위에서는 이 상수가 과대보고**하고(서울·경기 북부 전역), 남북 축은 반대로
#    **약 20% 과소보고**한다(실제 110,987m). 근본은 `shapely.distance()` 가 **경위도 평면의
#    비계량 유클리드**라는 것이다 — **스칼라 하나로는 원리적으로 맞출 수 없다.**
#
#  → 그래서 이 값은 **정보 제공용**(`max_pair_distance_m_min`)으로만 쓴다. 실제 판정이 필요하면
#    `EPSG:5186` 등으로 **투영**하거나 축별 변환(`hypot(dlon*m_lon(lat), dlat*m_lat)`)으로
#    다시 계산해야 하고, 그때는 **위도를 입력으로 받아야** 한다(현 시그니처엔 없다).
#  ★같은 루프의 `TOL_DEG # 약 6m` 는 ≈100,000 m/deg 기준이라 이 상수로는 **5.33m** 다 —
#    같은 `d` 에 두 변환이 공존한다. 투영으로 옮길 때 **함께** 정리해야 한다.
DEG_TO_M_MIN = 88_800.0
#: ★**판정에 쓰지 않는다** — 축이 틀렸기 때문이다. 원문 확인(2026-09-02):
#  · 건축법 §77의15① 의 「100미터」는 **외곽 한계**이고, 조작적 기준은 시행령 **§111①** 이
#    정한다 — ①동일 지역 + ②**너비 12m 이상 도로로 둘러싸인 하나의 구역** 안.
#    **거리 요건이 아니다**(가로구역과 같은 형태). 현 분석은 그 축을 측정하지 못한다.
#  · **3개 이상 대지는 §111③ 이 「500미터」** 다 — 100m 를 적용하면 **거짓 「불가」**가 난다.
#  → 값은 남기되(요건 문구·향후 구현의 기준점) **판정에서는 뺐다.** 되살리려면 위 두 축을
#    먼저 측정할 수 있어야 한다.
COMBINED_BUILDING_MAX_DISTANCE_M = 100.0
#: 시행령 §111③ — 3개 이상 대지의 최단거리 상한.
COMBINED_BUILDING_MAX_DISTANCE_M_3PLUS = 500.0


def combined_building_distance_verdict(adjacency: dict[str, Any] | None) -> tuple[bool | None, float | None]:
    """결합건축의 **거리 요건**을 판정한다 — (충족여부, 실측 최댓값m).

    반환 `None` 은 **미측정**(형상 미확보·분석 실패)이고 「불가」가 아니다 — 양방향으로 건다.
    """
    d = (adjacency or {}).get("max_pair_distance_m_min")
    if d is None:
        return None, None
    return (float(d) <= COMBINED_BUILDING_MAX_DISTANCE_M), float(d)


def _zone_mix_from(enriched: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """전제감사기가 요구하는 `zone_mix` — **형제 스키마**(`special_parcel`)를 따른다.

    감사기의 `dominant_argmax`·`area_conservation` 이 `zone` 과 `area_sqm` 만 읽으므로
    그 둘을 낸다(면적 내림차순 — 형제와 같은 정렬).
    """
    agg: dict[str, float] = {}
    for p in enriched or []:
        z, a = p.get("zone"), p.get("area")
        if not z or not a:
            continue
        agg[str(z).strip()] = agg.get(str(z).strip(), 0.0) + float(a)
    return [{"zone": z, "area_sqm": round(a, 2)}
            for z, a in sorted(agg.items(), key=lambda kv: kv[1], reverse=True)]


def _low_rise_only(zones: list[str]) -> bool:
    """제1종일반주거의 **층수 제한**([별표 4] 1호 머리 — 4층 이하 · 단지형은 5층 이하)."""
    return any(("제1종일반주거" in z) or ("1종일반주거" in z) for z in (zones or []))


def apartment_restricted_zones(enriched: list[dict[str, Any]]) -> list[str]:
    """부지에서 **아파트가 법정 불허**인 용도지역 목록 — ★국토계획법 **§84①** 을 반영한다.

    §84① 원문: *"…각 용도지역등에 걸치는 부분 중 **가장 작은 부분의 규모가 대통령령으로 정하는
    규모 이하**인 경우에는 … **그 밖의 건축 제한 등에 관한 사항은 그 대지 중 가장 넓은 면적이
    속하는 용도지역등에 관한 규정을 적용**한다."*

    ★따라서 **전수 판정은 과잉 억제**다 — 제1종 자투리가 **330㎡ 이하**면 그 부분은
    가장 넓은 용도지역(예: 제2종)에 **흡수**되어 아파트가 가능하다.
    반대로 **330㎡ 초과**면 §84① 이 적용되지 않아 각 부분에 각각의 규정이 적용되므로,
    그 제1종 부분은 여전히 아파트 불허다.

    흡수 규칙은 새로 만들지 않고 기존 `mixed_zone_limits`(§84·시행령 §94)를 **재사용**한다.

    Returns:
        불허 용도지역명 목록(중복 제거·면적 큰 순). 빈 목록이면 제약 없음.
    """
    named = [p for p in (enriched or []) if p.get("zone")]
    if not named:
        return []
    agg: dict[str, float | None] = {}
    for p in named:
        z = str(p["zone"]).strip()
        a = p.get("area")
        if z not in agg:
            agg[z] = float(a) if a else None
        elif a and agg[z] is not None:
            agg[z] += float(a)

    restricted = [z for z in agg if zone_prohibits_apartment(z)]
    if not restricted:
        return []
    if len(agg) < 2:
        return restricted  # 단일 용도지역이면 흡수 여지가 없다
    if not all(v for v in agg.values()):
        # ★면적 미확보 — 흡수 여부를 판정할 수 없다. **불허 쪽으로 남긴다**(고지가 사라지는 것보다
        #   낫다). 이 선택은 §84① 을 「적용하지 않는다」가 아니라 「판정 불가」다.
        return restricted

    from app.services.zoning.legal_zone_limits import mixed_zone_limits

    mix = mixed_zone_limits([{"zone_type": z, "area_sqm": a} for z, a in agg.items()])
    absorbed = mix.get("absorbed")
    if absorbed and absorbed in restricted:
        # 가장 작은 부분이 330㎡ 이하로 흡수됐다 → 그 부분의 건축 제한은 적용되지 않는다.
        restricted = [z for z in restricted if z != absorbed]
    return sorted(restricted, key=lambda z: -(agg[z] or 0.0))


def measured_zone_count(enriched: list[dict[str, Any]]) -> int:
    """실측(추론 아님) 용도지역을 가진 필지 수. ★`select_primary_zone` 과 **같은 술어**를 쓴다.

    적대 리뷰 J-2: 배선을 순수함수로 꺼낸 뒤에도 `simulate()` 안에 **인라인 복제본**이 남아
    `primary_zone_is_inferred`(프론트 소비처 있음)를 조용히 죽일 수 있었다.
    술어를 한 곳에 두면 드리프트가 **원리적으로** 불가능해진다.
    """
    return sum(1 for p in (enriched or [])
               if p.get("zone") and p.get("zone_source") != "keyword_inference")


def select_primary_zone(enriched: list[dict[str, Any]], site_zone_type: str = "") -> tuple[str, str]:
    """부지 대표 용도지역을 고르는 **배선 전체**를 순수함수로 꺼낸다.

    ★기계 변이(`scripts/mutate_changed.py`)가 이 배선의 두 줄(`_all_rows` 대입 · `if not
      primary_zone` 폴백)을 **생존**시켰다 — `simulate()` 안에 인라인이라 태울 방법이 없었다.
      판단은 `dominant_zone_by_area` 가, **어느 모집단을 줄지**는 여기가 정한다.

    우선순위: ①실측 용도지역(추론 제외) → ②전체(추론 포함) → ③호출자가 준 `site.zone_type`.
    """
    measured = [
        {"zone": p.get("zone"), "area": p.get("area")} for p in (enriched or [])
        if p.get("zone") and p.get("zone_source") != "keyword_inference"
    ]
    assert len(measured) == measured_zone_count(enriched), "술어 드리프트"
    every = [{"zone": p.get("zone"), "area": p.get("area")} for p in (enriched or []) if p.get("zone")]
    zone, basis = dominant_zone_by_area(measured or every)
    if not zone:
        return (site_zone_type or ""), ZONE_BASIS_NONE
    return zone, basis


def dominant_zone_by_area(rows: list[dict[str, Any]]) -> tuple[str, str]:
    """면적가중 **우세** 용도지역을 고른다 — ★「첫 필지」가 아니다.

    종전 `zones_measured[0]` 은 배열 선두를 썼다. 라이브 실측(2026-09-02):
    `zones=[제1종일반주거, 제2종일반주거]` 인 부지에서 `제1종` 이 선택돼,
    같은 응답의 `far_effective_blended`(면적가중 156.9)와 **기준이 어긋났다**
    — 용적률은 혼합인데 용도지역 라벨만 첫 필지였다.

    규칙은 새로 만들지 않고 `mixed_zone_limits`(국토계획법 §84·시행령 §94 —
    면적가중 및 330㎡ 이하 흡수)를 **재사용**한다. 그 함수는 이미 4개 표면이 쓴다.

    Args:
        rows: [{"zone": 용도지역명, "area": 면적㎡}] — 부지 내 각 필지.
    Returns:
        (zone, basis) — basis 는 **무엇을 근거로 골랐는지**를 호출부가 구별할 수 있게 한다.
        면적 미확보 시 첫 필지로 떨어지되 그 사실을 `ZONE_BASIS_NO_AREA` 로 **말한다**
        (조용히 첫 필지를 쓰면 종전 결함이 그대로 남는다).
    """
    named = [r for r in (rows or []) if r.get("zone")]
    if not named:
        return "", ZONE_BASIS_NONE
    uniq = list(dict.fromkeys(str(r["zone"]).strip() for r in named))
    if len(uniq) == 1:
        return uniq[0], ZONE_BASIS_SINGLE
    if not all(r.get("area") for r in named):
        return str(named[0]["zone"]).strip(), ZONE_BASIS_NO_AREA
    # ★형제(`special_parcel._aggregate_integrated_zoning`)의 판정을 **그대로 따른다.**
    #   실측(2026-09-04) — 4모집단 중 **3개가 갈렸다**:
    #     상업+주거 → 형제 `mixed_review_required` / 내 종전 `일반상업지역`   ★임의 단일화
    #     동률(±5%) → 형제 `mixed_review_required` / 내 종전 `제3종일반주거지역`
    #     녹지+주거 → 형제 `mixed_review_required` / 내 종전 `제2종일반주거지역`
    #   ★볼트가 *"형제가 이미 옳게 한다 — **시뮬레이터만 자기 방식을 만들었다**"* 라고
    #     적어 둔 그 자리인데, `#940` 이 RC-2 를 고치면서 **같은 클래스의 약한 판본**을 다시 만들었다.
    #   생태계는 이 센티널을 이미 안다 — 백엔드 6곳 소비 · 프론트 `lib/zoning/dominant-zone.ts`
    #   (`MIXED_REVIEW_SENTINEL`) · `app/utils/withheld.py` 의 **표준 보류 어휘**.
    from app.services.zoning.special_parcel import _aggregate_integrated_zoning

    agg = _aggregate_integrated_zoning(
        [{"zone_type": str(r["zone"]).strip(), "area_sqm": float(r["area"]),
          "areaSqm": float(r["area"])} for r in named]
    )
    dom = agg.get("dominant_zone")
    if dom == MIXED_REVIEW_SENTINEL:
        # ★「보류」를 «면적가중으로 골랐다» 고 말하면 거짓이다 — 근거도 보류여야 한다.
        return MIXED_REVIEW_SENTINEL, ZONE_BASIS_MIXED_REVIEW
    if dom:
        return str(dom), ZONE_BASIS_AREA_WEIGHTED
    # ★형제가 `None` 을 내면(판정 불가) **첫 필지로 지어내지 않는다** — 보류를 명시한다.
    return MIXED_REVIEW_SENTINEL, ZONE_BASIS_MIXED_REVIEW


def _is_residential(zone: str) -> bool:
    return "주거" in (zone or "")


def _is_commercial(zone: str) -> bool:
    return "상업" in (zone or "") or "준주거" in (zone or "")


class DevelopmentScenarioSimulator:
    async def simulate(
        self,
        address: str,
        parcels: list[str] | list[dict[str, Any]] | None = None,
        site: dict[str, Any] | None = None,
        use_llm: bool = True,
    ) -> dict[str, Any]:
        site = site or {}
        addrs = self._merge(address, parcels)
        # ★중복제거 **전** 요청 수 — 붕괴를 말할 수 있게(아래 ctx 참조).
        requested_count = self._requested_count(address, parcels)
        multi = len(addrs) >= 2

        # ★호출자가 이미 아는 값(면적·용도지역)을 받아 둔다 — `ParcelsIn` 정규화를 거친
        #   dict 행이면 `area_sqm`·`zone_type` 이 실려 온다. 이 값들은 우리 API 가 이미 준
        #   것이라 새 진실원천이 아니다(재조회 불필요).
        supplied = self._supplied_rows(parcels)

        # 부지 정보 수집(단일/다필지)
        enriched, subway_m = await self._collect(addrs, site)

        # ── 조회로 못 채운 칸만 호출자 값으로 메운다(**덮어쓰기 금지**) ──────────────
        # ★진실원천 우선순위: 토지대장/VWorld 실측 > 호출자 제공값. 실측이 있으면 그대로 두고,
        #   **비어 있을 때만** 메운다. 반대로 하면 클라이언트 입력이 실측을 이겨 면적을
        #   부풀릴 수 있다(공개 엔드포인트라 더 그렇다).
        for row in enriched:
            src = supplied.get((row.get("address") or "").strip())
            if not src:
                continue
            if row.get("area") is None and src.get("area_sqm") is not None:
                row["area"] = src["area_sqm"]
                row["area_source"] = "caller_supplied"
            if not row.get("zone") and src.get("zone_type"):
                row["zone"] = src["zone_type"]
                row["zone_type"] = src["zone_type"]
                row["zone_source"] = "caller_supplied"

        # ── 미해석 필지 정직화 ────────────────────────────────────────────────
        # ★실측(2026-08-19): 주소가 해석되지 않으면 `analyze_by_address` 가
        #   `pnu=None · land_area_sqm=None · zone_source='keyword_inference'` 를 낸다.
        #   종전 `sum(p.get("area") or 0)` 은 그 필지를 **조용히 0㎡** 로 더해, 다필지 부지의
        #   총면적이 실제보다 작게 나오고 면적 게이트가 개발방식을 대량 '불가' 로 막았다.
        #   합계 자체는 바뀌지 않는다(미해석은 지금도 0을 더한다) — **몇 개가 빠졌는지를
        #   드러내는 것**이 이 블록의 전부다. 조용한 축소가 조용한 오답을 만든다.
        unresolved = [
            {"address": p.get("address"), "reason": (
                "용도지역 추론값(주소 미해석 — 조회 실패)"
                if p.get("zone_source") == "keyword_inference" else "필지 조회 실패"
            )}
            for p in enriched
            if not p.get("pnu") or p.get("area") is None
        ]
        resolved = [p for p in enriched if p.get("pnu") and p.get("area") is not None]

        # ── 계획 상한·허용용도 미확보 집계(다필지) ─────────────────────────────────
        # 한 필지라도 계획구역이면 부지 전체의 제안이 미검증이다(분할 개발이 아니면
        # 그 필지를 빼고 사업이 성립하지 않는다) — 보수측으로 부지 단위 고지한다.
        _plan_rows = [p.get("plan_limit_unknown") for p in enriched if p.get("plan_limit_unknown")]
        plan_unknown_agg = None
        if _plan_rows:
            _districts = list(dict.fromkeys(
                d for row in _plan_rows for d in (row.get("districts") or [])
            ))
            plan_unknown_agg = {
                **_plan_rows[0],
                "districts": _districts,
                "parcel_count": len(_plan_rows),
            }
        total_area = sum(p.get("area") or 0 for p in enriched)
        # ★용적률 출처: 실효(현행·조례 반영)를 시나리오 기준으로 사용(결함A 교정).
        #   법정상한은 라벨 구분용으로 별도 보관.
        far_effective = self._blended_far(enriched, "max_far")
        far_legal = self._blended_far(enriched, "max_far_legal")
        # ★실측 용도지역을 추론값보다 앞세운다 — 종전 `zones[0]` 은 **첫 필지**를 쓰므로,
        #   1번 필지 주소만 해석에 실패해도 **지어낸 용도지역이 부지 전체의 기준**이 됐다.
        #   (면적가중 우세용도까지 가는 것은 별건 — 여기서는 '날조가 실측을 이기는' 역전만 막는다.)
        # ★인라인 복제본을 제거하고 `measured_zone_count` 한 곳으로 모은다(적대 리뷰 J-2).
        measured_zone_n = measured_zone_count(enriched)
        zones = [p.get("zone") for p in enriched if p.get("zone")]
        # ★선두가 아니라 **면적가중 우세**를 쓴다. 실측(2026-09-02) — `zones=[제1종,제2종]` 부지에서
        #   `제1종` 이 선택돼 같은 응답의 `far_effective_blended`(면적가중)와 기준이 어긋났다.
        #   실측 용도지역(추론 제외) 우선순위는 종전 그대로 유지한다.
        primary_zone, primary_zone_basis = select_primary_zone(enriched, site.get("zone_type") or "")
        near_station = (subway_m is not None and subway_m <= 500) or any(
            "역세권" in (p.get("zone") or "") for p in enriched
        )

        # ── 특이부지 게이트(orchestrator.recommend:66-84 패턴 복제·비대칭 해소) ──
        #   임야/산지/농지/GB/맹지/학교용지 등 비일상 토지에도 20개 시나리오를 찍어내던 결함B 차단.
        #   developability∈{BLOCKED} 또는 resolvable∈{NO}면 시나리오 생성 중단·정직고지(가짜 면적/규모 미산정).
        #   CONDITIONAL/PRECONDITION은 시나리오를 생성하되 경고·선행절차를 동반(아래 ctx로 전파).
        from app.services.zoning.special_parcel import (
            detect_multi_parcel,
            detect_special_parcel,
        )

        if multi:
            special_gate = detect_multi_parcel(enriched)
        else:
            sp = detect_special_parcel(enriched[0]) if enriched else None
            special_gate = sp  # None이면 일상 부지(특이 없음)

        # ── WP-B: 개발행위허가 절차게이트(국토계획법 §56~58) — 주 필지 기준 additive 부착 ──
        #   자연녹지 등 비도시·녹지 지역에 개발방식 20종을 밀도한도만으로 찍어내던 과대낙관을 봉합한다
        #   (건축 전 개발행위허가 대상 여부·기준을 별도 게이트로 고지). 실패는 무손상(graceful).
        dev_act_gate = None
        try:
            from app.services.permit.dev_act_permit_gate import assess_dev_act_permit

            if enriched:
                dev_act_gate = assess_dev_act_permit(enriched[0])
        except Exception as e:  # noqa: BLE001 — 개발행위허가 게이트 실패는 시나리오 산출 무손상
            logger.warning("개발행위허가 게이트 스킵(graceful)", err=str(e)[:160])

        if special_gate and (
            special_gate.get("developability") in {"BLOCKED"}
            or special_gate.get("resolvable") in {"NO"}
        ):
            # ★P0(개발불가만 제시 해소): 다필지에서 '일부' 필지만 차단(구거/하천/GB 등)이면, 차단필지를
            #   제외한 '가용 필지'로 개발방식을 재산정해 함께 제시한다(detect_multi_parcel의 max/min 게이트가
            #   최악 1필지로 전체를 BLOCKED로 떨군 것을 보완). 신규 산식 0 — 가용필지로 simulate()를 1회
            #   재귀호출(차단필지 없으니 정상경로로 시나리오 산출). 필지수 strict 감소라 무한재귀 불가.
            available_subset = None
            excluded_parcels: list[dict[str, Any]] = []
            if multi:
                avail_addrs: list[str] = []
                for p in enriched:
                    sp_i = detect_special_parcel(p)
                    blocked_i = bool(sp_i and (
                        sp_i.get("developability") in {"BLOCKED"} or sp_i.get("resolvable") in {"NO"}))
                    if blocked_i:
                        excluded_parcels.append({
                            "address": p.get("address"), "zone": p.get("zone"),
                            "area": p.get("area"), "gate": sp_i})
                    elif p.get("address"):
                        avail_addrs.append(p.get("address"))
                if avail_addrs and len(avail_addrs) < len(enriched):
                    try:
                        sub = await self.simulate(
                            avail_addrs[0], parcels=avail_addrs[1:], site=site, use_llm=False)
                        # 가용필지가 또 전면 차단이면(이중특이) None 처리 — 가짜 제시 금지.
                        if sub.get("scenarios"):
                            _sub_site = sub.get("site") or {}
                            available_subset = {
                                "parcels": avail_addrs,
                                "parcel_count": len(avail_addrs),
                                "total_area_sqm": _sub_site.get("total_area_sqm"),
                                # ★★2026-09 — **세 번째 site 표면**이다. 종전엔 `total_area_sqm` 만
                                #   복사하고 정직 필드를 **전부 버렸다**. 화면은 이 값을 **성공색**
                                #   박스에 「가용 N필지 · X㎡」로 **단정** 표시한다 — 부분합인데
                                #   부분합이라 말하지 않는 자리였다.
                                #   ★그리고 형제 패리티 락이 이것을 **구조적으로 못 봤다**:
                                #     선별자가 `resolved_parcel_count` 였는데 **그 키가 빠진 것이
                                #     바로 결함**이라, 결함 있는 dict 만 정확히 모집단에서 빠졌다.
                                #     («파생의 축» 때문에 파생형 스윕이 무력화된 형태)
                                "resolved_parcel_count": _sub_site.get("resolved_parcel_count"),
                                "unresolved_parcels": _sub_site.get("unresolved_parcels"),
                                "requested_parcel_count": _sub_site.get("requested_parcel_count"),
                                "collapsed_parcel_count": _sub_site.get("collapsed_parcel_count"),
                                "area_is_partial": _sub_site.get("area_is_partial"),
                                "scenarios": sub.get("scenarios"),
                                "recommended": sub.get("recommended"),
                                "pyeong_classification": sub.get("pyeong_classification"),
                            }
                    except Exception as e:  # noqa: BLE001 — subset 재산정 실패는 본 응답을 막지 않음
                        logger.warning("가용필지 subset 재산정 스킵(graceful)", err=str(e)[:160])
            # 후보생성 중단 — 가짜 개발규모/시나리오는 미산정(무목업). 다만 ★사용자 피드백:
            #   '개발 불가'로 끝내지 말고 인허가·도시계획 변경 등 '개발가능 방안(선행절차)'을 제시한다.
            #   special_parcel이 이미 보유한 resolution_paths·permit_prerequisites·alternatives·법령을
            #   추천 '방안'으로 surface(가짜 규모는 여전히 미산정 — 정직).
            disclosure = special_gate.get("honest_disclosure") or (
                "통상 절차로는 즉시 개발이 어려운 제약이 포함됩니다."
            )
            # 해결 방안 집계(게이트 resolution_paths + 각 factor permit_prerequisites + alternatives).
            methods, ref_keys, alternatives = self._resolution_from_gate(special_gate)
            try:
                from app.services.legal.legal_reference_registry import get_legal_refs
                method_refs = get_legal_refs(ref_keys) if ref_keys else []
            except Exception:  # noqa: BLE001
                method_refs = []
            # 추천: '개발 불가'가 아니라 '선행절차(도시계획 변경·인허가) 통과 시 개발 가능' 방안 제시.
            has_path = bool(methods)
            # ★가용필지 subset이 산출됐으면 그것을 우선 추천(개발불가→가용필지 실개발방식).
            _sub = available_subset or {}
            has_subset = bool(_sub.get("scenarios"))
            if has_subset:
                _sub_rec = _sub.get("recommended") or {}
                rec_scheme = f"가용 {_sub.get('parcel_count')}필지 개발 — {_sub_rec.get('scheme') or '단순 건축'}"
                rec_reason = (f"일부 필지({len(excluded_parcels)}개: 구거/하천/GB 등)는 통상 개발이 어려우나, "
                              f"이를 제외한 가용 {_sub.get('parcel_count')}필지"
                              + (f"(통합 {_sub.get('total_area_sqm')}㎡)" if _sub.get('total_area_sqm') else "")
                              + f"로는 '{_sub_rec.get('scheme') or '단순 건축'}' 등 개발이 가능합니다. " + disclosure)
            elif has_path:
                rec_scheme = "특이부지 개발 — 선행절차(도시계획 변경·인허가) 방안"
                rec_reason = (disclosure
                              + " 다만 아래 선행절차(인허가·도시계획 변경 등)를 거치면 개발이 가능할 수 있습니다.")
            else:
                rec_scheme = "현 제약상 통상 개발 불가 — 대안 검토"
                rec_reason = (disclosure
                              + " 통상 개발경로가 막혀 있어, 대안(필지 제외·용도 재검토)을 검토하세요.")
            return {
                "site": {
                    "address": address, "region": self._region(address),
                    "multi": multi, "parcel_count": len(addrs),
                    "total_area_sqm": round(total_area, 1) if total_area else None,
                    # ★형제 미러 — 아래 정상경로 ctx 와 **같은 정직 키**를 낸다. 차단 경로에서
                    #   빠지면 정작 "왜 막혔나"를 설명해야 할 화면에서 신호가 사라진다.
                    "resolved_parcel_count": len(resolved),
                    "unresolved_parcels": unresolved,
                    # ★★2026-08-29 — `#933` 이 이 **형제 미러를 안 쓸었다.** 정상경로 ctx 에만
                    #   붕괴 필드를 넣어, **차단 경로에서는 「77필지를 요청했는데 1로 줄었다」를
                    #   말하지 못했다.** 바로 위 주석이 그 위험을 이미 적어 두었는데도 놓쳤다:
                    #   *"차단 경로에서 빠지면 정작 «왜 막혔나»를 설명해야 할 화면에서 신호가 사라진다."*
                    #   ★사용자가 신고한 44㎡ 화면이 **정확히 이 차단 경로**였다(특이부지 → 불가).
                    "requested_parcel_count": requested_count,
                    "collapsed_parcel_count": max(0, requested_count - len(addrs)),
                    "area_is_partial": bool(unresolved) or requested_count > len(addrs),
                    "plan_limit_unknown": plan_unknown_agg,   # 형제 미러
                    "primary_zone": primary_zone, "primary_zone_basis": primary_zone_basis, "zones": zones,
            # ★§84① 흡수를 반영한 아파트 불허 용도지역(면적이 여기서만 보인다).
            "apartment_restricted_zones": apartment_restricted_zones(enriched),
                    "primary_zone_is_inferred": bool(primary_zone) and measured_zone_n == 0,
                    "special_parcel_gate": special_gate,
                    "dev_act_permit_gate": dev_act_gate,
                },
                "special_parcel_gate": special_gate,
                "dev_act_permit_gate": dev_act_gate,
                "scenarios": [],  # 전체(full) 기준 시나리오는 미생성(무목업) — 가용필지는 available_subset.
                "recommended": {
                    "scheme": rec_scheme,
                    "est_far": (_sub.get("recommended") or {}).get("est_far") if has_subset else None,
                    "reason": rec_reason,
                },
                # ★P0: 차단필지 제외 '가용 필지'로 실제 산출한 개발방식(개발불가만 제시 해소). 없으면 None.
                "available_subset": available_subset,
                "excluded_parcels": excluded_parcels,
                # ★개발가능 방안(선행절차) — 인허가·도시계획 변경 등 actionable 경로 + 법령(verified).
                "resolution_methods": methods,
                "resolution_legal_refs": method_refs,
                "alternatives": alternatives,
                "developable_via_precondition": has_path,
                "fallback_simple_build": None,
                "magdo_summary": None,
                "honest_disclosure": disclosure,
                # 선행절차 경로 또는 가용필지 개발이 있으면 완전 blocked 아님.
                "blocked": (not has_path) and (not has_subset),
            }

        # 인접성: 통합개발(합필/일단지)은 필지가 맞닿아야 가능
        adjacency = self._adjacency(enriched) if multi else {"contiguous": True, "components": 1, "note": "단일 필지"}
        integration_ok = adjacency.get("contiguous") is not False  # None(미상)은 허용하되 주의

        # 건축물 노후도·세대수·소유구분(실데이터)
        buildings = self._buildings(enriched)

        # 블록(주변 필지 일괄) 노후도 — 주거지역에서만(가로주택/모아/정비 노후요건)
        block = None
        if _is_residential(primary_zone):
            primary_coords = (enriched[0] or {}).get("coords") if enriched else None
            block = await self._block_aging(primary_coords, radius_m=100)

        ctx = {
            "address": address, "region": self._region(address),
            "multi": multi, "parcel_count": len(addrs),
            "total_area_sqm": round(total_area, 1) if total_area else None,
            # ★총면적의 **분모**를 함께 낸다 — `total_area_sqm` 만 보면 미해석 필지가 0으로
            #   섞여 있어도 "이 부지는 원래 작다"로 읽힌다(면적 게이트가 개발방식을 막은 이유를
            #   화면이 설명할 수 없었다). 몇 개 중 몇 개가 실측인지를 같이 낸다.
            "resolved_parcel_count": len(resolved),
            "unresolved_parcels": unresolved,
            # ★요청 수(중복제거 **전**)와 붕괴 수 — `parcel_count` 만으로는 «원래 1필지였다» 와
            #   «77을 요청했는데 1로 줄었다» 를 **구별할 수 없다**(2026-08-28 실측 결함).
            "requested_parcel_count": requested_count,
            "collapsed_parcel_count": max(0, requested_count - len(addrs)),
            # 면적이 부분합인 두 경로 — ①조회 실패(unresolved) ②주소 붕괴(collapsed).
            #   종전엔 ①만 봤다. ②가 바로 44㎡ 사고의 경로다.
            "area_is_partial": bool(unresolved) or requested_count > len(addrs),
            # ★계획이 한도·**허용용도**를 정하는 구역인데 그 내용을 못 구했다면, 아래 개발방식·
            #   세대수 제안은 전부 미검증이다. 수치 경고만 달고 용도 추천을 그대로 내보내면
            #   더 비싼 오답(불허 용도 추천)이 조용히 나간다.
            "plan_limit_unknown": plan_unknown_agg,
            "primary_zone": primary_zone, "primary_zone_basis": primary_zone_basis, "zones": zones,
            # ★§84① 흡수를 반영한 아파트 불허 용도지역(면적이 여기서만 보인다).
            "apartment_restricted_zones": apartment_restricted_zones(enriched),
            # 대표 용도지역이 조회값인지 추론값인지 — 추론값이면 화면이 단정하면 안 된다.
            "primary_zone_is_inferred": bool(primary_zone) and measured_zone_n == 0,
            # ★시나리오 산정 기준 = 실효 용적률(현행·조례 반영). 법정상한은 라벨 구분용으로 병기.
            "far_effective_blended": far_effective,
            "far_legal_blended": far_legal,
            "near_station_m": subway_m, "near_station": near_station,
            "adjacency": adjacency, "integration_feasible": integration_ok,
            "buildings": buildings, "block_aging": block,
            # 특이부지 게이트(통과/조건부) 결과 — CONDITIONAL/PRECONDITION이면 경고·선행절차 동반.
            "special_parcel_gate": special_gate,
            # 개발행위허가 절차게이트(WP-B) — 대상 필지면 개발가능=허가 판정 전제임을 고지.
            "dev_act_permit_gate": dev_act_gate,
            "parcels": [{"address": p.get("address"), "zone": p.get("zone"),
                         "area": p.get("area"), "max_far": p.get("max_far"),
                         "max_far_legal": p.get("max_far_legal"),
                         "owner_type": p.get("owner_type"), "bldg_year": p.get("bldg_year"),
                         "units": p.get("units")} for p in enriched],
        }

        scenarios = self._scenarios(ctx)

        # ── ★전제 감사 — **이미 있는 감시망을 켠다**(새로 만드는 것이 아니다) ────────────
        #   실측(2026-09-04): `premise_audit.audit()` 호출부가 **`routers/auto_zoning.py` 1곳뿐**
        #   이라 이 경로는 **감시망 밖**이었다. 등록된 전제 6종 중 `dominant_argmax` 는
        #   `#940` 의 RC-2(첫 필지를 우세 용도지역으로 씀)를 **정확히** 잡는다 —
        #   그 감사기를 신고 부지 형상으로 직접 태워 확인했다(종전 발화 / 수정 후 침묵).
        #   ★**읽기 전용이다** — 판정(`applicable`)을 바꾸지 않고 위반을 표면에 싣기만 한다.
        premise_audit_result: dict[str, Any] | None = None
        try:
            from app.services.zoning import premise_audit

            _zm = _zone_mix_from(enriched)
            premise_audit_result = premise_audit.audit({
                "dominant_zone": primary_zone,
                "zone_mix": _zm,
                "per_parcel": [
                    {"zone": p.get("zone"), "area_sqm": p.get("area")} for p in enriched
                ],
                "integrated": {"total_area_sqm": total_area},
                "scenario": {"top3": scenarios[:3]},
                "_request_parcel_count": requested_count,
            })
        except Exception as e:  # noqa: BLE001
            # ★감사기 사망을 «위반 0» 으로 뭉개지 않는다 — 사유를 싣는다.
            logger.warning("전제 감사 실패", err=str(e)[:120])
            premise_audit_result = {"ok": None, "reason": "audit_failed", "detail": str(e)[:200]}

        # 적합도 정렬(가능>조건부>불가, est_far 내림차순)
        rank = {"가능": 0, "조건부": 1, "불가": 2}
        scenarios.sort(key=lambda s: (rank.get(s["applicable"], 3), -(s.get("est_far") or 0)))
        applicable = [s for s in scenarios if s["applicable"] in ("가능", "조건부")]
        recommended = applicable[0] if applicable else next(
            s for s in scenarios if s["scheme"] == "단순 건축"
        )

        # 매도청구 요약(추천안 기준 + 다필지 잔여 추정)
        magdo_summary = self._magdo_summary(recommended, ctx)

        result: dict[str, Any] = {
            "site": ctx,
            "scenarios": scenarios,
            "recommended": {"scheme": recommended["scheme"], "est_far": recommended.get("est_far"),
                            "reason": recommended.get("notes") or recommended.get("pros", [""])[0]},
            "fallback_simple_build": next(s for s in scenarios if s["scheme"] == "단순 건축"),
            "magdo_summary": magdo_summary,
            # ★평수 티어 매트릭스(소규모 필지 가능/조건부/불가 상세 분류) — 순수 additive 뷰.
            "pyeong_classification": self._classify_by_pyeong_tier(total_area, scenarios),
            # 개발행위허가 절차게이트(WP-B) 최상위 노출 — 대상 필지의 개발규모=허가 판정 전제.
            "dev_act_permit_gate": dev_act_gate,
            # ★전제 감사 결과 — 이 경로가 감시망 밖이었다(호출부 1곳뿐). 판정은 안 바꾸고
            #   위반만 싣는다. ★`#940` 에서 «백엔드 계약만 서고 화면 소비처 0» 으로 데였으므로
            #   여기 싣는 것만으로 끝내지 않는다 — 소비처는 별도 좌표로 남긴다.
            "premise_audit": premise_audit_result,
        }
        # 특이부지가 조건부/선행절차 부지면 정직 고지를 최상위로 노출(시나리오는 산정하되 경고 동반).
        #   산지전용·농지전용·도시계획시설 폐지 등 선행절차 통과를 전제로만 개발 가능함을 명시.
        # ★전역전파방지(SSOT): 하드코딩 튜플 대신 GATE_TENTATIVE_DEVELOPABILITY 멤버십으로 판정한다.
        #   이렇게 하면 NEEDS_OFFICIAL_SURVEY(임야 공식 산림조사 필요) 등 새 잠정 등급이 자동으로
        #   최상위 honest_disclosure를 받아, 임야 부지가 정직 고지 없이 시나리오만 노출되던 결함을 막는다.
        #   (CAUTION은 GATE_TENTATIVE에 없으므로 명시적으로 포함한다.)
        from app.services.zoning.special_parcel import GATE_TENTATIVE_DEVELOPABILITY

        if special_gate and (
            special_gate.get("developability") in GATE_TENTATIVE_DEVELOPABILITY
            or special_gate.get("developability") == "CAUTION"
        ):
            result["special_parcel_gate"] = special_gate
            result["honest_disclosure"] = special_gate.get("honest_disclosure") or (
                "특이 토지특성으로 인허가·전용·도시계획 변경 등 선행절차 통과를 조건으로만 개발이 가능합니다. "
                "아래 시나리오의 개발규모는 선행절차 통과를 전제로 한 잠재치입니다."
            )
        if use_llm:
            result["ai"] = await self._llm(ctx, scenarios)

        # ── 표준 근거 블록(#5): 통합면적·실효용적률·추천 사업방식의 산식·법령을 가산(graceful). ──
        # 무목업: 실제 산출한 총면적·블렌디드 실효용적률·추천 시나리오(가능/조건부 1위)만 트레이스.
        # 법령(verified): 국토계획법 제78조(far_law·용적률)·제76조(zone_use·용도제한)·제52조(district_unit_plan).
        # build_evidence_block 실패해도 시뮬레이션 결과는 그대로 반환(가산·정직).
        try:
            from app.services.data_validation.evidence_contract import build_evidence_block

            ev_items: list[dict[str, Any]] = []
            if total_area:
                ev_items.append({
                    "label": "통합 부지면적",
                    "value": f"{round(total_area, 1):,}㎡",
                    "basis": f"필지 {len(addrs)}개 면적 합산" if multi else "단일 필지 면적",
                })
            if far_effective:
                ev_items.append({
                    "label": "실효 용적률(현행)",
                    "value": f"{far_effective}%",
                    "basis": ("면적가중 블렌디드 실효용적률(현행·조례 반영)"
                              + (f", 법정상한 {far_legal}%" if far_legal else "")),
                })
            ev_items.append({
                "label": "추천 사업방식",
                "value": recommended.get("scheme"),
                "basis": ("적합도(가능>조건부>불가)·예상 용적률 정렬 1위"
                          + (f", 예상 용적률 {recommended.get('est_far')}%" if recommended.get("est_far") else "")),
            })
            if applicable:
                ev_items.append({
                    "label": "적용가능 사업방식 수",
                    "value": len(applicable),
                    "basis": f"정책별 적용요건 판정 결과 '가능/조건부' {len(applicable)}건 / 전체 {len(scenarios)}건",
                })
            result["evidence"] = build_evidence_block(
                items=ev_items,
                legal_ref_keys=["far_law", "zone_use", "district_unit_plan"],
                sources=["vworld_zoning"],
            )
        except Exception:  # noqa: BLE001 — 근거 블록 실패는 시뮬레이션 결과를 막지 않음.
            pass

        return result

    # ── 부지 수집 ──
    @staticmethod
    def _merge(address: str, parcels: list[str] | list[dict[str, Any]] | None) -> list[str]:
        """주소 목록으로 수렴. ★dict 행(ParcelsIn 정규화 결과)도 받는다 — 종전처럼
        `str.strip()` 을 바로 부르면 dict 가 오는 순간 AttributeError 다."""
        out: list[str] = []
        for item in [address, *(parcels or [])]:
            if isinstance(item, dict):
                a = item.get("address")
            elif isinstance(item, str) or item is None:
                a = item
            else:
                # 그 외 타입(int 등)은 **드롭**한다 — `str(item)` 으로 승격하면 존재하지 않는
                # 주소가 필지로 진입한다(무날조). `normalize_parcels` 와 동일 정책.
                continue
            a = (a or "").strip()
            if a and a not in out:
                out.append(a)
        return out

    @staticmethod
    def _requested_count(
        address: str, parcels: list[str] | list[dict[str, Any]] | None,
    ) -> int:
        """호출자가 **요청한** 필지 수 — 중복제거 **전**, 주소가 있는 것만 센다.

        ★`_merge` 는 주소 문자열로 중복제거한다. 그 자체는 옳지만(같은 주소는 같은 필지다),
          **주소에 지번이 없으면 서로 다른 필지가 같은 문자열이 되어 통째로 붕괴**한다.
          2026-08-28 라이브 실측: 77필지 부지(86,755㎡)가 **1필지 44㎡** 로 시뮬레이션돼
          「도시개발사업 1만㎡ 미달」 등 **19개 개발방식이 거짓 '불가'** 로 막혔다.

        ★★그때 `parcel_count`(= 중복제거 **후**)만 보면 *"원래 1필지였다"* 와 구별되지 않는다.
          이 함수는 **분모**를 만든다 — *"몇 개를 요청했는데 몇 개로 줄었는가"* 를 말할 수 있게.
          같은 파일이 이미 적어 둔 원칙이다: **조용한 축소가 조용한 오답을 만든다.**
        """
        def _addr(item: Any) -> str:
            a = item.get("address") if isinstance(item, dict) else (
                item if isinstance(item, str) else None
            )
            return (a or "").strip()

        rows = [a for a in (_addr(i) for i in (parcels or [])) if a]
        rep = _addr(address)
        # ★★대표주소를 **이중으로 세지 않는다.** 프로덕션 호출부는 `parcels` 선두에 대표주소를
        #   넣는다(`buildAnalysisParcelAddrs`: `[target, ...]`). 그것을 또 세면 정상 다필지에서
        #   `requested > used` 가 되어 **붕괴가 없는데 빨간 경보**가 뜬다 — 독립 리뷰 실측.
        #   ★내 첫 위양성 테스트는 `("A", ["B","C"])` 였는데 그건 **프로덕션이 보내지 않는 형태**다.
        #     픽스처가 두 모집단을 안 가르면 위양성은 영원히 안 보인다.
        return len(rows) + (1 if rep and rep not in rows else 0)

    @staticmethod
    def _supplied_rows(
        parcels: list[str] | list[dict[str, Any]] | None,
    ) -> dict[str, dict[str, Any]]:
        """호출자가 준 dict 행 → {주소: {area_sqm, zone_type}}. str 행은 줄 게 없으므로 제외."""
        out: dict[str, dict[str, Any]] = {}
        for item in parcels or []:
            if not isinstance(item, dict):
                continue
            addr = (item.get("address") or "").strip()
            if not addr:
                continue
            area = item.get("area_sqm")
            if area is None:
                area = item.get("areaSqm")
            try:
                area = float(area) if area is not None else None
            except (TypeError, ValueError):
                area = None
            # 0·음수 면적은 값이 아니다(0을 채우면 미해석과 구분이 사라진다).
            out[addr] = {
                "area_sqm": area if (area or 0) > 0 else None,
                "zone_type": item.get("zone_type") or item.get("zoneCode"),
            }
        return out

    async def _collect(self, addrs: list[str], site: dict) -> tuple[list[dict], float | None]:
        import asyncio

        from app.services.zoning.auto_zoning_service import ZONE_LIMITS, AutoZoningService

        az = AutoZoningService()

        from app.services.external_api.building_registry_service import BuildingRegistryService
        from app.services.external_api.vworld_service import VWorldService

        vworld = VWorldService()
        breg = BuildingRegistryService()

        from app.services.land_intelligence.far_tier_service import calc_effective_far
        from app.services.land_intelligence.ordinance_service import OrdinanceService

        _ord_svc = OrdinanceService()

        async def one(a: str) -> dict:
            try:
                r = await az.analyze_by_address(a)
                zl = r.get("zone_limits") or {}
                # 법정상한(라벨/ZONE_LIMITS 기준) — 별도 보관(라벨 구분용).
                far_legal = zl.get("max_far_pct") or zl.get("max_far")
                if not far_legal and r.get("zone_type"):
                    lim = ZONE_LIMITS.get((r["zone_type"] or "").replace(" ", ""))
                    far_legal = lim.get("max_far") if lim else None
                # ★실효 용적률(현행 baseline·조례 반영) — orchestrator._baseline_far와 동일 SSOT.
                #   법정상한만 쓰던 결함A 교정. 조회 실패/미산정 시 법정상한으로 폴백(회귀0).
                zone_type = r.get("zone_type") or ""
                far = far_legal
                plan_unknown = None
                if zone_type:
                    # ★조례 실효 반영 — local_ordinance가 비면 calc_effective_far가 법정값을 반환하므로,
                    #   OrdinanceService로 조례 한도를 조회해 주입(permits/parcels-info와 동일 — 서울 제1종 150 등 실효).
                    try:
                        ordinance = await _ord_svc.get_ordinance_limits(a, zone_type)
                    except Exception:  # noqa: BLE001 — 조례 조회 실패는 법정 폴백(정직)
                        ordinance = None
                    try:
                        eff = calc_effective_far(
                            {
                                "zone_limits": zl,
                                "special_districts": r.get("special_districts") or [],
                                "local_ordinance": ordinance or {},
                            },
                            zone_type,
                            r.get("land_area_sqm") or 0,
                        )
                        eff_far = eff.get("effective_far_pct")
                        if eff_far is not None and eff_far > 0:
                            far = float(eff_far)
                        # ★계획 상한·허용용도 미확보 신호를 필지에 싣는다 — 종전엔 이 함수의
                        #   산출에서 `effective_far_pct` **한 값만** 읽어, 계획구역 필지인데도
                        #   개발방식·용도 추천이 아무 경고 없이 나갔다(소비처 기아).
                        plan_unknown = eff.get("plan_limit_unknown")
                    except Exception:  # noqa: BLE001
                        pass
                pnu = r.get("pnu")
                coords = r.get("coordinates") or {}
                geometry = None
                owner_type = None
                try:
                    if pnu:
                        li = await vworld.get_land_info(pnu)
                        if li:
                            geometry = li.get("geometry")
                            owner_type = (li.get("properties") or {}).get("owner_type")
                    if geometry is None and coords.get("lat") and coords.get("lon"):
                        pp = await vworld.get_parcel_by_point(coords["lat"], coords["lon"])
                        geometry = pp.get("geometry") if pp else None
                except Exception:  # noqa: BLE001
                    pass
                # 건축물대장(노후도·세대수)
                bldg_year = units = None
                structure = None
                try:
                    if pnu:
                        b = await breg.get_title_by_pnu(pnu) or await breg.get_building_by_pnu(pnu)
                        if b:
                            ud = (b.get("use_approval_date") or "")[:4]
                            bldg_year = int(ud) if ud.isdigit() else None
                            units = b.get("household_count") or b.get("ho_count") or 0
                            structure = b.get("structure")
                except Exception:  # noqa: BLE001
                    pass
                return {"address": a, "zone": r.get("zone_type"),
                        # ★zone_source 동봉 — `keyword_inference` 는 주소 문자열에서 **추론한**
                        #   용도지역이지 조회된 값이 아니다. 이 키가 없으면 하류에서 지어낸 값과
                        #   실측값을 구분할 수 없다(실측: 미해석 주소가 '제2종일반주거지역'을 냈다).
                        "zone_source": r.get("zone_source"),
                        "area": r.get("land_area_sqm"),
                        "max_far": far,            # 실효 용적률(현행·조례 반영) — 시나리오 산정 기준
                        "max_far_legal": far_legal,  # 법정상한(라벨 구분용)
                        "pnu": pnu, "geometry": geometry, "owner_type": owner_type,
                        "bldg_year": bldg_year, "units": units, "structure": structure,
                        "coords": coords,
                        # ── 특이부지 게이트 입력 키(detect_special_parcel/detect_multi_parcel 정합) ──
                        "land_category": r.get("land_category") or "",
                        "special_districts": r.get("special_districts") or [],
                        "zone_limits": zl,
                        "official_price_per_sqm": r.get("official_price_per_sqm"),
                        # 접도 미확보 → None(맹지 오탐 방지). orchestrator._enrich_context와 동일 정책.
                        "road_contact": None, "road_width_m": None,
                        # 게이트는 zone_type 키로 읽으므로 동봉(zone과 동일값).
                        "zone_type": r.get("zone_type") or "",
                        # 계획(지구단위·성장관리 등)이 한도·용도를 정하는데 그 내용을 못 구한 경우.
                        "plan_limit_unknown": plan_unknown}
            except Exception:  # noqa: BLE001
                return {"address": a, "zone": None, "zone_source": None,
                        "area": None, "max_far": None,
                        "max_far_legal": None, "geometry": None,
                        "land_category": "", "special_districts": [], "zone_limits": {},
                        "official_price_per_sqm": None, "road_contact": None,
                        "road_width_m": None, "zone_type": ""}

        enriched = await asyncio.gather(*[one(a) for a in addrs])
        enriched = list(enriched)
        # 주 필지 인근 지하철 거리(comprehensive)
        subway_m = None
        try:
            from app.services.land_intelligence.land_info_service import LandInfoService

            comp = await LandInfoService().collect_comprehensive(addrs[0])
            infra = comp.get("infrastructure") or {}
            ns = infra.get("nearest_subway") if isinstance(infra, dict) else None
            if isinstance(ns, dict):
                subway_m = ns.get("distance_m")
            # 면적/용도 보강
            if not enriched[0].get("area") and comp.get("land_area_sqm"):
                enriched[0]["area"] = comp["land_area_sqm"]
            if not enriched[0].get("zone") and comp.get("zone_type"):
                enriched[0]["zone"] = comp["zone_type"]
                # 개발행위 게이트 등 하류가 zone_type 키를 읽으므로 함께 동기화(게이트 누락 FN 방지).
                if not enriched[0].get("zone_type"):
                    enriched[0]["zone_type"] = comp["zone_type"]
        except Exception:  # noqa: BLE001
            pass
        return enriched, subway_m

    @staticmethod
    def _adjacency(parcels: list[dict]) -> dict[str, Any]:
        """필지 인접성 판정 — 통합개발(합필/일단지)은 필지가 맞닿아야 가능.

        shapely로 각 필지 폴리곤 간 거리를 계산해 연결요소(그룹) 수를 구한다.
        contiguous=True면 모든 필지가 하나로 연결(통합개발 가능).
        """
        geoms = [p.get("geometry") for p in parcels]
        present = [g for g in geoms if g]
        if len(present) < 2:
            return {"contiguous": True, "components": 1, "checked": len(present),
                    "note": "단일 필지"}
        try:
            from shapely.geometry import shape

            polys = []
            for g in geoms:
                try:
                    polys.append(shape(g).buffer(0) if g else None)
                except Exception:  # noqa: BLE001
                    polys.append(None)
            idx = [i for i, p in enumerate(polys) if p is not None]
            if len(idx) < 2:
                return {"contiguous": None, "components": None, "checked": len(idx),
                        "note": "필지 형상 데이터 부족 — 인접성 확인 불가(현장 확인 필요)"}
            TOL_DEG = 0.00006  # 약 6m(공유경계 정밀오차·세도로 허용)
            n = len(idx)
            parent = list(range(n))

            def find(x: int) -> int:
                while parent[x] != x:
                    parent[x] = parent[parent[x]]
                    x = parent[x]
                return x

            max_pair_deg = 0.0
            for a in range(n):
                for b in range(a + 1, n):
                    d = polys[idx[a]].distance(polys[idx[b]])
                    max_pair_deg = max(max_pair_deg, d)
                    if d <= TOL_DEG:
                        parent[find(a)] = find(b)
            comps = len({find(i) for i in range(n)})
            return {
                "contiguous": comps == 1,
                "components": comps,
                "checked": n,
                # ★종전에는 쌍거리를 **계산하고 버렸다**(적대 리뷰 J-5). 결합건축의 법정 축
                #   (§77의15① *"대지간의 최단거리가 100미터 이내"*)이 여기 있는데 쓰이지 않았다.
                "max_pair_distance_m_min": round(max_pair_deg * DEG_TO_M_MIN, 1),
                "note": "모든 필지가 맞닿아 통합개발 가능" if comps == 1
                # ★「불가」로 단정하지 않는다 — 인접성은 **관측**이지 판정이 아니다.
                #   판정은 각 개발방식이 자기 축으로 한다(구역지정형은 인접이 법정 요건이
                #   아니고, 가로구역형은 도로 폭, 주택단지형은 20m/8m·철도다).
                #   ★라이브 실측(2026-09-03): 이 문구가 게이트 사유 **앞에 그대로 붙어**
                #     *"…통합개발(합필/일단지) 불가. 구역지정형 사업 — 물리적 인접은 법정
                #     요건이 아닙니다…"* 라는 **한 문장 안의 모순**이 사용자 화면에 나갔다.
                #     `#940` 이 판정어는 고쳤는데 **그 앞 문장은 안 고쳤다**(적용 범위 누락).
                else f"{comps}개 그룹으로 분리 — 합필/일단지 통합은 불가",
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("인접성 분석 실패", err=str(e)[:80])
            return {"contiguous": None, "components": None, "checked": len(present),
                    "note": "인접성 분석 실패 — 현장/지적도 확인 필요"}

    @staticmethod
    def _buildings(parcels: list[dict]) -> dict[str, Any]:
        """건축물 노후도·세대수·소유구분 집계(실데이터). 노후 기준: RC/철골 30년, 그 외 20년."""
        from datetime import datetime

        year_now = datetime.now().year
        with_b = [p for p in parcels if p.get("bldg_year")]
        old = 0
        ages: list[int] = []
        for p in with_b:
            yr = p.get("bldg_year")
            age = year_now - int(yr)
            ages.append(age)
            st = p.get("structure") or ""
            thr = 30 if any(k in st for k in ("철근", "철골", "RC", "SRC", "콘크리트")) else 20
            if age >= thr:
                old += 1
        total_units = sum(int(p.get("units") or 0) for p in with_b)
        owner_types = sorted({p.get("owner_type") for p in parcels if p.get("owner_type")})
        return {
            "buildings_found": len(with_b),
            "old_count": old,
            "old_ratio": round(old / len(with_b), 2) if with_b else None,
            "avg_age": round(sum(ages) / len(ages)) if ages else None,
            "oldest_age": max(ages) if ages else None,
            "total_units": total_units or None,
            "owner_types": owner_types or None,
            "note": "1필지=1대표건축물 기준(블록 전체 노후도는 현장확인 필요)",
        }

    @staticmethod
    async def _block_aging(coords: dict | None, radius_m: int = 100, max_parcels: int = 40) -> dict[str, Any] | None:
        """블록(주변 필지 일괄) 노후도 집계 — 가로주택/모아/정비 노후·불량 2/3 요건 판정용.

        대상 좌표 중심 bbox 내 필지(VWorld)를 가져와 각 필지 건축물 사용승인일로
        노후건물 비율을 산정한다(API 부하 제한: 반경·필지수 상한).
        """
        if not coords or not coords.get("lat") or not coords.get("lon"):
            return None
        import asyncio
        from datetime import datetime

        from app.services.external_api.building_registry_service import BuildingRegistryService
        from app.services.external_api.vworld_service import VWorldService

        lat, lon = coords["lat"], coords["lon"]
        dlat = radius_m / 111000.0
        import math as _m

        dlon = radius_m / (111000.0 * max(0.3, _m.cos(_m.radians(lat))))
        vworld = VWorldService()
        try:
            parcels = await vworld.get_parcels_in_bbox(
                lon - dlon, lat - dlat, lon + dlon, lat + dlat, max_count=max_parcels
            )
        except Exception:  # noqa: BLE001
            return None
        pnus = [p.get("pnu") for p in (parcels or []) if p.get("pnu")][:max_parcels]
        if not pnus:
            return None

        breg = BuildingRegistryService()
        sem = asyncio.Semaphore(8)
        year_now = datetime.now().year

        async def age_of(pnu: str):
            async with sem:
                try:
                    b = await breg.get_title_by_pnu(pnu)
                except Exception:  # noqa: BLE001
                    return None
                if not b:
                    return None
                ud = (b.get("use_approval_date") or "")[:4]
                if not ud.isdigit():
                    return None
                st = b.get("structure") or ""
                thr = 30 if any(k in st for k in ("철근", "철골", "RC", "SRC", "콘크리트")) else 20
                return {"age": year_now - int(ud), "old": (year_now - int(ud)) >= thr,
                        "units": int(b.get("household_count") or b.get("ho_count") or 0)}

        results = [r for r in await asyncio.gather(*[age_of(p) for p in pnus]) if r]
        if not results:
            return {"parcels_scanned": len(pnus), "buildings_found": 0, "old_ratio": None,
                    "note": "주변 건축물대장 데이터 부족 — 현장 확인 필요"}
        old = sum(1 for r in results if r["old"])
        ages = [r["age"] for r in results]
        return {
            "parcels_scanned": len(pnus),
            "buildings_found": len(results),
            "old_count": old,
            "old_ratio": round(old / len(results), 2),
            "avg_age": round(sum(ages) / len(ages)),
            "total_units": sum(r["units"] for r in results) or None,
            "meets_2_3": (old / len(results)) >= 2 / 3,
            "radius_m": radius_m,
            "note": f"중심 반경 {radius_m}m 내 {len(results)}개 건축물 기준 노후도(가로주택/모아/정비 2/3 요건 참고)",
        }

    @staticmethod
    def _magdo_summary(recommended: dict, ctx: dict) -> dict[str, Any] | None:
        """추천 사업방안 기준 매도청구 요약 + 다필지 잔여 매도청구 추정."""
        m = recommended.get("magdo")
        if not m:
            return {
                "applicable": False,
                "scheme": recommended.get("scheme"),
                "note": "단일 사업주체/단독 소유 또는 단순건축 — 매도청구 불요(전 토지 사용권원 확보 전제)",
            }
        n = ctx.get("parcel_count") or 1
        thr = m.get("consent_threshold_pct")
        remainder = m.get("claimable_remainder_pct")
        basis_axis = m.get("consent_basis")
        undetermined = bool(m.get("instrument_undetermined"))

        # ★★필지 개수 추정은 임계가 **소유자 수 기준일 때만** 성립한다.
        #   종전에는 축을 보지 않고 `ceil(parcel_count × thr/100)` 을 돌렸다 — 도시개발(면적 2/3)과
        #   주택법 계열(사용권원 면적 95%)에서 **면적 임계를 필지 개수에 곱하는** 축 오류였다.
        #   같은 95% 를 P2 `secured_ratio` 는 면적으로 올바르게 계산하므로 **두 기준이 갈렸다.**
        # ★수단이 미정(트랙 입력 필요)이면 애초에 추정하지 않는다 — 무엇을 청구할지도 모르는데
        #   "몇 필지에 청구 가능"을 세는 것은 순서가 뒤집힌 것이다.
        parcel_est = None
        if n >= 2 and thr and not undetermined and basis_axis == "owner_count":
            import math

            need = math.ceil(n * thr / 100.0)
            parcel_est = {
                "total_parcels": n,
                "consent_needed_parcels": min(need, n),
                "claimable_parcels_max": max(0, n - need),
                "assumption": "1필지=1소유자 가정(실제 소유관계·지분 확인 필요)",
            }
        elif n >= 2 and basis_axis in ("land_area", "use_right_area"):
            # 축이 다르면 **숫자를 내지 않고 사유를 낸다**(무언의 생략은 "해당 없음"으로 오독된다).
            parcel_est = {
                "total_parcels": n,
                "estimable": False,
                "reason": (
                    f"이 사업방식의 동의 임계({thr}%)는 **면적 기준**이라 필지 개수로 환산할 수 "
                    "없습니다. 필지별 면적·지분이 확정돼야 산정됩니다."
                ),
            }

        return {
            "applicable": True,
            "scheme": recommended.get("scheme"),
            # ★수단을 명시한다 — 도시개발은 **수용**(토지보상법 준용)이지 매도청구가 아니다.
            #   미정이면 None 이고, 소비처는 그때 "매도청구"라는 단어를 렌더하면 안 된다.
            "governing_act": m.get("governing_act"),
            "instrument": m.get("instrument"),
            "instrument_undetermined": undetermined,
            "consent_required": m.get("consent_required"),
            "consent_threshold_pct": thr,
            "consent_basis": basis_axis,
            "claimable_remainder_pct": remainder,
            "basis": m.get("basis"),
            "note": m.get("note"),
            "parcel_estimate": parcel_est,
        }

    @staticmethod
    def _blended_far(parcels: list[dict], key: str = "max_far") -> float | None:
        """면적가중 평균 용적률. key='max_far'면 실효(현행·조례 반영, 시나리오 기준),
        key='max_far_legal'이면 법정상한(라벨 구분용)."""
        # TODO(계약표준화 후속): 정본 _aggregate_integrated_zoning(면적가중 blended_far_*_pct)
        #   위임 검토 — 값 산출 경로 변경이라 이번(계약 shape 정규화) 라운드 제외.
        #   permit_analysis_service._blended_far 와 동일 산식(정본 일원화 대상).
        w = [(p.get("area"), p.get(key)) for p in parcels if p.get(key)]
        if not w:
            return None
        if all(a for a, _ in w):
            tot = sum(a for a, _ in w)
            return round(sum(a * f for a, f in w) / tot, 1) if tot else None
        fars = [f for _, f in w]
        return round(sum(fars) / len(fars), 1)

    @staticmethod
    def _resolution_from_gate(special_gate: dict) -> tuple[list[str], list[str], list[str]]:
        """특이부지 게이트에서 '개발가능 방안(선행절차)'·법령키·대안을 집계.

        ★사용자 피드백: '개발 불가'로 끝내지 말고 인허가·도시계획 변경 등 개발가능 방법을 제시.
        special_parcel이 보유한 resolution_paths(게이트)·permit_prerequisites(각 factor)·alternatives를
        중복 없이 모은다. 반환: (methods, legal_ref_keys, alternatives).
        """
        methods: list[str] = []
        ref_keys: list[str] = []
        for p in (special_gate.get("resolution_paths") or []):
            if p and p not in methods:
                methods.append(p)
        for f in (special_gate.get("factors") or []):
            for pre in (f.get("permit_prerequisites") or []):
                if pre and pre not in methods:
                    methods.append(pre)
            for k in (f.get("legal_ref_keys") or []):
                if k and k not in ref_keys:
                    ref_keys.append(k)
        alternatives = [a for a in (special_gate.get("alternatives") or []) if a]
        return methods, ref_keys, alternatives

    # 평수 티어 경계(㎡) — scenario 면적 게이트 상수와 정합(SINGLE_SMALL_MAX_SQM=1000 등 재사용 의미).
    #   T1<165(50평) T2<330(100평) T3<1000(300평) T4<3300(1000평) T5≥3300.
    _PYEONG_TIERS = (
        (165.0, "T1", "~50평(<165㎡)", "단순건축만(단독·다가구·다세대)"),
        (330.0, "T2", "50~100평(<330㎡)", "+자율주택정비(주거)"),
        (1000.0, "T3", "100~300평(<1000㎡)", "단독 정비 하한 직전 — 인접 통합 권고"),
        (3300.0, "T4", "300~1000평(<3300㎡)", "+모아주택(≥1500㎡)·지구단위 편입"),
        (float("inf"), "T5", "1000평+(≥3300㎡)", "+지구단위 단독(≥5000)·도시개발(≥10000)·정비사업"),
    )

    @staticmethod
    def _classify_by_pyeong_tier(area_sqm: float | None, scenarios: list[dict]) -> dict[str, Any]:
        """현 부지 면적을 평수 티어로 분류 + 시나리오 판정을 가능/조건부/불가 매트릭스로 재집계.

        ★순수 additive 뷰 — _scenarios 의 applicable 판정(이미 면적 게이트 반영)을 평수 축으로
        재구성할 뿐, 신규 게이트·상수를 만들지 않는다(결정론·기존 판정 무회귀).
        사용자 요청="소규모 단일/다필지의 총평수별 가능·불가 개발방식 상세 분류"의 백엔드 계약.
        """
        area = float(area_sqm or 0)
        pyeong = round(area / 3.3058, 1) if area else 0.0
        tier, tier_label = "T1", "~50평(<165㎡)"
        for boundary, t, label, _unlocks in DevelopmentScenarioSimulator._PYEONG_TIERS:
            if area < boundary:
                tier, tier_label = t, label
                break
        rank = {"가능": 0, "조건부": 1, "불가": 2}
        matrix = sorted(
            ({
                "scheme": s["scheme"],
                "status": s.get("applicable"),          # 가능 | 조건부 | 불가
                "reason": s.get("notes") or (s.get("cons") or [""])[0],
                "est_far_pct": s.get("est_far"),
            } for s in scenarios),
            key=lambda m: rank.get(m["status"], 3),
        )
        possible = [m["scheme"] for m in matrix if m["status"] == "가능"]
        conditional = [m["scheme"] for m in matrix if m["status"] == "조건부"]
        blocked = [m["scheme"] for m in matrix if m["status"] == "불가"]
        self_standing_only = possible == ["단순 건축"] and not conditional
        return {
            "area_sqm": round(area, 1), "pyeong": pyeong,
            "tier": tier, "tier_label": tier_label,
            "matrix": matrix,
            "possible": possible, "conditional": conditional, "blocked": blocked,
            "self_standing_only": self_standing_only,
            "tier_guide": [
                {"tier": t, "label": label, "unlocks": unlocks}
                for _b, t, label, unlocks in DevelopmentScenarioSimulator._PYEONG_TIERS
            ],
            "note": (
                f"단일 소규모 필지(약 {pyeong:g}평)는 단순건축 외 통합·정비·지구단위·역세권형 사업의 "
                "단독 검토대상이 아닙니다 — 인접 필지 통합 또는 기존 지구단위/정비구역 편입 시 "
                "가능 방식이 확장됩니다."
                if self_standing_only else
                f"약 {pyeong:g}평({tier}) 기준 — 가능 {len(possible)}·조건부 {len(conditional)}·불가 "
                f"{len(blocked)} 방식. 다필지 통합 시 상위 티어 방식 검토 가능."
            ),
        }

    # ── 규칙기반 시나리오 ──
    def _scenarios(self, c: dict) -> list[dict]:
        area = c.get("total_area_sqm") or 0
        zone = c.get("primary_zone") or ""
        # ★시나리오 est_far 기준 = 실효 용적률(현행·조례 반영). 미산정 시 법정상한 폴백(회귀0).
        far = c.get("far_effective_blended") or c.get("far_legal_blended") or 0
        multi = c.get("multi")
        station = c.get("near_station")
        integration_ok = c.get("integration_feasible", True)
        adj_note = (c.get("adjacency") or {}).get("note", "")
        res = _is_residential(zone)
        com = _is_commercial(zone)
        region = c.get("region") or ""
        seoul = "서울" in region  # 서울시 조례 고유 방식의 지역 적용가능성 판정
        # 건축물 실데이터(노후도·세대수) — 블록(주변) 우선, 없으면 입력필지
        b = c.get("buildings") or {}
        blk = c.get("block_aging") or {}
        block_ratio = blk.get("old_ratio")
        block_units = blk.get("total_units")
        parcel_ratio = b.get("old_ratio")
        oldest = b.get("oldest_age")
        units = block_units or b.get("total_units")

        def reno_note() -> str:
            parts = []
            if block_ratio is not None:
                meets = " · 2/3 충족" if blk.get("meets_2_3") else " · 2/3 미달"
                parts.append(f"블록 노후도 {int(block_ratio * 100)}%(반경{blk.get('radius_m', 100)}m·{blk.get('buildings_found')}동{meets})")
            elif parcel_ratio is not None:
                parts.append(f"필지 노후도 {int(parcel_ratio * 100)}%")
            if units:
                parts.append(f"세대수 {units}")
            return (" · 실데이터: " + ", ".join(parts)) if parts else ""

        S: list[dict] = []

        # ★인접성의 축을 **셋으로 가른다**(종전: 13종 한 덩어리 → 전부 「불가」).
        #   법제처 원문 직독(2026-09-02)으로 확인한 것:
        #   · 국토계획법 009294 §51·§52①3호 — 지구단위계획구역 지정에 **인접·연접 요건 없음**
        #   · 도시개발법 002024 §3의2 — *"서로 **떨어진** 둘 이상의 지역을 결합하여 하나의
        #     도시개발구역으로 지정"* 을 **명문으로 허용**(게이트가 정반대를 강제하고 있었다)
        #   · 소규모정비법 시행령 013079 §3② — 가로주택의 축은 **가로구역**(폭 4m/6m 초과 도로 관통)
        #   · 주택법 001809 §2 12호 — 재건축·대지조성의 축은 **주택단지**(20m/8m 도로·철도)
        #   ★따라서 「물리적 인접」은 **구역지정형 사업의 요건이 아니다.** 판정어도 저장소 자기
        #     기준선(`special_parcel.py` — *"관할 확인이 필요합니다"*)에 맞춰 **불가 → 조건부**로 낮춘다.
        #
        # ① 구역지정형 — **인접성으로 「불가」를 만들지 않는다**(조건부 + 관할 확인 고지).
        #   ★"재개발·재건축(정비사업)"·"공공재개발·공공재건축" 은 **요건이 다른 둘을 한 이름으로**
        #     묶고 있다(재개발=인접 불요 / 재건축=주택단지 축). 분리는 `scheme_legal_profile`·
        #     모듈맵 등 여러 레지스트리 키로 파급되므로 **이 PR 범위 밖**이고, 그때까지는
        #     **덜 제약적인 쪽(재개발)** 기준으로 둔다 — 이 게이트는 「조건부」까지만 내리므로
        #     과대허용이 되지 않는다. ★분리 전에는 이 주석이 그 부채를 드러내는 유일한 표지다.
        AREA_DESIGNATION_SCHEMES = {
            "지구단위계획 연계", "도시개발사업(도시개발법)", "재개발·재건축(정비사업)",
            "역세권 활성화사업", "역세권 장기전세주택(시프트)", "도심복합개발사업",
            "소규모재개발사업", "주거환경개선사업", "공공재개발·공공재건축",
            "입지규제최소구역", "대지조성사업",
        }
        # ② 가로구역형 — 축은 도시계획**시설**도로의 관통(폭 4m/6m 초과). ★현 구현은 그 축을
        #    재지 못하므로(물리 간격 6m 단일상수) **「불가」가 아니라 「조건부」로만** 강등한다.
        #    ※모아주택/모아타운은 자치법규 조회 0건이라 근거 미확보 — **보류**(여기 둔다).
        GARO_GUYEOK_SCHEMES = {"가로주택정비사업", "모아주택/모아타운"}
        # ③ 주택단지형 — 축은 20m/8m 도로·철도(주택법 §2 12호). 같은 이유로 조건부까지만.
        #   ※재건축은 위 병합 이름 안에 있어 여기서 따로 잡히지 않는다(위 주석의 부채).
        #     ★"소규모재건축사업" 은 종전 게이트에도 **없었고**, 그 인접 요건 조문을 이번에
        #       확인하지 못했으므로 **넣지 않는다**(지어내지 않는다 — 미검증).
        HOUSING_COMPLEX_SCHEMES: set[str] = set()
        # 인접성이 판정에 관여하는 전체 집합(파생형 — 아래 세 집합에서 만든다).
        INTEGRATION_SCHEMES = (
            AREA_DESIGNATION_SCHEMES | GARO_GUYEOK_SCHEMES | HOUSING_COMPLEX_SCHEMES
        )
        # ★단일 소규모 필지가 '단독'으로 추진 가능한 방식(나머지는 인접 통합/구역 편입/기존
        #   건축물·세대수 요건이 있어 단독 검토대상이 못 됨). 단순건축만 자립 가능.
        SELF_STANDING_SCHEMES = {"단순 건축"}
        # 단일 필지가 통합·정비·지구단위·역세권형 사업의 '단독' 검토대상이 되는 현실 하한(약 300평).
        #   이 미만의 '단일' 필지는 가로구역/블록/구역을 단독으로 구성할 수 없어 단독 추진 불가
        #   (인접 필지 통합 또는 기존 지구단위/정비구역 편입 시에만 가능).
        SINGLE_SMALL_MAX_SQM = 1000.0
        single_small = (not multi) and 0 < area < SINGLE_SMALL_MAX_SQM
        _pyeong = round(area / 3.3058) if area else 0

        def add(scheme, applicable, est_far, contrib, requirements, pros, cons, notes):
            # ★다필지 비인접 — **「불가」가 아니라 「조건부」**로 낮춘다(법적 근거는 위 주석).
            #   종전에는 전부 "불가"였고, 사용자 화면에서 지구단위계획이 그렇게 막혔다.
            if multi and not integration_ok and scheme in INTEGRATION_SCHEMES and applicable != "불가":
                # ★변이 생존에 대한 해명(`scripts/mutate_changed.py`) — 아래 안내문의 **문자열
                #   변이 11건은 의도적으로 잠그지 않는다.** 락은 계약 토큰(`§51`·`§52`·`4m`·
                #   `관할 확인`·`77의15`)의 **존재**만 단언한다. 문구 전체를 단언하면 표현을
                #   다듬을 때마다 깨지는 취약한 락이 되고, 그때 사람은 락을 고치는 게 아니라
                #   지운다. **계약은 「근거와 후속 안내가 실린다」이지 「이 문장이다」가 아니다.**
                if scheme in AREA_DESIGNATION_SCHEMES:
                    _why = ("구역지정형 사업 — 물리적 인접은 법정 요건이 아닙니다"
                            "(국토계획법 §51의 지구단위계획구역 지정 대상에 인접·연접 요건이 없고, "
                            "도시개발법 §3의2는 서로 떨어진 지역의 결합지정을 명문으로 허용합니다). "
                            "구역 지정·편입 가능성은 관할 확인이 필요합니다.")
                elif scheme in GARO_GUYEOK_SCHEMES:
                    _why = ("가로구역 요건 — 판정축은 필지 간 물리적 거리가 아니라 "
                            "폭 4m(일부 6m) 초과 도시계획시설도로의 관통 여부입니다"
                            "(소규모주택정비법 시행령 §3②). 현 분석은 그 축을 측정하지 못했습니다 — "
                            "관할 확인이 필요합니다.")
                elif scheme in HOUSING_COMPLEX_SCHEMES:
                    _why = ("주택단지 요건 — 판정축은 폭 20m 이상 일반도로·8m 이상 도시계획예정도로·"
                            "철도 등의 분리 여부입니다(주택법 §2 12호). 현 분석은 그 축을 측정하지 "
                            "못했습니다 — 관할 확인이 필요합니다.")
                else:
                    # ★도달 불가 — `INTEGRATION_SCHEMES` 가 위 세 집합의 합집합이므로.
                    #   축을 추가하고 여기 분기를 잊으면 **조용히 틀린 사유**가 나가는 대신
                    #   시끄럽게 죽는다(적대 리뷰 J-3: 종전 `else` 는 죽은 코드였는데
                    #   주석이 현재형으로 서술해 살아 있는 축처럼 읽혔다).
                    raise AssertionError(f"인접성 게이트에 사유 없는 축: {scheme}")
                applicable = "조건부"
                cons = [*(cons or []), "필지 비인접 — 구역 지정·편입 등 관할 확인 필요"]
                notes = f"⚠ {adj_note}. {_why}"
            # ★단일 소규모 필지: 통합·정비·지구단위·역세권형 사업은 단독 검토대상 아님(불가 강등).
            #   사용자가 지적한 "50~100평에 지구단위/도시개발/역세권 제시" 오류의 근본 차단.
            elif single_small and scheme not in SELF_STANDING_SCHEMES and applicable != "불가":
                applicable = "불가"
                cons = [*(cons or []),
                        f"단일 소규모 필지({round(area):,}㎡·약 {_pyeong:,}평) — 단독 추진 규모 미달"]
                notes = (f"⚠ 단일 {round(area):,}㎡(약 {_pyeong:,}평) 필지는 단독으로 통합·정비·"
                         "지구단위·역세권형 사업의 검토대상이 될 수 없습니다 — 인접 필지 통합(합필/"
                         "일단지) 또는 기존 지구단위계획구역·정비구역 편입 시에만 가능. "
                         "현 단계 현실적 추진방안: 단순 건축(현 용도지역 한도 내).")
            S.append({"scheme": scheme, "applicable": applicable,
                      "est_far": round(est_far) if est_far else None,
                      "contribution_pct": contrib, "requirements": requirements,
                      "pros": pros, "cons": cons, "notes": notes,
                      "magdo": _magdo(scheme)})  # 매도청구권 분석(해당 시)

        # 1) 단순 건축 (항상 가능 — 폴백 기준)
        add("단순 건축", "가능", far or None, 0,
            ["현 용도지역 허용용도·건폐율/용적률 한도 내 건축"],
            ["인허가 절차 단순·신속", "별도 정비/지정 절차 불필요"],
            ["용적률 인센티브 없음(현 한도)"],
            "특별 개발정책 미적용 시 기본 추진방안")

        # 2) 지구단위계획 연계
        if area >= 5000 or multi:
            add("지구단위계획 연계", "가능", (far or 0) * 1.2, 12,
                ["대지 5,000㎡ 이상 또는 다필지 통합", "지구단위계획 수립·심의"],
                ["용적률 인센티브(통상 +10~20%)", "용도·획지 유연화", "다필지 통합개발 적합"],
                ["계획 수립·심의 기간 소요", "공공기여 수반"],
                "다필지 통합개발의 핵심 수단. 기부채납 약 10~15%로 용적 상향")
        else:
            add("지구단위계획 연계", "조건부", (far or 0) * 1.15, 12,
                ["소규모는 인접 지구단위계획구역 편입 여부 확인"],
                ["편입 시 인센티브 가능"], ["단독 수립은 규모상 비효율"],
                "면적 5,000㎡ 미만 — 인접 구역 편입/특별계획구역 검토")

        # 3) 도시개발사업(도시개발법)
        if area >= 10000:
            add("도시개발사업(도시개발법)", "가능", (far or 0) * 1.3, 25,
                ["도시지역 1만㎡ 이상(비도시 3만㎡)", "도시개발구역 지정"],
                ["환지/수용 방식 대규모 개발", "기반시설 일체 정비", "용적 상향 여지 큼"],
                ["구역지정·실시계획 등 장기 절차", "공공기여 큼"],
                "대규모 통합개발에 적합. 구역지정 요건 충족")
        else:
            add("도시개발사업(도시개발법)", "불가", None, None,
                ["도시지역 1만㎡ 이상 필요"], [], ["면적 미달"],
                f"총면적 {round(area):,}㎡ < 1만㎡ — 도시개발구역 지정 요건 미달")

        # 4) 가로주택정비사업
        if res and 0 < area < 10000:
            add("가로주택정비사업", "조건부", (far or 0) * 1.2, 0,
                ["가로구역(폭6m이상 도로로 둘러싸임)", "노후·불량건축물 2/3 이상",
                 "기존 주택 단독10/공동20세대 이상", "면적 1만㎡ 미만"],
                ["소규모·신속(정비계획 생략)", "용적률 법적상한까지 완화 가능", "공공임대 시 추가 인센티브"],
                ["노후도·세대수 요건 충족 필요", "주민 동의 필요"],
                "노후 저층주거지 소규모 통합정비에 적합 — 요건 현장확인 필요" + reno_note())
        else:
            add("가로주택정비사업", "불가", None, None,
                ["주거지역·면적1만㎡ 미만·노후2/3·가로구역 필요"], [], ["요건 미해당"],
                "주거지역 아님 또는 면적 1만㎡ 이상")

        # 5) 모아주택(소규모주택정비) / 모아타운
        if res and 1500 <= area <= 100000:
            add("모아주택/모아타운", "조건부", (far or 0) * 1.2, 0,
                ["소규모주택정비 관리지역(모아타운) 지정", "노후·불량 2/3 이상", "면적 1,500㎡~"],
                ["블록단위 통합·지하주차 공유", "용적률·층수 완화", "기반시설 국비 지원"],
                ["관리지역 지정 필요", "주민 합의"],
                ("다세대·연립 밀집지 블록 통합개발 — 모아타운 지정 여부 확인"
                 if seoul else
                 f"⚠ '모아주택/모아타운'은 서울시 브랜드 — {region or '해당 지역'}은 동일 근거(빈집·소규모주택정비특례법)의 "
                 "'소규모주택정비 관리지역'으로 추진 가능(명칭·세부기준은 해당 시·도 조례 확인)") + reno_note())
        else:
            add("모아주택/모아타운", "불가", None, None,
                ["주거지역·면적 1,500㎡ 이상·노후 필요"], [], ["요건 미해당"], "")

        # 6) 역세권 활성화사업 / 역세권 장기전세주택 — ★서울시 조례 고유 제도
        if station and seoul:
            add("역세권 활성화사업", "조건부", (far or 0) * 1.5 if not com else (far or 0) * 1.2, 50,
                ["역 승강장 350m 이내", "용도지역 상향(일반→준주거/상업)", "증가용적 50% 공공기여", "★서울시 조례 적용지역"],
                ["용도지역 종상향으로 용적 대폭 상향", "복합개발 허용"],
                ["증가용적의 50% 공공기여(임대·생활SOC)", "심의 절차"],
                "역세권 입지 — 용도상향+공공기여로 고밀복합(서울시 역세권 활성화사업 운영기준)")
            if res:
                add("역세권 장기전세주택(시프트)", "조건부", 500, 50,
                    ["역세권 350m 이내", "준주거 상향", "증가용적 50% 장기전세 공급", "★서울시(SH)·운영지역 한정"],
                    ["준주거 상향(용적 500%)으로 사업성↑", "공공성 확보"],
                    ["임대주택 기부채납 부담", "서울시 등 운영지역 한정"],
                    "주거 역세권 — 준주거 상향 + 장기전세 연계(서울시 SH 고유)")
        elif station and not seoul:
            # 역세권이나 비-서울 — 서울 고유 제도는 불가, 전국 가능한 대체 제도 안내
            add("역세권 활성화사업", "불가", None, None,
                ["서울특별시 조례(역세권 활성화사업 운영기준) 적용지역 필요"], [],
                [f"{region or '해당 지역'}은 서울시 역세권 활성화사업 미적용"],
                f"⚠ 역세권 활성화사업은 서울시 고유 제도 — {region or '해당 지자체'}는 미적용. "
                "대체: 지구단위계획(역세권 용적 완화)·입지규제최소구역·도심복합개발사업 또는 해당 시·도 역세권 관련 조례 확인")
            add("역세권 장기전세주택(시프트)", "불가", None, None,
                ["서울특별시(SH) 운영지역 필요"], [], ["서울시 고유 제도(시프트)"],
                f"⚠ 장기전세(시프트)는 서울시(SH) 고유 — {region or '해당 지역'} 미적용. "
                "대체: 공공지원민간임대(뉴스테이)·국민임대 등 전국 임대제도 검토")
        else:
            add("역세권 활성화사업", "불가", None, None,
                ["역 승강장 350m 이내 필요"], [], ["역세권 범위 밖"],
                f"인근 역 거리 {c.get('near_station_m') or '미상'} — 역세권(350m) 미해당")

        # 7) 재개발·재건축(정비사업)
        if area >= 10000:
            add("재개발·재건축(정비사업)", "조건부", (far or 0) * 1.2, 15,
                ["정비구역 지정", "노후·불량건축물 2/3 이상", "면적 1만㎡ 이상"],
                ["대규모 정비·기반시설 확보", "용적률 상향"],
                ["정비구역 지정·조합설립 등 장기", "분담금·분쟁 리스크"],
                ("노후 시가지 대규모 정비 — 노후도 요건 확인"
                 + reno_note()
                 + (f" · 최고건물연령 {oldest}년" if oldest is not None else "")))
        else:
            add("재개발·재건축(정비사업)", "불가", None, None,
                ["면적 1만㎡ 이상·노후 필요"], [], ["면적 미달"], "")

        # 8) 도심복합개발사업 (도심 공공주택 복합사업 / 도심복합개발지원법 혁신지구·2024)
        primary_zone = c.get("primary_zone") or ""
        semi_ind = "준공업" in primary_zone
        if station or semi_ind:
            # 용도지역 상향 의제 → 역세권 최대 700%, 준공업 등 대폭 상향. 노후·면적·지구지정·시행자.
            est = min(700, max((far or 0) * 1.8, 500)) if station else max((far or 0) * 1.6, 400)
            add("도심복합개발사업", "조건부", est, 30,
                ["역세권/준공업/저층주거 + 노후도(통상 20년경과 60% 이상)",
                 "도심복합개발혁신지구 지정 또는 도심 공공주택 복합지구 지정",
                 "면적요건(주거상업혁신지구 약 5천㎡↑·성장거점형 1만㎡↑)", "공공 또는 지정개발자 시행"],
                ["용도지역 상향 의제로 용적률 대폭 완화(역세권 최대 700%)",
                 "주택·상업·업무 복합 고밀개발", "지구지정 시 인허가 통합·신속"],
                ["지구지정·계획 심의 절차", "공공기여·임대 비율 부담", "노후도·주민동의 요건"],
                ("도심 역세권/준공업 노후지 고밀복합 — 도심복합개발지원법(2024) 혁신지구 또는 "
                 "도심 공공주택 복합사업 검토" + reno_note()))
        else:
            add("도심복합개발사업", "불가", None, None,
                ["역세권/준공업/저층주거 + 노후도 + 지구지정 필요"], [], ["입지·용도 미해당"],
                "역세권/준공업 등 도심복합 대상 입지 아님 — 도심복합개발지원법 지구 요건 미해당")

        # 9) 자율주택정비사업 (빈집 및 소규모주택 정비 특례법)
        if res and 0 < area < 2000:
            add("자율주택정비사업", "조건부", (far or 0) * 1.1, 0,
                ["단독 10호 미만 또는 공동 20세대 미만(합 20 미만)", "노후·불량 2/3 이상", "주민합의체 구성", "비-정비예정구역"],
                ["주민합의체 자율시행·신속", "기금융자·기반시설 지원"],
                ["소규모 한정", "전원 합의 부담"],
                "노후 단독·다세대 소규모 자율정비" + reno_note())
        else:
            add("자율주택정비사업", "불가", None, None,
                ["주거지·단독10/공동20세대 미만·노후 필요"], [], ["규모·용도 미해당"], "")

        # 10) 소규모재개발사업 (2022 신설, 소규모주택정비 특례법)
        if (station or semi_ind) and 0 < area < 5000:
            add("소규모재개발사업", "조건부", (far or 0) * 1.4, 20,
                ["역세권(승강장 350m) 또는 준공업지역", "면적 5,000㎡ 미만", "노후·불량 2/3 이상"],
                ["역세권/준공업 소규모 신속정비", "용도지역 상향·용적 완화", "공공임대 시 인센티브"],
                ["노후도·면적 요건", "동의 필요"],
                "역세권/준공업 소규모 노후지 신속 정비(2022 신설)" + reno_note())
        else:
            add("소규모재개발사업", "불가", None, None,
                ["역세권/준공업·5천㎡ 미만·노후 필요"], [], ["요건 미해당"], "")

        # 11) 소규모재건축사업 (빈집 및 소규모주택 정비 특례법)
        if res and 0 < area < 10000:
            add("소규모재건축사업", "조건부", (far or 0) * 1.2, 0,
                ["기존 공동주택 200세대 미만", "노후·불량 2/3 이상", "면적 1만㎡ 미만·도로 요건"],
                ["조합·신속 절차(정비계획 생략)", "용적률 완화"],
                ["기존 공동주택·노후 요건", "동의 필요"],
                "노후 소규모 공동주택(연립·소형아파트) 재건축" + reno_note())
        else:
            add("소규모재건축사업", "불가", None, None,
                ["공동주택 200세대 미만·노후 필요"], [], ["요건 미해당"], "")

        # 12) 주거환경개선사업 (도시 및 주거환경정비법)
        if res:
            add("주거환경개선사업", "조건부", (far or 0) * 1.1, 0,
                ["도시저소득 밀집·기반시설 극히 열악", "노후·불량 과도 밀집", "정비구역 지정(공공 주도)"],
                ["공공 주도 기반시설·공동이용시설 확충", "현지개량/수용/환지/혼용 선택"],
                ["공공지정 필요", "장기 절차"],
                "저소득 노후밀집지 공공 주거환경개선")
        else:
            add("주거환경개선사업", "불가", None, None,
                ["주거지·노후밀집 필요"], [], ["미해당"], "")

        # 13) 공공재개발·공공재건축 (정비법 공공시행 — LH/SH 등)
        if area >= 10000:
            add("공공재개발·공공재건축", "조건부", (far or 0) * 1.4, 20,
                ["기존 정비(예정)구역 또는 해제구역", "LH/SH 등 공공 단독·공동시행", "노후 2/3"],
                ["용적률 법적상한 1.2배·종상향 인센티브", "공공기여 완화·신속·미분양 매입"],
                ["공공시행 동의(조합원 과반)", "임대 비율 부담"],
                "공공시행 정비 — 용적 인센티브·신속(공공재개발/공공재건축)" + reno_note())
        else:
            add("공공재개발·공공재건축", "불가", None, None,
                ["1만㎡↑·노후·공공시행 필요"], [], ["요건 미달"], "")

        # 14) 역세권 청년안심주택 (구 역세권 청년주택) — ★서울시 발원 조례, 타 지자체 유사제도 상이
        if station and res and seoul:
            add("역세권 청년안심주택", "조건부", 500, 30,
                ["역세권(350m) 또는 간선도로변", "준주거/상업 상향", "청년·신혼 임대 공급", "★서울시 조례"],
                ["준주거 상향(용적 대폭↑)", "청년임대 인센티브·기금 지원"],
                ["임대 의무(공공+민간)", "운영지역 한정"],
                "역세권 청년·신혼 임대주택 — 준주거 상향(서울시 역세권 청년안심주택)")
        elif station and res and not seoul:
            add("역세권 청년안심주택", "조건부", (far or 0) * 1.2, 20,
                ["역세권·간선도로변", "해당 시·도 청년·임대주택 조례", "청년·신혼 임대"],
                ["청년임대 기금·세제 지원(전국 공통)"],
                [f"'역세권 청년안심주택'은 서울시 명칭 — {region or '해당 지역'}은 유사 청년·임대 제도로 추진", "조례·요건 상이"],
                f"⚠ 서울시 고유 명칭 — {region or '해당 지역'}은 행복주택·청년매입임대·시도별 청년주택 조례 등 유사제도 확인 필요")
        else:
            add("역세권 청년안심주택", "불가", None, None,
                ["역세권·주거 필요"], [], ["미해당"], "")

        # 15) 공동주택 리모델링 (주택법 — 수직증축)
        if res and oldest is not None and oldest >= 15:
            add("공동주택 리모델링", "조건부", (far or 0) * 1.1, 0,
                ["준공 15년 경과 공동주택", "수직증축 최대 3개층·세대수 15% 증가", "안전진단 B등급 이상"],
                ["전면철거 없이 증축·신속", "이주 부담 적음"],
                ["구조안전·내력 한계", "증가 폭 제한"],
                f"노후 공동주택 리모델링(증축) — 최고건물연령 {oldest}년")
        else:
            add("공동주택 리모델링", "불가", None, None,
                ["기존 공동주택·준공 15년 경과 필요"], [], ["미해당"], "")

        # 16) 결합건축 (건축법 **§77의15** — 대지 간 용적률 결합·이전)
        #   ★조문 정정: §77의4 는 **건축협정**이다(오기). 결합건축은 §77의15~§77의17.
        #   ★★자기모순 제거: 종전은 `"가능" if integration_ok else "조건부"` 로 **물리적 인접**을
        #     따졌는데, 바로 다음 줄의 요건이 스스로 *"상호 100m 이내"* 라고 적는다.
        #     결합건축의 전제는 **떨어진 대지 사이의 용적 이전**이므로(§77의15 ① — 대지 간
        #     100m 범위), 인접을 요구하면 제도를 거꾸로 적용하는 것이다.
        #     → **축을 바꾼다**: 인접 여부가 아니라 **대상지역 해당 여부**다.
        #   ★§77의15① 원문(법제처 직독): *"대지간의 최단거리가 100미터 이내의 범위에서 …
        #     2개의 대지"* 이고, 대상지는 **한정**된다 —
        #       1호 상업지역 · 2호 역세권개발구역 · 3호 주거환경개선사업 정비구역 · 4호 대통령령 지역.
        #     종전은 `if multi:` 만으로 「가능」을 줬다(대상지역 무관 = **과대허용**).
        #     인접 강등만 없애면 그 과대허용이 더 커지므로, 여기서 **대상지역 축을 세운다.**
        #   ★적대 리뷰 J-1 반영 — `station` 을 적격 축에서 **뺀다.**
        #     §77의15①2호는 *"「역세권의 개발 및 이용에 관한 법률」 제4조에 따라 **지정된**
        #     역세권개발구역"* 인데, `near_station` 은 **지하철 500m 반경**이다(:399).
        #     자릿수가 다른 모집단이라(지정 사례는 극소수 / 서울 시가지 상당 부분이 500m 안)
        #     이것을 적격으로 쓰면 서울 다필지 대부분에 `est_far = far×1.2` 가 붙고,
        #     그 값은 화면 표시이자 **추천 정렬 키**다. → **1호(상업지역)만 측정된 축**으로 두고
        #     2·3·4호는 **미측정**으로 분류한다(모름이 유효값을 입지 않게).
        _combined_eligible = com
        if multi and _combined_eligible:
            add("결합건축", "조건부", (far or 0) * 1.2, 0,
                ["대상지역: 상업지역·역세권개발구역·주거환경개선 정비구역 등(건축법 §77의15① 각 호)",
                 "★**2개 대지**: 동일 지역 + **너비 12m 이상 도로로 둘러싸인 하나의 구역** 안"
                 "(건축법 시행령 §111①) — 현 분석은 이 축을 **측정하지 못했습니다**",
                 "★**3개 이상 대지**: 같은 지역 + **모든 대지 간 최단거리 500m 이내**"
                 "(같은 영 §111③) — 100m 가 아닙니다",
                 "용적률 결합·이전 협정·등기"],
                ["떨어진 대지 간 용적 이전으로 한쪽 고밀화", "역사·녹지 보전과 병행"],
                ["대상지역 해당 여부는 관할 확인 필요", "대지 간 협정·등기 필요"],
                "대지 간 용적률 결합·이전(건축법 §77의15) — ★인접이 아니라 **이격**이 전제입니다. "
                "대상지 요건(2개=12m 도로 구역 / 3개 이상=500m)은 관할 확인이 필요합니다")
        elif multi:
            add("결합건축", "조건부", None, None,
                ["대상지역 해당 필요 — 상업지역·역세권개발구역·주거환경개선 정비구역 등(§77의15① 각 호)"],
                [], ["현 부지는 상업지역·역세권으로 확인되지 않음 — 4호(대통령령 지역) 해당 여부는 관할 확인 필요"],
                "결합건축은 대상지역이 한정됩니다(건축법 §77의15①) — 관할 확인이 필요합니다")
        else:
            add("결합건축", "불가", None, None,
                ["2개 이상 대지 필요"], [], ["단일 대지"], "")

        # 17) 입지규제최소구역 (국토계획법)
        if area >= 5000 and (station or com):
            add("입지규제최소구역", "조건부", (far or 0) * 1.5, 30,
                ["도시지역 내 거점(역세권·복합환승 등)", "입지규제최소구역 지정", "건축·도시 융복합 계획"],
                ["용도·밀도·높이 제약 최소화", "복합 고밀개발"],
                ["구역지정·계획 심의", "공공기여"],
                "도심 거점 융복합 — 용도·밀도 제약 최소화(지정 필요)")
        else:
            add("입지규제최소구역", "불가", None, None,
                ["도심 거점·5천㎡↑·지정 필요"], [], ["요건 미해당"], "")

        # 18) 도시재생사업 (도시재생 활성화 및 지원에 관한 특별법)
        add("도시재생사업", "조건부", (far or 0) * 1.1, 0,
            ["쇠퇴지역(인구·산업·노후)", "도시재생활성화지역 지정", "마중물 공공지원"],
            ["공공지원·주민참여", "점진적 재생(전면철거 지양)"],
            ["대규모 개발엔 한계", "지정 필요"],
            "쇠퇴지역 활성화 — 공공지원 점진 재생(활성화지역 지정 시)")

        # 19) 공공지원민간임대(뉴스테이) (민간임대주택특별법)
        if area >= 5000:
            add("공공지원민간임대(뉴스테이)", "조건부", (far or 0) * 1.3, 20,
                ["촉진지구 지정(또는 일반형)", "8년 이상 장기 민간임대", "면적·세대 요건"],
                ["용적률·용도 인센티브", "주택기금 지원·안정적 임대수익"],
                ["임대 의무기간", "초기 분양수익 제약"],
                "장기 민간임대 — 촉진지구 용적 인센티브(뉴스테이)")
        else:
            add("공공지원민간임대(뉴스테이)", "불가", None, None,
                ["촉진지구·면적 요건 필요"], [], ["요건 미달"], "")

        # 20) 대지조성사업 (주택법 §15 대지조성 / 택지개발 — 주택건설용 대지 조성·분양)
        if area >= 10000 or (not res and not com):
            add("대지조성사업", "조건부", far or None, 10,
                ["주택건설용 대지 조성(주택법) 또는 택지개발", "기반시설(도로·상하수) 조성", "녹지·관리·비도시는 형질변경/전용 인허가"],
                ["택지 조성 후 단독·단지 용지 분양", "대규모 부지 정형화·단계 개발"],
                ["형질변경·전용 인허가", "기반시설 조성 비용"],
                "대규모 부지·녹지/관리지역 — 대지조성 후 단독·전원·단지 용지 공급")
        else:
            add("대지조성사업", "불가", None, None,
                ["대규모 부지 또는 녹지·관리·비도시 필요"], [], ["소규모 시가지 부적합"], "")

        # 각 방식에 건축 가능 분류(아파트/호텔/상가/지산/빌라/콘도/전원주택 등) 부착.
        _zone = c.get("primary_zone")
        # ★M-5 — **우세 용도지역만 보면 혼재 부지에서 제약이 꺼진다.**
        #   사용자가 신고한 부지가 정확히 `zones=[제1종, 제2종]` 이었고, 제2종이 면적으로
        #   우세하면 `primary_zone=제2종` 이라 제1종 부분의 아파트 불허가 **사라진다.**
        #   RC-2(면적가중)를 고치자 RC-3(제1종 분리)의 발화 조건이 지워진 것 — 둘이 서로를
        #   가린다고 적어 놓고 **같이 고쳤더니 한쪽이 다른 쪽을 껐다.**
        #   → 제약은 **부지에 존재하는 모든 용도지역**으로 판정한다(한 필지라도 불허면 고지).
        #   ★§84① 흡수(330㎡ 이하 자투리)는 `simulate()` 에서 면적을 보고 판정해 넘겨준다.
        #     여기서 `zones` 이름만으로 전수 판정하면 **1㎡ 자투리가 부지 전체를 막는다**(과잉 억제).
        _restricted_zones = [z for z in (c.get("apartment_restricted_zones") or []) if z]
        if _restricted_zones is None:
            _restricted_zones = []
        for _s in S:
            _s["buildable_types"] = self._buildable_types(_zone, _s.get("scheme", ""))
            # ★M-4 — 경고를 `buildable_types`(프론트가 「건축 가능」 칩으로 그린다)에 섞지 않고
            #   **전용 필드 + `cons`**(부정 목록)로 낸다.
            #   ★제안 여부와 **무관하게** 붙인다. 종전에는 `proposes_apartment` 일 때만 달았는데,
            #     그러면 **아파트가 제안되지 않는 경로**(제1종 + 지구단위계획·청년주택·단순건축 등)
            #     에서 **「왜 아파트가 없는지」가 화면에서 통째로 사라진다**(적대 리뷰 4차 실측).
            #     제약은 부지의 성질이지 특정 제안의 성질이 아니다.
            if _restricted_zones:
                _zlist = ", ".join(dict.fromkeys(_restricted_zones))
                _msg = f"{_zlist}: {APARTMENT_PROHIBITED_MARK}"
                if _low_rise_only(_restricted_zones):
                    _msg += " · 4층 이하(단지형 연립·다세대는 5층 이하)"
                _s["zone_use_constraint"] = {
                    "zones": list(dict.fromkeys(_restricted_zones)),
                    "prohibited": ["아파트"],
                    "message": _msg,
                    "legal_ref": "국토계획법 시행령 §71①3호 [별표 4] 1호 나목 — 공동주택(아파트를 제외한다)",
                }
                # ★`cons` 는 **현재 화면 소비처가 0** 이다(전용 렌더가 `zone_use_constraint` 를 읽는다).
                #   그래도 싣는 것은 다른 소비처(PDF·LLM 요약)가 `cons` 를 읽기 때문이다.
                _s["cons"] = [*(_s.get("cons") or []), _msg]
            # 시나리오↔규범 일치(가산) — 각 사업방식의 근거법령 verified 딥링크 부착(소비처 옵셔널).
            _s["legal_refs"] = _scheme_legal_refs(_s.get("scheme", ""))

        return S

    # ── 주소 → 시·도(지역) 판정. 서울시 조례 고유 방식의 지역 적용가능성 판정에 사용 ──
    @staticmethod
    def _region(address: str | None) -> str:
        a = (address or "").strip()
        sidos = [
            "서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시",
            "대전광역시", "울산광역시", "세종특별자치시", "경기도",
            "강원특별자치도", "강원도", "충청북도", "충청남도",
            "전북특별자치도", "전라북도", "전라남도",
            "경상북도", "경상남도", "제주특별자치도",
        ]
        for s in sidos:
            if a.startswith(s) or a.startswith(s[:2]):
                return s
        return ""

    # ── 방식·용도지역별 건축 가능 분류(아파트/호텔/상가/지산/빌라/콘도/전원주택 등) 제안 ──
    @staticmethod
    def _buildable_types(zone: str | None, scheme: str) -> list[str]:
        """★이 함수는 **2단계**다 — 1단계 `base`(용도지역) → 2단계 `scheme` 오버라이드가
        `base` 를 **통째로 버리고 early return** 한다.

        ★★적대 리뷰 실측(2026-09-02): `base` 만 고쳤더니 **21종 중 12종**이 제1종일반주거에서
          여전히 아파트를 제안했다(오버라이드 경로). *"1·2·3종 분리"* 라는 선언이 **9종에만**
          적용된 것 — 「처방을 적용한 범위 ≠ 결함이 사는 범위」.
          → 처방은 **이 함수가 아니라 호출부**에 있다: `_scenarios()` 가 결과를
            `proposes_apartment()` 로 검사해 `zone_use_constraint` 를 부착한다.
            ★한때 여기 `_annotate` 래퍼를 뒀다가 **순수 항등함수(죽은 코드)** 가 됐는데
              독스트링이 그것을 처방으로 지목해, 다음 사람이 **엉뚱한 곳을 고치러** 가게 했다.

        ★그리고 «아파트를 무조건 막는 것» 도 틀리다(원문 확인). 소규모주택정비법 012805 는
          **용도지역 변경 근거를 갖는다** — §43의3 7호(관리계획에 *"용도지역의 지정 및 변경"*) ·
          §43의5①(*"시행으로 용도지역이 변경된 경우"*) · §49의2① 단서(*"일부를 종전 용도지역으로
          그대로 유지"* → 반대해석상 변경 가능). 역세권활성화·도심복합도 종상향이 제도의 핵심이다.
          단 §48① 이 완화하는 것은 **조경·건폐율 산정·공지·높이 넷뿐**이고 **용도 제한은 없다** —
          즉 아파트는 **용도지역 변경을 거쳐야** 가능하다.
          → 막지도 허용하지도 않고 **「종상향 전제」임을 표면에 싣는다.**
        """
        z = zone or ""

        # 1) 용도지역 기준 기본 건축 가능 분류.
        if any(k in z for k in ("중심상업", "일반상업", "근린상업", "유통상업")):
            base = ["상가(근린생활)", "오피스(업무시설)", "오피스텔", "주상복합 아파트", "호텔/생활숙박", "지식산업센터"]
        elif "준주거" in z:
            base = ["주상복합 아파트", "아파트", "오피스텔", "상가", "근린생활"]
        elif "준공업" in z:
            base = ["지식산업센터", "공장/제조", "오피스", "근린생활", "생활숙박(조건부)"]
        elif "전용주거" in z:
            base = ["단독주택", "저층 연립/다세대(빌라)"]
        elif "제1종일반주거" in z or "1종일반주거" in z:
            # ★법정 확인(법제처 원문 PDF 직독 2026-09-02 — 국토계획법 시행령 009419 §71①3호 →
            #   **[별표 4]** 1호 나목): *"「건축법 시행령」 별표 1 제2호의 공동주택
            #   (**아파트를 제외한다**)"* 이고 같은 호 머리에 **4층 이하**(단지형 연립·다세대는
            #   5층 이하) 제한이 붙는다.
            #   종전 코드는 `elif "주거" in z:` 로 **1·2·3종을 한 덩어리**로 묶어 제1종에도
            #   아파트를 줬다 — **법정 불허를 허용**하는 과대허용이었다.
            # ★칩 목록에는 **지을 수 있는 것**만 넣는다. 프론트가 이 리스트의 모든 원소를
            #   「건축 가능」 라벨 아래 같은 악센트 칩으로 그리므로, 여기에 *"아파트 불가"* 를
            #   넣으면 **「건축 가능」 → 「아파트 불가」** 라는 모순된 칩이 선다.
            #   불허 사실도 **층수 제약도** `zone_use_constraint` 가 싣는다.
            #   ★`"(4층 이하)"` 를 여기 두는 것도 같은 위반이다 — 그건 **지을 수 있는 것이 아니라
            #     제약**이라 「건축 가능」 칩이 되면 매달린 수식어가 된다(적대 리뷰 4차 MINOR 1).
            base = ["연립/다세대(빌라)", "단독주택", "근린생활"]
        elif "주거" in z:  # 제2·3종 일반주거 및 그 밖의 주거계
            # [별표 5](제2종) 1호 나목은 *"「건축법 시행령」 별표 1 제2호의 공동주택"* 으로
            # **제외 문구가 없다** → 아파트 허용. 제3종도 같다([별표 6]).
            base = ["아파트", "연립/다세대(빌라)", "단독주택", "근린생활"]
        elif "계획관리" in z:
            base = ["전원주택", "단독주택", "근린생활", "물류창고", "공장", "콘도/펜션"]
        elif any(k in z for k in ("녹지", "보전관리", "생산관리", "농림", "자연")):
            base = ["단독/전원주택", "근린생활(제한적)", "(개발행위허가 필요)"]
        else:
            base = ["용도지역 확인 필요"]
        # 2) 개발방식 보정(방식 특성상 유리한 분류로 좁힘/추가).
        if "역세권" in scheme or "도심복합" in scheme:
            return (["주상복합 아파트", "오피스텔", "상가", "오피스", "호텔/생활숙박"]
                    + (["청년·신혼 임대주택"] if "청년" in scheme else []))
        if any(k in scheme for k in ("가로주택", "모아", "자율주택", "소규모재건축", "주거환경")):
            return ["저층 아파트", "연립/다세대(빌라)", "단독주택"]
        if "대지조성" in scheme:
            return ["단독/전원주택 용지", "아파트 건설용지", "상가/근생 용지(분양)"]
        if "리모델링" in scheme:
            return ["기존 공동주택 증축(아파트)"]
        if "뉴스테이" in scheme or "장기전세" in scheme or "청년안심" in scheme:
            return ["임대 아파트", "오피스텔", "주상복합"]
        return base

    async def _llm(self, ctx: dict, scenarios: list[dict]) -> dict[str, Any]:
        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            from app.services.ai.base_interpreter import GROUNDING_RULE
            from app.services.ai.llm_provider import get_llm

            sys = ("당신은 부동산개발 사업방식 전문가다. 제공된 부지정보와 규칙기반 후보 시나리오를 "
                   "근거로 가장 합리적인 최적 사업방안을 추천하고 그 이유, 차선책, 주의사항을 제시한다. "
                   "데이터·후보에 근거하고 과장 금지. JSON만 출력." + GROUNDING_RULE)
            usr = (f"## 부지\n{json.dumps(ctx, ensure_ascii=False)}\n\n"
                   f"## 후보 시나리오\n{json.dumps(scenarios, ensure_ascii=False)[:3000]}\n\n"
                   "## 출력 JSON\n{\"summary\":\"종합 판단 3~4문장\",\"best_scheme\":\"추천 사업방식\","
                   "\"why\":\"추천 이유 2~3문장\",\"alternatives\":[\"차선책 1~2개\"],"
                   "\"cautions\":[\"주의사항 1~3개\"]}")
            llm = get_llm(service="scenario", timeout=60, max_tokens=1500)
            resp = await llm.ainvoke([SystemMessage(content=sys), HumanMessage(content=usr)])
            # 계측: BaseInterpreter 밖 직접 호출도 동일하게 토큰·과금 기록(best-effort)
            from app.services.ai.base_interpreter import record_llm_response_billing
            await record_llm_response_billing(llm, resp, service="scenario")
            from app.services.ai.llm_json import parse_llm_json
            data = parse_llm_json(resp.content if hasattr(resp, "content") else str(resp))
            # ★`parse_llm_json` 은 dict **또는 list** 를 준다(반환 타입이 Any 다).
            #   종전 코드는 dict 를 가정하고 곧장 `data["generated"]` 를 대입해,
            #   모델이 배열을 주면 `list indices must be integers or slices, not str` 로 죽었다.
            #   2026-08-21 라이브 로그에 그 메시지가 그대로 있었다 — 화면에는 "일시적"이라고만
            #   보여 **영구 실패가 일시 장애로 위장**됐다.
            if not isinstance(data, dict):
                raise TypeError(
                    f"LLM 이 JSON 객체가 아닌 {type(data).__name__} 를 반환했다(스키마 불일치)"
                )
            data["generated"] = True
            return data
        except Exception as e:  # noqa: BLE001
            # ★실패 사유를 **화면까지** 들고 간다. 종전에는 "일시적으로 미제공"이라고만 적어
            #   결정론적 영구 실패(모델이 temperature 를 거부 · 스키마 불일치)를 일시 장애로
            #   위장했고, 그래서 아무도 오래 몰랐다. 조용한 폴백이 이 장애를 숨긴 주범이다.
            reason = f"{type(e).__name__}: {str(e)[:160]}"
            logger.warning("개발 시나리오 LLM 실패, 폴백", err=reason)
            return {"generated": False,
                    "summary": "AI 종합을 생성하지 못했습니다 — 아래 규칙기반 시나리오로 답합니다.",
                    "failure_reason": reason,
                    "best_scheme": None, "why": "", "alternatives": [], "cautions": []}
