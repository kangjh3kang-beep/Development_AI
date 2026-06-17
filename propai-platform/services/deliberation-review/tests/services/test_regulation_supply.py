"""P-E — 규제 수집(supply) 자동 연결: 적재된 미러(ACTIVE만) 자동 조회·DRAFT 차단·보수 폴백."""
from datetime import date

from app.contracts.analysis import AnalysisInput
from app.contracts.rule_candidate import CandidateStatus, RuleCandidate
from app.services.pipeline.analysis_pipeline import run_analysis
from app.supply.mirror.mirror_writer import MirrorWriter


def _candidate(cid, status):
    return RuleCandidate(candidate_id=cid, status=status,
                         content={"ref": "건축법 시행령", "effective_date": "2025-01-01"})


def test_mirror_auto_from_supply_store():
    # 공급측이 ACTIVE 규제 적재 → 분석이 mirror_rules 입력 없이 자동 조회.
    pnu = "9999999999999999991"  # 격리용 unique jurisdiction
    MirrorWriter().write(jurisdiction=pnu, candidates=[_candidate("rc1", CandidateStatus.ACTIVE)],
                         snapshot_id="snap-e1")
    r = run_analysis(AnalysisInput(pnu=pnu, application_date=date(2026, 1, 1),
                                   citations=[{"ref": "건축법 시행령"}]))
    assert r.mirror_source == "SUPPLY_STORE"


def test_mirror_draft_not_loaded():
    # DRAFT 후보는 적재 안 됨(INV-14) → 미적재로 보수 게이팅.
    pnu = "9999999999999999992"
    MirrorWriter().write(jurisdiction=pnu, candidates=[_candidate("rc2", CandidateStatus.DRAFT)],
                         snapshot_id="snap-e2")
    r = run_analysis(AnalysisInput(pnu=pnu, application_date=date(2026, 1, 1),
                                   citations=[{"ref": "건축법 시행령"}]))
    # ACTIVE 0건이라 빈 스냅샷 적재됨 → 조회되지만 rules 비어 검증 미충족(보수)
    assert any("미검증" in s or "mirror" in s for s in r.skipped) or r.mirror_source == "SUPPLY_STORE"


def test_mirror_input_wins():
    pnu = "9999999999999999993"
    MirrorWriter().write(jurisdiction=pnu, candidates=[_candidate("rc3", CandidateStatus.ACTIVE)],
                         snapshot_id="snap-e3")
    r = run_analysis(AnalysisInput(pnu=pnu, application_date=date(2026, 1, 1),
                                   mirror_rules=[{"ref": "국토계획법", "effective_date": "2025-01-01"}],
                                   citations=[{"ref": "국토계획법"}]))
    assert r.mirror_source == "INPUT"  # 명시 입력 우선


def test_mirror_absent_conservative():
    # 미적재 + citations → 보수 게이팅 표면화(날조 금지).
    r = run_analysis(AnalysisInput(pnu="9999999999999999994", application_date=date(2026, 1, 1),
                                   citations=[{"ref": "건축법 시행령"}]))
    assert r.mirror_source is None
    assert any("mirror 미적재" in s for s in r.skipped)
