"""특이부지 게이트 공용 부착 헬퍼(B2) — 설계 매스 산출 전 경로(/mass·/bim·/layout·seed-design)에
학교용지·GB·농지·산지·맹지 등 특이요인 경고를 additive로 부착한다.

배경: detect_special_parcel(특이부지 규칙엔진, app.services.zoning.special_parcel)이
design_ingest/orchestrator._detect_special(proposals 경로)에만 적용돼 있어, 같은 특이부지라도
/mass·/bim·seed-design 등 다른 설계 매스 산출 경로는 무게이트로 통과했다(의정부동224 재발 패턴 —
학교용지·GB 부지가 일반 상업지처럼 "최대 연면적 X평 가능"으로 오분석). 이 헬퍼는 그 경로들에
동일 판정을 공용 부착해 재발을 막는다(국소 패치 금지 — 공용화).

★차단(BLOCK) 아님 — additive 경고만 부착한다(developability·warnings·legal_refs를 응답에
동봉할 뿐, 매스 산출 자체를 막지 않는다). 기존 응답 계약은 무파괴.
★정직: pnu/지목(land_category)·특별구역(special_districts) 컨텍스트가 전혀 없으면 판정 불가이므로
None을 반환한다(무날조 — 근거 없는 "특이 없음" 단정도, 근거 없는 경고도 만들지 않는다).
"""
from __future__ import annotations

from typing import Any


def build_special_parcel_gate(
    *,
    land_category: str | None = None,
    zone_type: str | None = None,
    special_districts: list[str] | None = None,
    area_sqm: float | None = None,
    pnu: str | None = None,
) -> dict[str, Any] | None:
    """특이부지 게이트 표준 shape({developability, warnings, legal_refs, ...})을 산출한다.

    입력(land_category·special_districts) 모두 없으면 판정 불가 → None(정직 생략).
    detect_special_parcel(app.services.zoning.special_parcel) 단일 원천을 그대로 재사용한다
    (판정 로직 재구현 금지 — 전역 일관성). 게이트 산출 실패(예외)도 graceful None으로 흡수해
    특이부지 판정이 주 경로(매스 산출)를 절대 깨지 않게 한다.

    반환(있을 때만):
      is_special         True(특이 감지됨 — None 반환이면 이 함수는 애초에 요인이 없거나 컨텍스트 부족)
      developability      POSSIBLE|CAUTION|CONDITIONAL|NEEDS_OFFICIAL_SURVEY|PRECONDITION|BLOCKED
      severity_label       위 게이트의 한글 라벨
      resolvable           YES|CONDITIONAL|NO(해결가능성)
      warnings             ["[특이부지] ...", ...] — 정직 경고 문장(프론트 표기용)
      legal_refs            verified 법령링크(레지스트리 직렬화, 있으면)
      note                  종합 정직 고지 문구(honest_disclosure)
      pnu                   호출부가 넘긴 pnu 그대로 echo(추적용 메타 — 판정에는 미사용)
    """
    if not (land_category or special_districts):
        return None
    try:
        from app.services.zoning.special_parcel import detect_special_parcel

        result: dict[str, Any] = {
            "land_category": land_category or "",
            "zone_type": zone_type or "",
            "special_districts": list(special_districts or []),
        }
        if area_sqm:
            result["area_sqm"] = area_sqm
        sp = detect_special_parcel(result)
    except Exception:  # noqa: BLE001 — 게이트 실패가 매스 산출(주 경로)을 깨면 안 됨(best-effort)
        return None
    if not (sp and sp.get("is_special")):
        return None

    legal_refs: list[dict[str, Any]] = []
    for factor in sp.get("factors") or []:
        legal_refs.extend(factor.get("legal_refs") or [])

    return {
        "is_special": True,
        "developability": sp.get("developability"),
        "severity_label": sp.get("severity_label"),
        "resolvable": sp.get("resolvable"),
        "warnings": sp.get("warnings") or [],
        "legal_refs": legal_refs,
        "note": sp.get("honest_disclosure") or sp.get("note"),
        "pnu": pnu,
    }
