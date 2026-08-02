"""market_methodology 불변식(계층B 배지) — 이미 계산된 result의 **표시 토지 시세 방법론**을 판정해,
그 시세가 공시지가 기반 추정(실거래 미검증)이면 **비차단 P2 배지**로 상시 표면화한다
(Phase0 W2-b / G4).

성격(★오라클 독립성·범주 — 이 규칙의 핵심 함정과 그 회피):
- 이 규칙은 **값을 재계산하지 않는다**. 이미 부착된 시세의 **방법론/출처 태그**(source 문자열·
  추정값 존재 여부)만 규칙에 맞는가로 판정한다(neuro proposes / symbolic disposes).
- ★함정(스파이크 확증): desk_appraisal의 배수 오라클(land_price_estimator._market_multiplier,
  land_price_estimator.py:11·:23)은 comprehensive의 MARKET_MULTIPLIER_MAP+동일 1.2 폴백을
  **그대로 재사용**한다. 따라서 desk_appraisal 채택값이나 MARKET_MULTIPLIER 기반 어떤 값도
  오라클로 쓰면 검증대상(공시지가×배수)과 동일 계산으로 수렴해 **버그를 재구현**한다
  (W1-3/G3에서 독립오라클 frozenset이 ZONE_LIMITS 비임포트여야 변이-kill이 살았던 것과 동일 원리).
- 그래서 이 규칙은 **임계값 불요·값 재계산 불요**로 설계했다 — 방법론 태그(source에 '공시지가'·
  추정값 존재)만 보므로 오라클 의존 자체가 없다. 이게 오탐 0·오라클 독립의 근거다.

★R2(게이트 제거 — 거짓음성 봉합, R1 적대리뷰 HIGH):
  이전 초안은 (C) Section 4(transaction_prices)에 실거래 표본이 있으면 배지를 억제했다. 그러나
  _calc_land_prices(:1339-1385)에는 **실거래 산출 경로가 전무**해 표시 토지 시세는 Section 4와
  무관하게 **항상 공시지가×배수**다(estimated_market_per_sqm = official_price_per_sqm × multiplier,
  :1350). 동일한 공시지가 파생 land_prices인데 무관한 **건물** 실거래(아파트/오피스텔/연립) 유무로
  배지가 1↔0 뒤집히면, 방법론 한계가 가장 오인되기 쉬운 상황(실거래가 화면에 보일 때)에 정확히
  disclosure를 끄는 거짓음성이다. → 게이트 (C)를 **제거**한다. 배지는 Section 4 shape/유무와
  무관하게 (A)·(B)만으로 발동하는 **상시 방법론 고지**다(정직한 지속 disclosure).

경로 비의존(실제 shape 재확증 — 2026-07-29, comprehensive_analysis_service.py 라이브 코드 대조):
  · Section 3 = result["land_prices"](:697 조립) = _calc_land_prices() 반환(:1375-1385):
      - estimated_market_per_sqm(:1379) = official_price_per_sqm × market_multiplier(:1350). 원/㎡.
      - source(:1383) = "VWORLD 개별공시지가 + 지역별 시세보정" — 공시지가 방법론 태그(항상 부착).
    ★_calc_land_prices엔 실거래 기반 산출 경로가 없다 — 표시 토지 시세는 **항상** 공시지가×배수.
  · Section 4 = result["transaction_prices"](:698)는 이 규칙이 **읽지 않는다**(게이트 (C) 제거).
    참고로 라이브 shape는 둘이다(규칙과 무관·shape-무관 동작): base["nearby_transactions"]가 이미
    있으면 early-return(:1391-1393)으로 land_info shape "X"={"apt":{...},"land":{count,items:[{price_10k,
    area_sqm,...}]}}(land_info_service.py:934-1001)를 그대로 반환하고, 없으면 shape "Y"=
    {"아파트":{count,avg_price_10k,...},"오피스텔":…,"연립다세대":…}(:1418-1439)를 계산한다.

판정(pure O(1)·부작용 없음·비차단 P2·is_valid 불변):
  MARKET_PRICE_METHODOLOGY: (A) Section 3에 표시 추정시세 estimated_market_per_sqm > 0 이고
  (B) 그 방법론이 공시지가 기반(source에 '공시지가')이면 → P2 배지(상시 방법론 고지). 둘 중 하나라도
  아니면(추정값 없음·미래 실거래 기반 시세 등) 무발동.

★2차(MARKET_PRICE_DIVERGENCE) 미구현 — 연기(defer), 부재 아님(정직 정정):
  괴리 배지는 실거래 원/㎡와 추정 원/㎡의 **독립 대조**가 필요하다. 정본 seam의 기본 Section 4
  **요약통계**(transaction_prices의 avg/max/min_price_10k)는 만원·per-unit 총액이라 per-㎡ 비교값이
  아니다. 다만 per-㎡ 토지시세가 **원천적으로 없는 것은 아니다**: molit_service.get_land_transactions
  (molit_service.py:38)가 실재하고 land_info_service._fetch_nearby_transactions(:934-1001)의 "land"
  버킷 raw items가 price_10k(만원)+area_sqm(㎡)를 담아 **per-㎡ 토지시세를 도출할 수 있다
  (공시지가와 독립)**. 즉 데이터는 있으나 정본 seam 요약이 이를 per-㎡ 비교값으로 노출하지 않을
  뿐이다. per-㎡ 정규화·지역/지목별 기준선 학습은 W4 platform_insights 소관이라 **2차는 그때로
  연기**한다(학습된 기준선인 척 금지·억지 배지 금지).
"""

from __future__ import annotations

from typing import Any

from app.services.verification.field_audit.contracts import AuditFinding
from app.services.verification.field_audit.rules_registry import register_audit_rule

# 안정 식별자 — rule_id=rules_registry 등록·per-rule 롤백 키, code=finding 안정 식별자.
_METHODOLOGY_RULE_ID = "MARKET_PRICE_METHODOLOGY"
_METHODOLOGY_FINDING_CODE = "MARKET_PRICE_METHODOLOGY"

# 공시지가 방법론 태그 — Section 3 source 문자열의 안정 서명("VWORLD 개별공시지가 + 지역별
# 시세보정" :1383). 부분일치로 판정(문구 미세변경에 견고). 이 태그가 없으면(미래에 실거래 기반
# 시세로 교체되면) 무발동 — 방법론-특정 가드라 정직성이 자동 유지된다.
_OFFICIAL_PRICE_SOURCE_TAG = "공시지가"

# ★방법론 판정용 코드 — 표시 문구(source)와 분리된 안정 식별자. 생산자가 source 옆에 additive로
#   함께 싣는다. 규칙은 이 코드를 먼저 보고, 없을 때만 위 표시 문구로 폴백한다(구버전 payload).
#   종전에는 표시 문구가 유일한 판정 근거라, 출처 문구를 쉬운 말로 바꾸면 이 상시 배지가
#   아무 에러 없이 영구 침묵했다.
_OFFICIAL_PRICE_SOURCE_KIND = "OFFICIAL_LAND_PRICE"

# finding expected 마커(값이 아니라 '기대 방법론'을 기술). 테스트가 참조하도록 상수로 노출.
_METHODOLOGY_EXPECTED = "실거래로 교차검증된 시세"

# 배지 패널명(EvidencePanel 소비 라벨) — 시세 표면.
_PANEL = "시세"

# 배지 note(사용자 표면 문구) — Section 4와 무관한 순수 방법론 고지(값 오류 아님·P2 배지).
_METHODOLOGY_NOTE = "표시 토지 시세는 공시지가 기반 추정입니다(실거래로 검증되지 않음·값 신뢰도 독립 확인 권장)"


def _extract_land_prices(payload: dict[str, Any]) -> dict[str, Any] | None:
    """result["land_prices"](Section 3)를 안전 추출(경로 비의존). dict 아니면 None(오탐 0)."""
    if not isinstance(payload, dict):
        return None
    lp = payload.get("land_prices")
    return lp if isinstance(lp, dict) else None


def _market_price_methodology(
    payload: dict[str, Any], ctx: dict[str, Any]
) -> list[AuditFinding]:
    """MARKET_PRICE_METHODOLOGY(계층B): 표시 토지 시세가 공시지가 기반 추정이면 상시 P2 배지.

    발동 조건(AND) — 오탐 0·오라클 독립(값 재계산·임계값·Section 4 게이팅 없음):
      (A) Section 3에 표시 추정시세 estimated_market_per_sqm > 0 (경고할 표시값이 실재).
      (B) 그 방법론이 공시지가 기반 (source에 '공시지가' 태그).
    둘 중 하나라도 아니면 무발동. Section 4(실거래) 유무·shape는 판정에 영향 없음(토지 시세는
    항상 공시지가 파생이므로 — R2 거짓음성 봉합). P2 비차단 — is_valid 불변.
    """
    lp = _extract_land_prices(payload)
    if lp is None:
        return []  # Section 3 부재/비dict → 무발동

    est = lp.get("estimated_market_per_sqm")
    if isinstance(est, bool) or not isinstance(est, (int, float)) or est <= 0:
        return []  # 표시 추정시세 없음(공시지가 조회 실패 등) → 경고할 표시값 없음 → 무발동

    # ★판정용 코드 우선 — 표시 문구에 의존하지 않는다(문구를 바꿔도 배지가 죽지 않게).
    kind = str(lp.get("source_kind") or "").strip().upper()
    if kind:
        if kind != _OFFICIAL_PRICE_SOURCE_KIND:
            return []  # 공시지가 방법론 아님 → 무발동(방법론-특정 가드)
    else:
        # 코드가 없는 구버전 payload만 표시 문구로 폴백.
        source = lp.get("source")
        if not isinstance(source, str) or _OFFICIAL_PRICE_SOURCE_TAG not in source:
            return []

    return [
        AuditFinding(
            code=_METHODOLOGY_FINDING_CODE,
            severity="P2",
            panel=_PANEL,
            field="land_prices.estimated_market_per_sqm",
            expected=_METHODOLOGY_EXPECTED,
            observed="공시지가×보정계수 추정(실거래 미검증)",
            rule_id=_METHODOLOGY_RULE_ID,
            tier="B",
            note=_METHODOLOGY_NOTE,
        )
    ]


def register_rules() -> None:
    """market_methodology 불변식을 rules_registry에 등록(멱등 — _SEEN_IDS가 중복 무시).

    프로덕션은 모듈 임포트 시 하단에서 자동 호출한다. clear_registry()로 레지스트리를 비우는
    격리 테스트는 이 함수를 다시 호출해 프로덕션 규칙을 재등록한다.
    """
    register_audit_rule(rule_id=_METHODOLOGY_RULE_ID, tier="B")(_market_price_methodology)


# 프로덕션 임포트 시 자동 등록(field_audit 패키지 __init__가 이 모듈을 임포트한다).
register_rules()
