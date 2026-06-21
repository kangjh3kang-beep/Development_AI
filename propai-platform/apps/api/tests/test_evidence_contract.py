"""근거·법령링크 공용 계약(전역정책 Phase0) 테스트 — build_evidence_block.

검증 범위:
- evidence[]: 호출부 트레이스 정규화(label 필수·basis None 허용·legal_ref_key 통과).
- legal_refs[]: URL은 레지스트리(get_legal_refs) 출력과 정확히 일치(직접 조립 0).
- url_status='pending' 정직 표기(조례 sigungu 미상).
- provenance[]: 등록 소스만 상태 집계, 미등록은 registered=False(가짜 신선도 금지).
- trust: TrustResult.to_dict() / dict 모두 직렬화, None은 None.
- graceful: 빈 입력·이상 입력에서 빈 배열/None(예외 전파 0).

순수 빌더를 직접 호출해 외부 API/네트워크 없이 결정론 검증한다.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.services.data_validation.evidence_contract import (  # noqa: E402
    build_evidence_block,
    build_legal_refs,
    build_provenance,
)
from app.services.legal.legal_reference_registry import get_legal_refs  # noqa: E402
from app.services.data_validation.trust import Signal, cross_validate  # noqa: E402


class TestEvidenceNormalization:
    """evidence[] 정규화 — label 필수, basis/legal_ref_key 통과."""

    def test_label_required_filters_empty(self):
        block = build_evidence_block(items=[
            {"label": "법정 용적률 상한", "value": "250%", "basis": "제2종"},
            {"label": "", "value": "x"},            # label 없음 → 제외
            {"value": "no label"},                  # label 키 없음 → 제외
            "not a dict",                           # 비dict → 제외
        ])
        ev = block["evidence"]
        assert len(ev) == 1
        assert ev[0]["label"] == "법정 용적률 상한"
        assert ev[0]["value"] == "250%"
        assert ev[0]["basis"] == "제2종"

    def test_legal_ref_key_passthrough_and_basis_none(self):
        block = build_evidence_block(items=[
            {"label": "세금 — 취득세", "value": "1,000원", "legal_ref_key": "acquisition_tax"},
            {"label": "총사업비", "value": "5억원"},  # basis 없음 → None
        ])
        ev = block["evidence"]
        assert ev[0]["legal_ref_key"] == "acquisition_tax"
        assert ev[1]["basis"] is None
        assert "legal_ref_key" not in ev[1]


class TestLegalRefsFromRegistryOnly:
    """legal_refs[] URL은 레지스트리(get_legal_refs)와 동치 — 직접 조립 금지."""

    def test_url_equals_registry(self):
        keys = ["far_limit", "bcr_limit", "acquisition_tax"]
        refs = build_legal_refs(keys)
        expected = get_legal_refs(keys)
        assert refs == expected, "build_legal_refs는 get_legal_refs 출력을 그대로 통과해야 한다"
        for r in refs:
            assert r["url"] == "" or r["url"].startswith("https://www.law.go.kr")
            assert r["url_status"] in {"verified", "pending"}

    def test_block_legal_refs_match_registry(self):
        block = build_evidence_block(legal_ref_keys=["housing_price_cap"])
        expected = get_legal_refs(["housing_price_cap"])
        assert block["legal_refs"] == expected

    def test_empty_keys_returns_empty(self):
        assert build_legal_refs([]) == []
        assert build_legal_refs(None) == []
        assert build_evidence_block()["legal_refs"] == []

    def test_ordinance_sigungu_substitution(self):
        with_sgg = build_legal_refs(["ordinance_far"], sigungu="해운대구")[0]
        assert "해운대구" in with_sgg["law_name"]
        assert with_sgg["url_status"] == "verified"
        assert with_sgg["url"].startswith("https://www.law.go.kr")
        assert with_sgg["url"] == get_legal_refs(["ordinance_far"], sigungu="해운대구")[0]["url"]

    def test_ordinance_pending_when_no_sigungu(self):
        without = build_legal_refs(["ordinance_far"])[0]
        assert without["url"] == ""
        assert without["url_status"] == "pending"  # 가짜 링크 대신 정직 pending


class TestProvenance:
    """provenance[] — 등록 소스 상태 집계, 미등록은 정직 표기."""

    def test_registered_source_status(self):
        prov = build_provenance(["molit_transactions"])
        assert len(prov) == 1
        assert prov[0]["name"] == "molit_transactions"
        assert prov[0]["source_type"] == "api"
        assert "is_healthy" in prov[0]

    def test_unregistered_source_marked(self):
        prov = build_provenance(["does_not_exist_source"])
        assert prov[0]["registered"] is False
        assert prov[0]["source_type"] == "unknown"

    def test_empty_sources_returns_empty(self):
        assert build_provenance([]) == []
        assert build_provenance(None) == []


class TestTrustSerialization:
    """trust 직렬화 — TrustResult/.dict/None."""

    def test_trust_result_object(self):
        signals = [
            Signal("동_실거래", 2799, sample_size=361, source="live", weight=1.3),
            Signal("시군구_실거래", 3228, sample_size=3326, source="live", weight=1.0),
        ]
        tr = cross_validate(signals, anchor="동_실거래", plausible_min=300, plausible_max=20000)
        block = build_evidence_block(trust=tr)
        assert isinstance(block["trust"], dict)
        assert block["trust"]["verdict"] in {"pass", "warn", "fail"}
        assert "confidence" in block["trust"]

    def test_trust_dict_passthrough(self):
        block = build_evidence_block(trust={"verdict": "pass", "confidence": 0.9})
        assert block["trust"] == {"verdict": "pass", "confidence": 0.9}

    def test_trust_none(self):
        assert build_evidence_block()["trust"] is None


class TestGracefulAndShape:
    """전체 형태·graceful — 항상 4키, 예외 전파 0."""

    def test_block_always_has_four_keys(self):
        block = build_evidence_block()
        assert set(block.keys()) == {"evidence", "legal_refs", "provenance", "trust"}
        assert block["evidence"] == []
        assert block["legal_refs"] == []
        assert block["provenance"] == []
        assert block["trust"] is None

    def test_full_block_integration(self):
        block = build_evidence_block(
            items=[{"label": "법정 용적률 상한", "value": "250%", "legal_ref_key": "far_limit"}],
            legal_ref_keys=["far_limit"],
            sources=["vworld_zoning"],
            trust={"verdict": "pass"},
        )
        assert block["evidence"][0]["legal_ref_key"] == "far_limit"
        assert block["legal_refs"][0]["key"] == "far_limit"
        # evidence의 legal_ref_key가 legal_refs의 key와 조인 가능(프론트 adaptEvidence 전제).
        ev_key = block["evidence"][0]["legal_ref_key"]
        ref_keys = {r["key"] for r in block["legal_refs"]}
        assert ev_key in ref_keys
        assert block["provenance"][0]["name"] == "vworld_zoning"

    def test_malformed_items_do_not_raise(self):
        # items가 dict가 아닌 잡다한 입력이어도 빈 evidence(예외 전파 0).
        block = build_evidence_block(items=[None, 123, "x", {"no_label": 1}])
        assert block["evidence"] == []
