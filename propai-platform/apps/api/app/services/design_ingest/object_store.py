"""설계 원본 파일 객체 저장 — Cloudflare R2(S3 호환) 백엔드.

설계생성 자가학습은 업로드된 도면 원본을 축적해야 하는데(수TB), 벡터DB(Qdrant)는 메타·임베딩만
보관하므로 원본은 별도 객체 스토리지에 둔다. 결정된 방향은 **Cloudflare R2**(egress 무료).

설계 원칙:
- ★신규 파이썬 의존성 0 — boto3 없이 httpx + AWS SigV4(stdlib hmac/hashlib)로 R2 S3 API 호출
  (기존 storage_service의 'httpx REST·무의존' 관례 계승).
- ★자격증명은 인증/시크릿에서만(get_clean_env_key → admin secrets 오버레이). 미설정 시 비활성
  (best-effort 정직 강등 — 기능을 깨지 않고 stored=False + 사유 반환).
- ★테넌트 격리 + 중복제거: 키 = design/{tenant_id}/{content_hash}{ext}. 동일 내용은 1회만 저장.
- ★원본은 비공개(presigned URL로만 조회) — 자격증명·서명은 절대 로그에 남기지 않는다.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
from datetime import UTC, datetime
from urllib.parse import quote

logger = logging.getLogger(__name__)

# 키 세그먼트 안전화 — 경로 분리자/특수문자 제거(path traversal·교차테넌트 키 차단).
_UNSAFE_SEGMENT = re.compile(r"[^A-Za-z0-9_-]")
_HEX_HASH = re.compile(r"[0-9a-f]{16,128}")

_ALGORITHM = "AWS4-HMAC-SHA256"
_REGION = "auto"   # R2는 region이 'auto'
_SERVICE = "s3"
_UNSIGNED = "UNSIGNED-PAYLOAD"

# 확장자 → MIME(원본 다운로드 시 올바른 타입 — 미상은 octet-stream).
_EXT_MIME = {
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".dxf": "application/dxf",
    ".ifc": "application/x-step",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def _conf() -> dict | None:
    """R2 자격증명/버킷을 시크릿에서 읽는다(미설정이면 None=비활성)."""
    try:
        from app.services.ai.key_sanitizer import get_clean_env_key

        getk = get_clean_env_key
    except Exception:  # noqa: BLE001 — 시크릿 헬퍼 없으면 환경변수 직접(키오염 가드 우회 — 가시성 경고)
        logger.warning("R2 object_store: key_sanitizer 미가용 — 환경변수 직접 사용(값 미로깅)")
        getk = lambda k: (os.environ.get(k) or "").strip()  # noqa: E731

    account = getk("R2_ACCOUNT_ID")
    access = getk("R2_ACCESS_KEY_ID")
    secret = getk("R2_SECRET_ACCESS_KEY")
    bucket = getk("R2_BUCKET")
    if not (account and access and secret and bucket):
        return None
    endpoint = getk("R2_ENDPOINT") or f"https://{account}.r2.cloudflarestorage.com"
    host = endpoint.split("://", 1)[-1].rstrip("/")
    return {
        "account": account, "access": access, "secret": secret,
        "bucket": bucket, "endpoint": endpoint.rstrip("/"), "host": host,
    }


def is_configured() -> bool:
    """R2 사용 가능 여부(자격증명 모두 설정)."""
    return _conf() is not None


def _ext(filename: str) -> str:
    name = (filename or "").lower()
    for ext in _EXT_MIME:
        if name.endswith(ext):
            return ext
    return ""


def mime_for(filename: str) -> str:
    return _EXT_MIME.get(_ext(filename), "application/octet-stream")


def _safe_segment(value: str | None, default: str = "_shared") -> str:
    """키 세그먼트 안전화 — '/'·'..'·개행 등 제거(화이트리스트). 빈값이면 default."""
    t = (value or "").strip() or default
    return _UNSAFE_SEGMENT.sub("_", t) or default


def object_key(tenant_id: str | None, content_hash: str, filename: str = "") -> str:
    """객체 키 — 테넌트 격리 + content_hash 중복제거. design/{tenant}/{hash}{ext}.

    tenant_id는 화이트리스트 정화(경로 조작·교차테넌트 키 차단), content_hash는 hex 검증.
    tenant_id 미상이면 '_shared'(전역) 프리픽스. content_hash가 같으면 동일 키 → 멱등 dedup.
    """
    if not _HEX_HASH.fullmatch(content_hash or ""):
        raise ValueError("invalid content_hash")  # SHA-256 hex만 허용(키 안정성)
    return f"design/{_safe_segment(tenant_id)}/{content_hash}{_ext(filename)}"


# ── AWS SigV4 (stdlib) ──
def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _derive_signing_key(secret: str, datestamp: str, region: str, service: str) -> bytes:
    """SigV4 서명키 도출(HMAC 체인). region/service 파라미터화로 AWS 공식 벡터 검증 가능."""
    k_date = _hmac(("AWS4" + secret).encode("utf-8"), datestamp)
    k_region = _hmac(k_date, region)
    k_service = _hmac(k_region, service)
    return _hmac(k_service, "aws4_request")


def _signing_key(secret: str, datestamp: str) -> bytes:
    return _derive_signing_key(secret, datestamp, _REGION, _SERVICE)


def _uri_encode(key: str, *, encode_slash: bool) -> str:
    """RFC3986 경로 인코딩(SigV4 규칙). encode_slash=False면 '/'는 보존(경로용)."""
    safe = "-_.~" + ("" if encode_slash else "/")
    return quote(key, safe=safe)


def _amz_times() -> tuple[str, str]:
    now = datetime.now(UTC)
    return now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")


def _canonical_uri(conf: dict, key: str) -> str:
    """path-style 경로(/{bucket}/{key}) — '/'는 보존하고 나머지만 인코딩."""
    return "/" + _uri_encode(f"{conf['bucket']}/{key}", encode_slash=False)


def _object_url(conf: dict, key: str) -> str:
    return f"{conf['endpoint']}{_canonical_uri(conf, key)}"


def _auth_headers(
    conf: dict, method: str, key: str, *, payload_hash: str, content_type: str | None = None
) -> dict[str, str]:
    """헤더 기반 SigV4 서명 → 요청 헤더(Authorization 포함). path-style 경로 사용."""
    amz_date, datestamp = _amz_times()
    canonical_uri = _canonical_uri(conf, key)

    headers = {
        "host": conf["host"],
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
    }
    if content_type:
        headers["content-type"] = content_type
    signed_headers = ";".join(sorted(headers))
    canonical_headers = "".join(f"{h}:{headers[h]}\n" for h in sorted(headers))

    canonical_request = "\n".join(
        [method, canonical_uri, "", canonical_headers, signed_headers, payload_hash]
    )
    scope = f"{datestamp}/{_REGION}/{_SERVICE}/aws4_request"
    string_to_sign = "\n".join(
        [_ALGORITHM, amz_date, scope, _sha256_hex(canonical_request.encode("utf-8"))]
    )
    signature = hmac.new(
        _signing_key(conf["secret"], datestamp), string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    authorization = (
        f"{_ALGORITHM} Credential={conf['access']}/{scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    return {**headers, "Authorization": authorization}


def presigned_get_url(key: str, owner_tenant_id: str | None, expires: int = 600) -> str | None:
    """원본 조회용 presigned GET URL(쿼리 서명). 미설정/소유불일치/오류 시 None(정직).

    ★교차테넌트 차단: 키가 요청자 테넌트 프리픽스(design/{owner}/)에 속할 때만 서명 발급.
    원본은 비공개 버킷에 두고 단기 서명 URL로만 조회한다(자격증명 노출 없음).
    """
    conf = _conf()
    if not conf:
        return None
    # 소유권 가드 — 호출자 테넌트 소유 키만 서명(IDOR 차단).
    if not key.startswith(f"design/{_safe_segment(owner_tenant_id)}/"):
        return None
    try:
        amz_date, datestamp = _amz_times()
        scope = f"{datestamp}/{_REGION}/{_SERVICE}/aws4_request"
        exp = max(1, min(expires, 604800))  # 1초~7일
        canonical_uri = _canonical_uri(conf, key)
        qs_params = {
            "X-Amz-Algorithm": _ALGORITHM,
            "X-Amz-Credential": f"{conf['access']}/{scope}",
            "X-Amz-Date": amz_date,
            "X-Amz-Expires": str(exp),
            "X-Amz-SignedHeaders": "host",
        }
        canonical_qs = "&".join(
            f"{quote(k, safe='-_.~')}={quote(v, safe='-_.~')}" for k, v in sorted(qs_params.items())
        )
        canonical_headers = f"host:{conf['host']}\n"
        canonical_request = "\n".join(
            ["GET", canonical_uri, canonical_qs, canonical_headers, "host", _UNSIGNED]
        )
        string_to_sign = "\n".join(
            [_ALGORITHM, amz_date, scope, _sha256_hex(canonical_request.encode("utf-8"))]
        )
        signature = hmac.new(
            _signing_key(conf["secret"], datestamp), string_to_sign.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return f"{conf['endpoint']}{canonical_uri}?{canonical_qs}&X-Amz-Signature={signature}"
    except Exception as e:  # noqa: BLE001
        logger.warning("R2 presigned URL 생성 실패: %s", str(e)[:120])
        return None


async def object_exists(key: str) -> bool:
    """HEAD로 객체 존재 확인(중복제거용). 미설정/오류 시 False(=재업로드 시도)."""
    conf = _conf()
    if not conf:
        return False
    try:
        import httpx

        headers = _auth_headers(conf, "HEAD", key, payload_hash=_sha256_hex(b""))
        url = _object_url(conf, key)
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.head(url, headers=headers)
        return resp.status_code == 200
    except Exception as e:  # noqa: BLE001
        logger.debug("R2 HEAD 실패(존재 미확인): %s", str(e)[:120])
        return False


async def put_object(key: str, data: bytes, content_type: str) -> tuple[bool, str | None]:
    """객체 업로드(PUT). 반환: (성공, 실패사유|None). 미설정/오류는 정직 강등(예외 비전파)."""
    conf = _conf()
    if not conf:
        return False, "object_store_not_configured"
    try:
        import httpx

        payload_hash = _sha256_hex(data)
        headers = _auth_headers(conf, "PUT", key, payload_hash=payload_hash, content_type=content_type)
        url = _object_url(conf, key)
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.put(url, headers=headers, content=data)
        if resp.status_code in (200, 201):
            return True, None
        logger.warning("R2 PUT 실패: status=%s", resp.status_code)
        return False, f"r2_status_{resp.status_code}"
    except Exception as e:  # noqa: BLE001 — 자격증명/네트워크 실패는 본기능 비차단
        logger.warning("R2 PUT 예외: %s", str(e)[:120])
        return False, "r2_error"
