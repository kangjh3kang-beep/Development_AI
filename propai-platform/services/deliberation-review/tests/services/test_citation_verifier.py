"""AT-4 — 인용검증은 미러 대조(분석경로 라이브호출 0)."""
from app.contracts.mirror import MirrorSnapshot
from app.services.verify.citation_verifier import CitationVerifier

SNAP = MirrorSnapshot(
    snapshot_id="snap-1", jurisdiction="1111011111",
    rules=[{"ref": "건축법 시행령 제119조"}])


def test_citation_verify_uses_mirror_not_live(spy_network):
    result = CitationVerifier().verify({"ref": "건축법 시행령 제119조"}, snapshot=SNAP)
    assert result.matched is True
    assert result.method == "MIRROR"
    assert spy_network.live_calls == 0


def test_citation_unmatched_is_explicit(spy_network):
    result = CitationVerifier().verify({"ref": "존재하지않는조문"}, snapshot=SNAP)
    assert result.matched is False
    assert spy_network.live_calls == 0
