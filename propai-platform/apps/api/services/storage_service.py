"""Supabase Storage 업로드 서비스.

기존 인프라(서버 .env의 SUPABASE_URL/SERVICE_ROLE_KEY + config의 storage 버킷)를
재사용한다. 신규 파이썬 의존성 없이 httpx REST로 업로드한다.

흐름: 바이트 업로드 → 버킷 자동 보장(없으면 public 생성) → public URL 반환.
프론트는 base64(수 MB) 대신 짧은 URL만 보관하므로 localStorage 용량 문제도 해소된다.
"""

import os
import uuid

import httpx
import structlog

from apps.api.config import get_settings

logger = structlog.get_logger(__name__)

# 허용 이미지 형식 → 확장자
_ALLOWED_TYPES: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}
# 공용 콘텐츠 검증(inspect_upload)용 매직바이트 화이트리스트 — _ALLOWED_TYPES 와 1:1 대응.
_IMAGE_UPLOAD_KINDS = frozenset({"png", "jpeg", "gif", "webp"})


class StorageError(Exception):
    """스토리지 업로드 실패."""


class ContentRejectedError(StorageError):
    """콘텐츠 검증(content_inspection) 실패 전용 예외 — StorageError 를 상속한다(기존
    `except StorageError`만 있는 호출부도 하위호환으로 계속 잡는다).

    ★리뷰 필수 #2: 이 타입을 별도로 두는 이유는 "클라이언트 귀책(악성/위장 파일 거부)"과
    "서버측 인프라 장애(Supabase 다운 등)"를 **호출부가 구분해 다른 HTTP 상태를 매길 수 있게**
    하기 위함이다. 과거엔 둘 다 StorageError 하나로 뭉뚱그려져 라우터가 일괄 502 를 반환했는데,
    이는 악성 업로드 거부를 "일시적 서버 오류"로 오분류해 클라이언트 자동재시도·모니터링
    오탐(장애 알림)을 유발한다. 호출부는 `except ContentRejectedError`를 `except StorageError`
    보다 먼저 잡고 `exc.http_status`(4xx)를 응답 코드로 쓴다.
    """

    def __init__(self, code: str, reason: str) -> None:
        from app.services.security.content_inspection import http_status_for

        self.code = code
        self.reason = reason
        self.http_status = http_status_for(code)
        super().__init__(f"콘텐츠 검증 실패({code}): {reason}")


def _conf(env_names: tuple[str, ...], attr: str, default: str = "") -> str:
    """Supabase 설정값 읽기 — os.environ 우선, 그다음 캐시된 settings, 마지막 기본값.

    왜 os.environ 우선인가: 관리자 화면에서 등록한 키(SUPABASE_URL 등)는 앱 시작 시
    DB→os.environ 오버레이로 들어온다. 그런데 `get_settings()`는 @lru_cache 라
    최초 호출 시점의 env 만 캐시 → 오버레이가 그 뒤에 일어나면 settings 는 빈 값으로
    고착될 수 있다. os.environ 을 먼저 보면 ① 관리자 등록 URL 이 재배포 없이 반영되고
    ② .env 의 SERVICE_ROLE_KEY(보안상 관리자 DENYLIST 라 .env 전용) 도 확실히 반영된다.
    """
    for name in env_names:
        v = os.environ.get(name)
        if v:
            return v
    return (getattr(get_settings(), attr, "") or default)


async def _ensure_bucket(
    client: httpx.AsyncClient, base: str, bucket: str, headers: dict[str, str]
) -> None:
    """버킷 존재를 보장한다. 없으면 비공개 버킷으로 생성한다(멱등).

    보안: 자동 생성 버킷은 public=False. 공개 제공이 필요하면 관리자가
    Supabase 대시보드에서 명시적으로 public 전환한다(기존 버킷은 그대로 사용).
    """
    resp = await client.get(f"{base}/storage/v1/bucket/{bucket}", headers=headers)
    if resp.status_code == 200:
        return
    create = await client.post(
        f"{base}/storage/v1/bucket",
        headers=headers,
        json={"id": bucket, "name": bucket, "public": False},
    )
    if create.status_code in (200, 201):
        logger.info("Supabase Storage 버킷 생성", bucket=bucket)
        return
    # 동시성/기존 존재 등은 정상으로 간주
    if "already exists" in create.text.lower() or create.status_code == 409:
        return
    raise StorageError(f"버킷 생성 실패: {create.status_code} {create.text[:200]}")


async def upload_image(
    data: bytes, content_type: str, prefix: str = "site-images"
) -> str:
    """이미지 바이트를 Supabase Storage에 업로드하고 public URL을 반환한다.

    Args:
        data: 이미지 바이트
        content_type: MIME 타입 (image/png 등)
        prefix: 버킷 내 경로 프리픽스

    업로드 전 공용 콘텐츠 검증(content_inspection)을 additive 로 적용한다(★WP-H 세션2 전역 스윕):
    이 버킷은 공개(public)라 저장형 XSS(svg/html 위장)·실행파일 위장·MIME 위장이 즉시위험이다.
    실측 계열을 이미지 4종(png/jpeg/gif/webp)으로 화이트리스트하고, 검증 실패는
    ContentRejectedError(StorageError 서브클래스)로 명시 거부 — 라우터가 http_status(4xx)로 매핑한다.
    """
    from app.services.security.content_inspection import inspect_upload

    verdict = inspect_upload(data, "", content_type, expected_kinds=_IMAGE_UPLOAD_KINDS)
    if not verdict.allowed:
        raise ContentRejectedError(verdict.code, verdict.reason)

    base = _conf(("SUPABASE_URL",), "supabase_url").rstrip("/")
    # service_role 키는 두 이름 모두 허용 — 기존 SUPABASE_SERVICE_ROLE_KEY + 신규 대시보드
    # 명칭(SUPABASE_SERVICE_SECRET_KEY, sb_secret_…). 어느 이름으로 등록해도 동작.
    key = _conf(("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_SECRET_KEY"), "supabase_service_role_key")
    # 버킷명은 관리자 catalog(SUPABASE_BUCKET)·config(SUPABASE_STORAGE_BUCKET) 양쪽 키를 허용.
    bucket = _conf(("SUPABASE_BUCKET", "SUPABASE_STORAGE_BUCKET"), "supabase_storage_bucket", "propai-uploads")

    if not base or not key:
        raise StorageError(
            "Supabase Storage가 설정되지 않았습니다(SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY)."
        )

    ext = _ALLOWED_TYPES.get(content_type.lower())
    if not ext:
        raise StorageError(f"지원하지 않는 이미지 형식: {content_type}")

    path = f"{prefix}/{uuid.uuid4().hex}.{ext}"
    auth = {"Authorization": f"Bearer {key}", "apikey": key}

    async with httpx.AsyncClient(timeout=60.0) as client:
        await _ensure_bucket(client, base, bucket, auth)
        resp = await client.post(
            f"{base}/storage/v1/object/{bucket}/{path}",
            headers={**auth, "Content-Type": content_type, "x-upsert": "true"},
            content=data,
        )
        if resp.status_code not in (200, 201):
            raise StorageError(f"업로드 실패: {resp.status_code} {resp.text[:200]}")

    public_url = f"{base}/storage/v1/object/public/{bucket}/{path}"
    logger.info("이미지 업로드 완료", path=path, bytes=len(data))
    return public_url


# ── 등기부 PDF: 비공개 버킷 + 서명 URL(만료=TTL) ──

_REGISTRY_BUCKET = "propai-registry"


def _sb_conf() -> tuple[str, str]:
    base = _conf(("SUPABASE_URL",), "supabase_url").rstrip("/")
    key = _conf(("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_SECRET_KEY"), "supabase_service_role_key")
    if not base or not key:
        raise StorageError("Supabase Storage 미설정(SUPABASE_URL/SERVICE_ROLE_KEY)")
    return base, key


async def _ensure_private_bucket(client: httpx.AsyncClient, base: str, bucket: str, headers: dict) -> None:
    resp = await client.get(f"{base}/storage/v1/bucket/{bucket}", headers=headers)
    if resp.status_code == 200:
        return
    create = await client.post(
        f"{base}/storage/v1/bucket", headers=headers,
        json={"id": bucket, "name": bucket, "public": False},
    )
    if create.status_code in (200, 201) or "already exists" in create.text.lower() or create.status_code == 409:
        return
    raise StorageError(f"버킷 생성 실패: {create.status_code} {create.text[:160]}")


async def upload_registry_pdf(data: bytes, ttl_days: int = 30) -> dict[str, str]:
    """등기부 PDF를 비공개 버킷에 저장하고 만료 서명 URL을 반환한다(TTL=ttl_days)."""
    import datetime as _dt

    base, key = _sb_conf()
    auth = {"Authorization": f"Bearer {key}", "apikey": key}
    day = _dt.datetime.utcnow().strftime("%Y%m%d")
    path = f"registry/{day}/{uuid.uuid4().hex}.pdf"
    async with httpx.AsyncClient(timeout=60.0) as client:
        await _ensure_private_bucket(client, base, _REGISTRY_BUCKET, auth)
        up = await client.post(
            f"{base}/storage/v1/object/{_REGISTRY_BUCKET}/{path}",
            headers={**auth, "Content-Type": "application/pdf", "x-upsert": "true"},
            content=data,
        )
        if up.status_code not in (200, 201):
            raise StorageError(f"PDF 업로드 실패: {up.status_code} {up.text[:160]}")
        sign = await client.post(
            f"{base}/storage/v1/object/sign/{_REGISTRY_BUCKET}/{path}",
            headers=auth, json={"expiresIn": ttl_days * 86400},
        )
        if sign.status_code != 200:
            raise StorageError(f"서명URL 실패: {sign.status_code} {sign.text[:160]}")
        signed = (sign.json() or {}).get("signedURL") or ""
        url = f"{base}/storage/v1{signed}" if signed.startswith("/") else f"{base}/storage/v1/{signed}"
    logger.info("등기부 PDF 저장", path=path, bytes=len(data))
    return {"path": path, "url": url}


async def cleanup_registry_pdfs(days: int = 30) -> int:
    """registry/ 하위 날짜폴더 중 days 경과분을 삭제(TTL 자동삭제)."""
    import datetime as _dt

    base, key = _sb_conf()
    auth = {"Authorization": f"Bearer {key}", "apikey": key}
    cutoff = (_dt.datetime.utcnow() - _dt.timedelta(days=days)).strftime("%Y%m%d")
    deleted = 0
    async with httpx.AsyncClient(timeout=60.0) as client:
        folders = await client.post(
            f"{base}/storage/v1/object/list/{_REGISTRY_BUCKET}",
            headers=auth, json={"prefix": "registry/", "limit": 1000},
        )
        if folders.status_code != 200:
            return 0
        for f in folders.json() or []:
            name = f.get("name", "")
            if name and name.isdigit() and name < cutoff:
                objs = await client.post(
                    f"{base}/storage/v1/object/list/{_REGISTRY_BUCKET}",
                    headers=auth, json={"prefix": f"registry/{name}/", "limit": 1000},
                )
                paths = [f"registry/{name}/{o.get('name')}" for o in (objs.json() or []) if o.get("name")]
                if paths:
                    await client.request(
                        "DELETE", f"{base}/storage/v1/object/{_REGISTRY_BUCKET}",
                        headers=auth, json={"prefixes": paths},
                    )
                    deleted += len(paths)
    logger.info("등기부 PDF TTL 정리", deleted=deleted, days=days)
    return deleted


# ── 설계 참조도면(P7): 공개 버킷 propai-design-refs (DXF/PDF/이미지) ──

_DESIGN_REF_BUCKET = "propai-design-refs"
_DESIGN_EXT: dict[str, str] = {
    "application/pdf": "pdf",
    "image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg", "image/webp": "webp",
    "application/dxf": "dxf", "image/vnd.dxf": "dxf", "image/x-dxf": "dxf",
    "application/acad": "dwg", "image/vnd.dwg": "dwg", "application/x-dwg": "dwg",
}
# 매직바이트 화이트리스트(리뷰 필수 #3) — _DESIGN_EXT 가 허용하는 형식 계열과 1:1 대응.
# 이걸로 "시그니처 테이블에 없는(=미인식) 확장자 무통제 통과" 구멍도 함께 막는다(미인식=거부).
_DESIGN_UPLOAD_KINDS = frozenset({"pdf", "png", "jpeg", "webp", "dxf", "dwg"})


async def upload_design_file(data: bytes, content_type: str, file_name: str = "") -> dict[str, str]:
    """설계 참조도면(DXF/PDF/이미지)을 공개 버킷에 업로드하고 public URL+형식을 반환한다.

    업로드 전 공용 콘텐츠 검증(content_inspection)을 additive 로 적용한다(★기존 _DESIGN_EXT MIME
    allowlist 유지 + 강화): 실행/스크립트 위장·MIME 위장(선언≠실측)·경로 순회·압축폭탄(폴리글랏
    포함)·양성 화이트리스트(_DESIGN_UPLOAD_KINDS)를 차단한다.
    검증 실패는 ContentRejectedError(StorageError 서브클래스)로 명시 거부(무음 통과 금지) —
    라우터가 이를 먼저 잡아 http_status(4xx)로 매핑한다(진짜 인프라 장애 502 와 구분).
    """
    from app.services.security.content_inspection import inspect_upload

    verdict = inspect_upload(data, file_name, content_type, expected_kinds=_DESIGN_UPLOAD_KINDS)
    if not verdict.allowed:
        raise ContentRejectedError(verdict.code, verdict.reason)

    base, key = _sb_conf()
    ext = _DESIGN_EXT.get((content_type or "").lower())
    if not ext and file_name and "." in file_name:
        ext = file_name.rsplit(".", 1)[-1].lower()
    ext = (ext or "bin")[:8]
    path = f"refs/{uuid.uuid4().hex}.{ext}"
    auth = {"Authorization": f"Bearer {key}", "apikey": key}
    async with httpx.AsyncClient(timeout=120.0) as client:
        await _ensure_bucket(client, base, _DESIGN_REF_BUCKET, auth)
        resp = await client.post(
            f"{base}/storage/v1/object/{_DESIGN_REF_BUCKET}/{path}",
            headers={**auth, "Content-Type": content_type or "application/octet-stream", "x-upsert": "true"},
            content=data,
        )
        if resp.status_code not in (200, 201):
            raise StorageError(f"설계도면 업로드 실패: {resp.status_code} {resp.text[:200]}")
    url = f"{base}/storage/v1/object/public/{_DESIGN_REF_BUCKET}/{path}"
    logger.info("설계 참조도면 업로드", path=path, bytes=len(data))
    return {"url": url, "file_type": ext}


# ── SP3 회의방 자료교환: 비공개 버킷 propai-collab-docs (협력업체 심의문서, TTL 서명URL) ──
#    민감 협력업체 문서 → 비공개+만료 서명URL(upload_registry_pdf 패턴). 멤버만 시간제한 접근.

_COLLAB_BUCKET = "propai-collab-docs"


async def upload_collab_document(
    data: bytes, content_type: str, filename: str = "", ttl_days: int = 14
) -> dict[str, str]:
    """협업 회의방 문서를 비공개 버킷에 저장하고 만료 서명 URL을 반환한다(TTL=ttl_days).

    실파일은 Supabase 비공개 버킷에만 저장하고, DB(ProjectDocument)엔 path+서명URL 메타만 보관한다.
    저장 경로 자체는 서버측 uuid로 생성(원본 파일명은 DB 메타에만, 경로 traversal 차단).

    ★전역 스윕(리뷰 권장 반영): purpose=storage 는 제품 의도상 "임의 형식 무제한"이라
    expected_kinds 화이트리스트는 걸지 않는다(형식 자체는 제한하지 않음). 대신 실행/스크립트·웹
    활성 콘텐츠(svg/html/js)·MIME 위장·압축폭탄(zip bomb)·zip slip 은 형식과 무관하게 항상
    위험이므로 공용 헬퍼로 방어한다. 호출부(라우터)의 기존 `is_blocked_upload` 1차 검사에
    additive — 검증 실패는 ContentRejectedError 로 명시 거부.
    """
    import datetime as _dt

    from app.services.security.content_inspection import inspect_upload

    verdict = inspect_upload(data, filename, content_type)
    if not verdict.allowed:
        raise ContentRejectedError(verdict.code, verdict.reason)

    base, key = _sb_conf()
    auth = {"Authorization": f"Bearer {key}", "apikey": key}
    day = _dt.datetime.utcnow().strftime("%Y%m%d")
    ext = filename.rsplit(".", 1)[-1].lower() if filename and "." in filename else "bin"
    safe_ext = "".join(ch for ch in ext if ch.isalnum())[:8] or "bin"
    path = f"collab/{day}/{uuid.uuid4().hex}.{safe_ext}"
    async with httpx.AsyncClient(timeout=120.0) as client:
        await _ensure_private_bucket(client, base, _COLLAB_BUCKET, auth)
        up = await client.post(
            f"{base}/storage/v1/object/{_COLLAB_BUCKET}/{path}",
            headers={**auth, "Content-Type": content_type or "application/octet-stream", "x-upsert": "true"},
            content=data,
        )
        if up.status_code not in (200, 201):
            raise StorageError(f"협업 문서 업로드 실패: {up.status_code} {up.text[:160]}")
        url = await _sign_collab_path(client, base, auth, path, ttl_days)
    logger.info("협업 문서 저장", path=path, bytes=len(data))
    return {"path": path, "url": url}


async def sign_collab_document(path: str, ttl_days: int = 14) -> str:
    """저장된 협업 문서 path에 새 서명 URL을 발급한다(읽기 시 만료 재서명용)."""
    base, key = _sb_conf()
    auth = {"Authorization": f"Bearer {key}", "apikey": key}
    async with httpx.AsyncClient(timeout=30.0) as client:
        return await _sign_collab_path(client, base, auth, path, ttl_days)


async def download_collab_document(path: str) -> bytes:
    """비공개 버킷의 협업 문서를 다운로드한다(단기 서명 후 GET) — 서버측 재파싱(뷰어)용."""
    base, key = _sb_conf()
    auth = {"Authorization": f"Bearer {key}", "apikey": key}
    async with httpx.AsyncClient(timeout=60.0) as client:
        url = await _sign_collab_path(client, base, auth, path, 1)  # 1일 단기 서명
        resp = await client.get(url)
        if resp.status_code != 200:
            raise StorageError(f"문서 다운로드 실패: {resp.status_code} {resp.text[:120]}")
        return resp.content


async def _sign_collab_path(
    client: httpx.AsyncClient, base: str, auth: dict, path: str, ttl_days: int
) -> str:
    sign = await client.post(
        f"{base}/storage/v1/object/sign/{_COLLAB_BUCKET}/{path}",
        headers=auth, json={"expiresIn": ttl_days * 86400},
    )
    if sign.status_code != 200:
        raise StorageError(f"서명URL 실패: {sign.status_code} {sign.text[:160]}")
    signed = (sign.json() or {}).get("signedURL") or ""
    return f"{base}/storage/v1{signed}" if signed.startswith("/") else f"{base}/storage/v1/{signed}"
