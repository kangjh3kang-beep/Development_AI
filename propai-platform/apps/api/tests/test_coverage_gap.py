"""G3 관리지역 BCR/FAR 커버리지 갭 — coverage.py 불변식 + 근본봉합(ZONE_LIMITS) 단위검증(W1-3).

라이브 analyze() 미수집(하네스 환경 DB/API 부재)이므로, 불변식 pure fn과 BCR/FAR 룩업
(legal_limits_for←ZONE_LIMITS)·permit_validator 순수로직을 직접 호출해 근본수정을 실증한다:
  (a) 근본봉합: 관리지역(계획 40/100·생산/보전 20/80) BCR/FAR가 별표 한도로 산출 + 기존 zone 무회귀
  (b) coverage.py: 별표 한도 zone인데 BCR/FAR 판정불가면 P1 갭 finding·산출되면 무발동
  (c) ★M3 구분: 보전관리 BCR/FAR=산출(갭 해소) BUT 허용용도=정직 조례의존 판정불가(갭 아님) 동시 성립
  (d) ★변이-kill: 관리지역을 룩업(ZONE_LIMITS)에서 제거→legal_limits_for None(판정불가)→coverage G3 재발
  (e) 오탐 방지: 비표준 zone(개발제한구역)·BCR/FAR 무관 payload는 무발동
"""

import pytest

from app.services.feasibility.permit_validator import check_permit_feasibility
from app.services.verification.field_audit.invariants import coverage
from app.services.verification.field_audit.invariants.coverage import (
    _EXPECTED_MARK,
    _g3_zone_coverage_gap,
)
from app.services.zoning.legal_zone_limits import legal_limits_for


def _eff(bcr, far):
    """실 analyze() effective_far shape(national_*=법정 표시값). None=판정불가."""
    return {"national_bcr_pct": bcr, "national_far_pct": far}


# ────────────────────────────────────────────────────────────────────────────
# (a) 근본봉합 — BCR/FAR 룩업이 관리지역 별표 한도 산출 + 기존 zone 무회귀(전역 스윕)
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("zone,bcr,far", [
    # 관리지역 별표 한도(국토계획법 시행령 §84·85) — 근본봉합(ZONE_LIMITS 등재, 2026-06 M-7)
    ("계획관리지역", 40, 100),
    ("생산관리지역", 20, 80),
    ("보전관리지역", 20, 80),
    # ★무회귀: 기존 용도지역(주거/상업/녹지)의 별표값은 관리지역 등재에 영향받지 않는다
    ("자연녹지지역", 20, 100),
    ("보전녹지지역", 20, 80),
    ("제2종일반주거지역", 60, 250),
    ("일반상업지역", 80, 1300),
    ("농림지역", 20, 80),
])
def test_root_fix_zone_limits_registers_statutory_bcrfar(zone, bcr, far):
    """BCR/FAR 룩업(legal_limits_for←ZONE_LIMITS)이 관리지역 별표 한도를 산출하고 기존 zone은 무회귀."""
    lim = legal_limits_for(zone)
    assert lim is not None
    assert lim["max_bcr_pct"] == bcr and lim["max_far_pct"] == far


# ────────────────────────────────────────────────────────────────────────────
# (b) coverage.py 불변식 — 판정불가면 갭 finding·산출되면 무발동
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("zone", ["계획관리지역", "생산관리지역", "보전관리지역"])
def test_mgmt_zone_bcrfar_undetermined_fires_gap(zone):
    """별표 한도 명확한 관리지역인데 BCR/FAR가 판정불가(null) → P1 커버리지 갭 finding."""
    findings = _g3_zone_coverage_gap(
        {"zone_type": zone, "effective_far": {**_eff(None, None), "far_basis": "zone_unmatched"}},
        {"zone_type": zone},
    )
    assert len(findings) == 1
    f = findings[0]
    assert f.code == "G3_ZONE_COVERAGE_GAP" and f.severity == "P1" and f.tier == "A"
    assert f.panel == "법규/공급" and f.field == "legal_bcr_far_pct"
    assert f.expected == _EXPECTED_MARK and f.observed == "판정불가"
    assert zone in (f.note or "")


@pytest.mark.parametrize("zone,bcr,far", [
    ("계획관리지역", 40, 100), ("생산관리지역", 20, 80), ("보전관리지역", 20, 80),
    # 무회귀: 기존 zone도 산출되면 무발동
    ("제2종일반주거지역", 60, 250), ("일반상업지역", 80, 1300), ("자연녹지지역", 20, 100),
])
def test_bcrfar_present_no_gap(zone, bcr, far):
    """BCR/FAR가 산출(별표 한도 반영)되면 갭 무발동 — 근본봉합 후 정상 경로(전역 무회귀)."""
    assert _g3_zone_coverage_gap(
        {"zone_type": zone, "effective_far": _eff(bcr, far)}, {"zone_type": zone}
    ) == []


def test_partial_bcrfar_present_no_gap():
    """건폐율만 산출돼도(용적률 null) '하나라도 산출'이면 무발동 — 갭은 둘 다 판정불가일 때만."""
    assert _g3_zone_coverage_gap(
        {"zone_type": "보전관리지역", "effective_far": _eff(20, None)}, {"zone_type": "보전관리지역"}
    ) == []


# ────────────────────────────────────────────────────────────────────────────
# (c) ★M3 실증 — BCR/FAR=산출(갭 해소) BUT 허용용도=정직 조례의존 판정불가(갭 아님)
# ────────────────────────────────────────────────────────────────────────────


def test_m3_conservation_bcrfar_computed_but_permit_ordinance_dependent():
    """★M3 핵심: 보전관리 BCR/FAR=산출(별표 20/80, 갭 해소) BUT 허용용도=정직 판정불가(조례의존, 갭 아님)."""
    zone = "보전관리지역"

    # (a) BCR/FAR 커버리지 갭 해소: 룩업 등재로 별표 20/80 산출 → coverage 무발동
    lim = legal_limits_for(zone)
    assert lim["max_bcr_pct"] == 20 and lim["max_far_pct"] == 80
    assert _g3_zone_coverage_gap(
        {"zone_type": zone, "effective_far": _eff(20, 80)}, {"zone_type": zone}
    ) == []

    # (b) 허용용도는 본질적 조례의존 판정불가(억지 산출 금지) — 근거명시
    r = check_permit_feasibility("M06", zone)
    assert r["zone_known"] is False and r["is_permitted"] is False
    assert "조례" in r["reason"] and "개별심의" in r["reason"] and "판정불가" in r["reason"]

    # (c) coverage.py는 허용용도(permit)를 건드리지 않는다 — permit만 있는 payload엔 갭 무발동
    #     (조용한 판정불가와 정직한 조례의존 판정불가를 구분: BCR/FAR만 대조).
    assert _g3_zone_coverage_gap({"zone_type": zone, "permit": r}, {"zone_type": zone}) == []


def test_permit_reason_mgmt_zones_are_ordinance_dependent():
    """관리지역 허용용도 판정불가 사유가 '조례·개별심의'를 명시(M3 (b) — 커버리지 갭 프레이밍 아님)."""
    for z in ("보전관리지역", "생산관리지역", "계획관리지역"):
        r = check_permit_feasibility("M06", z)
        assert r["zone_known"] is False
        assert "도시계획조례" in r["reason"] and "개별심의" in r["reason"] and "판정불가" in r["reason"]


def test_permit_reason_registered_zone_unchanged():
    """등재 zone(제2종주거)은 기존 판정 유지(무회귀 — 허용용도 프레이밍 변경 없음)."""
    r = check_permit_feasibility("M06", "제2종일반주거지역")
    assert r["zone_known"] is True and r["is_permitted"] is True


def test_permit_reason_other_unregistered_zone_generic():
    """관리지역 아닌 미등재 zone(개발제한구역)은 기존 일반 판정불가 메시지 유지(스코프 최소)."""
    r = check_permit_feasibility("M06", "개발제한구역")
    assert r["zone_known"] is False and "매트릭스 미등재" in r["reason"]


# ────────────────────────────────────────────────────────────────────────────
# (d) ★변이-kill — 관리지역을 룩업에서 제거 → 판정불가 복귀 → coverage G3 재발
# ────────────────────────────────────────────────────────────────────────────


def _payload_from_lookup(zone):
    """BCR/FAR 룩업(legal_limits_for) 결과로 effective_far payload 구성. 미매칭이면 national_*=None."""
    lim = legal_limits_for(zone) or {}
    return {
        "zone_type": zone,
        "effective_far": _eff(lim.get("max_bcr_pct"), lim.get("max_far_pct")),
    }


def test_mutation_removing_mgmt_zone_reverts_bcrfar_and_recurs_gap(monkeypatch):
    """★변이-kill: BCR/FAR 룩업(ZONE_LIMITS)에서 보전관리를 제거하면 legal_limits_for가 판정불가(None)로
    복귀하고, 그 판정불가 payload에서 coverage.py G3 finding이 재발한다.

    골든 flip이 룩업 등재(ZONE_LIMITS)에 **실제로 의존**함을 증명(가드가 죽는지 확인). 독립 오라클
    (_STATUTORY_LIMIT_ZONES)은 ZONE_LIMITS 비의존이라 제거 후에도 '보전관리는 별표 한도 표준 zone'을
    계속 알아 갭을 적발한다.
    """
    from app.services.zoning import legal_zone_limits as lzl

    zone = "보전관리지역"
    ctx = {"zone_type": zone}

    # 기준선(등재): 별표 20/80 산출 → payload BCR/FAR 산출 → coverage 무발동
    assert legal_limits_for(zone)["max_far_pct"] == 80
    assert _g3_zone_coverage_gap(_payload_from_lookup(zone), ctx) == []

    # 변이: BCR/FAR 룩업에서 보전관리 제거(legal_zone_limits가 참조하는 ZONE_LIMITS 바인딩 교체)
    mutated = {k: v for k, v in lzl.ZONE_LIMITS.items() if k != zone}
    monkeypatch.setattr(lzl, "ZONE_LIMITS", mutated)
    assert lzl.legal_limits_for(zone) is None  # BCR/FAR 판정불가 복귀(등재 의존 증명)

    # 판정불가 payload 재구성 → coverage.py G3 finding 재발(가드 실재)
    findings = _g3_zone_coverage_gap(_payload_from_lookup(zone), ctx)
    assert len(findings) == 1 and findings[0].code == "G3_ZONE_COVERAGE_GAP"


# ────────────────────────────────────────────────────────────────────────────
# (e) 오탐 방지 — 비표준 zone·BCR/FAR 무관 payload·경로 비의존
# ────────────────────────────────────────────────────────────────────────────


def test_non_statutory_zone_undetermined_is_not_gap():
    """개발제한구역 등 비표준 용도지역은 별표 한도가 없어 판정불가여도 갭 아님(오탐 방지)."""
    assert _g3_zone_coverage_gap(
        {"zone_type": "개발제한구역", "effective_far": {**_eff(None, None), "far_basis": "zone_unmatched"}},
        {"zone_type": "개발제한구역"},
    ) == []


def test_no_bcrfar_container_no_gap():
    """BCR/FAR 컨테이너가 아예 없으면(규제·학교만) 무발동 — 다른 결함 fixture(G1 규제·G2 학교) 오탐 방지."""
    assert _g3_zone_coverage_gap(
        {"zone_type": "보전관리지역", "regulations": ["보전산지"], "poi": {"schools": []}},
        {"zone_type": "보전관리지역"},
    ) == []


def test_path_independent_shapes_detect_gap():
    """실 analyze(effective_far)·정산(legal_limits)·컨테이너 내 zone_type 모두에서 판정불가를 잡는다."""
    z = "생산관리지역"
    ctx = {"zone_type": z}
    # effective_far shape(실 analyze)
    assert len(_g3_zone_coverage_gap({"zone_type": z, "effective_far": _eff(None, None)}, ctx)) == 1
    # legal_limits shape(정산/그라운딩)
    assert len(_g3_zone_coverage_gap({"zone_type": z, "legal_limits": {"far_pct": None, "bcr_pct": None}}, ctx)) == 1
    # ctx 없이 컨테이너 내부 zone_type로 추출
    assert len(_g3_zone_coverage_gap({"legal_limits": {"zone_type": z, "far_pct": None, "bcr_pct": None}}, {})) == 1
    # 산출되면 무발동
    assert _g3_zone_coverage_gap({"zone_type": z, "legal_limits": {"far_pct": 80, "bcr_pct": 20}}, ctx) == []


# ────────────────────────────────────────────────────────────────────────────
# (f) 독립 오라클 계약 — 변이-kill 성립 조건
# ────────────────────────────────────────────────────────────────────────────


def test_statutory_oracle_is_independent_and_complete():
    """오라클 = 국토계획법 21 용도지역(관리지역 포함)·비용도지역(보호구역) 미포함(ZONE_LIMITS 비의존)."""
    z = coverage._STATUTORY_LIMIT_ZONES
    assert len(z) == 21
    for m in ("보전관리지역", "생산관리지역", "계획관리지역"):
        assert m in z
    assert "개발제한구역" not in z and "통제보호구역" not in z
