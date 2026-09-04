"""market_methodology 계층B 배지 불변식 테스트(Phase0 W2-b / G4) — 공시지가 기반 추정 토지시세 상시 P2 배지.

검증 축:
  1) 등록·멱등: register_all_rules 후 MARKET_PRICE_METHODOLOGY 존재, 재등록해도 규칙 수 불변.
  2) 케이스별 카운트: 공시지가 추정시세=배지 1건(실거래 유무·shape 무관), 추정없음/비공시지가출처/Section3부재=0건(오탐 없음).
  3) ★P2 비차단(계층B 핵심): 배지가 있어도 AuditReport.is_valid==True(P0 없음) — is_valid 불변.
  4) ★변이-kill: 규칙 fn을 return []로 변이하면 배지 소멸(배지가 로직 산물임 증명·실함수 호출). 정상 off 케이스엔 0(오탐 없음).
  5) ★오라클 독립성: est/official/multiplier 극단값에도 배지 불변(공시지가 값은 오라클 아님).
     ★R2: 실거래(Shape X/Y) 주입해도 배지 불변(실거래는 방법론 배지를 바꾸지 않음 — 토지 시세는 항상 공시지가 파생).
  6) ★2차(MARKET_PRICE_DIVERGENCE) 미등록 확증(연기·부재 아님): per-㎡ 정규화가 W4 소관이라 미구현 — 레지스트리에 없음.
  7) 실제 shape 대조 + finding 계약: land_prices(source '공시지가')·transaction_prices Shape X({apt,land})/Y({아파트,…}).

★정직표기: fixture는 W0/W1 합성(라이브 미수집)이며 comprehensive_analysis_service._calc_land_prices·
_research_transactions·land_info_service._fetch_nearby_transactions 실제 산출 shape에 충실한 구조 시드다
(_meta.synthetic=true·honesty).
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

# 양성(배지 1) · 진짜 off(배지 0) 케이스 분리 — 런너 경로 오탐0 검증에 사용.
_POSITIVE_CASES = [k for k, v in _CASES.items() if v["expect"][_CODE] == 1]
_NEGATIVE_CASES = [k for k, v in _CASES.items() if v["expect"][_CODE] == 0]


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
    """★2차 미구현 확증(연기·부재 아님): MARKET_PRICE_DIVERGENCE는 레지스트리에 없다.

    정본 seam 기본 Section 4 요약통계엔 per-㎡ 비교값이 없다(raw land items의 price_10k+area_sqm에서
    도출 가능하나 per-㎡ 정규화·지역/지목별 기준선 학습은 W4 platform_insights 소관 → 연기). 이 결정이
    회귀로 슬그머니 켜지지 않도록 부재를 고정한다.
    """
    assert "MARKET_PRICE_DIVERGENCE" not in registered_rule_ids()


# ────────────────────────────────────────────────────────────────────────────
# 2) 케이스별 카운트(양성 1건 · 오탐 0건)
# ────────────────────────────────────────────────────────────────────────────


def test_fixture_wellformed():
    """골든 fixture 구조 계약 — 정직표기·전 케이스 존재·2차 연기 근거·Shape X/Y 양성 포함."""
    meta = _DATA["_meta"]
    assert meta["seed_id"] == "W2b"
    assert meta["synthetic"] is True
    assert "honesty" in meta and meta["tier"] == "B"
    assert "rule_2_not_implemented" in meta  # 2차 연기 정직 근거
    assert set(_CASE_IDS) >= {
        "official_price_no_tx_message", "official_price_empty_tx",
        "official_price_zero_count_tx", "official_price_error_tx", "section4_absent",
        "transactions_present_shape_y", "transactions_present_multi_shape_y",
        "transactions_present_shape_x_land_bucket",
        "no_market_estimate", "non_official_source", "section3_absent", "both_absent",
    }
    # ★R2 flip 실증: 실거래 존재(Shape X/Y) 케이스가 양성(배지 1)에 포함
    assert "transactions_present_shape_y" in _POSITIVE_CASES
    assert "transactions_present_shape_x_land_bucket" in _POSITIVE_CASES


@pytest.mark.parametrize("case_name", _CASE_IDS)
def test_case_expected_counts(case_name):
    """각 케이스 배지 카운트가 fixture expect와 일치. 공시지가 추정=배지 1(실거래 무관), 추정없음/비공시지가/Section3부재=0(오탐 없음)."""
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
    ["official_price_no_tx_message", "section4_absent",
     "transactions_present_shape_y", "transactions_present_shape_x_land_bucket"],
)
def test_p2_badge_is_non_blocking(case_name):
    """★계층B 핵심: 방법론 배지가 있어도 is_valid==True(P0 없음). is_valid 불변(실거래 유무·shape 무관)."""
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
    """오탐 0(런너 경로): 추정없음/비공시지가출처/Section3부재/양자부재는 배지 0건·is_valid True."""
    assert set(_NEGATIVE_CASES) == {
        "no_market_estimate", "non_official_source", "section3_absent", "both_absent",
    }
    for case_name in _NEGATIVE_CASES:
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
# 5) ★오라클 독립성 — 공시지가 값은 오라클 아님, 실거래는 방법론 배지를 바꾸지 않음
# ────────────────────────────────────────────────────────────────────────────


def test_oracle_independence_official_price_value_not_oracle():
    """★공시지가/배수/추정값만 바꿔도 배지 불변 — 공시지가를 오라클로 쓰지 않음 증명(핵심 오라클독립).

    임계값·값 재계산이 있었다면 추정값 크기 변화가 판정을 흔들었을 것. 방법론/출처 태그만 보므로
    추정값이 무엇이든(공시지가×배수 방법론이 유지되는 한) 배지 1건으로 불변이다.
    """
    base = copy.deepcopy(_CASES["official_price_no_tx_message"]["input"])
    assert len(_market_price_methodology(base, {})) == 1

    for est, opsm, mult in [(1, 1, 1.0), (999_999_999, 800_000_000, 2.0), (3_000_000, 2_500_000, 1.2)]:
        mutated = copy.deepcopy(base)
        mutated["land_prices"]["estimated_market_per_sqm"] = est
        mutated["land_prices"]["official_price_per_sqm"] = opsm
        mutated["land_prices"]["market_multiplier"] = mult
        assert len(_market_price_methodology(mutated, {})) == 1, f"공시지가값 변이({est})에도 배지 불변"


def test_transactions_do_not_change_methodology_badge():
    """★R2 거짓음성 봉합 증명: 실거래(Shape X/Y·유무)를 바꿔도 방법론 배지 불변(1건).

    이전 초안은 실거래 존재 시 배지를 억제(거짓음성)했다. 토지 시세는 Section 4와 무관하게 항상
    공시지가 파생이므로, 무관한 건물 실거래를 주입해도 배지는 그대로 1건이어야 한다(배지=source 태그 신호).
    공시지가 계열은 완전 고정하고 transaction_prices만 부재→Shape Y→Shape X로 바꿔 불변을 실증.
    """
    base = copy.deepcopy(_CASES["official_price_no_tx_message"]["input"])
    assert len(_market_price_methodology(base, {})) == 1  # 실거래 부재 → 배지 1

    shape_y = copy.deepcopy(base)  # 공시지가 계열 동일, Shape Y 실거래 주입
    shape_y["transaction_prices"] = {
        "아파트": {"count": 5, "avg_price_10k": 60000, "max_price_10k": 80000,
                   "min_price_10k": 45000, "excluded_outliers": 0, "items": []},
    }
    assert len(_market_price_methodology(shape_y, {})) == 1, "Shape Y 실거래 존재에도 배지 불변"

    shape_x = copy.deepcopy(base)  # 공시지가 계열 동일, Shape X(apt/land 버킷) 실거래 주입
    shape_x["transaction_prices"] = {
        "apt": {"avg_price_10k": 62000, "count": 8, "items": []},
        "land": {"avg_price_10k": 12000, "count": 5, "items": [
            {"price_10k": "12000", "area_sqm": "330.5", "deal_date": "2026.06.15", "name": "대"},
        ]},
    }
    assert len(_market_price_methodology(shape_x, {})) == 1, "Shape X 실거래 존재에도 배지 불변"


# ────────────────────────────────────────────────────────────────────────────
# 6) 실제 shape 대조 + finding 계약
# ────────────────────────────────────────────────────────────────────────────


def test_real_shape_land_prices_and_transaction_shapes():
    """실제 shape: land_prices(source '공시지가'·est=official×multiplier)·transaction_prices Shape Y({아파트,…})/X({apt,land})."""
    lp = _CASES["official_price_no_tx_message"]["input"]["land_prices"]
    assert lp["estimated_market_per_sqm"] > 0
    assert "공시지가" in lp["source"]
    # estimated = official × multiplier(방법론 서명 — _calc_land_prices:1350)
    assert lp["estimated_market_per_sqm"] == round(lp["official_price_per_sqm"] * lp["market_multiplier"])

    # Shape Y(계산 경로·:1418-1439) — 유형별 count/avg_price_10k
    tx_y = _CASES["transactions_present_shape_y"]["input"]["transaction_prices"]
    assert tx_y["아파트"]["count"] > 0 and "avg_price_10k" in tx_y["아파트"]

    # ★Shape X(early-return·:1391-1393 → land_info:934-1001) — {apt,land}, land items=price_10k/area_sqm
    tx_x = _CASES["transactions_present_shape_x_land_bucket"]["input"]["transaction_prices"]
    assert "apt" in tx_x and "land" in tx_x
    land_item = tx_x["land"]["items"][0]
    assert "price_10k" in land_item and "area_sqm" in land_item  # per-㎡ 도출 가능한 raw items


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
    # note는 Section 4와 무관한 순수 방법론 고지(값 오류 아님)
    assert "공시지가 기반 추정" in f.note and "실거래로 검증되지 않음" in f.note


# ────────────────────────────────────────────────────────────────────────────
# 7) 안전(오탐 0 · 예외 없음)
# ────────────────────────────────────────────────────────────────────────────


def test_non_dict_and_missing_safe():
    """비dict payload·키 부재/비dict 안전(오탐 0·예외 없음)."""
    assert _market_price_methodology({}, {}) == []
    assert _market_price_methodology({"land_prices": None}, {}) == []
    assert _market_price_methodology({"land_prices": "bad"}, {}) == []
    assert _market_price_methodology(None, {}) == []  # type: ignore[arg-type]
    # estimated 없음/0 → 무발동(공시지가 source여도)
    assert _market_price_methodology(
        {"land_prices": {"source": "VWORLD 개별공시지가 + 지역별 시세보정"}}, {}
    ) == []
    assert _market_price_methodology(
        {"land_prices": {"estimated_market_per_sqm": 0, "source": "공시지가"}}, {}
    ) == []
    # ★bool est(True=1)를 유효 추정값으로 오판하지 않음
    assert _market_price_methodology(
        {"land_prices": {"estimated_market_per_sqm": True, "source": "공시지가"}}, {}
    ) == []
