"""심의/설계 엔진(deliberation-review) 공용 입력 빌더 — SSOT.

★배경(A2 갭): decision_brief_service(정답 기준선)와 specialist_dispatch.build_sync_specialist_domains가
각자 심의/설계 엔진 입력(use_zone·calc_targets·provided·pnu ASCII 가드)을 따로 조립하다 후자가
`zone_type`(엔진이 읽지 않는 키)을 잘못 보내 registry 심의/설계 도메인이 항상 NEEDS_INPUT이었다
(services/deliberation-review/apps/api/app/api/routes/{permit,design}_routes.py 실측 — 두 라우트 모두
본문 최상위 `use_zone`만 읽는다). 이 모듈이 한 곳에서 계약을 조립해 두 소비처가 공유하게 한다.

엔진 계약(실측):
- POST /api/v1/permit/process, /api/v1/design/process: 본문 최상위 `use_zone`(용도지역명)·`dev_type`
  (선택)·`pnu`(19자리 ASCII, 아니면 빈값=address 지오코딩 폴백)·`address`. 나머지 키(calc_targets·
  rules 등)는 AnalysisInput 필드로 그대로 전달된다. `provided`(설계 전용 — 산출물 존재 표시)는
  design_process만 소비한다(permit_process는 무시·무해).
- permit 단계 required_inputs=["use_zone"], design programming 단계=["use_zone","program"].
"""
from __future__ import annotations

from typing import Any


def _pnu19(pnu: Any) -> str:
    """19자리 ASCII 숫자만 통과 — 전각/유니코드 숫자 등 비규격은 빈값(address 지오코딩 폴백)."""
    s = str(pnu) if pnu else ""
    return s if (s.isascii() and s.isdigit() and len(s) == 19) else ""


def build_bcr_far_rules(
    *, bcr_measured: float | None = None, bcr_limit: float | None = None,
    far_measured: float | None = None, far_limit: float | None = None,
) -> list[dict[str, Any]]:
    """BCR_LIMIT/FAR_LIMIT rules[] 조립 — measured·limit이 **둘 다** 있을 때만 additive로 포함(무날조).

    ★project_pipeline._run_design_review의 rules 구성 패턴을 단일화한 것: 대지면적 미확보(0)라
    measured를 계산할 수 없으면 0.0 등 가짜값을 넣지 않고 해당 rule 자체를 생략한다.
    """
    rules: list[dict[str, Any]] = []
    if bcr_measured is not None and bcr_limit is not None:
        rules.append({"rule": {"rule_id": "BCR_LIMIT", "comparator": "<="},
                      "measured": round(float(bcr_measured), 2), "limit": float(bcr_limit)})
    if far_measured is not None and far_limit is not None:
        rules.append({"rule": {"rule_id": "FAR_LIMIT", "comparator": "<="},
                      "measured": round(float(far_measured), 2), "limit": float(far_limit)})
    return rules


def build_deliberation_engine_input(
    *, zone_type: str, address: str | None = None, dev_type: str | None = None,
    pnu: Any = None,
) -> dict[str, Any]:
    """심의(엔진 /api/v1/permit/process) 입력 — use_zone(엔진 계약키)·address·pnu(ASCII 가드)·dev_type(선택).

    ★zone_type이 아니라 use_zone(엔진 permit_routes.py:39가 읽는 키)이어야 permit 단계가
    NEEDS_INPUT을 벗어난다.
    """
    out: dict[str, Any] = {"pnu": _pnu19(pnu), "address": address, "use_zone": zone_type}
    if dev_type:
        out["dev_type"] = dev_type
    return out


def build_design_engine_input(
    *, zone_type: str, address: str | None = None, dev_type: str | None = None,
    pnu: Any = None, land_area_sqm: float | None = None, proposed_gfa_sqm: float | None = None,
    bcr_measured: float | None = None, bcr_limit: float | None = None,
    far_measured: float | None = None, far_limit: float | None = None,
) -> dict[str, Any]:
    """설계(엔진 /api/v1/design/process) 입력 — use_zone·calc_targets(대지면적)·provided(기획/GFA)
    ·rules(BCR/FAR, additive) 조립. 정답 기준선=decision_brief_service._run_specialists 설계입력.

    - calc_targets: land_area_sqm이 양수일 때만 plot_area 산정입력을 공급(대지면적 부재는 엔진이
      '미상'으로 정직 표면화 — 가짜 0㎡ 금지).
    - provided: program=True(기획정보 가용) + proposed_gfa_sqm(있으면) → massing 단계 capacity 검증
      (제안 GFA ≤ 법정 최대 연면적) 활성화.
    - rules: build_bcr_far_rules 재사용(measured·limit 둘 다 있을 때만 포함).
    """
    out: dict[str, Any] = {"pnu": _pnu19(pnu), "address": address, "use_zone": zone_type}
    if dev_type:
        out["dev_type"] = dev_type
    if isinstance(land_area_sqm, (int, float)) and not isinstance(land_area_sqm, bool) and land_area_sqm > 0:
        out["calc_targets"] = [{"target": "plot_area", "payload": {"parcel_area": float(land_area_sqm)}}]
    provided: dict[str, Any] = {"program": True}
    if proposed_gfa_sqm:
        provided["proposed_gfa"] = float(proposed_gfa_sqm)
    out["provided"] = provided
    rules = build_bcr_far_rules(bcr_measured=bcr_measured, bcr_limit=bcr_limit,
                                far_measured=far_measured, far_limit=far_limit)
    if rules:
        out["rules"] = rules
    return out
