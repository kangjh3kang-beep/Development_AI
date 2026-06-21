"""R2 객체 저장(object_store) + 원본 저장 배선 단위테스트.

라이브 R2 없이 검증: ①SigV4 서명키를 AWS 공식 테스트벡터로 정확성 확인 ②키 테넌트격리·중복제거
③미설정 시 정직 강등(stored=False) ④presigned URL·헤더 구조 ⑤_store_original dedup/degrade.
"""

import hashlib
import hmac

import pytest

from app.services.design_ingest import object_store as os_mod

# R2 자격증명(테스트용 더미) — 환경 설정 시 동작 경로 검증용.
_ENV = {
    "R2_ACCOUNT_ID": "acct123",
    "R2_ACCESS_KEY_ID": "AKIAIOSFODNN7EXAMPLE",
    "R2_SECRET_ACCESS_KEY": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    "R2_BUCKET": "design-originals",
}


def _set_env(monkeypatch, **over):
    for k, v in {**_ENV, **over}.items():
        monkeypatch.setenv(k, v)


# ── SigV4: AWS S3 'GET Object' 공식 예제로 서명 정확성 검증(라이브 R2 불필요) ──
def test_sigv4_matches_aws_s3_get_example():
    # AWS 문서 'Signature Calculations for the Authorization Header'의 GET Object 예제.
    # _derive_signing_key + 최종 HMAC이 AWS 정답 서명과 일치해야 함(서명 체인 정확성 보증).
    secret = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    string_to_sign = (
        "AWS4-HMAC-SHA256\n"
        "20130524T000000Z\n"
        "20130524/us-east-1/s3/aws4_request\n"
        "7344ae5b7ee6c3e7e6b0fe0640412a37625d1fbfff95c48bbb2dc43964946972"
    )
    skey = os_mod._derive_signing_key(secret, "20130524", "us-east-1", "s3")
    sig = hmac.new(skey, string_to_sign.encode(), hashlib.sha256).hexdigest()
    assert sig == "f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41"


def test_sha256_hex_empty():
    assert os_mod._sha256_hex(b"") == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )


# ── 객체 키: 테넌트 격리 + content_hash 중복제거 ──
_H = "abc1230000def456"  # 유효 hex content_hash(테스트용, 16자)


def test_object_key_tenant_isolation_and_dedup():
    a = os_mod.object_key("T1", _H, "배치도.dxf")
    b = os_mod.object_key("T1", _H, "배치도.dxf")
    assert a == b == f"design/T1/{_H}.dxf"          # 동일 → 멱등(dedup)
    assert os_mod.object_key("T2", _H, "x.dxf") == f"design/T2/{_H}.dxf"  # 테넌트 분리
    assert a != os_mod.object_key("T2", _H, "x.dxf")
    # tenant 미상 → _shared 프리픽스(전역)
    assert os_mod.object_key(None, _H, "a.pdf") == f"design/_shared/{_H}.pdf"
    # 미지원 확장자는 확장자 없이(키 안정)
    assert os_mod.object_key("T1", _H, "noext") == f"design/T1/{_H}"


def test_object_key_sanitizes_tenant_traversal():
    # ★path traversal/교차테넌트 차단 — '/'·'..'·개행이 키 경로를 이탈하지 못함
    k = os_mod.object_key("../other/x", _H, "a.dxf")
    assert k.startswith("design/")
    assert "/" not in k.split("design/")[1].rsplit("/", 1)[0]  # tenant 세그먼트에 '/' 없음
    assert ".." not in k
    assert os_mod.object_key("a\nb", _H, "a.dxf") == f"design/a_b/{_H}.dxf"


def test_object_key_rejects_bad_content_hash():
    for bad in ("", "NOT-HEX!!", "../etc", "g" * 20):  # 비-hex
        with pytest.raises(ValueError):
            os_mod.object_key("T1", bad, "a.dxf")


def test_mime_for():
    assert os_mod.mime_for("a.pdf") == "application/pdf"
    assert os_mod.mime_for("a.DXF") == "application/dxf"
    assert os_mod.mime_for("a.unknown") == "application/octet-stream"


# ── 압축: 텍스트 도면만 gzip + 라운드트립(투명 해제) ──
def test_compress_text_drawing_gzip_roundtrip():
    import gzip
    raw = ("0\nSECTION\n2\nENTITIES\n0\nLINE\n8\n0\n" * 500).encode()
    body, enc = os_mod.compress_for_storage(raw, "배치도.dxf")
    assert enc == "gzip" and len(body) < len(raw)       # 압축됨
    assert gzip.decompress(body) == raw                  # 원본 무손실 복원(투명 해제 정합)
    # IFC도 압축
    _, enc2 = os_mod.compress_for_storage(b"ISO-10303-21;\n" * 200, "model.ifc")
    assert enc2 == "gzip"


def test_compress_skips_already_compressed():
    # 이미 압축된 형식(이미지·pdf·xlsx)·미지원은 패스(원본 그대로·encoding None)
    for fn in ("a.png", "a.jpg", "a.pdf", "a.xlsx", "a.unknown"):
        body, enc = os_mod.compress_for_storage(b"binarydata" * 50, fn)
        assert enc is None and body == b"binarydata" * 50


def test_compress_empty_passthrough():
    body, enc = os_mod.compress_for_storage(b"", "a.dxf")
    assert enc is None and body == b""


# ── 썸네일/프록시: 이미지만 WebP 저해상 + 키 ──
def _png(w=1000, h=800) -> bytes:
    import io

    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


def test_make_thumbnail_image_to_webp():
    import io

    from PIL import Image
    thumb = os_mod.make_thumbnail(_png(), "도면.png")
    assert thumb is not None
    out = Image.open(io.BytesIO(thumb))
    assert out.format == "WEBP" and max(out.size) <= 512


def test_make_thumbnail_non_image_none():
    for fn in ("a.dxf", "a.pdf", "a.ifc", "a.xlsx", "a.unknown"):
        assert os_mod.make_thumbnail(b"data" * 100, fn) is None
    assert os_mod.make_thumbnail(b"", "a.png") is None       # 빈입력
    assert os_mod.make_thumbnail(b"notanimage", "a.png") is None  # 손상 → None(정직)


def test_make_thumbnail_rejects_oversized_pixels(monkeypatch):
    # ★디컴프레션밤 가드 — 헤더 픽셀수가 한도 초과면 디코딩 전 None(메모리 폭증 차단).
    monkeypatch.setattr(os_mod, "_THUMB_MAX_DECODE_PX", 100)  # 작은 한도로 거부경로 검증
    assert os_mod.make_thumbnail(_png(1000, 800), "big.png") is None  # 800K px > 100 → None


def test_thumb_key():
    assert os_mod.thumb_key("T1", _H) == f"design/T1/{_H}_thumb.webp"
    k = os_mod.thumb_key("../x", _H)  # tenant 정화
    assert k.startswith("design/") and ".." not in k and k.endswith("_thumb.webp")
    with pytest.raises(ValueError):
        os_mod.thumb_key("T1", "NOThex")


def test_presigned_blocks_cross_tenant_thumb(monkeypatch):
    # ★썸네일 키에도 owner 프리픽스 가드 적용 — 타테넌트 썸네일 서명 거부
    _set_env(monkeypatch)
    tk = os_mod.thumb_key("T1", _H)
    assert os_mod.presigned_get_url(tk, "T2") is None       # 타테넌트 → None
    assert os_mod.presigned_get_url(tk, "T1") is not None    # 본인 → 발급


async def test_store_thumbnail_image_stored(monkeypatch):
    from app.services.design_ingest import ingest_service
    captured = {}

    async def _ne(_k):
        return False

    async def _put(_k, d, ct, content_encoding=None):
        captured["ct"], captured["data"] = ct, d
        return True, None

    monkeypatch.setattr(os_mod, "is_configured", lambda: True)
    monkeypatch.setattr(os_mod, "object_exists", _ne)
    monkeypatch.setattr(os_mod, "put_object", _put)
    ok = await ingest_service._store_thumbnail(_png(), "a.png", _H, "T1")
    assert ok is True and captured["ct"] == "image/webp" and len(captured["data"]) > 0


async def test_store_thumbnail_non_image_false(monkeypatch):
    from app.services.design_ingest import ingest_service
    monkeypatch.setattr(os_mod, "is_configured", lambda: True)
    assert await ingest_service._store_thumbnail(b"dxfdata", "a.dxf", _H, "T1") is False


async def test_store_thumbnail_unconfigured_false(monkeypatch):
    from app.services.design_ingest import ingest_service
    monkeypatch.setattr(os_mod, "is_configured", lambda: False)
    assert await ingest_service._store_thumbnail(_png(), "a.png", _H, "T1") is False


def test_auth_headers_signs_content_encoding(monkeypatch):
    _set_env(monkeypatch)
    conf = os_mod._conf()
    h = os_mod._auth_headers(conf, "PUT", "design/T1/h.dxf", payload_hash=os_mod._sha256_hex(b"x"),
                             content_type="application/dxf", content_encoding="gzip")
    assert h.get("content-encoding") == "gzip"
    # 서명된 헤더 목록에 content-encoding 포함(서명 정합)
    assert "content-encoding" in h["Authorization"].split("SignedHeaders=")[1]


# ── 미설정 시 비활성(정직 강등) — 네트워크 호출 없음 ──
def test_unconfigured_is_disabled(monkeypatch):
    for k in _ENV:
        monkeypatch.delenv(k, raising=False)
    assert os_mod.is_configured() is False
    assert os_mod.presigned_get_url("design/T1/h.pdf", "T1") is None


async def test_put_object_unconfigured_returns_reason(monkeypatch):
    for k in _ENV:
        monkeypatch.delenv(k, raising=False)
    ok, reason = await os_mod.put_object("k", b"data", "application/pdf")
    assert ok is False and reason == "object_store_not_configured"


async def test_object_exists_unconfigured_false(monkeypatch):
    for k in _ENV:
        monkeypatch.delenv(k, raising=False)
    assert await os_mod.object_exists("k") is False


# ── 설정 시: 헤더/presigned 구조(서명 자체는 네트워크 없이 생성) ──
def test_is_configured_and_conf(monkeypatch):
    _set_env(monkeypatch)
    assert os_mod.is_configured() is True
    conf = os_mod._conf()
    assert conf["host"] == "acct123.r2.cloudflarestorage.com"
    assert conf["endpoint"] == "https://acct123.r2.cloudflarestorage.com"


def test_auth_headers_structure(monkeypatch):
    _set_env(monkeypatch)
    conf = os_mod._conf()
    h = os_mod._auth_headers(conf, "PUT", "design/T1/h.pdf",
                             payload_hash=os_mod._sha256_hex(b"x"), content_type="application/pdf")
    assert h["Authorization"].startswith("AWS4-HMAC-SHA256 Credential=AKIAIOSFODNN7EXAMPLE/")
    assert "SignedHeaders=content-type;host;x-amz-content-sha256;x-amz-date" in h["Authorization"]
    assert h["host"] == "acct123.r2.cloudflarestorage.com"
    assert "x-amz-date" in h and "x-amz-content-sha256" in h


def test_presigned_url_structure(monkeypatch):
    _set_env(monkeypatch)
    url = os_mod.presigned_get_url("design/T1/abc.pdf", "T1", expires=300)
    assert url is not None
    assert url.startswith("https://acct123.r2.cloudflarestorage.com/design-originals/design/T1/abc.pdf?")
    assert "X-Amz-Algorithm=AWS4-HMAC-SHA256" in url
    assert "X-Amz-Expires=300" in url
    assert "X-Amz-Signature=" in url
    assert "X-Amz-Credential=AKIAIOSFODNN7EXAMPLE" in url


def test_presigned_blocks_cross_tenant(monkeypatch):
    # ★IDOR 차단 — 요청자 테넌트(T2)가 타 테넌트(T1) 키 서명 요청 시 None
    _set_env(monkeypatch)
    assert os_mod.presigned_get_url("design/T1/abc.pdf", "T2") is None
    # 본인 키는 발급됨
    assert os_mod.presigned_get_url("design/T2/abc.pdf", "T2") is not None


def test_presigned_expires_clamped(monkeypatch):
    _set_env(monkeypatch)
    url = os_mod.presigned_get_url("design/T1/k", "T1", expires=99999999)  # 7일 초과 → 클램프
    assert "X-Amz-Expires=604800" in url


# ── _store_original 배선: dedup/degrade ──
async def test_store_original_unconfigured(monkeypatch):
    from app.services.design_ingest import ingest_service
    monkeypatch.setattr(os_mod, "is_configured", lambda: False)
    key, stored, reason = await ingest_service._store_original(b"d", "a.dxf", _H, "T1")
    assert key is None and stored is False and reason == "object_store_not_configured"


async def test_store_original_uploads_when_new(monkeypatch):
    import gzip

    from app.services.design_ingest import ingest_service
    captured = {}

    async def _not_exists(_k):
        return False

    async def _put(_k, data, _ct, content_encoding=None):
        captured["data"], captured["enc"] = data, content_encoding
        return True, None

    monkeypatch.setattr(os_mod, "is_configured", lambda: True)
    monkeypatch.setattr(os_mod, "object_exists", _not_exists)
    monkeypatch.setattr(os_mod, "put_object", _put)
    raw = ("0\nLINE\n8\n0\n" * 300).encode()  # 텍스트 도면 → 압축 대상
    key, stored, reason = await ingest_service._store_original(raw, "배치.dxf", _H, "T1")
    assert key == f"design/T1/{_H}.dxf" and stored is True and reason is None
    # ★텍스트 도면은 gzip 압축돼 전송됐는지(저장GB 절감)
    assert captured["enc"] == "gzip" and len(captured["data"]) < len(raw)
    assert gzip.decompress(captured["data"]) == raw


async def test_store_original_dedup_skips_upload(monkeypatch):
    from app.services.design_ingest import ingest_service
    calls = {"put": 0}

    async def _exists(_k):
        return True

    async def _put(_k, _d, _ct):
        calls["put"] += 1
        return True, None

    monkeypatch.setattr(os_mod, "is_configured", lambda: True)
    monkeypatch.setattr(os_mod, "object_exists", _exists)
    monkeypatch.setattr(os_mod, "put_object", _put)
    key, stored, reason = await ingest_service._store_original(b"d", "a.dxf", _H, "T1")
    assert stored is True and reason == "deduplicated" and calls["put"] == 0  # 재업로드 안 함


async def test_store_original_put_failure_degrades(monkeypatch):
    from app.services.design_ingest import ingest_service

    async def _not_exists(_k):
        return False

    async def _put(_k, _d, _ct, content_encoding=None):
        return False, "r2_status_403"

    monkeypatch.setattr(os_mod, "is_configured", lambda: True)
    monkeypatch.setattr(os_mod, "object_exists", _not_exists)
    monkeypatch.setattr(os_mod, "put_object", _put)
    key, stored, reason = await ingest_service._store_original(b"d", "a.dxf", _H, "T1")
    assert key is None and stored is False and reason == "r2_status_403"


# ── compute_point_id(저장·조회 공유 ID 규칙) ──
def test_compute_point_id_deterministic_and_tenant_namespaced():
    from app.services.design_ingest.design_spec import DesignSpec, compute_point_id
    assert compute_point_id(_H, "T1") == compute_point_id(_H, "T1")     # 결정적
    assert compute_point_id(_H, "T1") != compute_point_id(_H, "T2")     # 테넌트 분리
    assert compute_point_id(_H) != compute_point_id(_H, "T1")           # 미지정=hash-only
    # DesignSpec.point_id와 동일 규칙(저장↔조회 공유)
    spec = DesignSpec(source_format="dxf", total_area_sqm=84.0)
    assert spec.point_id("T1") == compute_point_id(spec.content_hash(), "T1")


# ── get_drawing_object_key: 테넌트 스코프 조회 + 이중방어 ──
class _FakePoint:
    def __init__(self, payload):
        self.payload = payload


def _patch_qdrant(monkeypatch, points):
    class _Client:
        def retrieve(self, **_k):
            return points

    import apps.api.database.init_qdrant as initq
    monkeypatch.setattr(initq, "get_qdrant_client", lambda: _Client())


async def test_get_object_key_returns_for_owner(monkeypatch):
    from app.services.design_ingest.search_service import get_drawing_object_key
    _patch_qdrant(monkeypatch, [_FakePoint({"tenant_id": "T1", "object_key": f"design/T1/{_H}.dxf"})])
    key = await get_drawing_object_key(_H, "T1")
    assert key == f"design/T1/{_H}.dxf"


async def test_get_object_key_blocks_tenant_mismatch(monkeypatch):
    # payload 소유 테넌트(T1)와 요청자(T2) 불일치 → None(이중방어)
    from app.services.design_ingest.search_service import get_drawing_object_key
    _patch_qdrant(monkeypatch, [_FakePoint({"tenant_id": "T1", "object_key": f"design/T1/{_H}.dxf"})])
    assert await get_drawing_object_key(_H, "T2") is None


async def test_get_object_key_none_when_absent(monkeypatch):
    from app.services.design_ingest.search_service import get_drawing_object_key
    _patch_qdrant(monkeypatch, [])
    assert await get_drawing_object_key(_H, "T1") is None


async def test_get_object_key_rejects_bad_hash():
    # ★저장경로(object_key)와 hex 계약 통일 — 잘못된 content_hash는 Qdrant 조회 전 None
    from app.services.design_ingest.search_service import get_drawing_object_key
    for bad in ("", "NOT-HEX", "../etc/passwd", "g" * 20):
        assert await get_drawing_object_key(bad, "T1") is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
