"""AT-1..6 — 유사사례: 충분→통계, 부족→비제시(날조 금지), 출처 강제, 검색 비단정,
소비측 적재분만(라이브 0), 임계 파라미터화."""
import pathlib

import pytest

from app.adapters.vector.qdrant_client import QdrantClientAdapter
from app.contracts.precedent import DecisionType, PrecedentCase, StatStatus, emit
from app.core.errors import SourceMissing
from app.core.parameters import param
from app.services.precedent.corpus_ingest import CorpusIngest
from app.services.precedent.matcher import Matcher
from app.services.precedent.stat_aggregator import StatAggregator
from tools.static_scan import scan_for_numeric_legal_constants

_PRECEDENT_DIR = (
    pathlib.Path(__file__).resolve().parents[2]
    / "apps" / "api" / "app" / "services" / "precedent"
)

RICH = [
    PrecedentCase(case_id=f"c{i}", source=f"의결서-{i}", decision_type=DecisionType.CONDITIONAL,
                  issue_labels=["FAR_DISPUTE"], conditions=["공개공지 확대"])
    for i in range(8)
]
THIN = [PrecedentCase(case_id="r1", source="의결서-r1", decision_type=DecisionType.APPROVED,
                      issue_labels=["RARE"])]


def test_sufficient_corpus_stats():
    s = StatAggregator().aggregate(issue="FAR_DISPUTE", corpus=RICH)
    assert s.distribution
    assert s.common_conditions


def test_thin_data_suppresses_stats():
    s = StatAggregator(threshold=param("precedent_min_cases")).aggregate(issue="RARE", corpus=THIN)
    assert s.status == StatStatus.INSUFFICIENT
    assert s.distribution is None


def test_precedent_requires_source():
    with pytest.raises(SourceMissing):
        emit(PrecedentCase(case_id="x", source=None))


def test_match_is_candidate_not_assertion():
    client = QdrantClientAdapter()
    CorpusIngest(client=client).ingest(RICH)
    m = Matcher(client=client).search("FAR_DISPUTE")[0]
    assert m.similarity is not None
    assert m.is_candidate is True


def test_consumer_reads_ingested_only(spy_network):
    client = QdrantClientAdapter()
    CorpusIngest(client=client).ingest(RICH)
    Matcher(client=client).search("FAR_DISPUTE")
    assert spy_network.live_calls == 0


def test_matcher_excludes_sourceless_match():
    # 적재 게이트를 우회해 출처 없는 포인트가 들어와도 소비 경계에서 제외(INV-23 방어).
    client = QdrantClientAdapter()
    client.upsert(case_id="nosrc", vector=[0.0] * 16, payload={"source": None})
    CorpusIngest(client=client).ingest(RICH)
    matches = Matcher(client=client).search("FAR_DISPUTE")
    assert all(m.source for m in matches)
    assert "nosrc" not in [m.case_id for m in matches]


def test_maturity_threshold_parameterized():
    offenders = {}
    for py in _PRECEDENT_DIR.rglob("*.py"):
        hits = scan_for_numeric_legal_constants(py.read_text(encoding="utf-8"))
        if hits:
            offenders[py.name] = hits
    assert offenders == {}
