"""LAW1 — 참조법령 확충(전수조사 갭) + 끊긴 근거링크 복구 회귀.

부동산개발·건축 핵심 법규(집합건물법 등)가 사전에 수록·해소되고 1차출처 링크를 동반하는지(설명가능성 표준),
skyline basis_article의 끊긴 링크가 복구됐는지 검증.
"""
import pytest

from app.services.explain.legal_refs import resolve, resolve_text

# 사용자 지목 + 전수조사 missing_high 핵심 법규
_REQUIRED = [
    "집합건물법", "주택법", "공동주택관리법", "도시개발법", "소규모주택정비법",
    "환경영향평가법", "교통영향평가", "재해영향평가", "소방시설법",
    "감정평가법", "공시지가법", "개발이익환수법", "농지법", "산지관리법",
    "문화유산법", "매장유산법", "토지보상법", "기부채납", "국유재산법", "공유재산법",
    "도시정비법시행령", "주차장법", "주차장법시행령", "피난방화규칙", "경관법",
]


@pytest.mark.parametrize("ref_id", _REQUIRED)
def test_required_law_resolves_with_source_link(ref_id):
    r = resolve(ref_id)
    assert r is not None, f"{ref_id} 미수록(분석 시 근거 확보 불가)"
    assert r.law and r.summary, f"{ref_id} 법령명/요지 누락"
    assert r.source and r.source.startswith("https://"), f"{ref_id} 1차출처 링크 누락"


def test_jiphap_building_law_present():
    # 사용자 최초 질문 — 집합건물법 포함 여부
    r = resolve("집합건물법")
    assert r and "집합건물" in r.law


def test_skyline_basis_article_broken_link_recovered():
    # 끊긴 링크 복구: skyline_protrusion basis_article가 법령수준 키로 해소(경관법)
    d = resolve_text("경관법 제9조·지자체 경관조례")
    assert d is not None and d["law"] == "경관법"


def test_unregistered_still_surfaces_none():
    # 미등록은 None(날조 금지·표면화)
    assert resolve("존재하지않는법xyz") is None
