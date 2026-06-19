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


def test_overall_status_blocked_governs():
    # ★대량필지 'most-constrained governs' 차용 — BLOCKED 1건이면 전체 BLOCKED(CONFIRMED에 묻힘=구조적 할루시네이션 차단).
    r = ReportBuilder().build([CONFIRMED_ITEM, NEEDS_REVIEW_ITEM, BLOCKED_ITEM])
    assert r.overall_status == ReportStatus.BLOCKED


def test_overall_status_worst_of_ranking():
    assert ReportBuilder().build([CONFIRMED_ITEM, NEEDS_REVIEW_ITEM]).overall_status == ReportStatus.NEEDS_REVIEW
    assert ReportBuilder().build([CONFIRMED_ITEM]).overall_status == ReportStatus.CONFIRMED
    # 재량 보류(기준 미존재)는 NEEDS_REVIEW보다 낮은 심각도 — NEEDS_REVIEW 있으면 우선.
    assert ReportBuilder().build([NO_CRITERION_ITEM, NEEDS_REVIEW_ITEM]).overall_status == ReportStatus.NEEDS_REVIEW
    assert ReportBuilder().build([CONFIRMED_ITEM, NO_CRITERION_ITEM]).overall_status == ReportStatus.DISCRETION_HELD


def test_overall_status_none_when_empty():
    assert ReportBuilder().build([]).overall_status is None  # 항목 없음 → 요약 불가(정직 None)


def test_overall_status_serialized_for_consumers():
    # 소비자(BFF shadow·프런트)가 JSON으로 집계 신호를 받도록 직렬화 포함(구획 sections도 보존).
    r = ReportBuilder().build([CONFIRMED_ITEM, BLOCKED_ITEM])
    assert r.model_dump(mode="json")["overall_status"] == "BLOCKED"
    assert "BLOCKED" in r.model_dump(mode="json")["sections"]  # 은폐 아님 — 구획 그대로(INV-28)


def test_report_route_builds_and_separates_sections(client):
    resp = client.post("/api/v1/reports/build", json={
        "items": [CONFIRMED_ITEM, BLOCKED_ITEM]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["dashboard"]["section_counts"]["BLOCKED"] == 1
    assert body["dashboard"]["section_counts"]["CONFIRMED"] == 1
    assert body["dashboard"]["overall_status"] == "BLOCKED"  # 집계 신호 노출(BLOCKED 1건이 전체 좌우)


def test_report_route_rejects_evidenceless_item(client):
    resp = client.post("/api/v1/reports/build", json={
        "items": [{"item_id": "z", "status": "CONFIRMED", "evidence": None}]})
    assert resp.status_code == 400  # 근거 없는 항목 → 무음 통과 금지(INV-29)
