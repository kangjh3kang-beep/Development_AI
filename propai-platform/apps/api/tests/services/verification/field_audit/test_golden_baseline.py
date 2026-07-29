"""골든 strata 기준선 — 6대 결함(G1~G6) frozen 입력 + 현행(오류) 출력 assert.

W0 기준선의 의미(2층 flip 증명 앵커):
  ① 하네스 레벨: 등록규칙 0건이라 runner.run(golden)은 **빈 리포트**(is_valid=True·findings=[])
     → 플랫폼이 현재 이 결함들을 **못 잡는다**는 현행 상태를 박제. W1이 규칙을 등록하면
     동일 fixture가 findings를 내고 is_valid가 flip → 이 assert가 뒤집힘 = 가드 실재 증명.
  ② 도메인값 레벨: 각 fixture의 current_baseline(risk_level=낮음·school_count=5 등)이 W1
     근본수정으로 flip될 대상값을 앵커링.

G5는 regression_lock(이미 수정) — W1 이후에도 finding 0을 **유지**해야 하는 잠금 시드.

★정직표기: fixture는 W0 합성(라이브 analyze() 미수집·하네스 환경 DB/API 부재)이며, 현행
코드 baseline(risk_keywords 등)에 충실한 구조 시드다. W1 착수 시 실주소 라이브값으로 교체.
"""

import copy
import json
from pathlib import Path

import pytest

import app.services.growth.capture_service as cap
from app.services.verification.field_audit import runner
from app.services.verification.field_audit.invariants.cross_field import register_rules
from app.services.verification.field_audit.rules_registry import clear_registry

_FIX = Path(__file__).parent / "fixtures" / "landattr"

# (seed_id, 상대경로) — 6대 결함.
_GOLDEN = [
    ("G1", "imya__natural_green__survey_needed/G1_homigot_military_control.json"),
    ("G2", "imya__natural_green__survey_needed/G2_daebo_school_dedup.json"),
    ("G3", "imya__conservation_mgmt__conservation_forest/G3_conservation_mgmt_permit_gap.json"),
    ("G4", "imya__natural_green__survey_needed/G4_homigot_market_multiplier.json"),
    ("G5", "dae__natural_green__na/G5_realtx_iqr_lock.json"),
    ("G6", "imya__planning_mgmt__quasi_forest/G6_imya_slope_orphan.json"),
]


def _load(rel: str) -> dict:
    return json.loads((_FIX / rel).read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _isolate_and_silence(monkeypatch):
    """규칙 레지스트리 격리 + W1 프로덕션 규칙 재등록 + growth emit 무음화(테스트 부작용 차단).

    clear_registry()로 상태 누수를 막은 뒤 register_rules()로 프로덕션 불변식(W1-1 G1)을
    재등록한다 — golden이 '프로덕션에 등록된 규칙 집합'으로 판정하게 하여 flip을 실증한다.
    G2~G6는 아직 규칙이 없어 blind 유지, G1만 fires.
    """
    clear_registry()
    register_rules()
    monkeypatch.setattr(cap, "record_event", lambda *a, **k: None)
    yield
    clear_registry()


@pytest.mark.parametrize("seed_id,rel", _GOLDEN, ids=[g[0] for g in _GOLDEN])
def test_golden_fixture_is_wellformed(seed_id, rel):
    """골든 fixture 구조 계약 — strata·현행baseline·정직표기 필드 존재."""
    fx = _load(rel)
    meta = fx["_meta"]
    assert meta["seed_id"] == seed_id
    assert meta["synthetic"] is True  # W0 합성 정직표기
    assert "honesty" in meta
    la = meta["land_attrs"]
    assert set(("jimok", "zone", "sanji_gubun")).issubset(la.keys())  # 토지속성 조합 축
    assert "input" in fx and "ctx" in fx and "current_baseline" in fx


@pytest.mark.parametrize("seed_id,rel", _GOLDEN, ids=[g[0] for g in _GOLDEN])
def test_golden_current_baseline_platform_blind(seed_id, rel):
    """★W1 flip 기준선: G1은 이제 규칙이 잡고(finding·is_valid=False), 아직 규칙 없는 결함(G2~G6)은
    blind 유지.

    W0에선 전부 blind(규칙 0건)였다. W1-1이 G1 불변식을 붙여 동일 fixture가 findings를 내고
    is_valid가 flip → 가드 실재를 증명한다. 나머지 결함은 각자의 Wave에서 규칙이 붙을 때 flip한다.
    """
    fx = _load(rel)
    result = copy.deepcopy(fx["input"])
    report = runner.run(result, fx["ctx"])

    if seed_id == "G1":
        # 통제보호+방공 → risk 낮음(하한 '높음' 미달) → P0 finding(W0 blind→W1 catch flip)
        assert report.is_valid is False, "G1: W1 규칙이 buggy 시드를 잡아 is_valid=False로 flip"
        assert "G1_PROTECTION_ZONE_RISK_FLOOR" in [f.code for f in report.findings]
        assert result["field_audit"]["is_valid"] is False
    else:
        # 아직 규칙 없는 결함 → blind(빈 리포트) 유지 — additive 부착만(behavior 불변)
        assert report.findings == [], f"{seed_id}: 아직 규칙 미등록 → finding 0(blind 유지)"
        assert report.is_valid is True
        assert result["field_audit"]["findings"] == []


def test_g1_harness_flip_from_blind():
    """★W1 핵심 flip: G1 buggy 시드(통제보호+방공·risk 낮음)에서 harness가 P0 finding을 낸다.

    W0(규칙 0건)에선 blind였던 것이 W1-1 cross_field.G1 등록으로 잡힌다. expected=하한('높음')·
    observed=산출('낮음')·rule_id·tier까지 계약을 고정한다. (변이-kill은 test_protection_zone_severity.)
    """
    fx = _load("imya__natural_green__survey_needed/G1_homigot_military_control.json")
    report = runner.run(copy.deepcopy(fx["input"]), fx["ctx"])
    assert report.is_valid is False
    f = next(f for f in report.findings if f.code == "G1_PROTECTION_ZONE_RISK_FLOOR")
    assert f.severity == "P0" and f.tier == "A"
    assert f.expected == "높음" and f.observed == "낮음"       # 하한 vs 산출
    assert f.rule_id == "G1_PROTECTION_ZONE_RISK" and f.field == "risk_level"


def test_g1b_limited_protection_not_overcorrected():
    """★비블랭킷 증명(과잉교정 회피): 제한보호=중간을 '중간'으로 산출하면 harness 무발동.

    통제보호(낮음→높음 flip)와 대칭으로, 협의개발 가능한 제한보호를 '높음'으로 평탄화하지
    않음을 핀한다(계획 §12.3 M4). 하한('중간') 충족 → finding 0.
    """
    fx = _load("dae__planning_mgmt__na/G1b_limited_protection_negotiable.json")
    assert fx["_meta"]["seed_id"] == "G1b"
    assert fx["input"]["risk"]["risk_level"] == "중간"          # 높음 아님(반증)
    report = runner.run(copy.deepcopy(fx["input"]), fx["ctx"])
    assert report.findings == [], "제한보호=중간 산출은 하한(중간) 충족 → 무발동(과잉교정 X)"
    assert report.is_valid is True


@pytest.mark.parametrize("seed_id,rel", _GOLDEN, ids=[g[0] for g in _GOLDEN])
def test_golden_documents_buggy_value_anchor(seed_id, rel):
    """도메인값 앵커: current_baseline이 W1 근본수정으로 flip될 대상값을 명시 박제."""
    fx = _load(rel)
    cb = fx["current_baseline"]
    assert "field" in cb and "observed" in cb and "note" in cb


def test_g1_baseline_risk_underrated():
    """G1 앵커: 규제목록에 통제보호/방공기지가 있어도 risk_level=낮음(과소평가)."""
    fx = _load("imya__natural_green__survey_needed/G1_homigot_military_control.json")
    regs = fx["input"]["regulations"]
    assert any("통제보호" in r for r in regs)
    assert any("방공기지" in r for r in regs)
    assert fx["input"]["risk"]["risk_level"] == "낮음"       # 현행(오류)
    assert fx["current_baseline"]["observed"] == "낮음"       # W1: → 높음+ flip


def test_g2_baseline_school_overcounted():
    """G2 앵커: 대보초 부속시설·분교가 개별카운트 → 5개교(실제 1)."""
    fx = _load("imya__natural_green__survey_needed/G2_daebo_school_dedup.json")
    assert fx["input"]["poi"]["school_count"] == 5             # 현행(오류)
    names = [s["name"] for s in fx["input"]["poi"]["schools"]]
    assert all("대보초" in n for n in names)                   # 전부 동일 모학교
    assert fx["current_baseline"]["observed"] == 5            # W1: → 1(대보초) flip


def test_g5_regression_lock_robust_stats():
    """G5 잠금: log-IQR robust trim이 이상치(2만원)를 배제한 정상값 — W1 이후에도 유지."""
    fx = _load("dae__natural_green__na/G5_realtx_iqr_lock.json")
    assert fx["_meta"]["regression_lock"] is True
    rtx = fx["input"]["realtx"]
    assert rtx["robust_stats_applied"] is True
    assert 20000 in rtx["excluded_outliers"]                  # 이상치 배제(정상)
    assert rtx["robust_price_per_sqm"] == 500000              # 잠금 대상값
