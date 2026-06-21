"""design_ingest 근거(provenance) 단위테스트 — canonical registry(get_legal_refs) 연동.

전역 원칙: 모든 결과물에 근거 + 필요시 링크. 링크는 레지스트리 단일출처(직접조립 금지).
조례는 sigungu 확정 시에만 verified(링크), 아니면 pending(링크 없음·정직). 추정은 링크 없음.
"""

from app.services.design_ingest.composition import SiteContext
from app.services.design_ingest.provenance import (
    legal_envelope_evidence,
    permit_evidence,
    proposal_evidence,
)


def _ord_site():
    return SiteContext(area_sqm=1000.0, zone_code="2R", legal_bcr_pct=60.0,
                       legal_far_pct=200.0, far_source="ordinance")


def _stat_site():
    return SiteContext(area_sqm=1000.0, zone_code="2R", legal_bcr_pct=60.0,
                       legal_far_pct=200.0, far_source="statutory")


def test_statutory_far_links_to_law_go_kr():
    ev = legal_envelope_evidence(_stat_site())
    far = next(e for e in ev if "연면적" in e.claim)
    assert far.confidence == "statutory" and far.value == 2000.0
    assert "용적률 200.0%" in far.basis
    assert far.link and "law.go.kr" in far.link  # far_law(국토계획법 제78조) verified


def test_ordinance_pending_without_sigungu_verified_with():
    # 조례인데 sigungu 미상 → 링크 없음(pending·정직), confidence는 ordinance
    far = next(e for e in legal_envelope_evidence(_ord_site()) if "연면적" in e.claim)
    assert far.confidence == "ordinance" and far.link is None
    # sigungu 확정 → 자치법규 링크 verified
    far2 = next(e for e in legal_envelope_evidence(_ord_site(), sigungu="서울특별시") if "연면적" in e.claim)
    assert far2.confidence == "ordinance" and far2.link and "law.go.kr" in far2.link


def test_legal_evidence_unknown_when_no_limits():
    ev = legal_envelope_evidence(SiteContext(area_sqm=1000.0))  # 한도 미상
    assert len(ev) == 1 and ev[0].confidence == "unknown" and ev[0].link is None


def test_permit_evidence_rule_and_unknown():
    pe = permit_evidence({"is_permitted": True, "reason": "제2종일반주거지역에서 일반분양 개발 가능"})
    assert pe.confidence == "rule" and pe.value is True
    assert pe.link and "law.go.kr" in pe.link  # zone_use(국토계획법 제76조)
    none = permit_evidence(None)
    assert none.confidence == "unknown" and none.link is None


def test_proposal_evidence_estimates_have_no_link():
    site = _ord_site()
    candidate = {"estimated_gfa_sqm": 1500.0, "estimated_floors": 3,
                 "estimated_units": 13, "estimated_parking": 13, "compliant": True}
    ev = proposal_evidence(candidate, site)
    claims = {e.claim: e for e in ev}
    for key in ("추정 연면적", "추정 세대수", "추정 주차대수"):
        assert claims[key].confidence == "estimated" and claims[key].link is None
    assert "0.75" in claims["추정 세대수"].basis
    # 적합성은 조례 출처 — sigungu 없으면 링크 pending(None), confidence ordinance
    comp = claims["법적 한도 적합성"]
    assert comp.confidence == "ordinance" and comp.link is None
    # sigungu 주면 링크 verified
    comp2 = {e.claim: e for e in proposal_evidence(candidate, site, sigungu="서울특별시")}["법적 한도 적합성"]
    assert comp2.link and "law.go.kr" in comp2.link


def test_evidence_to_dict_shape():
    e = legal_envelope_evidence(_stat_site())[0]
    d = e.to_dict()
    assert set(d.keys()) == {"claim", "value", "basis", "source", "confidence", "link"}
