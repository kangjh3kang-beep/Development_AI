"""field_audit 불변식(pure fn 규칙) 모음 — 임포트 시 규칙이 rules_registry에 등록된다.

W1부터 계층 A 하드 불변식이 여기 등록된다:
  - W1-1: cross_field.G1 protection_zone_severity(보호구역 리스크 하한)
  - W1-2: cross_field.G2 school_poi_dedup(학교 과카운트)
  - W1-3: coverage.G3 zone_coverage_gap(관리지역 BCR/FAR 커버리지 갭)
W2부터 계층 B 비차단 배지가 여기 등록된다:
  - W2-a: provenance.PROV_UNKNOWN_SOURCE·PROV_STALE_DATA(미등록 출처·신선도 만료 P2 배지)
  - W2-b: market_methodology.MARKET_PRICE_METHODOLOGY(실거래 비교 없는 공시지가 폴백 시세 P2 배지)
W3부터 계층 A 수집갭 불변식·계층 C 형태 배지가 여기 등록된다:
  - W3-2: estimate_dispersion.SALE_PRICE_POINT_ESTIMATE(분양가 단일 점추정·분산 미동반 P2 배지)
  - W3-3: terrain_coverage.TERRAIN_SLOPE_COLLECTION_GAP(임야/산지 후보의 수집가능 경사도 미획득 P1 갭)
이 패키지를 임포트하면 하위 모듈의 register_rules()가 실행돼 프로덕션 규칙이 활성화된다.
"""

from app.services.verification.field_audit.invariants import (  # noqa: F401  임포트 부작용=규칙 등록
    coverage,
    cross_field,
    estimate_dispersion,
    market_methodology,
    provenance,
    terrain_coverage,
)


def register_all_rules() -> None:
    """모든 불변식 모듈의 프로덕션 규칙을 재등록(멱등). 격리 테스트가 clear_registry() 후
    '프로덕션에 등록된 전체 규칙 집합'을 한 번에 복원하는 SSOT — Wave가 늘어도 여기만 갱신하면
    골든/단위테스트가 새 규칙을 자동 포함한다(개별 모듈 register_rules를 일일이 호출하다 빠지는
    회귀를 원천 차단).
    """
    cross_field.register_rules()
    coverage.register_rules()
    provenance.register_rules()
    market_methodology.register_rules()
    estimate_dispersion.register_rules()
    terrain_coverage.register_rules()


__all__ = [
    "coverage",
    "cross_field",
    "estimate_dispersion",
    "market_methodology",
    "provenance",
    "register_all_rules",
    "terrain_coverage",
]
