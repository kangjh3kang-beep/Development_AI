"""개발행위허가 절차게이트(WP-B) — 국토계획법 §56~58 판정을 '절차 완결형'으로 조립한다.

무엇을 하나(쉬운 설명):
  '개발행위허가'는 건물을 짓기 전에 받아야 하는 허가입니다. 특히 도시지역이 아닌 땅
  (관리·농림·자연환경보전지역)이나 도시지역 안 녹지(자연·생산·보전녹지)는 건폐율·용적률
  한도만 맞으면 개발이 되는 게 아니라, 건축 전에 개발행위허가(규모·경사도·연접개발·도로/상하수
  같은 기반시설 기준)를 통과해야 합니다. 이 게이트는 어떤 땅이 그 허가 '대상'인지, 그리고
  각 기준(규모·연접·기반시설·경사도·표고)을 충족하는지 판정해 결과를 돌려줍니다.

결과(status):
  PASS                             — 개발행위허가 대상 아님(도시지역 주거·상업·공업의 이미 대지화된
                                     땅, 형질변경 없음). 건축허가로 처리.
  CONDITIONAL                      — 개발행위허가 대상 — 허가·형질변경 통과를 '조건'으로 개발 가능.
  BLOCKED                          — 보전 성격 지역에서 규모 등이 국가상한을 초과 — 단일 개발행위허가로는
                                     불가(도시계획 변경 등 중대한 선행절차 필요).
  REQUIRES_AUTHORITY_CONFIRMATION  — 개발행위허가 대상 여부(또는 세부기준)를 조례·현장데이터 없이
                                     확정할 수 없음 — 관할 확인 필요(정직 미확정, 낙관 폴백 아님).

★설계 원칙(정직·무날조·재사용):
- 판정 코어는 기존 평가기를 '재사용'한다: special_parcel._rule_by_dev_act_permit(용도지역 발동·
  developability)·_rule_by_sewer(하수 부담)·_slope_preliminary(조례/별표4 경사도 예비판정).
  새 평가기를 재발명하지 않고, 이들을 절차 완결형으로 조립·세분화하는 표면이다.
- 조례·데이터가 없으면 그 기준은 UNKNOWN(미확정)으로 남기고 관할 확인을 고지한다. 낙관 폴백 금지.
  규모·경사·표고 등 어떤 수치도 날조하지 않는다(국가기준 상한만 국토계획법 시행령 §55·별표4로 인용).
- 경사도는 DEM 예비판정(참고용·확정 아님) — 절대 hard-block(BLOCKED)하지 않는다.
- ★비협상 불변식(P0 — FN 0): 개발행위허가 '대상'(applicable=True)인 필지는 절대 PASS로 반환하지
  않는다("허가대상인데 미고지" False-Negative 0). 코드 말미에 방어 가드를 둔다.
- 모든 판정에 evidence(근거+법령링크)를 부착한다(evidence_contract 공용 계약 재사용).
"""
from __future__ import annotations

from typing import Any

# 종합 게이트 status(상위 4상태) — 계획서 §4 WP-B 계약.
STATUS_PASS = "PASS"
STATUS_CONDITIONAL = "CONDITIONAL"
STATUS_BLOCKED = "BLOCKED"
STATUS_CONFIRM = "REQUIRES_AUTHORITY_CONFIRMATION"

# 개별 기준(criterion)의 하위 상태 — 상위 status 집계 재료.
CR_SATISFIED = "SATISFIED"   # 충족(확인됨) — 규모 조례상한 이내 등
CR_MET = "MET"               # 충족(접도요건 등 구조적 확인)
CR_NOT_MET = "NOT_MET"       # 미충족(맹지 등 — 해소 선행 필요)
CR_EXCEEDS = "EXCEEDS"       # 초과(규모 국가상한 초과 등)
CR_CONFIRM = "CONFIRM"       # 관할 조례·심의 확인 필요(미확정)
CR_UNKNOWN = "UNKNOWN"       # 판정 데이터 미확보(미확정)

# 국토계획법 시행령 제55조 제1항 — 개발행위허가의 규모(국가기준 상한, 조례로 강화 가능).
#   ★이 값은 시행령(국가법령)의 실제 상한이며 조례 수치가 아니다(무날조). 조례가 더 엄격할 수
#   있으므로 '이내'라도 SATISFIED가 아닌 CONFIRM(조례 확인 필요)으로 정직 강등한다.
_SCALE_CAP_URBAN_GENERAL_SQM = 10_000.0   # 주거·상업·자연녹지·생산녹지
_SCALE_CAP_INDUSTRIAL_SQM = 30_000.0      # 공업지역
_SCALE_CAP_PRESERVATION_SQM = 5_000.0     # 보전녹지·자연환경보전
_SCALE_CAP_MANAGEMENT_SQM = 30_000.0      # 관리지역
_SCALE_CAP_AGRO_SQM = 30_000.0            # 농림지역

# 접도요건(건축법 제44조) — 통상 4m 이상 도로에 2m 이상 접함.
_MIN_ROAD_WIDTH_M = 4.0

# 면적 후보 키(호출부별 명칭 편차 흡수).
_AREA_KEYS = ("area_sqm", "land_area_sqm", "total_area_sqm", "area")


def _get_num(d: dict, keys: tuple[str, ...]) -> float | None:
    """여러 후보 키에서 첫 유효 숫자를 찾는다(없으면 None). special_parcel._num 재사용."""
    from app.services.zoning.special_parcel import _num

    for k in keys:
        v = _num(d.get(k))
        if v is not None:
            return v
    return None


def _scale_cap_sqm(zone_type: str) -> tuple[float | None, str]:
    """용도지역 → 개발행위허가 국가기준 규모 상한(㎡)과 근거 문구(시행령 §55).

    비대상(주거·상업·공업 등 세분 불가)이나 미상은 (None, 사유). 무날조 — 실제 시행령 값만.
    """
    from app.services.zoning.special_parcel import _zone_family

    z = (zone_type or "").replace(" ", "")
    family = _zone_family(zone_type)
    if family == "녹지":
        if "보전녹지" in z:
            return _SCALE_CAP_PRESERVATION_SQM, "국토계획법 시행령 제55조 — 보전녹지지역 5천㎡ 미만"
        return _SCALE_CAP_URBAN_GENERAL_SQM, "국토계획법 시행령 제55조 — 자연·생산녹지지역 1만㎡ 미만"
    if family == "자연환경보전":
        return _SCALE_CAP_PRESERVATION_SQM, "국토계획법 시행령 제55조 — 자연환경보전지역 5천㎡ 미만"
    if family == "관리":
        return _SCALE_CAP_MANAGEMENT_SQM, "국토계획법 시행령 제55조 — 관리지역 3만㎡ 미만"
    if family == "농림":
        return _SCALE_CAP_AGRO_SQM, "국토계획법 시행령 제55조 — 농림지역 3만㎡ 미만"
    if family == "주거" or family == "상업":
        return _SCALE_CAP_URBAN_GENERAL_SQM, "국토계획법 시행령 제55조 — 주거·상업지역 1만㎡ 미만"
    if family == "공업":
        return _SCALE_CAP_INDUSTRIAL_SQM, "국토계획법 시행령 제55조 — 공업지역 3만㎡ 미만"
    return None, "용도지역 미상 — 규모 국가상한 확인 불가"


def _eval_scale(
    zone_type: str, area_sqm: float | None, scale_limit_sqm: float | None
) -> dict[str, Any]:
    """규모기준 — 조례 상한(주입 시 우선) 또는 시행령 §55 국가상한 대비 판정.

    조례 상한 미주입 & 국가상한 이내 → CONFIRM(조례가 더 엄격할 수 있어 확인 필요 — 낙관 폴백 금지).
    """
    cap, cap_basis = _scale_cap_sqm(zone_type)
    if scale_limit_sqm is not None and scale_limit_sqm > 0:
        # 조례가 확보한 규모 상한이 있으면 그것을 정본으로 사용.
        if area_sqm is None:
            return {"status": CR_UNKNOWN, "limit_sqm": scale_limit_sqm,
                    "basis": "조례 규모 상한 확보 — 사업면적 미상으로 판정 불가",
                    "value": None}
        exceeds = area_sqm >= scale_limit_sqm
        return {
            "status": CR_EXCEEDS if exceeds else CR_SATISFIED,
            "limit_sqm": scale_limit_sqm, "value": area_sqm,
            "basis": (f"사업면적 {area_sqm:,.0f}㎡ vs 조례 개발행위허가 규모 상한 "
                      f"{scale_limit_sqm:,.0f}㎡ — {'초과' if exceeds else '이내'}"),
        }
    # 조례 상한 미확보 → 국가상한(시행령 §55) 참조.
    if cap is None:
        return {"status": CR_UNKNOWN, "limit_sqm": None, "value": area_sqm,
                "basis": cap_basis}
    if area_sqm is None:
        return {"status": CR_UNKNOWN, "limit_sqm": cap, "value": None,
                "basis": f"{cap_basis} — 사업면적 미상으로 판정 불가(관할 조례 규모기준 확인 필요)"}
    if area_sqm >= cap:
        return {
            "status": CR_EXCEEDS, "limit_sqm": cap, "value": area_sqm,
            "basis": (f"사업면적 {area_sqm:,.0f}㎡가 {cap_basis} 상한({cap:,.0f}㎡) 초과 — "
                      "단일 개발행위허가 규모 초과(도시계획위원회 심의·별도 절차 필요)"),
        }
    # 국가상한 이내라도 조례가 더 엄격할 수 있어 SATISFIED 단정 금지 → CONFIRM.
    return {
        "status": CR_CONFIRM, "limit_sqm": cap, "value": area_sqm,
        "basis": (f"사업면적 {area_sqm:,.0f}㎡는 {cap_basis} 상한({cap:,.0f}㎡) 이내이나, "
                  "지자체 도시계획조례가 더 엄격한 규모기준을 둘 수 있어 관할 조례 확인 필요"),
    }


def _eval_adjacent_development(cumulative_dev_area_sqm: float | None) -> dict[str, Any]:
    """연접개발·누적개발 영향 — 관할 개발행위허가 심의(§58 주변지역과의 관계) 검토사항.

    수치 임계를 날조하지 않는다(연접개발제한 규정은 폐지·개발행위허가기준으로 흡수). 관할 확인.
    """
    note = ("연접·누적개발 규모의 적정성은 관할 개발행위허가 심의(국토계획법 §58 — 주변지역 토지이용·"
            "기반시설과의 관계)에서 검토됩니다.")
    if cumulative_dev_area_sqm is not None:
        return {"status": CR_CONFIRM, "value": cumulative_dev_area_sqm,
                "basis": f"인접 누적개발면적 {cumulative_dev_area_sqm:,.0f}㎡ — {note} 관할 확인 필요"}
    return {"status": CR_CONFIRM, "value": None, "basis": note + " 관할 확인 필요"}


def _eval_infra_road(result: dict) -> dict[str, Any]:
    """기반시설(도로) — 진입도로 확보(건축법 §44 접도요건) 판정. 맹지/협소도로 세분.

    road_contact/road_width_m(또는 road_width)에서 접도 여부를 읽는다. 0폭·미접은 맹지(NOT_MET),
    4m 이상은 충족(MET), 0<폭<4m는 확인 필요(CONFIRM), 미상은 UNKNOWN(정직).
    """
    from app.services.zoning.special_parcel import _num

    rc = result.get("road_contact")
    rw = result.get("road_width_m")
    if rw is None:
        rw = result.get("road_width")
    rw = _num(rw)
    if rc is False or (rw is not None and rw == 0):
        return {"status": CR_NOT_MET, "value": (0.0 if rw is not None else None),
                "basis": ("도로에 접하지 않는 맹지 — 건축법 제44조 접도요건(4m 이상 도로에 2m 이상 접함) "
                          "미충족. 진입도로(사도 개설·지역권) 확보 선행 필요")}
    if rw is not None and rw >= _MIN_ROAD_WIDTH_M:
        return {"status": CR_MET, "value": rw,
                "basis": f"접도 도로폭 {rw:g}m(≥4m) — 건축법 제44조 접도요건 충족 추정"}
    if rw is not None and 0 < rw < _MIN_ROAD_WIDTH_M:
        return {"status": CR_CONFIRM, "value": rw,
                "basis": (f"접도 도로폭 {rw:g}m(<4m) — 현황도로 인정·도로 확폭 여부 관할 확인 필요")}
    return {"status": CR_UNKNOWN, "value": None,
            "basis": "접도(도로폭·접함) 데이터 미확보 — 진입도로 충족 판정 불가(현황도로 확인 필요)"}


def _eval_infra_sewer(result: dict) -> dict[str, Any]:
    """기반시설(상하수) — 하수처리구역 여부·원인자부담금/개인하수처리(하수도법) 판정.

    special_parcel._rule_by_sewer(정본)를 재사용해 하수 부담 고지를 흡수한다.
    """
    from app.services.zoning.special_parcel import _rule_by_sewer

    in_sewer = result.get("in_sewer_service_area")
    sewer_factor = _rule_by_sewer(result)  # 재사용(읽기 전용) — 원인자부담·개인하수처리 고지.
    disclosure = None
    if sewer_factor:
        impls = sewer_factor.get("implications") or []
        disclosure = impls[0] if impls else None
    if in_sewer is True:
        return {"status": CR_MET, "value": True,
                "basis": ("하수처리구역 내 — 공공하수도 이용 가능(신·증축 시 원인자부담금 검토). "
                          "하수도법 제61조"), "sewer_factor": sewer_factor}
    if in_sewer is False:
        return {"status": CR_CONFIRM, "value": False,
                "basis": ("하수처리구역 밖 — 개인하수처리시설(정화조·오수처리시설) 설치·신고 선행 필요. "
                          "하수도법 제34조"), "sewer_factor": sewer_factor}
    return {"status": CR_UNKNOWN, "value": None,
            "basis": (disclosure or "하수처리구역 편입 여부 미확보 — 상하수 기반시설 충족 판정 불가"),
            "sewer_factor": sewer_factor}


def _eval_slope(
    terrain_facts: dict | None, slope_criteria: dict | None
) -> dict[str, Any]:
    """경사도 — DEM 예비판정(special_parcel._slope_preliminary 재사용). ★예비(참고)·확정 아님.

    조례 경사도 기준(T2 resolve_slope_criteria)이 있으면 우선, 없으면 산지관리법 별표4 25° 폴백.
    예비 초과(EXCEEDS 상당)라도 hard-block하지 않는다 — 확정은 공식 평균경사도조사서로만.
    """
    from app.services.zoning.special_parcel import (
        _PRELIM_BORDER,
        _PRELIM_EXCEED,
        _num,
        _slope_preliminary,
    )

    dem_pct = _num((terrain_facts or {}).get("평균경사도_pct"))
    if dem_pct is None:
        return {"status": CR_UNKNOWN, "value": None,
                "basis": ("평균경사도(DEM/현장) 미확보 — 개발행위허가 경사도 기준 판정 불가"
                          "(관할 조례 경사도 기준·공식 평균경사도조사 필요)")}
    src = str((terrain_facts or {}).get("source") or "SRTM30_DEM")
    prelim = _slope_preliminary(dem_pct, slope_criteria, src)
    judg = prelim.get("judgment")
    if judg == _PRELIM_EXCEED:
        status = CR_EXCEEDS
    elif judg == _PRELIM_BORDER:
        status = CR_CONFIRM
    else:
        status = CR_SATISFIED
    return {
        "status": status, "value": dem_pct, "preliminary": prelim,
        "basis": (f"평균경사도 예비판정: {judg} (기준 {prelim.get('criteria_deg')}° / "
                  f"DEM {dem_pct}%) — 참고용(확정 아님, 공식 평균경사도조사서로만 확정)"),
    }


def _eval_elevation(
    elevation_m: float | None, elevation_criteria_m: float | None
) -> dict[str, Any]:
    """표고 — 조례 표고기준(별표1의2 위임)·현황표고 대비 판정. 둘 다 없으면 UNKNOWN(무날조)."""
    if elevation_m is not None and elevation_criteria_m is not None:
        exceeds = elevation_m > elevation_criteria_m
        return {"status": CR_NOT_MET if exceeds else CR_SATISFIED,
                "value": elevation_m, "criteria_m": elevation_criteria_m,
                "basis": (f"현황표고 {elevation_m:g}m vs 조례 표고기준 {elevation_criteria_m:g}m — "
                          f"{'초과' if exceeds else '이내'}")}
    return {"status": CR_UNKNOWN, "value": elevation_m,
            "basis": ("표고 기준(도시계획조례 별표1의2 위임) 또는 현황표고 미확보 — 관할 조례 표고기준 "
                      "확인 필요")}


def _criteria_evidence_items(criteria: dict[str, dict]) -> list[dict[str, Any]]:
    """기준별 판정을 evidence_contract items 형태로 변환({label,value,basis,legal_ref_key})."""
    label_ref = {
        "scale": ("규모기준(개발행위허가)", "dev_act_criteria"),
        "adjacent_development": ("연접·누적개발 영향", "dev_act_criteria"),
        "infrastructure_road": ("기반시설 — 진입도로", "road_relation"),
        "infrastructure_sewer": ("기반시설 — 상하수", "sewer_cause_charge"),
        "slope": ("경사도(예비판정)", "dev_permit_criteria"),
        "elevation": ("표고", "dev_permit_criteria"),
    }
    items: list[dict[str, Any]] = []
    for key, cr in criteria.items():
        label, ref = label_ref.get(key, (key, None))
        items.append({
            "label": f"{label}: {cr.get('status')}",
            "value": cr.get("value"),
            "basis": cr.get("basis"),
            "legal_ref_key": ref,
        })
    return items


def assess_dev_act_permit(
    result: dict[str, Any],
    *,
    slope_criteria: dict[str, Any] | None = None,
    terrain_facts: dict[str, Any] | None = None,
    scale_limit_sqm: float | None = None,
    elevation_m: float | None = None,
    elevation_criteria_m: float | None = None,
    cumulative_dev_area_sqm: float | None = None,
    sigungu: str | None = None,
) -> dict[str, Any] | None:
    """개발행위허가(국토계획법 §56~58) 절차게이트 — 대상 판정 + 기준별 판정 + 종합 status.

    Args:
        result: 부지 컨텍스트(zone_type·land_category·area_sqm·road_contact·road_width_m·
                in_sewer_service_area·land_form_change_required 등 — special_parcel 입력과 동형).
        slope_criteria: ordinance_service.resolve_slope_criteria(T2) 성공계약(있으면 경사도 기준).
        terrain_facts:  {"평균경사도_pct": float, "source": str}(있으면 경사도 예비판정).
        scale_limit_sqm: 조례 개발행위허가 규모 상한(㎡ — 확보 시 국가상한보다 우선).
        elevation_m / elevation_criteria_m: 현황표고 / 조례 표고기준(둘 다 있어야 판정).
        cumulative_dev_area_sqm: 인접 누적개발면적(있으면 연접 참고).
        sigungu:        조례 법령링크 치환용 관할명.

    Returns:
        None — zone_type·land_category·형질변경 신호가 전무해 판정 불가(정직 생략).
        아니면 {applicable, status, developability, zone_family, criteria{...}, reasons[...],
                honest_notes[...], evidence{...}, ...}.
    """
    from app.services.zoning.special_parcel import (
        _rule_by_dev_act_permit,
        _zone_family,
    )

    # ★키계약 관용: 상류 표면마다 용도지역 키가 zone_type/zone으로 갈리는 비대칭이 실존
    #   (예: scenario_simulator comp 폴백은 zone만 채움) — 어느 쪽이든 읽어 게이트 누락(FN)을 막는다.
    zone_type = str(result.get("zone_type") or result.get("zone") or "")
    land_category = str(result.get("land_category") or "")
    family = _zone_family(zone_type)
    # 형질변경(절토·성토·정지·포장) 명시 신호 — 도시지역이라도 형질변경 수반 시 개발행위허가 대상.
    explicit_form_change = bool(
        result.get("land_form_change_required") or result.get("requires_grading")
    )

    # ── 1) 개발행위허가 '대상' 판정(applicable) ── ★FN 0 핵심 ──
    applicable: bool | str
    applicability_basis: str
    if family in ("녹지", "관리", "농림", "자연환경보전"):
        applicable = True
        applicability_basis = "zone"  # 녹지·비도시 — 건축 전 개발행위허가 대상.
    elif family in ("주거", "상업", "공업"):
        if explicit_form_change:
            applicable = True
            applicability_basis = "land_form_change"  # 도시지역+형질변경 — 개발행위허가 대상.
        else:
            applicable = False
            applicability_basis = "urban_built"  # 도시지역 대지·형질변경 없음 — 건축허가로 처리.
    else:
        # 용도지역 미상(family=None).
        if explicit_form_change:
            applicable = True
            applicability_basis = "land_form_change"
        elif zone_type or land_category:
            applicable = "UNKNOWN"  # 신호는 있으나 분류 불가 — 관할 확인.
            applicability_basis = "zone_unclassified"
        else:
            return None  # 입력 전무 — 판정 불가(정직 생략, 무날조).

    # ── 2) 재사용: 발동 지역의 developability(_rule_by_dev_act_permit 확장) ──
    base_factor = None
    base_developability = None
    if applicable is True and applicability_basis == "zone":
        base_factor = _rule_by_dev_act_permit(result, include_non_urban=True)
        if base_factor:
            base_developability = base_factor.get("developability")

    # ── 3) 기준별(criteria) 판정 — 대상일 때만(비대상은 판정 불필요) ──
    criteria: dict[str, dict] = {}
    area_sqm = _get_num(result, _AREA_KEYS)
    if applicable is True:
        criteria["scale"] = _eval_scale(zone_type, area_sqm, scale_limit_sqm)
        criteria["adjacent_development"] = _eval_adjacent_development(cumulative_dev_area_sqm)
        criteria["infrastructure_road"] = _eval_infra_road(result)
        criteria["infrastructure_sewer"] = _eval_infra_sewer(result)
        criteria["slope"] = _eval_slope(terrain_facts, slope_criteria)
        criteria["elevation"] = _eval_elevation(elevation_m, elevation_criteria_m)

    # ── 4) 종합 status 집계 ──
    reasons: list[str] = []
    honest_notes: list[str] = []
    is_preservation = base_developability == "PRECONDITION"

    if applicable is False:
        status = STATUS_PASS
        developability = "POSSIBLE"
        reasons.append(
            "도시지역(주거·상업·공업)의 이미 대지화된 토지로, 형질변경이 수반되지 않으면 "
            "개발행위허가 별도 대상이 아닙니다(건축허가로 처리). ※절토·성토 등 형질변경 수반 시 재검토."
        )
    elif applicable == "UNKNOWN":
        status = STATUS_CONFIRM
        developability = "CONDITIONAL"
        reasons.append(
            "용도지역을 확정할 수 없어 개발행위허가 대상 여부를 단정할 수 없습니다 — "
            "토지이용계획확인원으로 용도지역을 확인하십시오(관할 확인 필요)."
        )
        honest_notes.append("개발행위허가 대상 여부 미확정(용도지역 미상) — 낙관 판단 금지.")
    else:
        # 대상(applicable=True) — 절대 PASS 아님.
        developability = base_developability or "CONDITIONAL"
        scale_exceeds = criteria.get("scale", {}).get("status") == CR_EXCEEDS
        road_not_met = criteria.get("infrastructure_road", {}).get("status") == CR_NOT_MET
        if is_preservation and scale_exceeds:
            # 보전 성격 지역에서 규모 국가상한 초과 → 단일 개발행위허가로 불가.
            status = STATUS_BLOCKED
            reasons.append(
                "보전 성격 용도지역에서 사업규모가 개발행위허가 국가상한을 초과해, 단일 개발행위허가로는 "
                "개발이 불가합니다(도시·군관리계획 변경 등 중대한 선행절차 필요)."
            )
        else:
            status = STATUS_CONDITIONAL
            if applicability_basis == "land_form_change":
                reasons.append(
                    "토지형질변경(절토·성토·정지·포장)이 수반되어 개발행위허가(국토계획법 §56)가 "
                    "선행/병행되어야 합니다 — 통과를 조건으로 개발 가능."
                )
            else:
                reasons.append(
                    "개발행위허가(국토계획법 §56)·토지형질변경 통과를 조건으로 개발이 가능합니다 — "
                    "밀도한도(건폐율·용적률) 충족만으로 개발이 확정되지 않습니다."
                )
            if is_preservation:
                honest_notes.append(
                    "보전 성격 용도지역 — 개발이 원칙적으로 제한되며 허용 범위가 좁습니다(강한 선행절차 전제)."
                )
        if scale_exceeds:
            reasons.append(criteria["scale"]["basis"])
        if road_not_met:
            reasons.append(criteria["infrastructure_road"]["basis"])
        # 미확정(조례·데이터 부재) 기준을 정직하게 집계 — 낙관 폴백 금지.
        unresolved = [k for k, cr in criteria.items()
                      if cr.get("status") in (CR_UNKNOWN, CR_CONFIRM)]
        if unresolved:
            honest_notes.append(
                "다음 기준은 조례·현장데이터 미확보로 확정 판정하지 못했습니다(관할 확인 필요): "
                + ", ".join(unresolved) + "."
            )

    # ── 5) ★FN 0 방어 가드 — 대상 필지는 절대 PASS 반환 금지 ──
    if applicable is True and status == STATUS_PASS:  # 논리상 도달 불가 — 안전장치.
        status = STATUS_CONDITIONAL
        honest_notes.append("[가드] 개발행위허가 대상 필지의 PASS 산출을 차단함(FN 방지).")

    # ── 6) evidence(근거+법령링크) 부착 — evidence_contract 공용 계약 재사용 ──
    legal_ref_keys = ["dev_act_permit", "dev_act_criteria", "land_form_change",
                      "dev_permit_criteria"]
    if applicable is True:
        if criteria.get("infrastructure_road", {}).get("status") in (CR_MET, CR_NOT_MET, CR_CONFIRM):
            legal_ref_keys.append("road_relation")
        sewer_factor = criteria.get("infrastructure_sewer", {}).get("sewer_factor")
        if sewer_factor:
            legal_ref_keys.extend(sewer_factor.get("legal_ref_keys") or [])
        if criteria.get("slope", {}).get("status") != CR_UNKNOWN:
            legal_ref_keys.append("forest_permit_criteria")
    # 중복 제거(순서 보존).
    legal_ref_keys = list(dict.fromkeys(legal_ref_keys))

    evidence_items = _criteria_evidence_items(criteria) if criteria else [{
        "label": f"개발행위허가 대상 판정: {applicability_basis}",
        "value": applicable, "basis": reasons[0] if reasons else None,
        "legal_ref_key": "dev_act_permit",
    }]
    try:
        from app.services.data_validation.evidence_contract import build_evidence_block

        evidence = build_evidence_block(
            items=evidence_items, legal_ref_keys=legal_ref_keys, sigungu=sigungu,
        )
    except Exception:  # noqa: BLE001 — evidence 실패는 판정 무손상(graceful).
        evidence = {"evidence": [], "legal_refs": [], "provenance": [], "trust": None}

    out: dict[str, Any] = {
        "gate": "dev_act_permit",  # 게이트 식별자.
        "applicable": applicable,
        "applicability_basis": applicability_basis,
        "status": status,
        "developability": developability,
        "zone_type": zone_type,
        "zone_family": family,
        "criteria": criteria,
        "reasons": reasons,
        "honest_notes": honest_notes,
        "evidence": evidence,
        "legal_basis": [
            "국토의 계획 및 이용에 관한 법률 제56조(개발행위의 허가)",
            "국토의 계획 및 이용에 관한 법률 제58조(개발행위허가의 기준)",
        ],
        "note": ("개발행위허가 판정(규칙기반) — 실제 허가 여부·세부기준은 관할 지자체 도시계획조례·"
                 "개발행위허가 심의로 확정하십시오. 경사도는 예비판정(참고용·확정 아님)입니다."),
    }
    if base_factor:
        # 재사용한 발동 요인(implications·permit_prerequisites·legal_refs)을 그대로 동봉(전역 패리티).
        out["base_factor"] = base_factor
    return out


def _resolve_zone_code_alias(zone_type: str | None) -> str | None:
    """축약 용도지역 코드(예: "2R") → 한글 용도지역명 리졸브 — 플랫폼 정본 별칭표 재사용(WP-B 항목4).

    design_ingest.design_geometry._ZONE_CODE_ALIAS(zone_code→한글명 7종 — 프론트 zoningToCode의
    파이썬측 정본 대응표)를 그대로 재사용한다(재발명 금지). 별칭표에 없는 값(이미 한글명이거나
    인식 불가 코드)은 원문 그대로 반환한다 — 이후 _zone_family가 재판정하므로 추측·날조가 없다.
    """
    if not zone_type:
        return zone_type
    from app.services.design_ingest.design_geometry import _ZONE_CODE_ALIAS

    key = zone_type.replace(" ", "").strip()
    return _ZONE_CODE_ALIAS.get(key, zone_type)


def build_dev_act_permit_gate(
    *,
    zone_type: str | None = None,
    land_category: str | None = None,
    area_sqm: float | None = None,
    road_contact: bool | None = None,
    road_width_m: float | None = None,
    in_sewer_service_area: bool | None = None,
    land_form_change_required: bool | None = None,
    special_districts: list[str] | None = None,
    slope_criteria: dict[str, Any] | None = None,
    terrain_facts: dict[str, Any] | None = None,
    scale_limit_sqm: float | None = None,
    elevation_m: float | None = None,
    elevation_criteria_m: float | None = None,
    sigungu: str | None = None,
    pnu: str | None = None,
) -> dict[str, Any] | None:
    """설계·매스 산출 경로(design_v61 등)용 표준 부착 헬퍼 — 명시 필드에서 게이트를 산출.

    build_special_parcel_gate(특이부지 게이트)와 동일한 additive 패턴. 컨텍스트가 전무하면
    None(정직 생략). 산출 실패(예외)는 graceful None으로 흡수해 주 경로(매스 산출)를 깨지 않는다.

    ★설계경로 노이즈 방어(WP-B 항목4): zone_type이 한글 용도지역명이 아니라 축약코드(예: "2R")면
    먼저 _resolve_zone_code_alias로 한글명 리졸브를 시도한다(예: "2R"→"제2종일반주거지역" — 이후
    정상적으로 '도시지역·형질변경 없음=PASS' 판정까지 흐른다). 리졸브에 실패(별칭표에 없는 코드)
    했고 형질변경 신호도 없을 때, 지목이 '대'(이미 대지화된 토지)면 불필요한 '관할 확인' 게이트를
    만들지 않는다(None). ★FN 0 불변식 보호: 리졸브 성공(녹지·비도시로 판명) 또는 형질변경 신호가
    있으면 이 억제는 절대 적용되지 않으며, 지목이 '대' 이외(임야·전·답 등 비도시 가능성이 있는
    지목)면 억제하지 않고 기존처럼 관할 확인(CONFIRM) 게이트를 그대로 발동한다.
    """
    if not (zone_type or land_category or land_form_change_required):
        return None
    from app.services.zoning.special_parcel import _zone_family

    resolved_zone_type = _resolve_zone_code_alias(zone_type)
    family = _zone_family(resolved_zone_type)
    if family is None:
        if land_form_change_required:
            pass  # 형질변경 신호가 있으면 비도시 가능성을 배제할 수 없어 정상 판정 경로로 진행.
        elif not land_category:
            return None  # 기존 동작 그대로 — 신호 전무는 정직 생략.
        elif land_category.strip() == "대":
            return None  # ★항목4 신설 — 리졸브 불가+형질변경 없음+이미 대지화(지목 '대')만 억제.
        # else: 지목이 '대' 이외(임야·전·답 등) — FN 0 보호를 위해 억제하지 않고 CONFIRM 경로 진행.
    try:
        result: dict[str, Any] = {
            "zone_type": resolved_zone_type or zone_type or "",
            "land_category": land_category or "",
            "special_districts": list(special_districts or []),
        }
        if area_sqm:
            result["area_sqm"] = area_sqm
        if road_contact is not None:
            result["road_contact"] = road_contact
        if road_width_m is not None:
            result["road_width_m"] = road_width_m
        if in_sewer_service_area is not None:
            result["in_sewer_service_area"] = in_sewer_service_area
        if land_form_change_required:
            result["land_form_change_required"] = True
        gate = assess_dev_act_permit(
            result,
            slope_criteria=slope_criteria,
            terrain_facts=terrain_facts,
            scale_limit_sqm=scale_limit_sqm,
            elevation_m=elevation_m,
            elevation_criteria_m=elevation_criteria_m,
            sigungu=sigungu,
        )
    except Exception:  # noqa: BLE001 — 게이트 실패가 매스 산출을 깨면 안 됨(best-effort).
        return None
    if gate and pnu:
        gate["pnu"] = pnu  # 추적용 메타 echo(판정에는 미사용).
    return gate
