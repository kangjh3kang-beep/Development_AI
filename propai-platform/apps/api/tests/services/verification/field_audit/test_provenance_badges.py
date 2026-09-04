"""provenance 계층B 배지 불변식 테스트(Phase0 W2-a) — 미등록 출처·신선도 만료 P2 배지.

검증 축:
  1) 등록·멱등: register_all_rules 후 PROV_UNKNOWN_SOURCE·PROV_STALE_DATA 존재, 재등록해도 규칙 수 불변.
  2) 케이스별 카운트: unknown/stale/mixed=배지 N건, healthy/absent/empty/ordinance_dict=0건(오탐 없음).
  3) ★P2 비차단(계층B 핵심): 배지가 있어도 AuditReport.is_valid==True(P0 없음) — is_valid 불변.
  4) ★변이-kill: 규칙 fn을 return []로 변이하면 배지 소멸(배지가 로직 산물임 증명). 정상 provenance엔 0(오탐 없음).
  5) 실제 shape 대조: 미등록={source_type:'unknown',registered:false}, 등록=to_dict()(registered 키 없음)+freshness{is_fresh}.
  6) stale 판정 가능한 것만: freshness 부재(last_updated None)면 무발동, is_fresh=false면 발동.

★정직표기: fixture는 W0/W1 합성(라이브 미수집)이며 evidence_contract.build_provenance 실제
산출 shape에 충실한 구조 시드다(_meta.synthetic=true·honesty).
"""

import copy
import json
from pathlib import Path

import pytest

import app.services.growth.capture_service as cap
from app.services.verification.field_audit import runner
from app.services.verification.field_audit.invariants import provenance, register_all_rules
from app.services.verification.field_audit.invariants.provenance import (
    _PANEL,
    _STALE_EXPECTED,
    _UNKNOWN_EXPECTED,
    _prov_stale_data,
    _prov_unknown_source,
)
from app.services.verification.field_audit.rules_registry import (
    clear_registry,
    registered_rule_ids,
    rule_count,
)

_FIX = Path(__file__).parent / "fixtures" / "provenance" / "W2a_provenance_badges.json"
_DATA = json.loads(_FIX.read_text(encoding="utf-8"))
_CASES = _DATA["cases"]
_CASE_IDS = sorted(_CASES.keys())

_PROV_CODES = ("PROV_UNKNOWN_SOURCE", "PROV_STALE_DATA")


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


def test_rules_registered():
    """register_all_rules 후 두 provenance 규칙이 레지스트리에 존재한다."""
    ids = registered_rule_ids()
    assert "PROV_UNKNOWN_SOURCE" in ids
    assert "PROV_STALE_DATA" in ids


def test_idempotent_registration():
    """register_all_rules·모듈 register_rules를 재호출해도 규칙 수 불변(멱등 — _SEEN_IDS 중복 무시)."""
    n1 = rule_count()
    register_all_rules()          # 2회
    provenance.register_rules()   # 3회(모듈 직접)
    register_all_rules()          # 4회
    assert rule_count() == n1
    ids = registered_rule_ids()
    assert ids.count("PROV_UNKNOWN_SOURCE") == 1
    assert ids.count("PROV_STALE_DATA") == 1


# ────────────────────────────────────────────────────────────────────────────
# 2) 케이스별 카운트(양성 N건 · 오탐 0건)
# ────────────────────────────────────────────────────────────────────────────


def test_fixture_wellformed():
    """골든 fixture 구조 계약 — 정직표기·전 케이스 존재."""
    meta = _DATA["_meta"]
    assert meta["seed_id"] == "W2a"
    assert meta["synthetic"] is True
    assert "honesty" in meta and meta["tier"] == "B"
    assert set(_CASE_IDS) >= {
        "unknown_source", "stale", "mixed", "healthy", "absent", "empty", "ordinance_dict_shape",
    }


@pytest.mark.parametrize("case_name", _CASE_IDS)
def test_case_expected_counts(case_name):
    """각 케이스의 배지 카운트가 fixture expect와 일치. 양성=배지 산출, healthy/absent/empty/ordinance=0(오탐 없음)."""
    case = _CASES[case_name]
    payload = case["input"]
    exp = case["expect"]
    unknown = _prov_unknown_source(payload, {})
    stale = _prov_stale_data(payload, {})
    assert len(unknown) == exp["PROV_UNKNOWN_SOURCE"], f"{case_name}: PROV_UNKNOWN_SOURCE"
    assert len(stale) == exp["PROV_STALE_DATA"], f"{case_name}: PROV_STALE_DATA"
    # 산출된 배지는 전부 P2·계층B(비차단 배지 계약)
    for f in unknown + stale:
        assert f.severity == "P2" and f.tier == "B" and f.panel == _PANEL


# ────────────────────────────────────────────────────────────────────────────
# 3) ★P2 비차단(계층B 핵심) — 배지가 있어도 is_valid 불변
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("case_name", ["unknown_source", "stale", "mixed"])
def test_p2_badges_are_non_blocking(case_name):
    """★계층B 핵심: 미등록/신선도만료 배지가 있어도 is_valid==True(P0 없음). is_valid 불변."""
    case = _CASES[case_name]
    result = copy.deepcopy(case["input"])
    report = runner.run(result, {})

    total = case["expect"]["PROV_UNKNOWN_SOURCE"] + case["expect"]["PROV_STALE_DATA"]
    prov = [f for f in report.findings if f.code in _PROV_CODES]
    assert len(prov) == total, "배지가 실제로 산출됨"
    assert all(f.severity == "P2" for f in prov)
    # P0 부재 → is_valid True(계층B 비차단 계약)
    assert all(f.severity != "P0" for f in report.findings)
    assert report.is_valid is True
    assert result["field_audit"]["is_valid"] is True  # 부착된 리포트도 동일


def test_healthy_absent_empty_ordinance_yield_no_findings_via_runner():
    """오탐 0(런너 경로): 건강/부재/빈/공존 dict 케이스는 배지 0건·is_valid True."""
    for case_name in ("healthy", "absent", "empty", "ordinance_dict_shape"):
        result = copy.deepcopy(_CASES[case_name]["input"])
        report = runner.run(result, {})
        prov = [f for f in report.findings if f.code in _PROV_CODES]
        assert prov == [], f"{case_name}: 배지 0건(오탐 없음)"
        assert report.is_valid is True


# ────────────────────────────────────────────────────────────────────────────
# 4) ★변이-kill — 규칙 fn을 return []로 변이하면 배지 소멸(로직 산물 증명)
# ────────────────────────────────────────────────────────────────────────────


def test_mutation_unknown_rule_noop_drops_badge(monkeypatch):
    """★변이-kill: PROV_UNKNOWN_SOURCE fn을 return []로 변이→재등록하면 배지가 사라진다(배지=로직 산물)."""
    payload = _CASES["unknown_source"]["input"]
    # 정상: 등록 파이프라인이 배지 2건 산출
    clear_registry()
    provenance.register_rules()
    rep = runner.run(copy.deepcopy(payload), {})
    assert sum(f.code == "PROV_UNKNOWN_SOURCE" for f in rep.findings) == 2

    # 변이: fn을 return []로 교체 후 재등록 → 배지 소멸
    clear_registry()
    monkeypatch.setattr(provenance, "_prov_unknown_source", lambda p, c: [])
    provenance.register_rules()
    rep2 = runner.run(copy.deepcopy(payload), {})
    assert sum(f.code == "PROV_UNKNOWN_SOURCE" for f in rep2.findings) == 0


def test_mutation_stale_rule_noop_drops_badge(monkeypatch):
    """★변이-kill: PROV_STALE_DATA fn을 return []로 변이→재등록하면 배지가 사라진다."""
    payload = _CASES["stale"]["input"]
    clear_registry()
    provenance.register_rules()
    rep = runner.run(copy.deepcopy(payload), {})
    assert sum(f.code == "PROV_STALE_DATA" for f in rep.findings) == 1

    clear_registry()
    monkeypatch.setattr(provenance, "_prov_stale_data", lambda p, c: [])
    provenance.register_rules()
    rep2 = runner.run(copy.deepcopy(payload), {})
    assert sum(f.code == "PROV_STALE_DATA" for f in rep2.findings) == 0


# ────────────────────────────────────────────────────────────────────────────
# 5) 실제 shape 대조 + finding 계약
# ────────────────────────────────────────────────────────────────────────────


def test_real_shape_unknown_and_registered_entries():
    """실제 shape: 미등록={source_type:'unknown', registered:false}, 등록=to_dict()(registered 키 없음)+freshness."""
    unknown_entry = _CASES["unknown_source"]["input"]["provenance"][1]
    assert unknown_entry["source_type"] == "unknown" and unknown_entry["registered"] is False

    reg_fresh = _CASES["unknown_source"]["input"]["provenance"][0]
    assert "registered" not in reg_fresh            # 등록 출처는 registered 키 없음(to_dict)
    assert reg_fresh["freshness"]["is_fresh"] is True

    stale_entry = _CASES["stale"]["input"]["provenance"][0]
    assert "registered" not in stale_entry
    assert stale_entry["freshness"]["is_fresh"] is False


def test_unknown_finding_contract():
    """PROV_UNKNOWN_SOURCE finding 계약 고정(code·severity·tier·panel·expected·observed·note·field)."""
    findings = _prov_unknown_source(_CASES["unknown_source"]["input"], {})
    assert len(findings) == 2
    f = findings[0]
    assert f.code == "PROV_UNKNOWN_SOURCE" and f.rule_id == "PROV_UNKNOWN_SOURCE"
    assert f.severity == "P2" and f.tier == "B" and f.panel == _PANEL
    assert f.expected == _UNKNOWN_EXPECTED and f.observed == "미등록"
    assert f.note == "출처 미등록(권위소스 목록에 없음)—값 신뢰도 확인 필요"
    assert f.field in ("custom_scraper", "manual_xls_upload")  # 엔트리별 소스명


def test_stale_finding_contract():
    """PROV_STALE_DATA finding 계약 고정 — 소스명·만료 observed·신선도 경고 note(correctness 아님)."""
    findings = _prov_stale_data(_CASES["stale"]["input"], {})
    assert len(findings) == 1
    f = findings[0]
    assert f.code == "PROV_STALE_DATA" and f.rule_id == "PROV_STALE_DATA"
    assert f.severity == "P2" and f.tier == "B" and f.panel == _PANEL
    assert f.expected == _STALE_EXPECTED and f.field == "vworld_zoning"
    assert "만료" in f.observed
    assert "신선도" in (f.note or "") and "오류 아님" in (f.note or "")


# ────────────────────────────────────────────────────────────────────────────
# 6) "stale 판정 가능한 것만" · 등록 출처는 unknown 아님(경계 대조)
# ────────────────────────────────────────────────────────────────────────────


def test_stale_requires_freshness_present():
    """★freshness 부재(last_updated None)면 stale 무발동(신선도 신호 자체 없음). is_fresh=false면 발동.

    ★is_fresh=None(판정불명)·키 누락은 무발동이어야 한다 — 오직 is_fresh **is False**만 만료.
    이 경계가 엄격판정(`is not False`)과 falsy판정을 가르는 유일한 지점이라 반드시 고정한다
    (falsy로 회귀하면 None/누락/0을 stale로 오판 → 라이브 도달 전 CI가 잡도록 변이-kill).
    """
    base = {
        "name": "tax_acquisition_rates", "source_type": "hardcoded",
        "update_frequency": "yearly", "last_updated": None, "is_healthy": True,
    }
    # freshness 없음 → 무발동
    assert _prov_stale_data({"provenance": [base]}, {}) == []
    # freshness.is_fresh=false → 발동
    staleish = {**base, "freshness": {"is_fresh": False, "age_days": 400, "max_age_days": 180}}
    assert len(_prov_stale_data({"provenance": [staleish]}, {})) == 1
    # freshness.is_fresh=true → 무발동
    freshish = {**base, "freshness": {"is_fresh": True, "age_days": 5, "max_age_days": 180}}
    assert _prov_stale_data({"provenance": [freshish]}, {}) == []
    # ★freshness 존재 + is_fresh=None(판정불명) → 무발동(엄격 is False만 만료·falsy회귀 방지)
    indeterminate = {**base, "freshness": {"is_fresh": None, "age_days": 100, "max_age_days": 90}}
    assert _prov_stale_data({"provenance": [indeterminate]}, {}) == []
    # ★freshness 존재 + is_fresh 키 누락 → 무발동(.get None을 stale로 오판 안 함)
    missing_isfresh = {**base, "freshness": {"age_days": 100, "max_age_days": 90}}
    assert _prov_stale_data({"provenance": [missing_isfresh]}, {}) == []


def test_registered_source_not_flagged_unknown():
    """등록 출처(to_dict, registered 키 없음)는 PROV_UNKNOWN_SOURCE 무발동(등록/미등록만 갈라냄)."""
    entry = {"name": "molit_transactions", "source_type": "api", "is_healthy": True}
    assert _prov_unknown_source({"provenance": [entry]}, {}) == []


def test_non_dict_and_missing_provenance_safe():
    """비dict payload·provenance 부재/비리스트 안전(오탐 0·예외 없음)."""
    assert _prov_unknown_source({}, {}) == []
    assert _prov_stale_data({}, {}) == []
    assert _prov_unknown_source({"provenance": None}, {}) == []
    assert _prov_stale_data({"provenance": "bad"}, {}) == []
    assert _prov_unknown_source(None, {}) == []  # type: ignore[arg-type]
