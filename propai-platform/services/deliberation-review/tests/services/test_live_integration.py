"""실연동 검증 — httpx 모킹으로 실 경로(요청 구성·응답 파싱) 증명. 실 키 없이도 검증 가능.

라이브 엔드포인트 실호출은 키+네트워크 필요(사용자 검증) → 여기선 어댑터 로직을 결정론으로 검증.
"""
import httpx
import pytest

from app.adapters.jurisdiction import build_external_jurisdiction
from app.adapters.jurisdiction.vworld import VWorldJurisdictionAdapter
from app.adapters.vision.vllm_sheet_classifier import AnthropicVisionClient, VLLMSheetClassifier
from app.services.preflight.adapters import AdapterTimeout, ExternalJurisdictionAdapter


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


# ── VLLM(Anthropic) 실 경로 ──

def test_anthropic_vision_real_path(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.update(url=url, headers=headers, model=json["model"], msg=json["messages"])
        return _FakeResp({"content": [{"text": "단면도"}]})

    monkeypatch.setattr(httpx, "post", fake_post)
    client = AnthropicVisionClient(api_key="sk-test", model="claude-x")
    out = client.classify_sheet("s3://sheet.png", "A-201")
    assert out == "단면도"  # raw 반환(정규화는 VLLMSheetClassifier가)
    assert captured["url"].endswith("/v1/messages")
    assert captured["headers"]["x-api-key"] == "sk-test"
    assert captured["model"] == "claude-x"


def test_vllm_classifier_with_anthropic_normalizes(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _FakeResp({"content": [{"text": "단면도"}]}))
    clf = VLLMSheetClassifier(vision_client=AnthropicVisionClient(api_key="sk-test"))
    assert clf.classify({"image_ref": "x", "titleblock_text": "A-201"}) == "SECTION"


def test_anthropic_no_key_returns_none():
    assert AnthropicVisionClient(api_key="").classify_sheet("x", None) is None


# ── VWORLD 관할 실 경로 ──

def test_vworld_real_path_parses(monkeypatch):
    captured = {}

    def fake_get(url, params=None, timeout=None):
        captured.update(url=url, params=params)
        return _FakeResp({"response": {"result": {"featureCollection": {"features": [
            {"properties": {"dgm_nm": "제2종일반주거지역"}},
            {"properties": {"dgm_nm": "제3종일반주거지역"}},
        ]}}}})

    monkeypatch.setattr(httpx, "get", fake_get)
    result = VWorldJurisdictionAdapter(api_key="testkey").lookup("1111010100100000001")
    assert [z["zone_code"] for z in result["zones"]] == ["제2종일반주거지역", "제3종일반주거지역"]
    assert captured["params"]["key"] == "testkey"
    assert "1111010100100000001" in captured["params"]["attrFilter"]


def test_vworld_no_key_degrades():
    with pytest.raises(AdapterTimeout):
        VWorldJurisdictionAdapter(api_key="").lookup("1111010100100000001")


def test_vworld_empty_response_degrades(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResp(
        {"response": {"result": {"featureCollection": {"features": []}}}}))
    with pytest.raises(AdapterTimeout):
        VWorldJurisdictionAdapter(api_key="testkey").lookup("x")


def test_factory_defaults_to_mock():
    assert isinstance(build_external_jurisdiction(), ExternalJurisdictionAdapter)


def test_factory_vworld_when_configured(monkeypatch):
    monkeypatch.setenv("JURISDICTION_ADAPTER", "vworld")  # env 우선(오버레이 동작)
    assert isinstance(build_external_jurisdiction(), VWorldJurisdictionAdapter)
