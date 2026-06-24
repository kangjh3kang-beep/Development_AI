"""LegalHub facade — 법령 단일경유(개념키 위임 + 조문키 교차 + 범용 resolve) 검증(#2)."""
from app.services.legal.legal_hub import LegalHub
from app.services.legal import legal_reference_registry as reg


def test_refs_delegates_to_registry():
    # 개념키 → registry.get_legal_refs와 동일 위임.
    keys = list(reg.LEGAL_REFERENCES.keys())[:3]
    assert LegalHub.refs(keys) == reg.get_legal_refs(keys)


def test_by_article_verified_url_and_cross_ref():
    # 조문 인용 → 검증 URL + (registry에 동일 조문 있으면 개념키·제목 교차).
    sample_key = next(iter(reg.LEGAL_REFERENCES))
    s = reg.LEGAL_REFERENCES[sample_key]
    rec = LegalHub.by_article(s["law_name"], s["article"])
    assert rec["url"].startswith("https://www.law.go.kr")
    assert rec["url_status"] == "verified"
    # 동일 (법령,조문)이 registry에 있으므로 교차 키 부착.
    assert rec.get("key") is not None
    assert rec["article"] == s["article"]


def test_resolve_both_forms():
    # (1) 개념키 직접 해석.
    k = next(iter(reg.LEGAL_REFERENCES))
    assert (LegalHub.resolve(k) or {}).get("key") == k
    # (2) 조문문자열('국토계획법§78') 파싱 해석 → 검증 URL.
    r = LegalHub.resolve("국토의 계획 및 이용에 관한 법률§78")
    assert r is not None and r["url"].startswith("https://www.law.go.kr") and "78" in r["article"]
    # (3) 해석 불가 → None(가짜 생성 금지).
    assert LegalHub.resolve("존재하지않는키_xyz") is None


def test_no_fabricated_url_for_unverified():
    # 빈/미확보 법령명은 law.go.kr 루트(가짜 조문링크 금지) — pending 가능.
    rec = LegalHub.by_article("", None)
    assert rec["url"].startswith("https://www.law.go.kr")
