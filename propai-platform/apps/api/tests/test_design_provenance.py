"""design_ingest 근거(provenance) 단위테스트 — 출처·신뢰도·링크·추정표기 검증.

전역 원칙: 모든 결과물에 근거 + 필요시 링크. 추정은 estimated·링크 없음(정직).
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


def test_legal_evidence_ordinance_has_elis_link():
    ev = legal_envelope_evidence(_ord_site())
    far = next(e for e in ev if "연면적" in e.claim)
    assert far.confidence == "ordinance"
    assert far.value == 2000.0 and "용적률 200.0%" in far.basis
    assert far.link and "elis.go.kr" in far.link  # 자치법규정보시스템


def test_legal_evidence_statutory_has_law_link():
    ev = legal_envelope_evidence(_stat_site())
    far = next(e for e in ev if "연면적" in e.claim)
    assert far.confidence == "statutory"
    assert far.link and "law.go.kr" in far.link


def test_legal_evidence_unknown_when_no_limits():
    ev = legal_envelope_evidence(SiteContext(area_sqm=1000.0))  # 한도 미상
    assert len(ev) == 1 and ev[0].confidence == "unknown" and ev[0].link is None


def test_permit_evidence_rule_and_unknown():
    pe = permit_evidence({"is_permitted": True, "reason": "제2종일반주거지역에서 일반분양 개발 가능"})
    assert pe.confidence == "rule" and pe.value is True
    assert pe.link and "law.go.kr" in pe.link
    # permit 없음 → 미확인(정직, 링크 없음)
    none = permit_evidence(None)
    assert none.confidence == "unknown" and none.link is None


def test_proposal_evidence_estimates_have_no_link():
    site = _ord_site()
    candidate = {"estimated_gfa_sqm": 1500.0, "estimated_floors": 3,
                 "estimated_units": 13, "estimated_parking": 13, "compliant": True}
    ev = proposal_evidence(candidate, site)
    claims = {e.claim: e for e in ev}
    # 추정값은 confidence=estimated + 링크 없음(정직 표기)
    for key in ("추정 연면적", "추정 세대수", "추정 주차대수"):
        assert claims[key].confidence == "estimated" and claims[key].link is None
    assert "0.75" in claims["추정 세대수"].basis  # 전용률 근거 명시
    # 적합성은 법적 한도 출처(조례) 연동 + 링크
    comp = claims["법적 한도 적합성"]
    assert comp.confidence == "ordinance" and comp.link and "elis.go.kr" in comp.link


def test_evidence_to_dict_shape():
    e = legal_envelope_evidence(_ord_site())[0]
    d = e.to_dict()
    assert set(d.keys()) == {"claim", "value", "basis", "source", "confidence", "link"}
