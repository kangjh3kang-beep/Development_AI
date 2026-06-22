"""LAW1 — 참조법령 확충(전수조사 갭) + 끊긴 근거링크 복구 회귀.

부동산개발·건축 핵심 법규(집합건물법 등)가 사전에 수록·해소되고 1차출처 링크를 동반하는지(설명가능성 표준),
skyline basis_article의 끊긴 링크가 복구됐는지 검증.
"""
import pytest

from app.services.explain.legal_refs import resolve, resolve_text

# 사용자 지목 + 전수조사 missing_high(LAW1) + missing_other(LAW2) 핵심 법규
_REQUIRED = [
    # LAW1 — missing_high
    "집합건물법", "주택법", "공동주택관리법", "도시개발법", "소규모주택정비법",
    "환경영향평가법", "교통영향평가", "재해영향평가", "소방시설법",
    "감정평가법", "공시지가법", "개발이익환수법", "농지법", "산지관리법",
    "문화유산법", "매장유산법", "토지보상법", "기부채납", "국유재산법", "공유재산법",
    "도시정비법시행령", "주차장법", "주차장법시행령", "피난방화규칙", "경관법",
    # LAW2 — missing_other
    "토지이용규제기본법", "국토계획법시행규칙", "개발제한구역법", "공원녹지법", "도로법",
    "건축물분양법", "건축설비기준규칙", "건축구조기준규칙", "도시재정비촉진법", "도시재생법",
    "택지개발촉진법", "공공주택특별법", "산업입지법", "역세권개발법", "수도권정비계획법",
    "군사기지법", "공항시설법", "하수도법", "수도법", "국토기본법",
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


def test_resolve_text_longest_match_not_parent_law():
    # branch3 최장일치 — 시행규칙/시행령이 부모법(국토계획법)으로 오해소되지 않음(삽입순 비의존)
    assert resolve_text("국토계획법 시행규칙 제3조")["law"] == "국토의 계획 및 이용에 관한 법률 시행규칙"
    assert resolve_text("국토계획법시행규칙 제3조")["law"] == "국토의 계획 및 이용에 관한 법률 시행규칙"
    assert resolve_text("국토계획법 시행령 제84조")["law"] == "국토의 계획 및 이용에 관한 법률 시행령"
    assert resolve_text("건축법 시행령 제119조")["law"] == "건축법 시행령"
    # 부모법 단독 텍스트는 부모법으로
    assert resolve_text("국토계획법 제36조")["law"] == "국토의 계획 및 이용에 관한 법률"


def test_resolve_text_prefix_anchor_no_composed_name_false_positive():
    # 접두 앵커 — 합성 법령명이 짧은 등록키의 접미와 겹쳐도 오해소 금지(미등록→None, 날조 금지)
    # (민간임대주택법≠주택법, 상수도법≠수도법, 유료도로법≠도로법, 부설주차장법≠주차장법)
    for txt in ("민간임대주택법 제5조", "상수도법", "유료도로법", "부설주차장법", "지역주택조합주택법"):
        d = resolve_text(txt)
        assert d is None or d["law"] not in ("주택법", "수도법", "도로법", "주차장법"), f"{txt} 오해소: {d}"
    # 정당 인용(법령명이 맨 앞)은 보존
    assert resolve_text("건축법 제46조/도시계획")["law"] == "건축법"
    assert resolve_text("경관법 제9조·지자체 경관조례")["law"] == "경관법"
