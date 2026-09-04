"""terrain_coverage 불변식 테스트(Phase0 W3-3 / G6) — 임야/산지 후보의 수집가능 경사도(DEM) 미획득 갭.

검증 축:
  1) 등록·멱등: register_all_rules 후 TERRAIN_SLOPE_COLLECTION_GAP 존재, 재등록해도 규칙 수 불변.
  2) 케이스별 카운트(fixture): 임야+경사None=1, 임야+경사present=0, 비임야+경사None=0(후보 아님),
     임야+경사present+임목축적None=0(실측필요 무관), terrain부재=0, 산지district+게이트경사None=1.
  3) ★P1 비차단(계층A 완전성 갭): finding이 있어도 AuditReport.is_valid==True(P0 없음) — is_valid 불변.
  4) ★변이-kill: 규칙 fn을 return []로 변이하면 finding 소멸(실함수 호출 증명·가짜 동어반복 아님). 정상 off 케이스엔 0.
  5) ★오라클 독립성: 경사도 '값'을 바꿔도(획득 수치 극단값) 판정 불변 — 값 재계산·임계값 없음(완전성만 판정).
  6) ★수집가능/실측필요 구분: 임목축적_per_ha None을 아무리 바꿔도 slope present면 무발동(경사도 키만 읽음).
  7) 실제 shape 대조 + finding 계약: forest_facts.평균경사도_pct·dev_act_permit_gate.criteria.slope.value.
  8) 안전: 비dict·키 부재·경사도 구조 부재(부재≠미획득) → 오탐 0·예외 없음.

★정직표기: fixture는 W0/W3 합성(라이브 terrain 미수집)이며 special_parcel/dev_act_permit_gate 값은
detect_special_parcel·assess_dev_act_permit(정본 함수)의 실제 반환 shape다(_meta.synthetic=true·honesty).
"""

import copy
import json
from pathlib import Path

import pytest

import app.services.growth.capture_service as cap
from app.services.verification.field_audit import runner
from app.services.verification.field_audit.invariants import (
    register_all_rules,
    terrain_coverage,
)
from app.services.verification.field_audit.invariants.terrain_coverage import (
    _EXPECTED_MARK,
    _NOTE,
    _PANEL,
    _SLOPE_KEY,
    _terrain_slope_collection_gap,
)
from app.services.verification.field_audit.rules_registry import (
    clear_registry,
    registered_rule_ids,
    rule_count,
)

_FIX = Path(__file__).parent / "fixtures" / "terrain" / "W3_terrain_slope_coverage.json"
_DATA = json.loads(_FIX.read_text(encoding="utf-8"))
_CASES = _DATA["cases"]
_CASE_IDS = sorted(_CASES.keys())

_CODE = "TERRAIN_SLOPE_COLLECTION_GAP"

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
    """register_all_rules 후 TERRAIN_SLOPE_COLLECTION_GAP 규칙이 레지스트리에 존재한다."""
    assert _CODE in registered_rule_ids()


def test_idempotent_registration():
    """register_all_rules·모듈 register_rules를 재호출해도 규칙 수 불변(멱등 — _SEEN_IDS 중복 무시)."""
    n1 = rule_count()
    register_all_rules()
    terrain_coverage.register_rules()
    register_all_rules()
    assert rule_count() == n1
    assert registered_rule_ids().count(_CODE) == 1


# ────────────────────────────────────────────────────────────────────────────
# 2) 케이스별 카운트(양성 1건 · 오탐 0건)
# ────────────────────────────────────────────────────────────────────────────


def test_fixture_wellformed():
    """골든 fixture 구조 계약 — 정직표기·전 케이스 존재·양성/음성 분리·재확증 shape 노트."""
    meta = _DATA["_meta"]
    assert meta["seed_id"] == "W3-3"
    assert meta["synthetic"] is True
    assert "honesty" in meta and meta["tier"] == "A"
    assert meta["rule_id"] == _CODE
    assert "reconfirmed_shape" in meta  # 수집가능/실측필요 위치 재확증 근거
    assert set(_CASE_IDS) == {
        "imya_slope_missing", "imya_slope_present", "non_forest_slope_missing",
        "imya_slope_present_stocking_missing", "terrain_absent",
        "sanji_district_gate_slope_missing",
    }
    assert set(_POSITIVE_CASES) == {"imya_slope_missing", "sanji_district_gate_slope_missing"}


@pytest.mark.parametrize("case_name", _CASE_IDS)
def test_case_expected_counts(case_name):
    """각 케이스 finding 카운트가 fixture expect와 일치. 임야+경사None=1, 그 외/실측필요None/비후보/부재=0."""
    case = _CASES[case_name]
    findings = _terrain_slope_collection_gap(case["input"], {})
    assert len(findings) == case["expect"][_CODE], f"{case_name}: {_CODE}"
    for f in findings:  # 산출된 finding은 전부 P1·계층A·개발행위 패널
        assert f.severity == "P1" and f.tier == "A" and f.panel == _PANEL


# ────────────────────────────────────────────────────────────────────────────
# 3) ★P1 비차단(계층A 완전성 갭) — finding이 있어도 is_valid 불변
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("case_name", _POSITIVE_CASES)
def test_p1_finding_is_non_blocking(case_name):
    """★비차단: 경사도 갭 finding이 있어도 is_valid==True(P0 없음 — is_valid=not has_p0이라 P1은 안 막음)."""
    result = copy.deepcopy(_CASES[case_name]["input"])
    report = runner.run(result, {})

    mine = [f for f in report.findings if f.code == _CODE]
    assert len(mine) == 1, "finding이 실제로 산출됨"
    assert all(f.severity == "P1" for f in mine)
    assert all(f.severity != "P0" for f in report.findings)
    assert report.is_valid is True
    assert result["field_audit"]["is_valid"] is True  # 부착된 리포트도 동일


def test_negatives_yield_no_findings_via_runner():
    """오탐 0(런너 경로): 경사present/비후보/실측필요None/terrain부재는 finding 0건·is_valid True."""
    assert set(_NEGATIVE_CASES) == {
        "imya_slope_present", "non_forest_slope_missing",
        "imya_slope_present_stocking_missing", "terrain_absent",
    }
    for case_name in _NEGATIVE_CASES:
        result = copy.deepcopy(_CASES[case_name]["input"])
        report = runner.run(result, {})
        mine = [f for f in report.findings if f.code == _CODE]
        assert mine == [], f"{case_name}: finding 0건(오탐 없음)"
        assert report.is_valid is True


# ────────────────────────────────────────────────────────────────────────────
# 4) ★변이-kill — 규칙 fn을 return []로 변이하면 finding 소멸(로직 산물 증명)
# ────────────────────────────────────────────────────────────────────────────


def test_mutation_rule_noop_drops_finding(monkeypatch):
    """★변이-kill: fn을 return []로 교체 후 재등록하면 finding이 사라진다(finding=실함수 산물, 가짜 동어반복 아님)."""
    payload = _CASES["imya_slope_missing"]["input"]
    # 정상: 등록 파이프라인이 finding 1건 산출(실함수 호출)
    clear_registry()
    terrain_coverage.register_rules()
    rep = runner.run(copy.deepcopy(payload), {})
    assert sum(f.code == _CODE for f in rep.findings) == 1

    # 변이: fn을 return []로 교체 후 재등록 → finding 소멸
    clear_registry()
    monkeypatch.setattr(terrain_coverage, "_terrain_slope_collection_gap", lambda p, c: [])
    terrain_coverage.register_rules()
    rep2 = runner.run(copy.deepcopy(payload), {})
    assert sum(f.code == _CODE for f in rep2.findings) == 0


# ────────────────────────────────────────────────────────────────────────────
# 5) ★오라클 독립성 — 경사도 '값'은 오라클 아님(값 재계산·임계값 없음)
# ────────────────────────────────────────────────────────────────────────────


def test_oracle_independence_slope_value_not_recomputed():
    """★경사도 획득 수치를 극단값으로 바꿔도 판정 불변(0건) — 값을 재계산/임계비교하지 않음 증명.

    이 규칙은 '경사도 값이 맞는가'가 아니라 '수집가능 경사도가 None인가'(완전성)만 본다. 따라서
    슬로프가 수치(0·음수·초대형)면 무엇이든 '수집됨'으로 보아 무발동이어야 한다(값-오라클 부재).
    """
    base = copy.deepcopy(_CASES["imya_slope_present"]["input"])
    assert len(_terrain_slope_collection_gap(base, {})) == 0

    for v in [0.0, 0, -5.0, 3.2, 47.0, 999999.0]:
        mut = copy.deepcopy(base)
        mut["special_parcel"]["factors"][0]["forest_facts"][_SLOPE_KEY] = v
        assert len(_terrain_slope_collection_gap(mut, {})) == 0, f"경사도값 {v}(수치)=수집됨 → 무발동"


def test_missing_slope_fires_regardless_of_value_shape():
    """대칭: 슬로프가 None/비수치(str)/bool이면 '미획득'으로 발동(수집값 아님). 오라클 독립의 반대 축."""
    base = copy.deepcopy(_CASES["imya_slope_present"]["input"])
    for v in [None, "미상", True, False]:
        mut = copy.deepcopy(base)
        mut["special_parcel"]["factors"][0]["forest_facts"][_SLOPE_KEY] = v
        assert len(_terrain_slope_collection_gap(mut, {})) == 1, f"슬로프 {v!r}=유효 수집값 아님 → 발동"


# ────────────────────────────────────────────────────────────────────────────
# 6) ★수집가능/실측필요 구분 — 임목축적(실측필요) None은 판정 대상 아님
# ────────────────────────────────────────────────────────────────────────────


def test_stocking_missing_never_fires_when_slope_present():
    """★핵심 격리: 임목축적_per_ha(실측필요)를 어떻게 바꿔도 slope present면 무발동(경사도 키만 읽음).

    (d) 케이스는 이미 stocking None인데도 finding 0이다. 여기서 stocking을 present↔None으로 흔들어도
    slope(12.0)가 present인 한 항상 0임을 실증한다 — 실측필요 None은 갭이 아니다(정직 미획득).
    """
    base = copy.deepcopy(_CASES["imya_slope_present_stocking_missing"]["input"])
    ff = base["special_parcel"]["factors"][0]["forest_facts"]
    assert ff[_SLOPE_KEY] == 12.0 and ff["입목축적_per_ha"] is None
    assert len(_terrain_slope_collection_gap(base, {})) == 0  # slope present → 0(stocking None 무관)

    for stock in [None, 0, 150.0, -3.0, "미상"]:
        mut = copy.deepcopy(base)
        mut["special_parcel"]["factors"][0]["forest_facts"]["입목축적_per_ha"] = stock
        assert len(_terrain_slope_collection_gap(mut, {})) == 0, f"임목축적 {stock!r} 변이에도 무발동(경사도만 판정)"


def test_slope_missing_fires_even_when_stocking_present():
    """대칭 실증: 임목축적(실측필요) present여도 경사도(수집가능) None이면 발동 — slope 단독 신호."""
    base = copy.deepcopy(_CASES["imya_slope_missing"]["input"])
    ff = base["special_parcel"]["factors"][0]["forest_facts"]
    assert ff[_SLOPE_KEY] is None and ff["입목축적_per_ha"] == 120.0  # slope None·stocking present
    assert len(_terrain_slope_collection_gap(base, {})) == 1


# ────────────────────────────────────────────────────────────────────────────
# 7) 실제 shape 대조 + finding 계약
# ────────────────────────────────────────────────────────────────────────────


def test_real_shape_forest_facts_and_gate_slope():
    """실제 shape: 임야 요인 forest_facts.평균경사도_pct(정본 위치)·산지 후보 gate criteria.slope.value."""
    a = _CASES["imya_slope_missing"]["input"]["special_parcel"]
    ff = a["factors"][0]["forest_facts"]
    assert "평균경사도_pct" in ff and ff["평균경사도_pct"] is None          # 수집가능 미획득
    assert ff["입목축적_per_ha"] == 120.0                                  # 실측필요는 present(구분)
    # preliminary_assessment가 수집가능/실측필요를 별도 키로 분리(slope vs stocking)
    pa = a["factors"][0]["preliminary_assessment"]
    assert pa["slope"] is None and "slope_skip_reason" in pa               # 경사도 예비판정 생략
    assert pa["stocking"] is not None                                      # 임목축적 예비판정은 산출

    gate = _CASES["sanji_district_gate_slope_missing"]["input"]["dev_act_permit_gate"]
    assert gate["gate"] == "dev_act_permit"
    assert gate["criteria"]["slope"]["value"] is None                      # 게이트 경사도 미획득
    assert gate["criteria"]["slope"]["status"] == "UNKNOWN"


def test_finding_contract():
    """TERRAIN_SLOPE_COLLECTION_GAP finding 계약 고정(code·severity·tier·panel·field·expected·observed·note)."""
    findings = _terrain_slope_collection_gap(_CASES["imya_slope_missing"]["input"], {})
    assert len(findings) == 1
    f = findings[0]
    assert f.code == _CODE and f.rule_id == _CODE
    assert f.severity == "P1" and f.tier == "A" and f.panel == _PANEL
    assert f.field == f"special_parcel.forest_facts.{_SLOPE_KEY}"
    assert f.expected == _EXPECTED_MARK and f.observed == "미획득(None)"
    assert f.note == _NOTE
    assert "재수집 권장" in f.note and "실측필요" in f.note  # 재수집 권장·실측필요 구분 명시

    # 폴백 경로(산지 district)는 게이트 field 경로로 표기
    gate_findings = _terrain_slope_collection_gap(
        _CASES["sanji_district_gate_slope_missing"]["input"], {})
    assert len(gate_findings) == 1
    assert gate_findings[0].field == "dev_act_permit_gate.criteria.slope.value"


# ────────────────────────────────────────────────────────────────────────────
# 8) 안전(오탐 0 · 예외 없음)
# ────────────────────────────────────────────────────────────────────────────


def test_non_dict_and_missing_safe():
    """비dict payload·키 부재/비dict 안전(오탐 0·예외 없음)."""
    assert _terrain_slope_collection_gap({}, {}) == []
    assert _terrain_slope_collection_gap({"special_parcel": None}, {}) == []
    assert _terrain_slope_collection_gap({"special_parcel": "bad"}, {}) == []
    assert _terrain_slope_collection_gap({"special_parcel": {"factors": "bad"}}, {}) == []
    assert _terrain_slope_collection_gap(None, {}) == []  # type: ignore[arg-type]
    # 임야 후보이나 경사도 구조 자체가 부재(forest_facts 없고 게이트 없음) → 부재≠미획득 → 무발동
    assert _terrain_slope_collection_gap({"land_category": "임야"}, {}) == []
    assert _terrain_slope_collection_gap(
        {"special_parcel": {"factors": [{"category": "임야(산지)"}]}}, {}
    ) == []  # forest_facts 없음(비정상 shape) → 폴백은 게이트 필요 → 무발동


def test_non_forest_with_gate_slope_none_no_false_positive():
    """비임야(대지)·게이트 slope None이어도 후보 아님 → 무발동(후보 게이팅). fixture (c) 재확인."""
    result = copy.deepcopy(_CASES["non_forest_slope_missing"]["input"])
    assert result["dev_act_permit_gate"]["criteria"]["slope"]["value"] is None  # slope None인데도
    assert _terrain_slope_collection_gap(result, {}) == []                       # 비후보라 무발동
