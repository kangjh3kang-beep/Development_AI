"""AT-1..6 — 산출물: 분류 보존, 근거 강제, 재량 표기, 권고 근거접지, 감사 결속, BLOCKED 격리."""
import pytest

from app.contracts.report import ReportItem, ReportStatus, emit
from app.core.errors import EvidenceMissing
from app.services.report.recommendation import Recommendation
from app.services.report.report_builder import ReportBuilder

_EV = {"basis_article": "건축법 시행령 제119조"}

CONFIRMED_ITEM = {"item_id": "a", "status": "CONFIRMED", "evidence": _EV}
NEEDS_REVIEW_ITEM = {"item_id": "b", "status": "NEEDS_REVIEW", "evidence": _EV}
BLOCKED_ITEM = {"item_id": "c", "status": "BLOCKED", "evidence": _EV}
NO_CRITERION_ITEM = {"item_id": "d", "no_criterion": True, "evidence": {"note": "기준 미존재"}}
NON_COMPLIANT_FAR = {"verdict": "NON_COMPLIANT", "target_variable": "far_floor_area",
                     "basis_article": "국토계획법 시행령"}


def test_classification_preserved():
    r = ReportBuilder().build([CONFIRMED_ITEM, NEEDS_REVIEW_ITEM, BLOCKED_ITEM])
    assert r.section(ReportStatus.NEEDS_REVIEW)
    assert r.section(ReportStatus.BLOCKED)


def test_item_requires_evidence():
    with pytest.raises(EvidenceMissing):
        emit(ReportItem(item_id="x", verdict="FAIL", evidence=None))


def test_discretion_marked():
    r = ReportBuilder().build([NO_CRITERION_ITEM])
    item = r.find("d")
    assert item.status == ReportStatus.DISCRETION_HELD


def test_discretion_does_not_assert_verdict():
    # 재량영역은 단정 금지 — 입력 verdict가 있어도 무효화(INV-30).
    item_in = {"item_id": "e", "no_criterion": True, "verdict": "COMPLIANT", "evidence": {"note": "재량"}}
    r = ReportBuilder().build([item_in])
    assert r.find("e").status == ReportStatus.DISCRETION_HELD
    assert r.find("e").verdict is None


def test_recommendation_grounded():
    rec = Recommendation().make(NON_COMPLIANT_FAR)
    assert rec.basis_article is not None
    assert rec.grounded is True


def test_audit_binding():
    r = ReportBuilder().build([CONFIRMED_ITEM])
    item = r.items[0]
    assert item.snapshot_id and item.model_version and item.input_hash


def test_blocked_not_shown_as_confirmed():
    r = ReportBuilder().build([BLOCKED_ITEM])
    confirmed_ids = [it.item_id for it in r.section(ReportStatus.CONFIRMED)]
    assert "c" not in confirmed_ids
    assert "c" in [it.item_id for it in r.section(ReportStatus.BLOCKED)]


def test_ungrounded_recommendation_held():
    rec = Recommendation().make({"verdict": "NON_COMPLIANT", "target_variable": "x"})
    assert rec.grounded is False
    assert rec.text is None


def test_report_route_builds_and_separates_sections(client):
    resp = client.post("/api/v1/reports/build", json={
        "items": [CONFIRMED_ITEM, BLOCKED_ITEM]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["dashboard"]["section_counts"]["BLOCKED"] == 1
    assert body["dashboard"]["section_counts"]["CONFIRMED"] == 1


def test_report_route_rejects_evidenceless_item(client):
    resp = client.post("/api/v1/reports/build", json={
        "items": [{"item_id": "z", "status": "CONFIRMED", "evidence": None}]})
    assert resp.status_code == 400  # 근거 없는 항목 → 무음 통과 금지(INV-29)
