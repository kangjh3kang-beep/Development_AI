"""market_methodology 불변식(계층B 배지) — 이미 계산된 result의 **시세 산정 방법론**을 판정해,
표시 시세가 실거래 비교 없이 공시지가 폴백 추정으로만 산출됐으면 **비차단 P2 배지**로 표면화한다
(Phase0 W2-b / G4).

성격(★오라클 독립성·범주 — 이 규칙의 핵심 함정과 그 회피):
- 이 규칙은 **값을 재계산하지 않는다**. 이미 부착된 시세의 **방법론/출처 태그**(source 문자열·
  추정값 존재 여부·실거래 표본수)만 규칙에 맞는가로 판정한다(neuro proposes / symbolic disposes).
- ★함정(스파이크 확증): desk_appraisal의 배수 오라클(land_price_estimator._market_multiplier,
  land_price_estimator.py:11·:23)은 comprehensive의 MARKET_MULTIPLIER_MAP+동일 1.2 폴백을
  **그대로 재사용**한다. 따라서 desk_appraisal 채택값이나 MARKET_MULTIPLIER 기반 어떤 값도
  오라클로 쓰면 검증대상(공시지가×배수)과 동일 계산으로 수렴해 **버그를 재구현**한다
  (W1-3/G3에서 독립오라클 frozenset이 ZONE_LIMITS 비임포트여야 변이-kill이 살았던 것과 동일 원리).
- 그래서 1차(MARKET_PRICE_METHODOLOGY)는 **임계값 불요·값 재계산 불요**로 설계했다 — 방법론
  태그(source에 '공시지가'·추정값 존재)와 실거래 표본 부재만 보므로 오라클 의존 자체가 없다.
  이게 오탐 0·오라클 독립의 근거다.

경로 비의존(실제 shape 재확증 — 2026-07-29, comprehensive_analysis_service.py 라이브 코드 대조):
  · Section 3 = result["land_prices"](:697 조립) = _calc_land_prices() 반환(:1375-1385):
      - estimated_market_per_sqm(:1379) = official_price_per_sqm × market_multiplier(:1350). 원/㎡.
      - market_multiplier(:1382) — 폴백 시 1.2(:1337)이나 경기/인천/부산 등 정상 지역도 1.2라
        market_multiplier 값만으로는 폴백 구분 불가(폴백 사실은 annotations[](:1359)의
        multiplier_rationale 문자열에만 드러남).
      - source(:1383) = "VWORLD 개별공시지가 + 지역별 시세보정" — 공시지가 방법론 태그(항상 부착).
    ★_calc_land_prices에는 실거래 기반 산출 경로가 없다 — 표시 시세는 **항상** 공시지가×배수다.
  · Section 4 = result["transaction_prices"](:698 조립) = _research_transactions() 반환
      (:1418-1439) = 유형별 dict {"아파트":{count(:1432), avg_price_10k(:1433), ...}, "오피스텔":…,
      "연립다세대":…}. 실거래 부재 시: {"message":…}(:1399, PNU 부재)·{"error":…}(:1442)·{}(초기 :660).
    ★avg_price_10k(:1433)는 **거래 총액(만원·건물포함·per-unit)**이지 토지 per-㎡가 아니다
      (price_stats.robust_price_stats는 거래금액 리스트→대표통계·price_stats.py:21-22;
      molit_service price_10k_won=거래금액 정규화·molit_service.py:15). Section 4는 토지 실거래
      (get_land_transactions)를 부르지 않고 주거 건물 거래만 조회한다(:1407-1413).
  · 두 키(land_prices·transaction_prices)는 최상위이며 field_audit runner가 result 전체를 받는다
    (comprehensive_analysis_service.py:1110 runner.run(result, {...})).

판정(1차만 — pure O(n)·부작용 없음·비차단 P2·is_valid 불변):
  MARKET_PRICE_METHODOLOGY: (A) Section 3에 표시 추정시세(estimated_market_per_sqm>0)가 있고
  그 방법론이 공시지가 기반(source에 '공시지가')이며 (B) Section 4에 실거래 comparable이 전무
  (유형별 count 합계 0·부재·message/error)면 → P2 배지. 실거래 표본이 하나라도 있으면 무발동
  (실거래 맥락이 표면에 있으므로 '실거래 비교 없이'가 참이 아님 → 오탐 0·note 정직성 유지).

★2차(MARKET_PRICE_DIVERGENCE) 미구현 — 정직 보고(억지 배지 금지):
  2차 괴리 배지는 **독립오라클=실거래 원/㎡**를 추정 원/㎡와 신뢰성 있게 대조할 수 있어야 성립한다.
  그러나 재확증 결과 result는 그 대조를 지지하지 않는다:
    · Section 4 avg_price_10k = 만원·per-unit 총액·주거 **건물**(아파트/오피스텔/연립).
    · Section 3 estimated_market_per_sqm = 원·per-㎡·**토지**.
  단위(만원 vs 원)·분모(per-unit vs per-㎡)·대상(건물 총액 vs 토지 단가)이 3중 비호환이라 괴리비가
  물리적으로 무의미하다(수백 배 차이는 정상). result에 토지 per-㎡ 실거래 값은 없고 유일한 per-㎡
  값(official/estimated_market_per_sqm)은 전부 공시지가 파생(=검증대상 자신, 비독립)이다. 따라서
  2차는 **구현하지 않는다** — 억지 대조는 오탐 배지를 낳는다. (지역/지목별 per-㎡ 기준선 학습은
  W4 platform_insights 영역이며 그때 별도 티켓으로 다룬다 — 학습된 기준선인 척 금지.)
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

# finding expected 마커(값이 아니라 '기대 방법론'을 기술). 테스트가 참조하도록 상수로 노출.
_METHODOLOGY_EXPECTED = "실거래 comparable로 교차검증된 시세"

# 배지 패널명(EvidencePanel 소비 라벨) — 시세 표면.
_PANEL = "시세"

# 배지 note(사용자 표면 문구) — 방법론 한계 고지(값 오류 아님·P2 배지).
_METHODOLOGY_NOTE = "표시 시세가 실거래 비교 없이 공시지가 기반 추정입니다(방법론 한계·값 신뢰도 확인 권장)"


def _extract_land_prices(payload: dict[str, Any]) -> dict[str, Any] | None:
    """result["land_prices"](Section 3)를 안전 추출(경로 비의존). dict 아니면 None(오탐 0)."""
    if not isinstance(payload, dict):
        return None
    lp = payload.get("land_prices")
    return lp if isinstance(lp, dict) else None


def _real_transaction_count(payload: dict[str, Any]) -> int:
    """result["transaction_prices"](Section 4)의 실거래 유효 표본 총수를 안전 집계(경로 비의존).

    성공 shape는 유형별 dict {"아파트":{count,...},"오피스텔":{...},"연립다세대":{...}}이므로
    dict 값 중 count가 숫자인 것만 합산한다. {"message":…}·{"error":…}·{}·비dict는 값이 dict가
    아니거나 count가 없어 **0**으로 집계된다(실거래 부재 = comparable 없음 판정의 근거).
    """
    if not isinstance(payload, dict):
        return 0
    tx = payload.get("transaction_prices")
    if not isinstance(tx, dict):
        return 0
    total = 0
    for v in tx.values():
        if not isinstance(v, dict):
            continue
        c = v.get("count")
        if isinstance(c, bool):  # bool은 int 서브클래스 — count로 오집계 방지
            continue
        if isinstance(c, (int, float)) and c > 0:
            total += int(c)
    return total


def _market_price_methodology(
    payload: dict[str, Any], ctx: dict[str, Any]
) -> list[AuditFinding]:
    """MARKET_PRICE_METHODOLOGY(계층B): 표시 시세가 실거래 비교 없이 공시지가 폴백 추정이면 P2 배지.

    발동 조건(AND) — 오탐 0·오라클 독립(값 재계산·임계값 없음):
      (A) Section 3에 표시 추정시세 estimated_market_per_sqm > 0 (경고할 표시값이 실재).
      (B) 그 방법론이 공시지가 기반 (source에 '공시지가' 태그).
      (C) Section 4 실거래 comparable 총수 0 (부재/message/error/count 0).
    셋 중 하나라도 아니면 무발동. P2 비차단 — is_valid 불변.
    """
    lp = _extract_land_prices(payload)
    if lp is None:
        return []  # Section 3 부재/비dict → 무발동

    est = lp.get("estimated_market_per_sqm")
    if isinstance(est, bool) or not isinstance(est, (int, float)) or est <= 0:
        return []  # 표시 추정시세 없음(공시지가 조회 실패 등) → 경고할 표시값 없음 → 무발동

    source = lp.get("source")
    if not isinstance(source, str) or _OFFICIAL_PRICE_SOURCE_TAG not in source:
        return []  # 공시지가 방법론 아님(미래 실거래 기반 시세 등) → 무발동(방법론-특정 가드)

    if _real_transaction_count(payload) > 0:
        return []  # 실거래 comparable 존재 → '실거래 비교 없이'가 참 아님 → 무발동(오탐 0)

    return [
        AuditFinding(
            code=_METHODOLOGY_FINDING_CODE,
            severity="P2",
            panel=_PANEL,
            field="land_prices.estimated_market_per_sqm",
            expected=_METHODOLOGY_EXPECTED,
            observed="공시지가×보정계수 추정(실거래 comparable 부재)",
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
