"""design_contract — 매스에 C2R 계약(envelope_result·geometry_invariants·rule_trace·rule_set_hash)을
한 번에 묶어주는 '공용 헬퍼'.

이 파일이 푸는 문제(쉬운 설명):
- 지금까지 C2R 계약(매스를 표준 그릇 EnvelopeResult로 변환 + 기하 불변식 점검 + 적용 법규 추적표 +
  provenance 해시)은 자동설계 엔진의 generate() '한 군데'에만 손으로 길게 붙어 있었다.
- 그런데 사용자가 실제로 가장 많이 쓰는 설계스튜디오 입구(/mass·/layout·/bim)는 generate()를 거치지
  않고 compute_optimal_mass를 직접 부른다. 그래서 그 응답에는 계약이 '하나도' 안 실렸다(라이브 확인).
- 그래서 이 파일은 '계약을 매스에 붙이는 일'을 함수 하나(build_mass_contract)로 추출한다.
  앞으로 generate()도, /mass·/layout·/bim도 이 함수 하나만 부르면 같은 계약이 따라온다
  (한 곳을 고치면 전역이 따라오는 공용화 — 단발 국소패치 금지).

★무날조 원칙(핵심):
- 입력에 없는 값은 가짜로 채우지 않는다. site_input이 없으면 rule_trace를 생략하고(가짜 법규 entry 금지),
  total_units가 미상이면 세대 점검을 건너뛴다(가짜 0세대 FAIL 금지).
- check_mass_invariants/mass_to_envelope_result/build_rule_trace는 모두 '미상=SKIP'을 지키는 기존 함수다.

★무회귀 원칙:
- 이 헬퍼는 기존 generate()가 하던 계약 부착과 '거동이 동일'하다(같은 입력 → 같은 계약).
- 매스 산출값(층수·면적·치수·far/bcr)은 절대 바꾸지 않는다 — 계약은 '읽어서 묶기만' 한다.

신규 의존성 0: 전부 cad 패키지 안의 기존 모듈(geometry_invariants·envelope_result·rule_trace·provenance)을 재사용한다.
"""

from __future__ import annotations

from typing import Any

import structlog

from app.services.cad.envelope_result import mass_to_envelope_result
from app.services.cad.geometry_invariants import check_mass_invariants
from app.services.cad.provenance import compute_input_hash
from app.services.cad.rule_trace import build_rule_trace

logger = structlog.get_logger(__name__)


def _build_fingerprint(site_input: Any) -> dict[str, Any]:
    """site_input에서 '결정적 입력 핑거프린트'를 만든다(provenance run_id·input_hash 산출용).

    왜(쉬운 설명): 같은 부지를 똑같이 넣으면 같은 run_id가 나와야(멱등) 캐시·중복방지가 된다.
    그래서 결과가 갈리지 않는 '입력 필드'만 모아 지문을 만든다. 날짜·랜덤 같은 변하는 값은 절대 안 쓴다.

    ★generate()가 쓰던 핑거프린트 구성과 100% 동일하게 맞춘다(공용화·거동 동일).
      - target_unit_types는 sorted로 순서를 고정(리스트 순서까지 안정화 → 같은 입력 같은 해시).
      - getattr은 옵셔널 필드가 없으면 None(가짜값 금지·무날조).
    """
    return {
        "site_area_sqm": getattr(site_input, "site_area_sqm", None),
        "zone_code": getattr(site_input, "zone_code", None),
        "building_use": getattr(site_input, "building_use", None),
        "target_unit_types": sorted(getattr(site_input, "target_unit_types", None) or []),
        "floor_height_m": getattr(site_input, "floor_height_m", None),
        "target_far_percent": getattr(site_input, "target_far_percent", None),
        "target_bcr_percent": getattr(site_input, "target_bcr_percent", None),
        "ordinance_far_percent": getattr(site_input, "ordinance_far_percent", None),
        "ordinance_bcr_percent": getattr(site_input, "ordinance_bcr_percent", None),
    }


def build_mass_contract(
    mass: dict[str, Any],
    *,
    site_input: Any = None,
    legal: dict[str, Any] | None = None,
    total_units: int | None = None,
    units_feasible: bool | None = None,
    fingerprint: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """매스에 C2R 계약(geometry_invariants·envelope_result·rule_trace·rule_set_hash)을 묶어 돌려준다.

    전 설계경로(generate·/mass·/layout·/bim) 공용 — 한 곳 수정으로 전역이 따라온다.

    Args:
        mass: compute_optimal_mass 출력 매스 dict. ★이 함수는 mass["geometry_invariants"]만
            additive로 채운다(기존 산출 키·수치는 손대지 않음·무회귀).
        site_input: SiteInput(있으면 rule_trace·핑거프린트를 site_input에서 구성). 없으면 둘 다 생략.
        legal: get_legal_limits 반환 dict(있어야 rule_trace의 법정 한도 근거가 채워진다).
        total_units: 총 세대수(있으면 '0세대 차단' 점검 활성). 미상이면 None → 세대 점검 SKIP(무날조).
        units_feasible: 세대 성립 여부(작은 부지 정직한 0세대를 버그성 0세대와 구별). 미상이면 None.
        fingerprint: site_input이 없을 때 쓸 provenance 핑거프린트(예: req의 zone/use/dims).
            site_input이 있으면 무시하고 site_input에서 구성한다(중복 제거).

    Returns:
        {"envelope_result": <dict>, "geometry_invariants": <dict>}
        - envelope_result: 표준 그릇 직렬화(mode="json"). site_input+legal이 있으면 rule_trace/rule_set_hash 포함.
        - geometry_invariants: 기하 불변식 점검 결과 to_dict()(매스에도 additive로 부착됨).

    무날조: site_input/legal이 없으면 rule_trace를 붙이지 않는다(가짜 entry 금지).
    무회귀: 매스의 기존 키·수치는 변경하지 않는다(geometry_invariants만 추가).
    """
    # ① 기하 불변식 점검(그림자) — 판정만 한다(차단은 호출부가 ENFORCE 플래그로 결정).
    #    site_input이 있으면 site_area/building_use를 넘겨 'footprint≤대지'·'주거 0세대' 같은 점검을 활성.
    #    없으면 None → 해당 점검은 SKIP(가짜 FAIL 금지·무날조).
    site_area = getattr(site_input, "site_area_sqm", None) if site_input is not None else None
    building_use = getattr(site_input, "building_use", None) if site_input is not None else None
    geo = check_mass_invariants(
        mass,
        site_area_sqm=site_area,
        total_units=total_units,
        building_use=building_use,
        units_feasible=units_feasible,
    )
    mass["geometry_invariants"] = geo.to_dict()  # additive 부착(소비처 표기·후속 재사용)

    # ② provenance 핑거프린트 결정 — site_input이 있으면 그걸로 구성(중복 제거), 없으면 인자 사용(또는 None).
    fp = _build_fingerprint(site_input) if site_input is not None else fingerprint

    # ③ 표준 그릇(EnvelopeResult)으로 변환 — 매스를 '변환만' 한다(수치 무변경).
    envelope_result = mass_to_envelope_result(
        mass,
        total_units=total_units,
        geo_invariants=mass["geometry_invariants"],
        input_fingerprint=fp,
    )

    # ④ rule_trace + rule_set_hash 부착(★site_input+legal이 둘 다 있을 때만 — 무날조).
    #    '어떤 법규가 어떤 값으로 적용됐는지'를 site_input/legal/mass에서 '읽기만' 해서 추적표로 만들고,
    #    그 묶음(rule_set)의 결정적 해시(rule_set_hash)를 §4 provenance triad의 마지막 칸으로 채운다.
    if site_input is not None and legal is not None:
        rule_trace, rule_set = build_rule_trace(site_input, legal, mass)
        rule_set_hash = compute_input_hash(rule_set)  # 결정론(normalize+canonical 재사용)
        # Pydantic 모델은 model_copy(update=...)로 불변 갱신 — 원본 손대지 않고 새 필드만 채운다.
        envelope_result = envelope_result.model_copy(
            update={"rule_trace": rule_trace, "rule_set_hash": rule_set_hash}
        )

    return {
        "envelope_result": envelope_result.model_dump(mode="json"),
        "geometry_invariants": mass["geometry_invariants"],
    }
