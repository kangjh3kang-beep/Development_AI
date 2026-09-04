"""rule_trace — 매스 산출에 '어떤 법규가 어떤 값으로 적용됐는지' 추적표(rule_trace)를 붙이는 순수 헬퍼.

(C2R 문서 rule kernel trace + §4 rule_set_hash ADAPT·INC5-a)

이 파일이 푸는 문제(쉬운 설명):
- 지금 우리 엔진은 '용적률 1000%·정북일조 35m·조례 250%' 같은 한도를 적용해 매스(층수·면적)를
  산출한다. 그런데 결과만 보면 '왜 이 한도인가(어떤 법규·어떤 값)'가 보이지 않는다.
- 그래서 이 파일은 산출이 이미 끝난 매스/법규 dict를 '읽기만' 해서, 적용된 규칙별로
  {규칙코드·이름·적용값·근거·출처·법령링크} 한 줄(entry)을 모은 추적표(rule_trace)와,
  그 묶음의 결정적 해시(rule_set_hash)를 만들 dict(rule_set)를 돌려준다.
  이로써 §4 provenance triad(input_hash·geometry_hash·rule_set_hash)가 완성되고,
  결과물에 '근거(왜 이 한도인가)'를 추적할 수 있다.

★수치 무변경(핵심): 이 모듈은 매스를 절대 재산출하지 않는다. 이미 나온 값을 '읽어서' 추적표만 만든다.
★무날조: 적용 안 된 규칙은 entry를 만들지 않는다(가짜 entry 금지). 미상값은 None으로 둔다(가짜값 금지).
★결정론: rule_set은 결정적 수치만 담고, 해시는 호출부가 provenance.compute_input_hash(rule_set)로 계산한다
  (normalize_fingerprint+canonical_json 재사용 → int/float·키순서·미세 부동소수에 둔감).

신규 의존성 0: 표준 타입만 쓰고, 해시는 기존 provenance 헬퍼(INC3)를 호출부에서 재사용한다.
"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


# ── 작은 읽기 가드(무날조) ──

def _num(value: Any) -> float | None:
    """값이 숫자면 float로, 아니면 None(=미상 → 가짜값 금지). NaN/inf는 None으로 흡수."""
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    # NaN/inf는 자기 자신과 같지 않거나 무한대 — 둘 다 None으로 흡수(가짜값 금지).
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def _pick(d: dict, *keys: str) -> Any:
    """dict에서 후보 키들을 순서대로 보고 첫 번째로 존재하는 값을 돌려준다(없으면 None).

    왜: legal dict는 경로마다 키 이름이 갈린다(get_legal_limits는 max_far_percent,
    일부 소비처는 statutory_max_far_percent). 둘 다 받아 같은 추적표를 만든다(방어적 읽기).
    """
    if not isinstance(d, dict):
        return None
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def _verified_legal_link(ref_key: str) -> str | None:
    """마스터 법령 레지스트리에서 '검증된 법령 딥링크(law.go.kr 한글주소)'만 가져온다(무날조).

    왜(쉬운 설명): rule_trace의 출처(source)는 사람이 읽는 법령명 문자열이라 그대로는 링크가 안 된다.
      legal_reference_registry는 블루프린트 ②-3에서 '검증된 법령명+조문'만 모아 딥링크를 만들어 둔다.
      여기선 그 검증된 url만 끌어와 붙인다 — 레지스트리에 없거나 url이 비면 None(가짜 링크 절대 금지).

    ★결정론·무회귀: rule_set(해시 대상)에는 링크를 넣지 않으므로(아래 결정적 수치만), 링크를 채워도
      rule_set_hash는 불변이다. 레지스트리 조회 실패는 링크 없음으로 정직 폴백(예외 전파 안 함).
    """
    try:
        # 지연 import — 모듈 로드 시 순환참조·부작용 0(레지스트리는 순수 데이터 매핑).
        from app.services.legal.legal_reference_registry import get_legal_ref

        ref = get_legal_ref(ref_key)
    except Exception:  # noqa: BLE001 — 조회 실패는 링크 없음으로 정직 폴백
        return None
    url = ref.get("url") if isinstance(ref, dict) else None
    return url if isinstance(url, str) and url.strip() else None


def build_rule_trace(
    site_input: Any,
    legal: dict | None,
    mass: dict | None,
) -> tuple[list[dict], dict]:
    """매스 산출에 적용된 규칙별 추적표(rule_trace)와 해시 대상 dict(rule_set)를 만든다(순수·읽기전용).

    Args:
        site_input: SiteInput(zone_code·building_use·target_far_percent·target_bcr_percent·
            ordinance_far_percent·ordinance_bcr_percent). getattr로 안전하게 읽는다(미상=None).
        legal: get_legal_limits 반환 dict(statutory_max_*_percent 또는 max_*_percent 등).
        mass: compute_optimal_mass 출력 dict(applied_max_*_pct·far_pct·bcr_pct·sunlight_mode·
            max_height_by_sunlight_m·binding_constraint·num_floors).

    Returns:
        (rule_trace, rule_set).
        - rule_trace: 적용 규칙별 entry 리스트. 각 entry는 {rule_code,rule_name,applied,basis,
          source,legal_link}. ★적용 안 된 규칙은 제외(무날조).
        - rule_set: rule_set_hash 계산용 결정적 수치 dict. 호출부가 compute_input_hash(rule_set)로 해시.

    ★수치 무변경: mass/legal/site_input을 '읽기만' 한다(재산출 0·입력 변경 0).
    """
    legal = legal if isinstance(legal, dict) else {}
    mass = mass if isinstance(mass, dict) else {}

    # ── site_input에서 결정적 입력 필드를 안전하게 읽는다(미상=None·무날조) ──
    zone_code = getattr(site_input, "zone_code", None)
    building_use = getattr(site_input, "building_use", None)
    target_far = _num(getattr(site_input, "target_far_percent", None))
    target_bcr = _num(getattr(site_input, "target_bcr_percent", None))
    ord_far = _num(getattr(site_input, "ordinance_far_percent", None))
    ord_bcr = _num(getattr(site_input, "ordinance_bcr_percent", None))

    # ── legal(법정 한도) — 키 이름이 경로마다 달라 둘 다 받는다(방어적 읽기) ──
    statutory_far = _num(_pick(legal, "statutory_max_far_percent", "max_far_percent"))
    statutory_bcr = _num(_pick(legal, "statutory_max_bcr_percent", "max_bcr_percent"))

    # ── mass(이미 산출된 결과) — 읽기만 ──
    applied_far = _num(mass.get("applied_max_far_pct"))
    applied_bcr = _num(mass.get("applied_max_bcr_pct"))
    far_pct = _num(mass.get("far_pct"))
    bcr_pct = _num(mass.get("bcr_pct"))
    sunlight_mode = mass.get("sunlight_mode")
    max_h_by_sun = _num(mass.get("max_height_by_sunlight_m"))
    binding_constraint = mass.get("binding_constraint")
    num_floors = mass.get("num_floors")

    rule_trace: list[dict] = []

    # ── 1) 면적·용적/건폐(국토계획법 시행령 §84·85, 건축법 시행령 §119) ──
    #   적용된 용적률·건폐율(far_pct·bcr_pct)이 어떤 한도들의 min으로 정해졌는지 근거를 만든다.
    #   basis는 '있는 항'만 묶는다(법정/조례/목표 중 주어진 것만 — 가짜 항 금지·무날조).
    far_terms: list[str] = []
    if statutory_far is not None:
        far_terms.append(f"법정 {statutory_far:g}%")
    if ord_far is not None:
        far_terms.append(f"조례 {ord_far:g}%")
    if target_far is not None:
        far_terms.append(f"목표 {target_far:g}%")
    bcr_terms: list[str] = []
    if statutory_bcr is not None:
        bcr_terms.append(f"법정 {statutory_bcr:g}%")
    if ord_bcr is not None:
        bcr_terms.append(f"조례 {ord_bcr:g}%")
    if target_bcr is not None:
        bcr_terms.append(f"목표 {target_bcr:g}%")
    far_basis = f"용적률 = min({', '.join(far_terms)})" if far_terms else "용적률 한도 미상"
    bcr_basis = f"건폐율 = min({', '.join(bcr_terms)})" if bcr_terms else "건폐율 한도 미상"
    rule_trace.append({
        "rule_code": "건축법시행령_119/국토계획법시행령_84_85",
        "rule_name": "용적률·건폐율 한도",
        "applied": {
            "far_pct": far_pct,
            "bcr_pct": bcr_pct,
            "applied_max_far_pct": applied_far,
            "applied_max_bcr_pct": applied_bcr,
        },
        "basis": f"{far_basis}; {bcr_basis}",
        "source": "국토계획법 시행령 §84·85, 건축법 시행령 §119",
        # ★검증된 법령 딥링크 — 용적률 한도(국토계획법 시행령 §85)를 대표 링크로(far_limit 키).
        #   건폐율(§84)·면적산정(건축법 시행령 §119)은 source 문자열에 함께 표기(단일 링크는 대표 1개).
        "legal_link": _verified_legal_link("far_limit"),
    })

    # ── 2) 정북일조 높이제한(건축법 §61·시행령 §86) ──
    #   ★적용된 경우에만 entry(무날조). sunlight_mode가 not_applicable이면 적용 안 됨(상업/준주거) → 생략.
    #   hard_cap(높이캡)/step_profile(단계후퇴) 모드만 적용 대상(주거지역).
    if sunlight_mode and sunlight_mode != "not_applicable":
        rule_trace.append({
            "rule_code": "건축법_61/시행령_86",
            "rule_name": "정북일조 높이제한",
            "applied": {
                "sunlight_mode": sunlight_mode,
                "max_height_by_sunlight_m": max_h_by_sun,
            },
            "basis": "전용·일반주거지역 정북사선(높이 10m 초과부 h/2 이격)",
            "source": "건축법 §61·시행령 §86",
            # ★검증된 법령 딥링크 — 일조 높이제한 모법(건축법 §61, daylight_height 키). 시행령 §86은 source에 병기.
            "legal_link": _verified_legal_link("daylight_height"),
        })

    # ── 3) 조례/실효 한도(지자체 도시계획조례·부지분석 실효) ──
    #   ★조례값(ordinance_*)이 실제로 주어진 경우에만 entry(무날조 — 없으면 생략).
    #   ★WP-U2a: 주입값이 far_tier SSOT(calc_effective_far) 산출 실효치면 그 산정 근거
    #     (far_basis — 예 "구조상한(건폐율×층수)")를 정직 병기한다. 종전엔 SSOT 실효치도
    #     일괄 "조례 실효한도"로 표기해 근거가 소실됐다(구조상한 유래를 조례로 오인).
    ssot_far_basis = getattr(site_input, "far_basis", None)
    ssot_far_reliable = getattr(site_input, "far_reliable", None)
    if ord_far is not None or ord_bcr is not None:
        _applied: dict[str, Any] = {
            "ordinance_far_pct": ord_far,
            "ordinance_bcr_pct": ord_bcr,
        }
        _basis = "조례 실효한도(법정 이내로만 적용 — 가짜 상향 금지)"
        if ssot_far_basis is not None or ssot_far_reliable is not None:
            # SSOT 근거 메타가 온 경우에만 additive 키 추가(기존 trace 모양 불변·무회귀).
            _applied["far_basis"] = ssot_far_basis
            _applied["far_reliable"] = ssot_far_reliable
            if ssot_far_basis:
                _basis = (
                    f"부지분석 실효한도(산정근거: {ssot_far_basis} — far_tier SSOT, "
                    "법정 이내로만 적용·가짜 상향 금지)"
                )
        rule_trace.append({
            "rule_code": "지자체_도시계획조례",
            "rule_name": "조례 실효 한도",
            "applied": _applied,
            "basis": _basis,
            "source": "지자체 도시계획조례",
            # ★조례 딥링크는 지자체명(sigungu)이 있어야 검증 가능(예: "서울특별시 도시계획 조례").
            #   이 추적표에는 지자체명이 없어 가짜 링크 대신 None으로 둔다(무날조 — build_ordinance_url 미사용).
            "legal_link": None,
        })

    # ── 4) 층수 결속요인(binding_constraint) ──
    #   어떤 제약이 층수를 결정했는지(far|height|sunlight|setback) 기록한다(있으면).
    if binding_constraint is not None:
        rule_trace.append({
            "rule_code": "binding_constraint",
            "rule_name": "층수 결속요인",
            "applied": {
                "binding_constraint": binding_constraint,
                "num_floors": num_floors,
            },
            "basis": f"{binding_constraint}이(가) 층수를 결정",
            "source": "설계엔진 산출(법정 한도·일조·높이 종합)",
            # 이 entry는 특정 법조문이 아니라 '엔진의 종합 산출'이라 법령 딥링크 대상이 아니다(None — 정직).
            "legal_link": None,
        })

    # ── rule_set: rule_set_hash 계산용 결정적 수치 dict(미상은 None으로 일관·결정론) ──
    #   ★결정적 수치만 담는다(basis 문자열·링크 제외). 호출부가 compute_input_hash로 해시한다.
    rule_set: dict[str, Any] = {
        "zone_code": zone_code,
        "building_use": building_use,
        "statutory_far": statutory_far,
        "statutory_bcr": statutory_bcr,
        "applied_far": applied_far,
        "applied_bcr": applied_bcr,
        "ordinance_far": ord_far,
        "ordinance_bcr": ord_bcr,
        "target_far": target_far,
        "target_bcr": target_bcr,
        "sunlight_mode": sunlight_mode,
        "binding_constraint": binding_constraint,
    }

    logger.debug(
        "rule_trace 구성 완료",
        zone=zone_code,
        entries=len(rule_trace),
        sunlight_mode=sunlight_mode,
    )
    return rule_trace, rule_set
