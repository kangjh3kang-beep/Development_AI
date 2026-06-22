"""VLLM 멀티모달 완성 — image_ref(파일/URL/data-uri/텍스트) → image 블록·content 구성."""
import base64

from app.adapters.vision.image_source import build_content, build_image_block

# 1x1 PNG(최소 유효 이미지)
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


def test_url_image_block():
    b = build_image_block("https://example.com/sheet.png")
    assert b["type"] == "image" and b["source"]["type"] == "url"
    assert b["source"]["url"].endswith("sheet.png")


def test_data_uri_block():
    uri = "data:image/png;base64,AAAA"
    b = build_image_block(uri)
    assert b["source"]["type"] == "base64"
    assert b["source"]["media_type"] == "image/png"
    assert b["source"]["data"] == "AAAA"


def test_local_file_base64(tmp_path, monkeypatch):
    monkeypatch.setenv("ALLOWED_IMAGE_DIR", str(tmp_path))  # 허용 디렉터리 내 파일만
    p = tmp_path / "drawing.png"
    p.write_bytes(_PNG)
    b = build_image_block(str(p))
    assert b["source"]["type"] == "base64"
    assert b["source"]["media_type"] == "image/png"
    assert base64.b64decode(b["source"]["data"]) == _PNG


def test_local_file_blocked_outside_allowed(tmp_path, monkeypatch):
    # 보안: 허용 디렉터리 미설정 → 로컬 파일 fail-closed 차단(임의 파일 유출 방지).
    p = tmp_path / "secret.png"
    p.write_bytes(_PNG)
    assert build_image_block(str(p)) is None
    # 허용 디렉터리 설정해도 경로 밖(..)은 차단.
    allowed = tmp_path / "uploads"
    allowed.mkdir()
    monkeypatch.setenv("ALLOWED_IMAGE_DIR", str(allowed))
    assert build_image_block(str(tmp_path / "secret.png")) is None
    # 비이미지 확장자 차단.
    bad = allowed / "x.txt"
    bad.write_bytes(b"data")
    assert build_image_block(str(bad)) is None


def test_url_ssrf_blocked():
    # 보안: 내부/사설/메타데이터 호스트 차단(SSRF).
    for u in ("http://localhost/x.png", "http://127.0.0.1/x.png",
              "http://169.254.169.254/meta.png", "http://192.168.0.1/x.png", "http://10.0.0.5/x.png"):
        assert build_image_block(u) is None
    # 공인 호스트는 허용.
    assert build_image_block("https://example.com/x.png")["source"]["type"] == "url"


def test_non_image_returns_none():
    assert build_image_block("sheet-A-PLAN") is None  # 단순 텍스트 참조
    assert build_image_block(None) is None
    assert build_image_block("") is None


def test_build_content_multimodal_vs_text():
    # 이미지 → [image, text] 멀티모달
    c = build_content("https://x/y.png", "분류하라")
    assert isinstance(c, list) and c[0]["type"] == "image" and c[1]["type"] == "text"
    # 이미지 아님 → 텍스트(참조 명시)
    t = build_content("sheet-1", "분류하라")
    assert isinstance(t, str) and "sheet-1" in t


def test_drawing_client_builds_multimodal(monkeypatch):
    # 실 클라이언트가 이미지 참조 시 멀티모달 content로 호출하는지(httpx 모킹).
    from app.adapters.vision import drawing_extractor

    captured = {}

    class _Resp:
        def raise_for_status(self): ...
        def json(self):
            return {"content": [{"text": '[{"type":"PARKING","confidence":0.9}]'}]}

    def _fake_post(url, headers=None, json=None, timeout=None):
        captured["content"] = json["messages"][0]["content"]
        return _Resp()

    import httpx
    monkeypatch.setattr(httpx, "post", _fake_post)
    client = drawing_extractor.AnthropicDrawingVisionClient(api_key="sk-test")
    out = client.extract_elements("https://x/sheet.png", "주차 평면")
    assert out == [{"type": "PARKING", "confidence": 0.9}]
    # content가 멀티모달 배열(image + text)
    assert isinstance(captured["content"], list)
    assert captured["content"][0]["type"] == "image"
