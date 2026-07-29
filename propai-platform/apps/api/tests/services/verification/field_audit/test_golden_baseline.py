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
    """규칙 레지스트리 격리(W0 0건) + growth emit 무음화(테스트 부작용 차단)."""
    clear_registry()
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
    """★현행 기준선: 등록규칙 0건 → 플랫폼이 결함을 못 잡는다(빈 리포트).

    W1이 규칙을 붙이면 이 assert가 flip(findings 발생·is_valid=False)되어 가드 실재를 증명한다.
    """
    fx = _load(rel)
    result = copy.deepcopy(fx["input"])
    report = runner.run(result, fx["ctx"])

    # 현행: 결함을 못 잡음 → 빈 findings·is_valid True (W1이 뒤집을 대상)
    assert report.findings == [], f"{seed_id}: W0는 규칙 0건이라 finding 0이어야(현행 blind)"
    assert report.is_valid is True
    # additive 부착 확인(behavior 불변)
    assert result["field_audit"]["findings"] == []


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
