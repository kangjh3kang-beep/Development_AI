"""AT-2 — LLM/자동 추출 룰은 HITL 승인 전 비활성(분석 사용 금지, INV-14)."""
from app.consume.ruleset_reader import RulesetReader
from app.contracts.rule_candidate import CandidateStatus
from app.supply.extractor.rule_extractor import RuleExtractor
from app.supply.mirror.mirror_store import MirrorStore

DOC = {"doc_id": "d-101", "target_variable": "far_limit", "content": {"ref": "x"}}


def test_candidate_inactive_until_hitl():
    c = RuleExtractor().extract(DOC)
    assert c.status == CandidateStatus.DRAFT
    reader = RulesetReader(store=MirrorStore(), enqueue=lambda job: None)
    assert reader.is_active(c.candidate_id) is False
