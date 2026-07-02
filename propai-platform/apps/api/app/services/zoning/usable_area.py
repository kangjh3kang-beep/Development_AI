"""실사용가능용지(usable_area) 3계층 정산 + 제외 시나리오 what-if — 순수함수(외부콜 0).

S3-B(MULTI_PARCEL_ATTRIBUTES_PLAN_2026-07-03): 다필지 세트에서 '전체 면적'과 '실제로 개발에
쓸 수 있는 면적'은 다르다. 도로·구거·하천 지목이나 BLOCKED 필지가 섞이면 그 면적은 통합
개발규모 산정에서 빠져야 하고, 조건부(PRECONDITION/CONDITIONAL/NEEDS_OFFICIAL_SURVEY)
필지는 '선행절차 통과를 전제로 한 잠정 면적'으로 구분 표기돼야 한다.

3계층 + 제외 명세:
  gross_sqm               전 필지 면적 합(면적 미확보 필지는 합산 제외 + 명세)
  usable_confirmed_sqm    POSSIBLE·CAUTION — 통상 개발 가능 면적
  usable_conditional_sqm  PRECONDITION·CONDITIONAL·NEEDS_OFFICIAL_SURVEY — 조건 목록 동반
  excluded_sqm            BLOCKED/resolvable=NO + 도로·구거·하천 지목 — 사유별 명세

무날조 원칙:
  · 임의 감보 계수 금지 — 도로·구거·하천은 '건축 불가 지목'으로 전액 제외하되,
    용도폐지·합필(토지합병) 시 포함 가능성은 관할 확인 사항으로 honest 고지한다.
  · 정밀 감보율(도로개설·기부채납·환지 감보)은 사업계획 확정 전 산정 불가 — 미산정 + 사유.
  · 면적 미확보 필지는 0으로 날조하지 않고 area_unknown_parcels 로 별도 명세 + 경고.

S3-C simulate_exclusion: 필지 제외 what-if — 제외 전/후 3계층 재정산 비교표(순수).
  ★통합 한도(용적률·GFA) 재산정은 호출부가 `_aggregate_integrated_zoning`으로 조립한다
  (본 모듈은 면적 3계층 재정산까지만 담당 — W2 배선 소관).

게이트 문자열 계약: special_parcel.py 의 GATE_* SSOT와 동일 문자열을 자체 상수로 유지한다.
  (special_parcel.py 가 W2에서 본 모듈을 임포트해 detect_multi_parcel 에 합류시킬 예정이라,
   여기서 special_parcel 을 모듈수준 임포트하면 순환 임포트가 된다 — 자체 상수 + 계약 테스트
   `test_gate_contract_matches_special_parcel_ssot` 로 문자열 일치를 고정한다.)
"""
from __future__ import annotations

from typing import Any

# ── 게이트 문자열 계약(★special_parcel.py GATE_* SSOT와 문자 단위 일치 — 계약 테스트로 고정) ──
GATE_BLOCK_DEVELOPABILITY = {"BLOCKED"}
GATE_BLOCK_RESOLVABLE = {"NO"}
GATE_TENTATIVE_DEVELOPABILITY = {"PRECONDITION", "CONDITIONAL", "NEEDS_OFFICIAL_SURVEY"}
GATE_TENTATIVE_RESOLVABLE = {"CONDITIONAL"}

# 건축 불가 지목(전액 제외) — 계획서 S3-B 확정 범위: 도로·구거·하천만(임의 확장 금지).
#   공부 지목부호(공간정보관리법 시행령 제58조·지적공부 표기): 도로→도, 구거→구, 하천→천.
EXCLUDED_LAND_CATEGORIES = {"도로", "구거", "하천"}
_EXCLUDED_CATEGORY_CODES = {"도": "도로", "구": "구거", "천": "하천"}

# 조건부 등급별 조건 문구 — special_parcel.tentative_marker 의 사유 체계와 정합(문구는 요약형).
_CONDITION_BY_GRADE = {
    "PRECONDITION": "선행 도시계획 변경·시설폐지 등 중대한 선행절차 통과 필요(확정 아님)",
    "CONDITIONAL": "인허가·전용·협의 등 선행절차 통과 필요(확정 아님)",
    "NEEDS_OFFICIAL_SURVEY": (
        "공식 산림데이터(산지구분·평균경사도·입목축적) 확보 후 산지전용 가능규모 확정 필요"
        "(현재는 참고용 예비안)"
    ),
}


def _area_sqm(p: dict) -> float | None:
    """필지 면적(㎡) — area_sqm / areaSqm / area 순으로 탐색. 미확보·비양수는 None(무날조)."""
    for key in ("area_sqm", "areaSqm", "area"):
        v = p.get(key)
        if v is None:
            continue
        try:
            a = float(v)
        except (TypeError, ValueError):
            continue
        if a > 0:
            return a
    return None


def _gates(p: dict) -> tuple[str, str]:
    """필지에서 (developability, resolvable) 추출 — 최상위 키 우선, 없으면 special 중첩.

    detect_multi_parcel per_parcel 형상({special: {...}|None})과 평면 형상 모두 수용.
    신호가 전혀 없으면 (POSSIBLE, YES) — special=None 은 '일상 필지'라는 기존 계약과 동일.
    """
    special = p.get("special") if isinstance(p.get("special"), dict) else {}
    dev = p.get("developability") or special.get("developability") or "POSSIBLE"
    res = p.get("resolvable") or special.get("resolvable") or "YES"
    return str(dev).strip().upper(), str(res).strip().upper()


def _factor_categories(p: dict) -> list[str]:
    """special.factors[].category — 조건 상세(설명가능성)용. 없으면 빈 리스트."""
    special = p.get("special") if isinstance(p.get("special"), dict) else {}
    out: list[str] = []
    for f in special.get("factors") or []:
        cat = (f or {}).get("category")
        if cat:
            out.append(str(cat))
    return out


def _excluded_category(land_category: str | None) -> str | None:
    """건축 불가 지목이면 정규화된 지목명(도로/구거/하천), 아니면 None. 정확 매칭만(오탐 방지)."""
    c = str(land_category or "").strip()
    if c in EXCLUDED_LAND_CATEGORIES:
        return c
    return _EXCLUDED_CATEGORY_CODES.get(c)


def _brief(p: dict, i: int, area: float | None, dev: str, res: str) -> dict[str, Any]:
    return {
        "index": p.get("index", i),
        "pnu": p.get("pnu"),
        "land_category": p.get("land_category"),
        "area_sqm": round(area, 2) if area is not None else None,
        "developability": dev,
        "resolvable": res,
    }


def compute_usable_area(parcels: list[dict]) -> dict[str, Any]:
    """다필지 세트의 실사용가능용지 3계층 정산(순수함수·결정론).

    입력: per_parcel 유사 dict 리스트 — 면적(area_sqm|areaSqm|area)·지목(land_category)·
      게이트(developability/resolvable 최상위 또는 special 중첩; special=None=일상 필지).
    반환: {parcel_count, gross_sqm, usable_confirmed_sqm, usable_conditional_sqm(조건 목록),
      excluded_sqm(사유 명세), confirmed/conditional/excluded/area_unknown parcels,
      share, basis, honest_notes, warnings} — 미확보는 명세+경고(무날조), 입력 불변(순수).
    불변식: confirmed + conditional + excluded == gross (면적 확보 필지 기준, 면적 보존).
    """
    items = list(parcels or [])
    confirmed: list[dict] = []
    conditional: list[dict] = []
    excluded: list[dict] = []
    area_unknown: list[dict] = []
    warnings: list[str] = []

    sum_confirmed = 0.0
    sum_conditional = 0.0
    sum_excluded = 0.0
    gross = 0.0
    has_category_exclusion = False

    for i, p in enumerate(items):
        area = _area_sqm(p)
        dev, res = _gates(p)
        brief = _brief(p, i, area, dev, res)

        # ── 계층 판정(면적과 독립 — 면적 미확보여도 계층은 명세) ──
        reasons: list[dict[str, str]] = []
        norm_cat = _excluded_category(p.get("land_category"))
        if norm_cat:
            has_category_exclusion = True
            reasons.append({
                "code": "non_buildable_land_category",
                "detail": (f"지목 '{norm_cat}'은(는) 건축 불가 지목으로 사용가능 면적에서 전액 "
                           "제외했습니다(임의 감보 계수 미적용). 용도폐지·합필 시 포함 가능성은 "
                           "관할 지자체 확인이 필요합니다."),
            })
        if dev in GATE_BLOCK_DEVELOPABILITY:
            reasons.append({
                "code": "developability_blocked",
                "detail": f"개발가능성 게이트 {dev} — 원칙적으로 일반 개발 불가 판정 필지입니다.",
            })
        if res in GATE_BLOCK_RESOLVABLE:
            reasons.append({
                "code": "resolvable_no",
                "detail": "해결가능성 NO — 통상 절차로 해결 불가능한 제약이 있는 필지입니다.",
            })

        if reasons:
            tier = "excluded"
            brief["reasons"] = reasons
            excluded.append(brief)
        elif dev in GATE_TENTATIVE_DEVELOPABILITY or res in GATE_TENTATIVE_RESOLVABLE:
            tier = "conditional"
            conditions = []
            grade_note = _CONDITION_BY_GRADE.get(dev)
            if grade_note:
                conditions.append(grade_note)
            if res in GATE_TENTATIVE_RESOLVABLE and not grade_note:
                conditions.append(_CONDITION_BY_GRADE["CONDITIONAL"])
            cats = _factor_categories(p)
            if cats:
                conditions.append("특이요인: " + " · ".join(cats))
            if not conditions:  # 방어 — 조건부인데 사유 미상이면 미상임을 정직 표기.
                conditions.append("선행절차 통과 필요(세부 조건 미상 — 확정 아님)")
            brief["conditions"] = conditions
            conditional.append(brief)
        else:
            tier = "confirmed"
            confirmed.append(brief)

        # ── 면적 합산(미확보는 날조 없이 별도 명세) ──
        if area is None:
            area_unknown.append({"index": brief["index"], "pnu": brief["pnu"],
                                 "land_category": brief["land_category"], "tier": tier})
            continue
        gross += area
        if tier == "confirmed":
            sum_confirmed += area
        elif tier == "conditional":
            sum_conditional += area
        else:
            sum_excluded += area

    if area_unknown:
        warnings.append(
            f"{len(area_unknown)}개 필지의 면적이 미확보되어 합산에서 제외했습니다"
            "(0으로 가정하지 않음 — 공부 면적 확보 후 재정산 필요)."
        )

    honest_notes = [
        "정밀 감보율(도로개설·기부채납·환지 감보 등)은 사업계획 확정 전에는 산정할 수 없어 "
        "미적용했습니다 — 실제 사용가능 면적은 이 수치보다 줄어들 수 있습니다.",
    ]
    if has_category_exclusion:
        honest_notes.append(
            "도로·구거·하천 지목 필지는 건축 불가 지목으로 전액 제외했습니다. 다만 용도폐지·"
            "합필(토지합병) 시 포함될 가능성이 있으므로 관할 지자체 확인이 필요합니다."
        )
    if conditional:
        honest_notes.append(
            "조건부(usable_conditional) 면적은 선행절차 통과를 전제로 한 잠정치입니다(확정 아님) — "
            "미통과 시 해당 필지 제외 후 재정산이 필요합니다."
        )

    def _pct(v: float) -> float | None:
        return round(v / gross * 100, 1) if gross > 0 else None

    return {
        "parcel_count": len(items),
        "gross_sqm": round(gross, 2),
        "usable_confirmed_sqm": round(sum_confirmed, 2),
        "usable_conditional_sqm": round(sum_conditional, 2),
        "excluded_sqm": round(sum_excluded, 2),
        "share": {
            "confirmed_pct": _pct(sum_confirmed),
            "conditional_pct": _pct(sum_conditional),
            "excluded_pct": _pct(sum_excluded),
        },
        "confirmed_parcels": confirmed,
        "conditional_parcels": conditional,
        "excluded_parcels": excluded,
        "area_unknown_parcels": area_unknown,
        "basis": ("지목(도로·구거·하천 전액 제외)·developability 게이트 기반 3계층 면적 정산 — "
                  "임의 감보 계수 미적용(무날조), 게이트 기준은 특이부지 감지 SSOT와 동일"),
        "honest_notes": honest_notes,
        "warnings": warnings,
    }


def simulate_exclusion(parcels: list[dict], exclude_pnus: list[str] | set[str] | None) -> dict[str, Any]:
    """제외 시나리오 what-if — exclude_pnus 필지 제외 전/후 3계층 재정산 비교표(순수).

    반환: {requested/applied/not_found pnus, excluded_parcels(제외분 명세), lost_area_sqm,
      before/after(compute_usable_area 결과), delta(after-before), remaining_parcels(입력
      dict 원본 참조 — 무변형), remaining_parcel_count, note}.
    ★통합 한도(blended FAR·GFA) 재산정은 여기서 하지 않는다 — 호출부(W2)가 remaining_parcels
      를 `_aggregate_integrated_zoning`에 넘겨 조립한다(면적 3계층까지가 본 함수 소관).
    """
    items = list(parcels or [])
    requested = sorted({str(x).strip() for x in (exclude_pnus or []) if x is not None and str(x).strip()})
    req_set = set(requested)

    removed: list[dict] = []
    remaining: list[dict] = []
    applied: set[str] = set()
    for i, p in enumerate(items):
        pnu = str(p.get("pnu") or "").strip()
        if pnu and pnu in req_set:
            applied.add(pnu)
            area = _area_sqm(p)
            removed.append({"index": p.get("index", i), "pnu": p.get("pnu"),
                            "land_category": p.get("land_category"),
                            "area_sqm": round(area, 2) if area is not None else None})
        else:
            remaining.append(p)

    before = compute_usable_area(items)
    after = compute_usable_area(remaining)
    delta_keys = ("gross_sqm", "usable_confirmed_sqm", "usable_conditional_sqm", "excluded_sqm")
    delta = {k: round((after[k] or 0.0) - (before[k] or 0.0), 2) for k in delta_keys}
    lost = round(sum(r["area_sqm"] for r in removed if r["area_sqm"] is not None), 2)

    return {
        "requested_exclude_pnus": requested,
        "applied_exclude_pnus": sorted(applied),
        "not_found_pnus": sorted(req_set - applied),
        "excluded_parcels": removed,
        "lost_area_sqm": lost,
        "before": before,
        "after": after,
        "delta": delta,
        "remaining_parcels": remaining,
        "remaining_parcel_count": len(remaining),
        "note": ("면적 3계층 재정산 비교표(순수 산출) — 통합 한도(면적가중 용적률·통합 GFA) "
                 "재산정은 호출부가 remaining_parcels 로 _aggregate_integrated_zoning 을 "
                 "재실행해 조립합니다."),
    }
