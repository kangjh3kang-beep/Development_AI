"""아키텍처 문서 계약 — 계층 경계·LLM 비수치 규칙·원장 SSOT가 문서로 명문화됐는지 박제."""
import os

DOC = os.path.join(
    os.path.dirname(__file__), "..", "..", "..",
    "docs", "architecture", "layered-architecture.md",
)

REQUIRED = [
    "## 계층1 — 결정론 분석 코어",
    "## 계층2 — 프로젝트 지식저장소",
    "## 계층3 — 공동경영 멀티에이전트",
    "LLM은 절대 수치를 생성하지 않는다",
    "citation_gate",
    "analysis_ledger",
    "verify_chain",
    "schema_version",       # payload 규약(Task 5.5) 박제
    "prior_context",        # read 계약(Phase 1 전제) 박제
]


def test_architecture_doc_exists_and_covers_layers():
    assert os.path.exists(DOC), f"아키텍처 문서 부재: {DOC}"
    text = open(DOC, encoding="utf-8").read()
    missing = [s for s in REQUIRED if s not in text]
    assert not missing, f"필수 섹션/규칙 누락: {missing}"
