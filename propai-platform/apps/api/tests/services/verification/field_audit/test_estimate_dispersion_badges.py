"""estimate_dispersion 계층C 배지 불변식 테스트(Phase0 W3-2 / G4형) — 분양가 단일 점추정 상시 P2 배지.

검증 축:
  1) 등록·멱등: register_all_rules 후 SALE_PRICE_POINT_ESTIMATE 존재, 재등록해도 규칙 수 불변.
  2) 케이스별 카운트: bare 점추정=섹션 배지 1건, 판정불가/부재/빈/분산동반/0가격/비dict=0건(오탐 없음).
  3) ★P2 비차단(계층C 핵심): 배지가 있어도 AuditReport.is_valid==True(P0 없음) — is_valid 불변.
  4) ★변이-kill: 규칙 fn을 return []로 변이하면 배지 소멸(배지=로직 산물·실함수 호출·가짜 동어반복 아님).
  5) ★오라클 독립성: 분양가 값 극단(1~10억)에도 배지 불변(값은 오라클 아님·형태만 판정).
  6) ★분산 동반 억제(오탐 방지): 분산 표식(band/range/low-high/scenario/confidence) 동반 항목은 배지 억제.
  7) 실제 shape 대조 + finding 계약: _calc_sale_prices 반환 shape(bare/판정불가) 충실·code/severity/tier/panel/note.
  8) ★폴백 감지 불가 확증: 폴백(1500)이어도 정상 케이스와 동일 배지/note(폴백 별도 note 없음·억지 배지 금지).

★정직표기: fixture는 W3 합성(라이브 미수집)이며 comprehensive_analysis_service._calc_sale_prices 실제 산출
shape에 충실한 구조 시드다(_meta.synthetic=true·honesty). 분산 동반 케이스는 향후 pricing_band 배선 시
실릴 법한 형태를 규칙 억제 검증용으로 additive 부여한 것(라이브 정본은 아직 bare point만 냄).
"""

import copy
import json
from pathlib import Path

import pytest

import app.services.growth.capture_service as cap
from app.services.verification.field_audit import runner
from app.services.verification.field_audit.invariants import (
    estimate_dispersion,
    register_all_rules,
)
from app.services.verification.field_audit.invariants.estimate_dispersion import (
    _EXPECTED_MARK,
    _NOTE,
    _PANEL,
    _sale_price_point_estimate,
)
from app.services.verification.field_audit.rules_registry import (
    clear_registry,
    registered_rule_ids,
    rule_count,
)

_FIX = Path(__file__).parent / "fixtures" / "saleprice" / "W3_2_sale_price_point_estimate.json"
_DATA = json.loads(_FIX.read_text(encoding="utf-8"))
_CASES = _DATA["cases"]
_CASE_IDS = sorted(_CASES.keys())

_CODE = "SALE_PRICE_POINT_ESTIMATE"

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
    """register_all_rules 후 SALE_PRICE_POINT_ESTIMATE 규칙이 레지스트리에 존재한다."""
    assert _CODE in registered_rule_ids()


def test_idempotent_registration():
    """register_all_rules·모듈 register_rules를 재호출해도 규칙 수 불변(멱등 — _SEEN_IDS 중복 무시)."""
    n1 = rule_count()
    register_all_rules()                     # 2회
    estimate_dispersion.register_rules()     # 3회(모듈 직접)
    register_all_rules()                     # 4회
    assert rule_count() == n1
    assert registered_rule_ids().count(_CODE) == 1


# ────────────────────────────────────────────────────────────────────────────
# 2) 케이스별 카운트(양성 1건 · 오탐 0건)
# ────────────────────────────────────────────────────────────────────────────


def test_fixture_wellformed():
    """골든 fixture 구조 계약 — 정직표기·전 케이스 존재·폴백 감지불가 근거·분산동반 억제 케이스 포함."""
    meta = _DATA["_meta"]
    assert meta["seed_id"] == "W3-2"
    assert meta["synthetic"] is True
    assert "honesty" in meta and meta["tier"] == "C"
    assert "fallback_not_detectable" in meta          # 폴백 감지불가 정직 근거
    assert "band_computable_but_unwired" in meta      # 구간 산출 가능하나 미배선 근거
    assert set(_CASE_IDS) >= {
        "bare_point_estimates", "single_bare_point_estimate", "fallback_still_bare",
        "undetermined_only", "sale_prices_absent", "sale_prices_empty",
        "all_items_have_dispersion", "mixed_bare_and_dispersion",
        "zero_price_item", "non_dict_items",
    }
    # ★분산 동반 억제·혼합 실증 케이스 존재
    assert "all_items_have_dispersion" in _NEGATIVE_CASES
    assert "mixed_bare_and_dispersion" in _POSITIVE_CASES
    assert "fallback_still_bare" in _POSITIVE_CASES


@pytest.mark.parametrize("case_name", _CASE_IDS)
def test_case_expected_counts(case_name):
    """각 케이스 배지 카운트가 fixture expect와 일치. bare=배지 1(섹션), 판정불가/부재/분산동반/0가격=0(오탐 없음)."""
    case = _CASES[case_name]
    findings = _sale_price_point_estimate(case["input"], {})
    assert len(findings) == case["expect"][_CODE], f"{case_name}: {_CODE}"
    for f in findings:  # 산출된 배지는 전부 P2·계층C·분양가 패널
        assert f.severity == "P2" and f.tier == "C" and f.panel == _PANEL


# ────────────────────────────────────────────────────────────────────────────
# 3) ★P2 비차단(계층C 핵심) — 배지가 있어도 is_valid 불변
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("case_name", _POSITIVE_CASES)
def test_p2_badge_is_non_blocking(case_name):
    """★계층C 핵심: 점추정 배지가 있어도 is_valid==True(P0 없음). is_valid 불변."""
    result = copy.deepcopy(_CASES[case_name]["input"])
    report = runner.run(result, {})

    badges = [f for f in report.findings if f.code == _CODE]
    assert len(badges) == 1, "배지가 실제로 산출됨"
    assert all(f.severity == "P2" for f in badges)
    # P0 부재 → is_valid True(계층C 비차단 계약)
    assert all(f.severity != "P0" for f in report.findings)
    assert report.is_valid is True
    assert result["field_audit"]["is_valid"] is True  # 부착된 리포트도 동일


def test_negatives_yield_no_findings_via_runner():
    """오탐 0(런너 경로): 판정불가/부재/빈/분산동반/0가격/비dict는 배지 0건·is_valid True."""
    assert set(_NEGATIVE_CASES) == {
        "undetermined_only", "sale_prices_absent", "sale_prices_empty",
        "all_items_have_dispersion", "zero_price_item", "non_dict_items",
    }
    for case_name in _NEGATIVE_CASES:
        result = copy.deepcopy(_CASES[case_name]["input"])
        report = runner.run(result, {})
        badges = [f for f in report.findings if f.code == _CODE]
        assert badges == [], f"{case_name}: 배지 0건(오탐 없음)"
        assert report.is_valid is True


# ────────────────────────────────────────────────────────────────────────────
# 4) ★변이-kill — 규칙 fn을 return []로 변이하면 배지 소멸(로직 산물 증명)
# ────────────────────────────────────────────────────────────────────────────


def test_mutation_rule_noop_drops_badge(monkeypatch):
    """★변이-kill: fn을 return []로 변이→재등록하면 배지가 사라진다(배지=로직 산물, 가짜 동어반복 아님)."""
    payload = _CASES["bare_point_estimates"]["input"]
    # 정상: 등록 파이프라인이 배지 1건 산출(실함수 호출)
    clear_registry()
    estimate_dispersion.register_rules()
    rep = runner.run(copy.deepcopy(payload), {})
    assert sum(f.code == _CODE for f in rep.findings) == 1

    # 변이: fn을 return []로 교체 후 재등록 → 배지 소멸
    clear_registry()
    monkeypatch.setattr(estimate_dispersion, "_sale_price_point_estimate", lambda p, c: [])
    estimate_dispersion.register_rules()
    rep2 = runner.run(copy.deepcopy(payload), {})
    assert sum(f.code == _CODE for f in rep2.findings) == 0


# ────────────────────────────────────────────────────────────────────────────
# 5) ★오라클 독립성 — 분양가 값은 오라클 아님(형태만 판정)
# ────────────────────────────────────────────────────────────────────────────


def test_oracle_independence_sale_price_value_not_oracle():
    """★분양가 값을 극단(1~10억)으로 바꿔도 배지 불변(1건) — 값을 오라클로 쓰지 않음 증명(핵심 오라클독립).

    임계값·값 재계산이 있었다면 분양가 크기 변화가 판정을 흔들었을 것. 형태(분산 동반 여부)만 보므로
    분양가가 무엇이든(양수·bare인 한) 배지 1건으로 불변이다.
    """
    base = copy.deepcopy(_CASES["single_bare_point_estimate"]["input"])
    assert len(_sale_price_point_estimate(base, {})) == 1

    for pyeong, sqm in [(1, 1), (999_999_999, 302_500_000), (2500, 756), (1500, 453)]:
        mutated = copy.deepcopy(base)
        mutated["sale_prices"][0]["sale_price_per_pyeong_man"] = pyeong
        mutated["sale_prices"][0]["sale_price_per_sqm_man"] = sqm
        assert len(_sale_price_point_estimate(mutated, {})) == 1, f"분양가값 변이({pyeong})에도 배지 불변"


# ────────────────────────────────────────────────────────────────────────────
# 6) ★분산 동반 억제(오탐 방지) — 구간이 이미 반영되면 배지 억제
# ────────────────────────────────────────────────────────────────────────────


def test_dispersion_accompanied_items_suppress_badge():
    """★분산 표식(band_10k/scenarios/confidence 등)이 동반된 항목만 있으면 배지 0(오탐 방지·구간 반영 시 자동 억제)."""
    all_disp = copy.deepcopy(_CASES["all_items_have_dispersion"]["input"])
    assert _sale_price_point_estimate(all_disp, {}) == [], "분산 동반 항목만 → 배지 억제"

    # 혼합(일부 bare) → bare 항목이 트리거 → 배지 1(분산 항목은 기여 없음)
    mixed = copy.deepcopy(_CASES["mixed_bare_and_dispersion"]["input"])
    assert len(_sale_price_point_estimate(mixed, {})) == 1, "혼합 시 bare 항목이 섹션 배지 발동"

    # ★다양한 분산 표식 각각이 개별적으로 억제하는가(단일 항목 억제 스윕)
    for disp_field, disp_val in [
        ("band_10k", [1000, 2000]), ("price_range", {"low": 1000, "high": 2000}),
        ("low", 1000), ("high", 2000), ("scenarios", [{"v": 1}]),
        ("confidence", 0.9), ("confidence_interval", [0.8, 0.95]),
        ("recommended_cap_10k", 1500), ("stddev", 120.0),
    ]:
        item = {"dev_type": "M01", "type_name": "아파트", "sale_price_per_pyeong_man": 2500,
                "sale_price_per_sqm_man": 756, "source": "지역 통계 기반 추정", disp_field: disp_val}
        assert _sale_price_point_estimate({"sale_prices": [item]}, {}) == [], f"{disp_field} 동반 → 억제"

    # ★빈/None 분산 필드는 억제하지 않음(오억제 방지 — 실질 분산 아님)
    for empty_field, empty_val in [("band_10k", []), ("scenarios", []), ("confidence", None), ("low", 0)]:
        item = {"dev_type": "M01", "type_name": "아파트", "sale_price_per_pyeong_man": 2500,
                "sale_price_per_sqm_man": 756, "source": "지역 통계 기반 추정", empty_field: empty_val}
        assert len(_sale_price_point_estimate({"sale_prices": [item]}, {})) == 1, f"{empty_field}={empty_val}(빈값) → 억제 안 함(배지 유지)"


def test_unrelated_substring_keys_do_not_over_suppress():
    """★R1 LOW 반증(R2 봉합): 무관 키가 분산 토큰을 substring으로 포함해도 배지 오억제 안 됨(배지 1 유지).

    이전 bare substring `in` 매칭은 arrangement(⊃'range')·subband_note(⊃'band')·misconfidence_flag
    (⊃'confidence')·storage_range_id(⊃'range')를 오매칭해 배지를 조용히 껐다(false-negative — 자가검증
    조언 침묵). exact/워드바운더리 매칭으로 좁힌 뒤엔 경계 불일치라 억제하지 않는다. R1 repro를 고정한다.
    """
    unrelated_keys = {
        "arrangement": "정렬됨",          # ⊃ "range" (경계 아님)
        "subband_note": "메모",           # ⊃ "band" (경계 아님)
        "misconfidence_flag": True,       # ⊃ "confidence" (경계 아님)
        "storage_range_id": "S-1",        # ⊃ "range" (경계 아님·_range_id 접미도 아님)
        "highlight": "강조",              # ⊃ "high" (경계 아님)
        "allowance": 100,                 # ⊃ "low" (경계 아님)
        "maximal_note": "x",              # ⊃ "max" (경계 아님)
    }
    item = {"dev_type": "M01", "type_name": "아파트", "sale_price_per_pyeong_man": 2500,
            "sale_price_per_sqm_man": 756, "source": "지역 통계 기반 추정", **unrelated_keys}
    assert len(_sale_price_point_estimate({"sale_prices": [item]}, {})) == 1, (
        "무관 substring 키가 배지를 오억제하면 안 된다(false-negative 차단)"
    )
    # 개별 반증(각 무관 키 단독으로도 오억제 없음)
    for bad_key, bad_val in unrelated_keys.items():
        one = {"dev_type": "M01", "type_name": "아파트", "sale_price_per_pyeong_man": 2500,
               "sale_price_per_sqm_man": 756, "source": "지역 통계 기반 추정", bad_key: bad_val}
        assert len(_sale_price_point_estimate({"sale_prices": [one]}, {})) == 1, f"{bad_key} 단독 오억제 없음"


def test_real_dispersion_keys_still_suppress():
    """★정상 억제 유지(R2 무회귀): 진짜 분산키(band_10k·range_per_sqm·scenarios·confidence·low/high)는
    정확/경계 매칭으로 여전히 배지를 억제한다(방향성: 진짜 분산 신호일 때만 억제)."""
    # 정확 키
    for real_key, real_val in [
        ("band_10k", [3600, 4400]), ("range_per_sqm", [1000, 1400]), ("scenarios", [{"v": 1}]),
        ("confidence", 0.85), ("confidence_interval", [0.8, 0.95]), ("low", 3600), ("high", 4400),
        ("recommended_cap_10k", 3600), ("stddev", 120.0), ("percentile", 90),
    ]:
        item = {"dev_type": "M01", "type_name": "아파트", "sale_price_per_pyeong_man": 4000,
                "sale_price_per_sqm_man": 1210, "source": "거래사례비교", real_key: real_val}
        assert _sale_price_point_estimate({"sale_prices": [item]}, {}) == [], f"{real_key} 동반 → 정상 억제"
    # 워드바운더리(합성 분산키 — 접미/접두 경계)
    for boundary_key, boundary_val in [
        ("sale_price_band", [3600, 4400]), ("price_range", {"low": 1, "high": 2}),
        ("pyeong_low", 3600), ("pyeong_high", 4400), ("band_note", "밴드"),
        ("confidence_level", 0.9), ("recommended_cap_man", 3600),
    ]:
        item = {"dev_type": "M01", "type_name": "아파트", "sale_price_per_pyeong_man": 4000,
                "sale_price_per_sqm_man": 1210, "source": "거래사례비교", boundary_key: boundary_val}
        assert _sale_price_point_estimate({"sale_prices": [item]}, {}) == [], f"{boundary_key}(경계) 동반 → 정상 억제"


# ────────────────────────────────────────────────────────────────────────────
# 7) 실제 shape 대조 + finding 계약
# ────────────────────────────────────────────────────────────────────────────


def test_real_shape_sale_prices_bare_and_undetermined():
    """실제 shape: bare 항목(dev_type/type_name/sale_price_per_pyeong_man/sale_price_per_sqm_man/source·분산필드 전무)·판정불가(development_type/type_name/note)."""
    bare = _CASES["bare_point_estimates"]["input"]["sale_prices"][0]
    assert set(bare.keys()) == {
        "dev_type", "type_name", "sale_price_per_pyeong_man", "sale_price_per_sqm_man", "source",
    }
    assert bare["sale_price_per_pyeong_man"] > 0
    assert bare["source"] == "지역 통계 기반 추정"
    # ★정본 반환엔 분산 필드가 없다(band/range/low/high/scenario/confidence)
    for k in bare:
        kl = k.lower()
        assert not any(t in kl for t in ("band", "range", "scenario", "confidence", "interval"))
        assert kl not in {"low", "high"}

    und = _CASES["undetermined_only"]["input"]["sale_prices"][0]
    assert und["type_name"] == "판정불가"
    assert und.get("development_type") is None
    assert "sale_price_per_pyeong_man" not in und  # 판정불가 항목은 점추정 필드 없음


def test_finding_contract():
    """SALE_PRICE_POINT_ESTIMATE finding 계약 고정(code·severity·tier·panel·expected·observed·note·field)."""
    findings = _sale_price_point_estimate(_CASES["bare_point_estimates"]["input"], {})
    assert len(findings) == 1
    f = findings[0]
    assert f.code == _CODE and f.rule_id == _CODE
    assert f.severity == "P2" and f.tier == "C" and f.panel == _PANEL
    assert f.field == "sale_prices.sale_price_per_pyeong_man"
    assert f.expected == _EXPECTED_MARK
    assert "점추정" in str(f.observed) and "분산" in str(f.observed)
    assert f.note == _NOTE
    # note는 순수 형태 고지(값 오류 아님)·과제 지정 문구
    assert "단일 점추정" in f.note and "신뢰구간·시나리오 미제공" in f.note and "구간 산출 가능하나 미반영" in f.note


# ────────────────────────────────────────────────────────────────────────────
# 8) ★폴백 감지 불가 확증(정직 정정) — 폴백이어도 정상 케이스와 동일 배지/note
# ────────────────────────────────────────────────────────────────────────────


def test_fallback_not_separately_detectable():
    """★폴백(base 1500)은 result 감지 불가 → 정상 케이스와 동일 배지 1건·동일 note(폴백 별도 note 없음).

    source가 폴백 여부와 무관하게 동일하고 1500이 정당 지역가와 충돌하므로 폴백-특정 표식이 불가능하다.
    억지 폴백 note를 만들지 않았음을 고정한다(감지 불가면 생략 — 과제 지정).
    """
    fb = _sale_price_point_estimate(_CASES["fallback_still_bare"]["input"], {})
    normal = _sale_price_point_estimate(_CASES["bare_point_estimates"]["input"], {})
    assert len(fb) == 1 and len(normal) == 1
    # 폴백 케이스 note에 '폴백'·'전국 기본값' 같은 별도 문구가 없다(정상과 동일 note)
    assert fb[0].note == normal[0].note == _NOTE
    assert "폴백" not in fb[0].note and "전국 기본값" not in fb[0].note


# ────────────────────────────────────────────────────────────────────────────
# 9) 안전(오탐 0 · 예외 없음 · 경로 비의존)
# ────────────────────────────────────────────────────────────────────────────


def test_non_dict_and_missing_safe():
    """비dict payload·키 부재/비list/비dict 항목 안전(오탐 0·예외 없음)."""
    assert _sale_price_point_estimate({}, {}) == []
    assert _sale_price_point_estimate({"sale_prices": None}, {}) == []
    assert _sale_price_point_estimate({"sale_prices": "bad"}, {}) == []
    assert _sale_price_point_estimate({"sale_prices": {}}, {}) == []       # dict(비list) → 무발동
    assert _sale_price_point_estimate({"sale_prices": []}, {}) == []
    assert _sale_price_point_estimate({"sale_prices": [None, "x", 1]}, {}) == []  # 비dict 항목만
    assert _sale_price_point_estimate(None, {}) == []  # type: ignore[arg-type]
    # 점추정 필드 없음/0/음수/bool → 무발동
    assert _sale_price_point_estimate({"sale_prices": [{"type_name": "아파트"}]}, {}) == []
    assert _sale_price_point_estimate(
        {"sale_prices": [{"sale_price_per_pyeong_man": 0}]}, {}
    ) == []
    assert _sale_price_point_estimate(
        {"sale_prices": [{"sale_price_per_pyeong_man": -100}]}, {}
    ) == []
    # ★bool price(True=1)를 유효 점추정으로 오판하지 않음
    assert _sale_price_point_estimate(
        {"sale_prices": [{"sale_price_per_pyeong_man": True}]}, {}
    ) == []
    # ★판정불가 항목에 spurious price가 붙어도 판정불가 마커로 제외
    assert _sale_price_point_estimate(
        {"sale_prices": [{"type_name": "판정불가", "sale_price_per_pyeong_man": 2500}]}, {}
    ) == []
