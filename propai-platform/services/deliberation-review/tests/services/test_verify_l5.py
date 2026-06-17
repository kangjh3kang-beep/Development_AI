"""AT-1..8 — 검증 계층: 인용 차단(없음/시행일), 이중경로 보류, 무근거 제거, 최종 게이팅,
미러 라이브0, 정합 잡 분리, 임계 파라미터화."""
import pathlib
from datetime import date

from app.contracts.enums import RecordStatus
from app.contracts.mirror import MirrorSnapshot
from app.contracts.verification import FinalStatus, GateItem
from app.core.parameters import param
from app.services.verify.citation_check import CitationCheck
from app.services.verify.claim_evidence import ClaimEvidence
from app.services.verify.dual_path_check import DualPathCheck
from app.services.verify.final_gate import FinalGate
from app.services.verify.reconcile_job import ReconcileJob
from tools.static_scan import scan_for_numeric_legal_constants

_VERIFY_DIR = pathlib.Path(__file__).resolve().parents[2] / "apps" / "api" / "app" / "services" / "verify"

SNAP = MirrorSnapshot(
    snapshot_id="snap-1", jurisdiction="1111011111",
    rules=[{"ref": "건축법 시행령 제119조", "effective_date": "2025-01-01", "content": "산정"}])

FABRICATED_CITATION = {"ref": "없는조문 제999조"}
CITATION_WRONG_EFFECTIVE_DATE = {"ref": "건축법 시행령 제119조", "effective_date": "2020-01-01"}
VALID_CITATION = {"ref": "건축법 시행령 제119조"}


def test_invalid_citation_blocked():
    r = CitationCheck().verify(FABRICATED_CITATION, snapshot=SNAP)
    assert r.passed is False
    gated = FinalGate().apply(GateItem(composite_confidence=0.9, verification=r))
    assert gated.status == FinalStatus.BLOCKED


def test_outdated_citation_blocked():
    r = CitationCheck().verify(CITATION_WRONG_EFFECTIVE_DATE, snapshot=SNAP, base_date=date(2026, 1, 1))
    assert r.passed is False


def test_dual_path_mismatch_holds():
    r = DualPathCheck(tol=param("area_tol")).check(table=500, geom=455)
    assert r.status == RecordStatus.HELD


def test_unsupported_claim_removed():
    finding = {"claims": [
        {"text": "SUPPORTED", "evidence_refs": ["건축법 시행령 제119조"]},
        {"text": "UNSUPPORTED", "evidence_refs": []},
    ]}
    out = ClaimEvidence().enforce(finding)
    assert "UNSUPPORTED" not in out.claims
    assert "SUPPORTED" in out.claims


def test_final_gate_separates_unconfirmed():
    low_conf_unverified = GateItem(composite_confidence=0.3, verification=None)
    f = FinalGate(threshold=param("finding_confidence_threshold")).apply(low_conf_unverified)
    assert f.status in (FinalStatus.NEEDS_REVIEW, FinalStatus.BLOCKED)
    assert f.status != FinalStatus.CONFIRMED


def test_final_gate_confirms_verified_high_conf():
    r = CitationCheck().verify(VALID_CITATION, snapshot=SNAP)
    item = GateItem(composite_confidence=0.95, verification=r)
    assert FinalGate().apply(item).status == FinalStatus.CONFIRMED


def test_dual_path_held_forces_review():
    # 정량 이중경로 HELD는 인용·신뢰도가 양호해도 CONFIRMED 금지(무음 오판 0, 감사 D절).
    r = CitationCheck().verify(VALID_CITATION, snapshot=SNAP)
    held = DualPathCheck(tol=param("area_tol")).check(table=500, geom=455).status.value
    item = GateItem(composite_confidence=0.95, verification=r, dual_path_status=held)
    assert FinalGate().apply(item).status == FinalStatus.NEEDS_REVIEW


def test_citation_uses_mirror(spy_network):
    CitationCheck().verify(VALID_CITATION, snapshot=SNAP)
    assert spy_network.live_calls == 0


def test_reconcile_is_offline_job():
    assert ReconcileJob.is_async is True
    assert ReconcileJob.in_analysis_path is False


def test_gate_thresholds_parameterized():
    offenders = {}
    for py in _VERIFY_DIR.rglob("*.py"):
        hits = scan_for_numeric_legal_constants(py.read_text(encoding="utf-8"))
        if hits:
            offenders[py.name] = hits
    assert offenders == {}
