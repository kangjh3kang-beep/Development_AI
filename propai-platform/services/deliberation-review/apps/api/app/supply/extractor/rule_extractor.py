"""R2 — 룰 추출. 문서 prose -> 정량 술어/정성 루브릭 후보(status=DRAFT).

LLM 보조이나 출력은 '후보'일 뿐. 자동 활성 절대 금지(INV-14) — HITL 승인 전 분석 사용 불가.
공급측 전용(소비 경로 아님). 결정론 mock 추출.
"""
from __future__ import annotations

from app.contracts.rule_candidate import CandidateStatus, RuleCandidate


class RuleExtractor:
    def extract(self, doc: dict) -> RuleCandidate:
        return RuleCandidate(
            candidate_id=f"cand-{doc.get('doc_id', 'x')}",
            status=CandidateStatus.DRAFT,  # 항상 DRAFT — 활성화는 HITL만.
            target_variable=doc.get("target_variable"),
            content=doc.get("content", {}),
            source_doc_id=doc.get("doc_id"),
            confidence=doc.get("confidence", 0.5),
            jurisdiction=doc.get("jurisdiction"),
        )
