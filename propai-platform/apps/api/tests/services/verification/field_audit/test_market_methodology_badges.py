"""market_methodology 계층B 배지 불변식 테스트(Phase0 W2-b / G4) — 실거래 비교 없는 공시지가 폴백 시세 P2 배지.

검증 축:
  1) 등록·멱등: register_all_rules 후 MARKET_PRICE_METHODOLOGY 존재, 재등록해도 규칙 수 불변.
  2) 케이스별 카운트: 실거래부재+공시지가폴백=배지 1건, 실거래존재/추정없음/비공시지가출처/Section부재=0건(오탐 없음).
  3) ★P2 비차단(계층B 핵심): 배지가 있어도 AuditReport.is_valid==True(P0 없음) — is_valid 불변.
  4) ★변이-kill: 규칙 fn을 return []로 변이하면 배지 소멸(배지가 로직 산물임 증명). 정상 입력엔 0(오탐 없음).
  5) ★오라클 독립성: 공시지가/배수/추정값만 바꾸면 배지 불변(공시지가를 오라클로 안 씀), 실거래를
     추가하면 배지 소멸(실거래 부재/존재가 유일한 판정 신호 — 값 재계산·임계 없음).
  6) ★2차(MARKET_PRICE_DIVERGENCE) 미등록 확증: 재확증상 result가 실거래 원/㎡와 추정 원/㎡를
     신뢰성 있게 함께 노출하지 않아 괴리 배지는 억지가 되므로 미구현(정직) — 레지스트리에 없음.
  7) 실제 shape 대조 + finding 계약: land_prices/transaction_prices 키·source 태그·유형별 count.

★정직표기: fixture는 W0/W1 합성(라이브 미수집)이며 comprehensive_analysis_service._calc_land_prices·
_research_transactions 실제 산출 shape에 충실한 구조 시드다(_meta.synthetic=true·honesty).
"""

import copy
import json
from pathlib import Path

import pytest

import app.services.growth.capture_service as cap
from app.services.verification.field_audit import runner
from app.services.verification.field_audit.invariants import (
    market_methodology,
    register_all_rules,
)
from app.services.verification.field_audit.invariants.market_methodology import (
    _METHODOLOGY_EXPECTED,
    _METHODOLOGY_NOTE,
    _PANEL,
    _market_price_methodology,
    _real_transaction_count,
)
from app.services.verification.field_audit.rules_registry import (
    clear_registry,
    registered_rule_ids,
    rule_count,
)

_FIX = Path(__file__).parent / "fixtures" / "market" / "W2b_market_methodology.json"
_DATA = json.loads(_FIX.read_text(encoding="utf-8"))
_CASES = _DATA["cases"]
_CASE_IDS = sorted(_CASES.keys())

_CODE = "MARKET_PRICE_METHODOLOGY"


@pytest.fixture(autouse=True)
def _isolate_and_silence(monkeypatch):
    """규칙 레지스트리 격리 + 프로덕션 규칙 재등록 + growth emit 무음화(테스트 부작용 차단)."""
    clear_registry()
    register_all_rules()
    monkeypatch.setattr(cap, "record_event", lambda *a, **k: None)
    yield
    clear_registry()


# ────────────────────────────────────────────────────────────────────────────
# 1) 등록 · 멱등
# ────────────────────────────────────────────────────────────────────────────


def test_rule_registered():
    """register_all_rules 후 MARKET_PRICE_METHODOLOGY 규칙이 레지스트리에 존재한다."""
    assert _CODE in registered_rule_ids()


def test_idempotent_registration():
    """register_all_rules·모듈 register_rules를 재호출해도 규칙 수 불변(멱등 — _SEEN_IDS 중복 무시)."""
    n1 = rule_count()
    register_all_rules()                    # 2회
    market_methodology.register_rules()     # 3회(모듈 직접)
    register_all_rules()                    # 4회
    assert rule_count() == n1
    assert registered_rule_ids().count(_CODE) == 1


def test_rule2_divergence_not_registered():
    """★2차 미구현 확증: MARKET_PRICE_DIVERGENCE는 레지스트리에 없다(억지 괴리 배지 금지·정직).

    재확증: Section 4 avg_price_10k(만원·per-unit 주거 건물 총액)와 Section 3 estimated_market_per_sqm
    (원·per-㎡ 토지)은 단위·분모·대상 3중 비호환이라 괴리비가 무의미 → 독립오라클(실거래 원/㎡)
    부재로 2차 미구현. 이 결정이 회귀로 슬그머니 켜지지 않도록 부재를 고정한다.
    """
    assert "MARKET_PRICE_DIVERGENCE" not in registered_rule_ids()


# ────────────────────────────────────────────────────────────────────────────
# 2) 케이스별 카운트(양성 1건 · 오탐 0건)
# ────────────────────────────────────────────────────────────────────────────


def test_fixture_wellformed():
    """골든 fixture 구조 계약 — 정직표기·전 케이스 존재·2차 미구현 근거 명시."""
    meta = _DATA["_meta"]
    assert meta["seed_id"] == "W2b"
    assert meta["synthetic"] is True
    assert "honesty" in meta and meta["tier"] == "B"
    assert "rule_2_not_implemented" in meta  # 2차 미구현 정직 근거
    assert set(_CASE_IDS) >= {
        "official_price_no_tx_message", "official_price_empty_tx",
        "official_price_zero_count_tx", "official_price_error_tx", "section4_absent",
        "transactions_present", "transactions_present_large_apparent_gap",
        "no_market_estimate", "non_official_source", "section3_absent", "both_absent",
    }


@pytest.mark.parametrize("case_name", _CASE_IDS)
def test_case_expected_counts(case_name):
    """각 케이스 배지 카운트가 fixture expect와 일치. 양성=배지 산출, 실거래존재/추정없음/비공시지가/부재=0(오탐 없음)."""
    case = _CASES[case_name]
    findings = _market_price_methodology(case["input"], {})
    assert len(findings) == case["expect"][_CODE], f"{case_name}: {_CODE}"
    for f in findings:  # 산출된 배지는 전부 P2·계층B·시세 패널
        assert f.severity == "P2" and f.tier == "B" and f.panel == _PANEL


# ────────────────────────────────────────────────────────────────────────────
# 3) ★P2 비차단(계층B 핵심) — 배지가 있어도 is_valid 불변
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "case_name",
    ["official_price_no_tx_message", "official_price_empty_tx",
     "official_price_zero_count_tx", "official_price_error_tx", "section4_absent"],
)
def test_p2_badge_is_non_blocking(case_name):
    """★계층B 핵심: 방법론 한계 배지가 있어도 is_valid==True(P0 없음). is_valid 불변."""
    result = copy.deepcopy(_CASES[case_name]["input"])
    report = runner.run(result, {})

    market = [f for f in report.findings if f.code == _CODE]
    assert len(market) == 1, "배지가 실제로 산출됨"
    assert all(f.severity == "P2" for f in market)
    # P0 부재 → is_valid True(계층B 비차단 계약)
    assert all(f.severity != "P0" for f in report.findings)
    assert report.is_valid is True
    assert result["field_audit"]["is_valid"] is True  # 부착된 리포트도 동일


def test_negatives_yield_no_findings_via_runner():
    """오탐 0(런너 경로): 실거래존재/추정없음/비공시지가출처/Section부재는 배지 0건·is_valid True."""
    for case_name in (
        "transactions_present", "transactions_present_large_apparent_gap",
        "no_market_estimate", "non_official_source", "section3_absent", "both_absent",
    ):
        result = copy.deepcopy(_CASES[case_name]["input"])
        report = runner.run(result, {})
        market = [f for f in report.findings if f.code == _CODE]
        assert market == [], f"{case_name}: 배지 0건(오탐 없음)"
        assert report.is_valid is True


# ────────────────────────────────────────────────────────────────────────────
# 4) ★변이-kill — 규칙 fn을 return []로 변이하면 배지 소멸(로직 산물 증명)
# ────────────────────────────────────────────────────────────────────────────


def test_mutation_rule_noop_drops_badge(monkeypatch):
    """★변이-kill: fn을 return []로 변이→재등록하면 배지가 사라진다(배지=로직 산물, 가짜 동어반복 아님)."""
    payload = _CASES["official_price_no_tx_message"]["input"]
    # 정상: 등록 파이프라인이 배지 1건 산출(실함수 호출)
    clear_registry()
    market_methodology.register_rules()
    rep = runner.run(copy.deepcopy(payload), {})
    assert sum(f.code == _CODE for f in rep.findings) == 1

    # 변이: fn을 return []로 교체 후 재등록 → 배지 소멸
    clear_registry()
    monkeypatch.setattr(market_methodology, "_market_price_methodology", lambda p, c: [])
    market_methodology.register_rules()
    rep2 = runner.run(copy.deepcopy(payload), {})
    assert sum(f.code == _CODE for f in rep2.findings) == 0


# ────────────────────────────────────────────────────────────────────────────
# 5) ★오라클 독립성 — 공시지가는 오라클 아님, 실거래 부재/존재가 유일 판정 신호
# ────────────────────────────────────────────────────────────────────────────


def test_oracle_independence_official_price_value_not_oracle():
    """★공시지가/배수/추정값만 바꿔도(실거래 부재 고정) 배지 불변 — 공시지가를 오라클로 쓰지 않음 증명.

    임계값·값 재계산이 있었다면 추정값 크기 변화가 판정을 흔들었을 것. 방법론/출처 태그만 보므로
    추정값이 무엇이든(공시지가×배수 방법론이 유지되는 한) 실거래 부재면 배지 1건으로 불변이다.
    """
    base = copy.deepcopy(_CASES["official_price_no_tx_message"]["input"])
    assert len(_market_price_methodology(base, {})) == 1

    for est, opsm, mult in [(1, 1, 1.0), (999_999_999, 800_000_000, 2.0), (3_000_000, 2_500_000, 1.2)]:
        mutated = copy.deepcopy(base)
        mutated["land_prices"]["estimated_market_per_sqm"] = est
        mutated["land_prices"]["official_price_per_sqm"] = opsm
        mutated["land_prices"]["market_multiplier"] = mult
        # 실거래는 고정(부재) — 공시지가 계열 값만 변이
        assert len(_market_price_methodology(mutated, {})) == 1, f"공시지가값 변이({est})에도 배지 불변"


def test_oracle_independence_transactions_flip_verdict():
    """★실거래를 추가하면(부재→존재) 배지 소멸 — 실거래 신호가 유일한 판정 입력임 증명.

    공시지가 계열은 고정하고 transaction_prices만 부재→count>0로 바꾸면 판정이 뒤집힌다
    (실거래 comparable 존재 = '실거래 비교 없이'가 거짓 → 무발동). 실거래가 실제 신호임을 실증.
    """
    base = copy.deepcopy(_CASES["official_price_no_tx_message"]["input"])
    assert len(_market_price_methodology(base, {})) == 1  # 실거래 부재 → 배지

    with_tx = copy.deepcopy(base)  # 공시지가 계열 완전 동일, 실거래만 주입
    with_tx["transaction_prices"] = {
        "아파트": {"count": 5, "avg_price_10k": 60000, "max_price_10k": 80000,
                   "min_price_10k": 45000, "excluded_outliers": 0, "items": []},
    }
    assert _market_price_methodology(with_tx, {}) == [], "실거래 존재 → 배지 소멸(판정 뒤집힘)"


# ────────────────────────────────────────────────────────────────────────────
# 6) 실제 shape 대조 + finding 계약
# ────────────────────────────────────────────────────────────────────────────


def test_real_shape_land_prices_and_transactions():
    """실제 shape: land_prices(estimated_market_per_sqm·source '공시지가')·transaction_prices(유형별 count·부재 message)."""
    lp = _CASES["official_price_no_tx_message"]["input"]["land_prices"]
    assert lp["estimated_market_per_sqm"] > 0
    assert "공시지가" in lp["source"]
    # estimated = official × multiplier(방법론 서명 — _calc_land_prices:1350)
    assert lp["estimated_market_per_sqm"] == round(lp["official_price_per_sqm"] * lp["market_multiplier"])

    tx_msg = _CASES["official_price_no_tx_message"]["input"]["transaction_prices"]
    assert "message" in tx_msg  # 실거래 부재 shape(_research_transactions:1399)

    tx_ok = _CASES["transactions_present"]["input"]["transaction_prices"]
    assert tx_ok["아파트"]["count"] > 0 and "avg_price_10k" in tx_ok["아파트"]  # 성공 shape


def test_methodology_finding_contract():
    """MARKET_PRICE_METHODOLOGY finding 계약 고정(code·severity·tier·panel·expected·observed·note·field)."""
    findings = _market_price_methodology(_CASES["official_price_no_tx_message"]["input"], {})
    assert len(findings) == 1
    f = findings[0]
    assert f.code == _CODE and f.rule_id == _CODE
    assert f.severity == "P2" and f.tier == "B" and f.panel == _PANEL
    assert f.field == "land_prices.estimated_market_per_sqm"
    assert f.expected == _METHODOLOGY_EXPECTED
    assert "공시지가" in str(f.observed) and "실거래" in str(f.observed)
    assert f.note == _METHODOLOGY_NOTE
    assert "실거래 비교 없이" in f.note and "방법론 한계" in f.note


# ────────────────────────────────────────────────────────────────────────────
# 7) 실거래 표본 집계 경계 · 안전(오탐 0 · 예외 없음)
# ────────────────────────────────────────────────────────────────────────────


def test_real_transaction_count_shapes():
    """실거래 표본 집계: 유형별 count 합산, message/error/빈/count0/비dict=0, bool count 미집계."""
    assert _real_transaction_count({"transaction_prices": {"아파트": {"count": 3}, "오피스텔": {"count": 2}}}) == 5
    assert _real_transaction_count({"transaction_prices": {"아파트": {"count": 0}}}) == 0
    assert _real_transaction_count({"transaction_prices": {"message": "부재"}}) == 0
    assert _real_transaction_count({"transaction_prices": {"error": "실패"}}) == 0
    assert _real_transaction_count({"transaction_prices": {}}) == 0
    assert _real_transaction_count({}) == 0
    assert _real_transaction_count({"transaction_prices": "bad"}) == 0
    # ★bool은 int 서브클래스 — count=True(1)로 오집계하지 않음
    assert _real_transaction_count({"transaction_prices": {"아파트": {"count": True}}}) == 0


def test_non_dict_and_missing_safe():
    """비dict payload·키 부재/비dict 안전(오탐 0·예외 없음)."""
    assert _market_price_methodology({}, {}) == []
    assert _market_price_methodology({"land_prices": None}, {}) == []
    assert _market_price_methodology({"land_prices": "bad"}, {}) == []
    assert _market_price_methodology(None, {}) == []  # type: ignore[arg-type]
    # estimated 없음/0 → 무발동
    assert _market_price_methodology(
        {"land_prices": {"source": "VWORLD 개별공시지가 + 지역별 시세보정"}}, {}
    ) == []
    assert _market_price_methodology(
        {"land_prices": {"estimated_market_per_sqm": 0, "source": "공시지가"}}, {}
    ) == []
