"""estimate_dispersion 불변식(계층 C 배지) — 이미 계산된 result의 **분양가 표현 형태**를 판정해,
분양가가 신뢰구간·시나리오·분산 없이 **단일 점추정**으로만 표시되면 **비차단 P2 배지**로 상시
표면화한다(Phase0 W3-2 / G4형). 사용자가 과신하기 쉬운 분양가에 "이건 점추정이지 정밀값 아님"
불확실성을 정직하게 고지한다.

성격(★오라클 독립성·범주 — 이 규칙의 핵심 함정과 그 회피, market_methodology(W2-b)와 동형):
- 이 규칙은 분양가 **값을 재계산·검증하지 않는다**. 이미 부착된 분양가의 **표현 형태**
  (분산 표식 band/range/low-high/scenario/confidence의 동반 여부)만 판정한다
  (neuro proposes / symbolic disposes). 값 오라클 불요·재구현 위험 없음.
- ★오라클 독립 근거: 분양가 수치를 극단으로 바꿔도(1원이든 10억이든) 판정은 불변이다 —
  규칙이 보는 것은 '분산 구조가 동반됐는가'라는 형태이지 값이 아니다. 임계값·값 재계산이 없어
  오라클 의존 자체가 없다(이게 오탐 0·오라클 독립의 근거 — W2-b market_methodology와 동일 원리).

배지 발동 설계(★상시 P2 고지 — W2-b 선례와 동형):
  정본 _calc_sale_prices(comprehensive_analysis_service.py:1447-1473)는 분양가를 **항상** bare
  point로 산출한다(반환 항목 = {dev_type, type_name, sale_price_per_pyeong_man,
  sale_price_per_sqm_man, source:"지역 통계 기반 추정"} — band/range/low/high/scenario/confidence
  필드가 전무). pricing_band_service.compute_fair_price(app/services/market/pricing_band_service.py)
  가 band_10k[low,high]·recommended_cap_10k를 산출할 수 있는데도 _calc_sale_prices에 **미배선**이라,
  "구간 산출 가능한데 점추정만 표시"가 구조적으로 성립한다. 따라서 이 배지는 유효 분양가가 있는 한
  **상시 P2 고지**(보편적 한계의 정직 disclosure)다. 단 노이즈 최소화를 위해 판정불가·추정없음·
  sale_prices 부재면 무발동한다.

★배지 단위 = 섹션 1건(per-item 아님 — W2-b 동형·노이즈 최소화):
  sale_prices는 허용 개발유형별 항목 리스트라 항목이 여러 개다. 각 항목이 동일하게 bare point인데
  항목마다 동일 note의 배지를 N건 내면 순수 노이즈다. 배지 메시지("분양가는 점추정")는 sale_prices
  섹션에 대한 **하나의 보편 고지**이므로, 유효 bare 점추정이 하나라도 있으면 **섹션 배지 1건**만 낸다
  (market_methodology가 land_prices 섹션에 배지 1건을 낸 것과 동형). 순회는 각 항목을 검사해
  '유효 점추정이면서 분산 미동반'인 항목이 있는지를 판정하는 데 쓴다 — 분산 동반 항목·판정불가
  항목은 배지 트리거에 기여하지 않는다(오탐 방지).

★폴백(base_price=1500) note 미병기 — 감지 불가(정직 정정, 억지 배지 금지):
  _get_base_price(:1475-1482)는 지역 기준가 미매칭 시 전국 기본값 1500으로 폴백한다. 그러나 이
  폴백은 **result에서 감지 불가능**하다: (1) source 문자열이 폴백 여부와 무관하게 항상 "지역 통계
  기반 추정"으로 동일하고, (2) 값 1500은 정당한 지역 기준가와 충돌한다(SIGUNGU 안산시=1500·광주시=1500,
  REGION 광주광역시=1500·제주=1500 :84,86,97,98) — 여러 개발유형의 배수도 1.0이라(M01~M03·M06·M15
  :65-69) 폴백 1500과 정상 1500이 값으로 구분되지 않는다. 값 역산으로 폴백을 판정하려면
  SALE_PRICE_MULTIPLIER를 임포트해야 하는데 이는 오라클 의존(값-재구현 위험)이다. 따라서 폴백-특정
  note를 **병기하지 않는다**(과제 지정: 감지 불가면 생략·억지 금지). 감지 가능성이 생기면(예: 향후
  source에 폴백 플래그가 실리면) 그때 additive로 병기한다.

경로 비의존·안전(오탐 0): sale_prices가 list 아님/빈/비dict 항목/부재/None → finding 0. 결정론 티어
  (LLM 무관·위반 위험 낮음).
"""

from __future__ import annotations

from typing import Any

from app.services.verification.field_audit.contracts import AuditFinding
from app.services.verification.field_audit.rules_registry import register_audit_rule

# 안정 식별자 — rule_id=rules_registry 등록·per-rule 롤백 키, code=finding 안정 식별자.
_RULE_ID = "SALE_PRICE_POINT_ESTIMATE"
_FINDING_CODE = "SALE_PRICE_POINT_ESTIMATE"

# 배지 패널명(EvidencePanel 소비 라벨) — 분양가 표면.
_PANEL = "분양가"

# 유효 점추정의 정본 신호 키 — _calc_sale_prices:1469. 이 키가 양수여야 '경고할 표시 분양가'가 실재.
_POINT_KEY = "sale_price_per_pyeong_man"

# 판정불가 항목 마커(:1451 type_name) — 이 항목은 유효 점추정이 아니므로 배지 대상에서 제외.
_UNDETERMINED_MARK = "판정불가"

# finding expected 마커(값이 아니라 '기대 형태'를 기술 — 특정 분양가 수치가 아님). 테스트가 참조하도록 상수로 노출.
_EXPECTED_MARK = "신뢰구간·시나리오 등 분산 표식 동반 분양가"

# 배지 note(사용자 표면 문구) — 순수 형태 고지(값 오류 아님·P2 배지). 과제 지정 문구.
_NOTE = (
    "분양가는 지역통계 기반 단일 점추정입니다(신뢰구간·시나리오 미제공 — 구간 산출 가능하나 미반영·"
    "값 신뢰도 확인 권장)"
)

# ★분산 표식 탐지 — 긴 명확 토큰(부분일치 안전 — 비분산 키와 충돌 가능성 낮음). 향후 pricing_band
#   배선 시 항목에 실릴 법한 키(band_10k·recommended_cap_10k·price_range·scenarios·confidence_interval
#   등)를 부분일치로 흡수해 '구간이 반영되면 배지 자동 억제'(경로 비의존·미래 견고성).
_DISPERSION_SUBSTR: tuple[str, ...] = (
    "band", "range", "scenario", "confidence", "interval",
    "dispersion", "variance", "stddev", "std_dev",
    "quantile", "percentile", "recommended_cap",
)

# 짧은 모호 토큰은 정확 키 매칭(부분일치 시 'allowed'의 'low' 등 오탐 → 분산 오억제 방지).
_DISPERSION_EXACT: frozenset[str] = frozenset({
    "low", "high", "min", "max", "std", "ci",
    "low_man", "high_man", "low_10k", "high_10k",
    "sale_price_low_man", "sale_price_high_man",
    "sale_price_range_man", "p10", "p90", "p25", "p75",
})


def _is_meaningful(v: Any) -> bool:
    """분산 표식 값이 '실질적으로 존재'하는가. None·False·0·빈 컨테이너/문자열은 미존재로 본다
    (분산 없음인데 빈 필드만 있어 배지가 잘못 억제되는 오억제를 막는다).
    """
    if v is None:
        return False
    if isinstance(v, bool):
        return v  # True=존재 플래그, False=미존재(반드시 int 판정보다 먼저 — bool은 int 하위형)
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, (list, dict, str)):
        return len(v) > 0
    return True


def _has_dispersion(item: dict[str, Any]) -> bool:
    """항목에 분산 표식(band/range/low-high/scenario/confidence 등)이 실질적으로 동반됐는가.

    실 bare 항목(dev_type/type_name/sale_price_*/source)엔 어느 토큰도 매칭되지 않아 False다
    (→ 배지 발동). 향후 구간이 배선되면 해당 키가 True를 만들어 배지가 자동 억제된다(오탐 방지).
    """
    for k, v in item.items():
        if not isinstance(k, str) or not _is_meaningful(v):
            continue
        kl = k.lower()
        if kl in _DISPERSION_EXACT:
            return True
        if any(tok in kl for tok in _DISPERSION_SUBSTR):
            return True
    return False


def _is_valid_point_estimate(item: Any) -> bool:
    """항목이 '유효 점추정'인가 — 배지 대상 자격. dict이고 sale_price_per_pyeong_man이 양수
    (bool 아님)이며 판정불가가 아니어야 한다. 판정불가/추정없음(price 부재·0·음수)은 제외(오탐 0).
    """
    if not isinstance(item, dict):
        return False
    if str(item.get("type_name") or "") == _UNDETERMINED_MARK:
        return False  # 판정불가 항목(:1451) — 경고할 점추정 아님
    price = item.get(_POINT_KEY)
    if isinstance(price, bool) or not isinstance(price, (int, float)):
        return False
    return price > 0


def _finding() -> AuditFinding:
    """분양가 단일 점추정(분산 미동반) 배지 조립(Tier C·P2 비차단 — is_valid 불변)."""
    return AuditFinding(
        code=_FINDING_CODE,
        severity="P2",
        panel=_PANEL,
        field=f"sale_prices.{_POINT_KEY}",
        expected=_EXPECTED_MARK,
        observed="단일 점추정(분산 표식 부재)",
        rule_id=_RULE_ID,
        tier="C",
        note=_NOTE,
    )


def _sale_price_point_estimate(
    payload: dict[str, Any], ctx: dict[str, Any]
) -> list[AuditFinding]:
    """SALE_PRICE_POINT_ESTIMATE(계층 C): 분양가가 분산 없이 단일 점추정으로만 표시되면 상시 P2 배지.

    발동 조건 — 오탐 0·오라클 독립(값 재계산·임계값 없음):
      · sale_prices가 비어있지 않은 list이고,
      · 그 중 '유효 점추정(sale_price_per_pyeong_man>0·판정불가 아님)이면서 분산 표식(band/range/
        low-high/scenario/confidence)이 동반 부재'인 항목이 하나라도 있으면 → 섹션 배지 1건.
    판정불가/추정없음/sale_prices 부재·빈·비list·비dict 항목 → 무발동(오탐 없음). 분산 동반 항목만
    있으면(구간이 이미 반영된 미래 상태) 무발동(억지 배지 금지). P2 = 비차단(is_valid=not has_p0 불변).
    ★값 재계산·오라클 의존 없음 — 형태(분산 동반 여부)만 판정(market_methodology와 동형).
    """
    if not isinstance(payload, dict):
        return []
    sale_prices = payload.get("sale_prices")
    if not isinstance(sale_prices, list) or not sale_prices:
        return []  # 부재/빈/비list → 무발동

    for item in sale_prices:
        if not _is_valid_point_estimate(item):
            continue  # 판정불가·추정없음·비dict → 트리거 기여 없음
        if _has_dispersion(item):  # type: ignore[arg-type]  (_is_valid가 dict 보장)
            continue  # 분산 동반 항목 → 배지 억제(오탐 방지)
        return [_finding()]  # 유효 bare 점추정 발견 → 섹션 배지 1건(상시 고지)
    return []  # 유효 점추정이 전부 분산 동반이거나 없음 → 무발동


def register_rules() -> None:
    """estimate_dispersion 불변식을 rules_registry에 등록(멱등 — _SEEN_IDS가 중복 무시).

    프로덕션은 모듈 임포트 시 하단에서 자동 호출한다. clear_registry()로 레지스트리를 비우는
    격리 테스트는 이 함수를 다시 호출해 프로덕션 규칙을 재등록한다.
    """
    register_audit_rule(rule_id=_RULE_ID, tier="C")(_sale_price_point_estimate)


# 프로덕션 임포트 시 자동 등록(field_audit 패키지 __init__가 이 모듈을 임포트한다).
register_rules()
