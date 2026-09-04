"""판정 키와 표시 문구의 분리 회귀락 — 문구를 바꿔도 자가검증 규칙이 죽지 않는다.

## 왜 필요한가

자가검증 규칙 두 개가 **화면에 나가는 한국어 문자열**을 판정 근거로 쓰고 있었다:

- `estimate_dispersion`: `type_name == "판정불가"` (정확 일치)
- `market_methodology`: `"공시지가" in land_prices["source"]` (부분 일치)

두 값 모두 사용자 화면에 그대로 렌더되는 표시 문구다. 즉 "판정불가"를 "확인이 필요합니다"로,
출처를 "정부 공표 땅값 기준 추정"으로 **쉬운 말로 바꾸는 순간** 규칙이 아무 예외 없이
무발동이 된다 — 배지가 사라진 걸 아무도 모른다. 비전문가 언어화(W4)를 하려면 이 결합을
먼저 끊어야 한다.

그래서 생산자가 표시 문구 **옆에** 판정용 코드(`type_name_code`·`source_kind`)를 additive로
싣고, 규칙은 코드를 먼저 읽는다. 이 파일은 그 분리가 **실제로 성립하는지**를 잠근다.

## 오라클 설계

문구를 임의 문자열로 바꿔 넣고 finding 수가 **변하지 않는지** 본다. 결합이 남아 있으면
문구를 바꾼 순간 finding이 사라지거나 생겨서 단언이 깨진다. 리터럴 비교가 아니라 규칙을
실제로 호출한다.
"""

from __future__ import annotations

from typing import Any

from app.services.verification.field_audit.invariants import (
    estimate_dispersion as ed,
)
from app.services.verification.field_audit.invariants import (
    market_methodology as mm,
)


def _sale_payload(type_name: str, *, code: str | None = "UNDETERMINED") -> dict[str, Any]:
    """분양가 섹션 payload — **판정불가 항목 단 1건**만 담는다.

    ★게이트 격리: 유효 점추정 항목을 함께 넣으면 그 항목만으로 배지가 떠서, 판정불가 게이트를
      어떻게 바꾸든 finding 수가 1로 같아진다(실제로 첫 변이가 이 이유로 생존했다).
    ★가격을 함께 싣는 이유: 가격이 없으면 '유효 점추정 아님'이 가격 부재로 먼저 결정돼 역시
      게이트를 격리하지 못한다. 판정불가 여부**만** 결과를 가르도록 만든 픽스처다.
    """
    undetermined: dict[str, Any] = {
        "development_type": None,
        "type_name": type_name,
        "sale_price_per_pyeong_man": 1200,
    }
    if code is not None:
        undetermined["type_name_code"] = code
    return {"sale_prices": [undetermined]}


def _land_payload(source: str, *, kind: str | None = "OFFICIAL_LAND_PRICE") -> dict[str, Any]:
    lp: dict[str, Any] = {
        "official_price_per_sqm": 2820,
        "estimated_market_per_sqm": 3384,
        "market_multiplier": 1.2,
        "source": source,
    }
    if kind is not None:
        lp["source_kind"] = kind
    return {"land_prices": lp}


# ── 분양가 점추정 규칙 ────────────────────────────────────────────────────────

def test_sale_price_rule_ignores_display_wording():
    """표시 문구를 바꿔도 판정 결과가 같다(코드가 판정 근거).

    ★변이-kill: 규칙이 다시 type_name 문자열로 판정하게 되돌리면, 아래 '쉬운 말' payload에서
      판정불가 항목이 유효 점추정으로 오인돼 finding 수가 달라진다.
    """
    ctx: dict = {}
    baseline = ed._sale_price_point_estimate(_sale_payload("판정불가"), ctx)
    assert baseline == [], "판정불가 항목만 있는데 배지가 떴다(테스트 전제 파손)"

    for wording in ["확인이 필요합니다", "산정할 수 없음", "", "Not determined"]:
        got = ed._sale_price_point_estimate(_sale_payload(wording), ctx)
        assert len(got) == len(baseline), (
            f"표시 문구 '{wording}' 로 바꾸자 판정이 달라졌다 — 규칙이 아직 화면 문구에 결합돼 있다."
        )
        # 게이트 자체도 직접 확인한다(규칙 조립을 거치지 않는 최소 오라클).
        item = _sale_payload(wording)["sale_prices"][0]
        assert ed._is_valid_point_estimate(item) is False, (
            f"표시 문구 '{wording}' 항목이 유효 점추정으로 오인됐다 — 코드 판정이 안 먹는다."
        )


def test_sale_price_rule_falls_back_to_wording_when_code_absent():
    """구버전 payload(코드 없음)는 표시 문구로 폴백해 종전과 동일하게 판정한다."""
    ctx: dict = {}
    with_code = ed._sale_price_point_estimate(_sale_payload("판정불가"), ctx)
    legacy = ed._sale_price_point_estimate(_sale_payload("판정불가", code=None), ctx)
    assert len(legacy) == len(with_code), "구버전 payload 폴백이 깨졌다(무회귀 실패)"


# ── 시세 방법론 규칙 ──────────────────────────────────────────────────────────

def test_market_methodology_rule_ignores_display_wording():
    """출처 표시 문구를 바꿔도 상시 방법론 배지가 계속 뜬다."""
    ctx: dict = {}
    baseline = mm._market_price_methodology(_land_payload("VWORLD 개별공시지가 + 지역별 시세보정"), ctx)
    assert len(baseline) == 1, "기준선에서 방법론 배지가 나오지 않는다(테스트 전제 파손)"

    for wording in ["정부가 공표한 땅값을 기준으로 추정", "추정 시세", ""]:
        got = mm._market_price_methodology(_land_payload(wording), ctx)
        assert len(got) == 1, (
            f"출처 문구를 '{wording}' 로 바꾸자 배지가 사라졌다 — 규칙이 아직 화면 문구에 결합돼 있다."
        )


def test_market_methodology_rule_falls_back_when_code_absent():
    """구버전 payload는 종전대로 출처 문자열로 판정한다(무회귀)."""
    ctx: dict = {}
    legacy_hit = mm._market_price_methodology(
        _land_payload("VWORLD 개별공시지가 + 지역별 시세보정", kind=None), ctx)
    legacy_miss = mm._market_price_methodology(
        _land_payload("실거래 기반 추정", kind=None), ctx)
    assert len(legacy_hit) == 1
    assert legacy_miss == []


def test_market_methodology_rule_respects_non_official_kind():
    """코드가 공시지가 방법론이 아니면 문구가 '공시지가'를 포함해도 발동하지 않는다.

    ★코드가 표시 문구를 **이긴다**는 것을 잠근다 — 둘이 어긋날 때 판정 근거가 무엇인지 고정.
    """
    ctx: dict = {}
    got = mm._market_price_methodology(
        _land_payload("VWORLD 개별공시지가 + 지역별 시세보정", kind="MARKET_TRANSACTION"), ctx)
    assert got == [], "코드가 비공시지가인데 표시 문구 때문에 배지가 떴다(판정 근거 역전)"


# ── 생산자 계약: 코드가 실제로 응답에 실리는가 ────────────────────────────────

def test_producer_emits_source_kind_next_to_display_source():
    """실제 생산자가 표시 문구 **옆에** 판정 코드를 함께 싣는다.

    ★이 테스트가 없으면 규칙은 영원히 오지 않는 코드를 기다리고, 실제 판정은 폴백(표시 문구)에
      계속 의존한다 — 분리가 서류상으로만 성립하는 상태.
    """
    from app.services.land_intelligence.comprehensive_analysis_service import (
        ComprehensiveAnalysisService,
    )

    out = ComprehensiveAnalysisService()._calc_land_prices(
        {"individual_land_price": 2820, "address": "경상북도 포항시 남구 호미곶면 대보리 산1-1"},
        1000.0,
    )
    assert out.get("source_kind") == "OFFICIAL_LAND_PRICE", (
        f"생산자가 판정 코드를 싣지 않았다 — 규칙이 표시 문구 폴백에 계속 묶인다. out={out!r}"
    )
    assert "공시지가" in str(out.get("source") or ""), "표시 문구는 그대로 유지돼야 한다(무회귀)"


def test_producer_emits_type_name_code_for_undetermined_sale_prices():
    """실제 생산자가 '판정불가' 분양가 항목에 판정 코드를 함께 싣는다.

    ★R1 적대검증 적발: `source_kind` 쪽에는 생산자 계약 테스트가 있었는데 `type_name_code`
      쪽에는 없었다. 생산자에서 그 1줄을 지워도 전 테스트가 통과했다(변이 생존) — 즉 규칙은
      영원히 오지 않는 코드를 기다리고 판정은 표시 문구 폴백에 계속 묶인 채 남는다.
      W4가 "판정불가" 문구를 쉬운 말로 바꾸는 순간 이 규칙이 무음 사망한다.
    """
    from app.services.land_intelligence.comprehensive_analysis_service import (
        ComprehensiveAnalysisService,
    )

    # 인허가 매트릭스 미등재 용도지역 → 판정불가 항목이 나오는 경로.
    out = ComprehensiveAnalysisService()._calc_sale_prices("경기도 어딘가 1-1", "미등재가상용도지역")
    undetermined = [i for i in out if str(i.get("type_name") or "") == "판정불가"]
    assert undetermined, f"판정불가 항목이 생성되지 않아 계약을 확인할 수 없다: {out!r}"
    for item in undetermined:
        assert item.get("type_name_code") == "UNDETERMINED", (
            f"생산자가 판정 코드를 싣지 않았다 — 규칙이 표시 문구 폴백에 묶인다: {item!r}"
        )
