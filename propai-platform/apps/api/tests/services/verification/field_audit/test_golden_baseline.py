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
from app.services.verification.field_audit.invariants import register_all_rules
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

    clear_registry()로 상태 누수를 막은 뒤 register_all_rules()로 프로덕션 불변식(W1-1 G1·
    W1-2 G2·W1-3 G3·W3-3 G6)을 재등록한다 — golden이 '프로덕션에 등록된 규칙 집합'으로 판정하게 하여
    flip을 실증한다. G1(P0)·G2(P1)·G3(P1)·G6(P1)가 fires, 아직 규칙 없는 G4~G5는 blind 유지.
    """
    clear_registry()
    register_all_rules()
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
    """★flip 기준선: G1(P0)·G2(P1)·G3(P1)·G6(P1)는 이제 규칙이 잡고, 아직 규칙 없는 결함(G4~G5)은 blind 유지.

    W0에선 전부 blind(규칙 0건)였다. W1-1이 G1(차단후보 P0·is_valid flip), W1-2가 G2(제자리교정
    P1·비차단·is_valid 유지), W1-3이 G3(BCR/FAR 커버리지 갭 P1·비차단), W3-3이 G6(수집가능 경사도
    미획득 갭 P1·비차단) 불변식을 붙여 동일 fixture가 findings를 낸다 → 가드 실재를 증명한다.
    나머지 결함(G4·G5)은 각자의 Wave에서 규칙이 붙을 때 flip한다.
    """
    fx = _load(rel)
    result = copy.deepcopy(fx["input"])
    report = runner.run(result, fx["ctx"])

    if seed_id == "G1":
        # 통제보호+방공 → risk 낮음(하한 '높음' 미달) → P0 finding(W0 blind→W1 catch flip)
        assert report.is_valid is False, "G1: W1 규칙이 buggy 시드를 잡아 is_valid=False로 flip"
        assert "G1_PROTECTION_ZONE_RISK_FLOOR" in [f.code for f in report.findings]
        assert result["field_audit"]["is_valid"] is False
    elif seed_id == "G2":
        # 대보초 5개교 과카운트(dedup 1) → P1 finding(W0 blind→W1-2 catch flip). P1은 비차단이라
        # is_valid는 True 유지(제자리 교정+배지 — §2.4).
        codes = [f.code for f in report.findings]
        assert "G2_SCHOOL_POI_DEDUP" in codes, "G2: W1-2 dedup 규칙이 과카운트를 잡아 finding 산출"
        g2 = next(f for f in report.findings if f.code == "G2_SCHOOL_POI_DEDUP")
        assert g2.severity == "P1"
        assert report.is_valid is True, "G2는 P1(비차단) — is_valid 미변경"
        assert result["field_audit"]["findings"], "result에 G2 finding 부착"
    elif seed_id == "G3":
        # 보전관리 BCR/FAR 판정불가(null·별표 20/80 존재) → P1 커버리지 갭 finding(W0 blind→W1-3 catch).
        # P1은 비차단이라 is_valid True 유지(제자리 표면화+배지 — §2.4). ★허용용도 판정불가는
        # 조례의존이라 무플래그(갭 아님) — coverage.py가 BCR/FAR만 대조(M3 구분).
        codes = [f.code for f in report.findings]
        assert "G3_ZONE_COVERAGE_GAP" in codes, "G3: W1-3 coverage 규칙이 조용한 판정불가를 잡아 갭 finding 산출"
        g3 = next(f for f in report.findings if f.code == "G3_ZONE_COVERAGE_GAP")
        assert g3.severity == "P1"
        assert report.is_valid is True, "G3는 P1(비차단) — is_valid 미변경"
        assert result["field_audit"]["findings"], "result에 G3 finding 부착"
    elif seed_id == "G6":
        # 임야(준보전산지) 수집가능 경사도(DEM) 미획득 → P1 갭 finding(W0 blind→W3-3 catch flip). P1은
        # 비차단이라 is_valid True 유지(제자리 표면화+배지 — §2.4). ★실측필요(임목축적) None은 무플래그.
        codes = [f.code for f in report.findings]
        assert "TERRAIN_SLOPE_COLLECTION_GAP" in codes, "G6: W3-3 terrain_coverage 규칙이 수집가능 경사도 미획득을 잡아 갭 finding 산출"
        g6 = next(f for f in report.findings if f.code == "TERRAIN_SLOPE_COLLECTION_GAP")
        assert g6.severity == "P1"
        assert report.is_valid is True, "G6는 P1(비차단) — is_valid 미변경"
        assert result["field_audit"]["findings"], "result에 G6 finding 부착"
    else:
        # 아직 규칙 없는 결함(G4~G5) → blind(빈 리포트) 유지 — additive 부착만(behavior 불변)
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
    """G2 앵커: 대보초 부속시설·분교가 개별카운트 → 5개교(실제 1). W1-2 dedup으로 1 flip."""
    from app.services.external_api.poi_dedup import dedup_school_cluster

    fx = _load("imya__natural_green__survey_needed/G2_daebo_school_dedup.json")
    assert fx["input"]["poi"]["school_count"] == 5             # 현행(오류 입력)
    names = [s["name"] for s in fx["input"]["poi"]["schools"]]
    assert all("대보초" in n for n in names)                   # 전부 동일 모학교
    assert fx["current_baseline"]["observed"] == 5            # W1: → 1(대보초) flip
    # ★도메인 flip: dedup 후 고유 모학교 1(대보초) — 입지점수 학교 보너스 재계산 대상값.
    deduped = dedup_school_cluster(fx["input"]["poi"]["schools"])
    assert len(deduped) == 1
    assert "대보초등학교" in deduped[0]["name"]                 # 대표=모학교(본교)


def test_g2_harness_flip_from_blind():
    """★W1-2 핵심 flip: G2 buggy 시드(대보초 5개교 과카운트)에서 harness가 P1 finding을 낸다.

    W0(규칙 0건)에선 blind였던 것이 W1-2 cross_field.G2 등록으로 잡힌다. expected=dedup 고유수(1)·
    observed=원카운트(5)·rule_id·tier·panel·field까지 계약을 고정한다. P1은 비차단이라 is_valid
    True 유지(제자리교정+배지). (변이-kill은 test_poi_dedup.)
    """
    fx = _load("imya__natural_green__survey_needed/G2_daebo_school_dedup.json")
    report = runner.run(copy.deepcopy(fx["input"]), fx["ctx"])
    f = next(f for f in report.findings if f.code == "G2_SCHOOL_POI_DEDUP")
    assert f.severity == "P1" and f.tier == "A"
    assert f.expected == 1 and f.observed == 5                 # dedup 고유 vs 원카운트
    assert f.rule_id == "G2_SCHOOL_POI_DEDUP" and f.field == "school_count" and f.panel == "입지"
    assert report.is_valid is True                             # P1 — 비차단(배지)


def test_g3_baseline_bcr_far_undetermined():
    """G3 앵커: 별표 한도 명확한 보전관리(20/80)인데 BCR/FAR가 판정불가(null). 허용용도는 조례의존 판정불가."""
    fx = _load("imya__conservation_mgmt__conservation_forest/G3_conservation_mgmt_permit_gap.json")
    eff = fx["input"]["effective_far"]
    assert eff["national_far_pct"] is None and eff["national_bcr_pct"] is None  # 현행(조용한 판정불가)
    assert eff["far_basis"] == "zone_unmatched"
    assert fx["current_baseline"]["observed"] is None                          # W1-3: → 표면화 flip
    # ★M3 (b): 허용용도 판정불가는 조례의존(갭 아님) — 이 필드는 W1-3 후에도 유지(무플래그).
    assert fx["input"]["permit"]["verdict"] == "판정불가"
    assert fx["input"]["permit"]["ordinance_dependent"] is True


def test_g3_harness_flip_from_blind():
    """★W1-3 핵심 flip: G3 buggy 시드(보전관리 BCR/FAR 판정불가)에서 harness가 P1 갭 finding을 낸다.

    W0(규칙 0건)에선 blind였던 것이 W1-3 coverage.G3 등록으로 잡힌다. expected=별표 한도존재 마커·
    observed=판정불가·rule_id·tier·panel·field까지 계약을 고정한다. P1은 비차단이라 is_valid True
    유지(제자리 표면화+배지). ★허용용도(조례의존 판정불가)는 갭 미플래그 — coverage.py가 BCR/FAR만
    대조(M3 구분). (변이-kill·zone 단위검증은 test_coverage_gap.)
    """
    from app.services.verification.field_audit.invariants.coverage import _EXPECTED_MARK

    fx = _load("imya__conservation_mgmt__conservation_forest/G3_conservation_mgmt_permit_gap.json")
    report = runner.run(copy.deepcopy(fx["input"]), fx["ctx"])
    f = next(f for f in report.findings if f.code == "G3_ZONE_COVERAGE_GAP")
    assert f.severity == "P1" and f.tier == "A"
    assert f.expected == _EXPECTED_MARK and f.observed == "판정불가"
    assert f.rule_id == "G3_ZONE_COVERAGE_GAP" and f.field == "legal_bcr_far_pct" and f.panel == "법규/공급"
    assert report.is_valid is True                             # P1 — 비차단(배지)
    # 갭 finding은 정확히 1건(허용용도 조례의존 판정불가를 갭으로 오플래그하지 않음 — M3 (b))
    assert sum(1 for x in report.findings if x.code == "G3_ZONE_COVERAGE_GAP") == 1


def test_g6_harness_flip_from_blind():
    """★W3-3 핵심 flip: G6 시드(임야·수집가능 경사도 미획득)에서 harness가 P1 갭 finding을 낸다.

    W0(규칙 0건)·W1~W2에선 blind였던 것이 W3-3 terrain_coverage.TERRAIN_SLOPE_COLLECTION_GAP 등록으로
    잡힌다. expected=수집가능 경사도 획득 마커·observed=미획득(None)·rule_id·tier·panel·field까지 계약을
    고정한다. P1은 비차단이라 is_valid True 유지(제자리 표면화+배지). ★실측필요(임목축적) None은 무플래그
    — 규칙이 경사도 키만 읽는다(수집가능/실측필요 구분). (변이-kill·단위검증은 test_terrain_coverage.)
    """
    from app.services.verification.field_audit.invariants.terrain_coverage import (
        _EXPECTED_MARK,
        _PANEL,
    )

    fx = _load("imya__planning_mgmt__quasi_forest/G6_imya_slope_orphan.json")
    # ★실 shape 대조: 수집가능 경사도(평균경사도_pct)=None인데 실측필요(입목축적_per_ha)는 present
    ff = fx["input"]["special_parcel"]["factors"][0]["forest_facts"]
    assert ff["평균경사도_pct"] is None                    # 수집가능 미획득(현행 — W3-3 표면화 대상)
    assert ff["입목축적_per_ha"] == 110.0                  # 실측필요는 present(갭 아님 — 구분)

    report = runner.run(copy.deepcopy(fx["input"]), fx["ctx"])
    f = next(f for f in report.findings if f.code == "TERRAIN_SLOPE_COLLECTION_GAP")
    assert f.severity == "P1" and f.tier == "A"
    assert f.expected == _EXPECTED_MARK and f.observed == "미획득(None)"
    assert f.rule_id == "TERRAIN_SLOPE_COLLECTION_GAP"
    assert f.field == "special_parcel.forest_facts.평균경사도_pct" and f.panel == _PANEL
    assert report.is_valid is True                          # P1 — 비차단(배지)
    # 갭 finding은 정확히 1건(실측필요 임목축적 None을 갭으로 오플래그하지 않음)
    assert sum(1 for x in report.findings if x.code == "TERRAIN_SLOPE_COLLECTION_GAP") == 1


def test_g6_baseline_slope_collectible_missing():
    """G6 앵커: 임야(준보전산지) 수집가능 경사도(DEM 평균경사도_pct)=None(미획득)을 명시 박제.

    실측필요(임목축적_per_ha)는 present(110.0)라 갭 아님 — current_baseline이 W3-3 근본수집(_fetch_terrain_facts
    DEM 실수집)으로 flip될 대상값을 앵커링한다(수집가능만 갭·실측필요 None 무관).
    """
    fx = _load("imya__planning_mgmt__quasi_forest/G6_imya_slope_orphan.json")
    assert fx["_meta"]["land_attrs"] == {"jimok": "임야", "zone": "계획관리지역", "sanji_gubun": "준보전산지"}
    ff = fx["input"]["special_parcel"]["factors"][0]["forest_facts"]
    assert ff["평균경사도_pct"] is None                    # 현행(수집가능 미획득)
    pa = fx["input"]["special_parcel"]["factors"][0]["preliminary_assessment"]
    assert pa["slope"] is None and "slope_skip_reason" in pa   # 경사도 예비판정 생략(수집가능 미획득)
    assert pa["stocking"] is not None                          # 임목축적 예비판정은 산출(실측필요 present)
    assert fx["current_baseline"]["observed"] is None          # W3-3: → DEM 실수집 flip 대상


def test_g5_regression_lock_robust_stats():
    """★G5 회귀 잠금(정직화·Phase0 W2-c): 실함수 robust_price_stats를 실호출해 log-IQR trim이
    2만원 이상치를 실제로 배제함을 잠근다.

    과거 이 골든은 실함수를 호출하지 않고 fixture가 손으로 적은 필드(robust_price_per_sqm·
    excluded_outliers)만 assert하는 동어반복이라, robust_price_stats가 깨져도 절대 FAIL하지 않는
    거짓 안전이었다. 게다가 과거 fixture의 n=6 표본은 _MIN_SAMPLE_FOR_TRIM=8 미만이라 트림이 아예
    스킵돼(원시 유지) 수치(excluded=[20000]·500000)가 실함수 반환과 모순인 픽션이었다.

    이제 트림 발동 표본(n>=8)으로 실함수를 직접 호출하고, 실제 반환에 대해 잠근다. (변이-kill:
    trim을 무력화하면 2만원이 배제되지 않아 excluded/min/avg 잠금이 FAIL한다.)
    """
    from app.services.data_validation.price_stats import (
        _MIN_SAMPLE_FOR_TRIM,
        robust_price_stats,
    )

    fx = _load("dae__natural_green__na/G5_realtx_iqr_lock.json")
    assert fx["_meta"]["regression_lock"] is True
    rtx = fx["input"]["realtx"]
    samples = rtx["raw_samples_won_per_sqm"]
    expected = rtx["expected_robust_stats"]

    # 트림 발동 표본(n>=8)이어야 log-IQR 잠금이 유효하다 — 실함수 실호출.
    assert len(samples) >= _MIN_SAMPLE_FOR_TRIM, "잠금 표본은 트림 발동(n>=8) 표본이어야 함"
    result = robust_price_stats(samples)

    # ★핵심 잠금: log-IQR trim이 2만원 이상치를 실제로 배제한다(fixture 자기필드가 아니라 실호출 반환).
    assert result["excluded"] == expected["excluded"] == 1     # 이상치 정확히 1건 배제
    assert 20000 not in (result["min"], result["max"])         # 2만원이 대표 양단에서 제거됨
    assert result["min"] == expected["min"]                    # 배제 후 최저(정상값)
    assert result["avg"] == expected["avg"]                    # 배제 후 평균(정상값·실호출 반환)
    assert result["max"] == expected["max"]
    assert result["count"] == expected["count"] == len(samples)  # 원시 유효건수 정직표기

    # 경계 잠금: 같은 함수에 n<8 표본 → 트림 미발동(원시 유지·excluded=0·2만원 잔존).
    below = samples[:6]
    assert len(below) < _MIN_SAMPLE_FOR_TRIM
    r_below = robust_price_stats(below)
    assert r_below["excluded"] == 0                            # 표본 과소 → 트림 스킵(원시 유지)
    assert r_below["min"] == 20000                             # 미발동이라 2만원 유지(임계 경계 반증)
