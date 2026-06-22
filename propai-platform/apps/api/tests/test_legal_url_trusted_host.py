"""MEDIUM 감사: legal 진실원천 URL 신뢰호스트 게이트.

배경: ① url_status="verified"가 url 비어있지 않음만 의미(실접속/형식 무게이트)라 오신뢰 소지,
② inject_urls가 호스트 검증 없이 임의 URL을 진실원천 레지스트리에 주입 가능(law.go.kr 규율 우회).
수선: 신뢰 법령호스트(law.go.kr/elis.go.kr/eum.go.kr, https) 게이트로 ① url_status를 정직화
(현 레지스트리 URL 전부 law.go.kr→무회귀), ② inject_urls가 비신뢰 호스트를 거부(진실원천 보호).
"""
from app.services.legal import legal_reference_registry as reg


def test_trusted_hosts_accepted():
    assert reg._is_trusted_legal_host("https://www.law.go.kr/법령/건축법") is True
    assert reg._is_trusted_legal_host("https://law.go.kr/자치법규/서울특별시건축조례") is True
    assert reg._is_trusted_legal_host("https://www.elis.go.kr/x") is True


def test_untrusted_or_malformed_rejected():
    assert reg._is_trusted_legal_host("https://evil.example.com/법령") is False
    assert reg._is_trusted_legal_host("http://www.law.go.kr/법령/건축법") is False  # 비https
    assert reg._is_trusted_legal_host("https://law.go.kr.evil.com/x") is False  # suffix 위장
    assert reg._is_trusted_legal_host("javascript:alert(1)") is False
    assert reg._is_trusted_legal_host("") is False
    assert reg._is_trusted_legal_host(None) is False


def test_get_legal_refs_url_status_reflects_trust():
    refs = reg.get_legal_refs(["far_limit"])
    assert refs and refs[0]["url"].startswith("https://www.law.go.kr")
    assert refs[0]["url_status"] == "verified"  # law.go.kr → 신뢰


def test_inject_urls_rejects_untrusted_host():
    key = "far_limit"
    before = reg.get_legal_ref(key)["url"]
    reg.inject_urls({key: "https://evil.example.com/fake-law"})
    after = reg.get_legal_ref(key)["url"]
    assert after == before  # 진실원천 미오염(거부)


def test_inject_urls_accepts_trusted_host_and_isolates():
    key = "far_limit"
    original = reg.get_legal_ref(key)["url"]
    try:
        good = "https://www.law.go.kr/법령/건축법/제55조"
        reg.inject_urls({key: good})
        assert reg.get_legal_ref(key)["url"] == good
    finally:
        reg.inject_urls({key: original})  # 테스트 격리 복원
    assert reg.get_legal_ref(key)["url"] == original
