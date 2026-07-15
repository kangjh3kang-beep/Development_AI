"""업로드 콘텐츠 보안 검증 헬퍼 (P0 콘텐츠 보안 최소형).

왜 필요한가: 확장자·선언 content_type 은 클라이언트가 위조할 수 있다(png 라 우기며 exe 를
올리는 식). 그래서 "실제 바이트(매직바이트)"로 형식을 검증하고, 압축파일은 풀기 전에
한도(압축비·엔트리 수·전개 총량·재귀 깊이)를 검사해 zip bomb 를 막고, 파일명·아카이브 내부
경로의 순회(../)를 차단한다.

핵심 계약(★): `inspect_upload()` 는 **예외를 던지지 않는다**. 항상 `InspectionResult` 를 반환한다.
이렇게 두 가지를 명확히 구분한다.
  1) 검증 헬퍼 자체 오류(내부 버그·손상 아카이브 파싱 예외) → 500 으로 업로드 경로 전체를
     죽이지 않는다. 대신 그 검사를 실패로 처리하고 구조화 결과로 돌려준다.
  2) 보안 검증 실패(위장·bomb·순회 탐지) → **fail-closed**(allowed=False). 호출부는 4xx 로 거부한다.
  즉, 내부 오류든 위반이든 "확실히 안전"을 증명 못 하면 통과시키지 않는다(보안 우선). 다만
  크래시(500)로 번지지 않게 헬퍼가 삼켜서 구조화 거부로 변환한다.

폴백 전략(★): 매직바이트 판별의 **정본은 자체 시그니처 테이블**이다. `python-magic`(libmagic)
이 설치돼 있으면 부가 신호로 함께 기록(details.libmagic)하되, 판정 자체는 시그니처 테이블이
담당한다 → 라이브러리 유무와 무관하게 동작·판정이 동일(배포 리스크 없는 선택적 의존).

AV(ClamAV): 데몬 미설치가 기본값이다(사용자 결정 D4). `av_scan()` 은 데몬이 없으면 "미수행"
상태를 **정직하게** 반환한다(날조 'clean' 금지). AV 미수행은 그 자체로 거부 사유가 아니다
(Gate-OFF) — 매직바이트·아카이브 한도까지가 이번 게이트의 차단선이다.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger(__name__)


# ── 아카이브 한도(zip bomb 방어) ─────────────────────────────────────────
@dataclass(frozen=True)
class ArchiveLimits:
    """압축파일 검사 한도. 기본값은 일반 문서(docx/xlsx/hwpx)·설계 zip 을 넉넉히 통과시키되
    악의적 bomb(수십MB→수십GB 전개, 수십만 엔트리)는 막도록 잡았다."""

    max_entries: int = 4096  # 엔트리(파일) 개수 상한
    max_total_uncompressed: int = 500 * 1024 * 1024  # 전개 총량 상한(500MB)
    max_ratio: float = 120.0  # 압축비 상한(전개/압축) — 정상 문서는 보통 <20, bomb 은 1000+
    max_depth: int = 3  # 중첩 아카이브 재귀 깊이(zip 안의 zip …). 루트 아래 허용 단계 수.
    ratio_min_compressed: int = 4096  # 이 크기 미만 소형 엔트리는 압축비 계산 제외(작은 텍스트 오탐 방지)
    max_nested_read: int = 64 * 1024 * 1024  # 중첩 아카이브 재귀 검사 시 실제로 읽는 엔트리 상한(64MB)


_DEFAULT_LIMITS = ArchiveLimits()


# ── 시그니처 테이블(매직바이트 → 정규 형식) ──────────────────────────────
# (offset, magic bytes, 정규 형식명). 순서 중요(더 구체적인 것 먼저).
_SIGNATURES: list[tuple[int, bytes, str]] = [
    (0, b"\x89PNG\r\n\x1a\n", "png"),
    (0, b"\xff\xd8\xff", "jpeg"),
    (0, b"GIF87a", "gif"),
    (0, b"GIF89a", "gif"),
    (0, b"%PDF-", "pdf"),
    (0, b"PK\x03\x04", "zip"),  # zip 기반(xlsx/docx/hwpx/pptx/zip). PK\x05\x06=빈zip, PK\x07\x08=스팬
    (0, b"PK\x05\x06", "zip"),
    (0, b"PK\x07\x08", "zip"),
    (0, b"AC10", "dwg"),  # AutoCAD DWG(AC1012~AC1032). 뒤 2자리는 버전.
    (0, b"AutoCAD Binary DXF", "dxf"),  # 바이너리 DXF
]

# 실행/스크립트 시그니처(악성 가능) — 기존 collaboration_rules.is_blocked_upload 를 일반화·확장.
_EXECUTABLE_SIGNATURES: list[tuple[int, bytes, str]] = [
    (0, b"MZ", "exe"),  # Windows PE(.exe/.dll)
    (0, b"\x7fELF", "elf"),  # Linux ELF
    (0, b"\xfe\xed\xfa\xce", "macho"),
    (0, b"\xfe\xed\xfa\xcf", "macho"),
    (0, b"\xca\xfe\xba\xbe", "macho"),  # Mach-O fat / java class
    (0, b"\xcf\xfa\xed\xfe", "macho"),
    (0, b"#!", "script"),  # shell/script shebang
]

# 실행 확장자(zip 기반 .jar 포함) — 시그니처가 무해해 보여도 확장자로 차단.
_BLOCKED_EXTS = frozenset(
    {"exe", "dll", "so", "dylib", "bat", "cmd", "com", "scr", "msi", "sh", "ps1", "jar", "app", "bin"}
)

# 선언 MIME → 정규 형식 계열(위장 판정용). 우리가 아는 계열만 사상(모르는 MIME 은 판정 보류).
_MIME_TO_KIND: dict[str, str] = {
    "image/png": "png",
    "image/jpeg": "jpeg",
    "image/jpg": "jpeg",
    "image/gif": "gif",
    "image/webp": "webp",
    "application/pdf": "pdf",
    "application/zip": "zip",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "zip",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "zip",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "zip",
    "application/dxf": "dxf",
    "image/vnd.dxf": "dxf",
    "image/x-dxf": "dxf",
    "application/acad": "dwg",
    "image/vnd.dwg": "dwg",
    "application/x-dwg": "dwg",
}

# 같은 계열로 취급(위장 아님)하는 그룹 — 예: zip 을 xlsx/docx 로 선언해도 동일 계열이라 정상.
_KIND_ALIASES: dict[str, str] = {
    "jpg": "jpeg",
}


@dataclass
class InspectionResult:
    """검사 결과(구조화). allowed=False 면 호출부가 4xx 로 거부한다(fail-closed)."""

    allowed: bool
    code: str  # ok|empty|too_large|executable|path_traversal|mime_mismatch|
    #            unsupported_type|archive_bomb|archive_corrupt|inspection_error
    reason: str  # 사람이 읽는 한국어 사유
    declared_type: str | None = None  # 선언된 형식 계열(있으면)
    detected_type: str | None = None  # 실측된 형식 계열(매직바이트)
    av: dict = field(default_factory=dict)  # AV 스캔 상태(정직: not_scanned 가능)
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "code": self.code,
            "reason": self.reason,
            "declared_type": self.declared_type,
            "detected_type": self.detected_type,
            "av": self.av,
            "details": self.details,
        }


def _ext(filename: str) -> str:
    name = (filename or "").strip().lower()
    return name.rsplit(".", 1)[-1] if "." in name else ""


def _match_signatures(data: bytes, table: list[tuple[int, bytes, str]]) -> str | None:
    """시그니처 테이블에서 첫 일치 형식명을 반환. WEBP(RIFF....WEBP)는 별도 처리 필요."""
    for offset, magic, kind in table:
        if data[offset : offset + len(magic)] == magic:
            return kind
    return None


def sniff_type(data: bytes) -> str | None:
    """실제 바이트로 형식 계열을 판별한다(정본=시그니처 테이블). 미지원/미상은 None.

    반환 예: 'png'|'jpeg'|'gif'|'webp'|'pdf'|'zip'|'dwg'|'dxf'|'ifc'|None.
    실행 시그니처(exe/elf/…)는 여기서 판별하지 않는다(_detect_executable 별도).
    """
    data = data or b""
    if not data:
        return None
    # WEBP: RIFF????WEBP (앞 4바이트 RIFF, 8~12바이트 WEBP)
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    kind = _match_signatures(data, _SIGNATURES)
    if kind:
        return kind
    # IFC: 텍스트(STEP) — 'ISO-10303' 헤더를 앞부분에서 확인.
    head = data[:512]
    if b"ISO-10303" in head:
        return "ifc"
    # ASCII DXF: 강한 매직이 없다. 텍스트(널바이트 없음)이면서 DXF 마커가 앞부분에 있으면 dxf.
    if b"\x00" not in head and (b"SECTION" in head or b"HEADER" in head) and _looks_dxf(head):
        return "dxf"
    return None


def _looks_dxf(head: bytes) -> bool:
    """ASCII DXF 휴리스틱: 그룹코드 '0' 다음 SECTION, 또는 초반 주석(999)/AutoCAD 흔적."""
    try:
        text = head.decode("utf-8", "ignore")
    except Exception:  # noqa: BLE001
        return False
    up = text.upper()
    return ("SECTION" in up and ("HEADER" in up or "ENTITIES" in up or "TABLES" in up)) or "AUTOCAD" in up


def _libmagic_mime(data: bytes) -> str | None:
    """python-magic(libmagic) 가 있으면 MIME 을 부가 신호로 반환. 없으면 None(정본 아님)."""
    try:
        import magic  # type: ignore

        return magic.from_buffer(data[:4096], mime=True)  # type: ignore[no-any-return]
    except Exception:  # noqa: BLE001 — 미설치/오류 시 조용히 폴백(시그니처 테이블이 정본)
        return None


def _detect_executable(data: bytes, filename: str) -> str | None:
    """실행/스크립트면 그 종류(exe/elf/macho/script/ext:<확장자>)를 반환, 아니면 None."""
    ext = _ext(filename)
    if ext in _BLOCKED_EXTS:
        return f"ext:{ext}"
    return _match_signatures(data or b"", _EXECUTABLE_SIGNATURES)


def _has_traversal(name: str) -> bool:
    """경로 순회/절대경로/드라이브 지정이면 True. 아카이브 내부 이름·업로드 파일명 공통."""
    if not name:
        return False
    n = name.replace("\\", "/")
    if n.startswith("/") or n.startswith("~"):
        return True
    if len(n) >= 2 and n[1] == ":":  # 윈도우 드라이브(C:\ …)
        return True
    parts = n.split("/")
    return ".." in parts  # 세그먼트 단위 '..' (부분문자열 오탐 방지: '..foo' 는 정상)


def _canon_kind(kind: str | None) -> str | None:
    if kind is None:
        return None
    return _KIND_ALIASES.get(kind, kind)


def inspect_archive(data: bytes, limits: ArchiveLimits = _DEFAULT_LIMITS) -> InspectionResult:
    """zip 계열 아카이브를 **풀지 않고** 중앙 디렉터리 메타로 한도 검사한다(zip bomb 방어).

    검사: 엔트리 수·전개 총량·엔트리별 압축비·내부 경로 순회·중첩 아카이브 재귀 깊이.
    zipfile 은 각 엔트리의 file_size(전개크기)/compress_size 를 central directory 에서
    바로 읽으므로, 실제 압축해제(디스크·메모리 폭발) 없이 bomb 여부를 판정할 수 있다.
    중첩 아카이브만은 그 엔트리 바이트를 읽어야 하나(그 엔트리 1개만 부분 해제), 읽기 전에
    선언 전개크기를 상한으로 걸러 재귀 bomb 도 막는다.
    """
    return _inspect_archive_depth(data, limits, depth=0)


def _inspect_archive_depth(data: bytes, limits: ArchiveLimits, depth: int) -> InspectionResult:
    if depth > limits.max_depth:
        return InspectionResult(
            allowed=False, code="archive_bomb",
            reason=f"중첩 압축 깊이 초과(최대 {limits.max_depth}단계) — 재귀 압축폭탄 의심.",
            detected_type="zip", details={"depth": depth},
        )
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            infos = zf.infolist()
            if len(infos) > limits.max_entries:
                return InspectionResult(
                    allowed=False, code="archive_bomb",
                    reason=f"압축 내부 파일 수 초과({len(infos)} > {limits.max_entries}).",
                    detected_type="zip", details={"entries": len(infos)},
                )
            total_uncompressed = 0
            for zi in infos:
                # 내부 경로 순회 차단(zip slip): ../ 또는 절대경로 엔트리.
                if _has_traversal(zi.filename):
                    return InspectionResult(
                        allowed=False, code="path_traversal",
                        reason=f"압축 내부에 경로 순회 항목이 있습니다: {zi.filename[:80]}",
                        detected_type="zip", details={"entry": zi.filename[:120]},
                    )
                total_uncompressed += zi.file_size
                if total_uncompressed > limits.max_total_uncompressed:
                    return InspectionResult(
                        allowed=False, code="archive_bomb",
                        reason=(f"압축 전개 총량 초과({total_uncompressed} > "
                                f"{limits.max_total_uncompressed} bytes) — 압축폭탄 의심."),
                        detected_type="zip", details={"total_uncompressed": total_uncompressed},
                    )
                # 엔트리별 압축비(작은 엔트리는 제외 — 헤더만 있는 작은 텍스트 오탐 방지).
                if zi.compress_size >= limits.ratio_min_compressed:
                    ratio = zi.file_size / max(zi.compress_size, 1)
                    if ratio > limits.max_ratio:
                        return InspectionResult(
                            allowed=False, code="archive_bomb",
                            reason=(f"압축비 초과({ratio:.0f} > {limits.max_ratio:.0f}) — "
                                    f"압축폭탄 의심: {zi.filename[:80]}"),
                            detected_type="zip",
                            details={"ratio": round(ratio, 1), "entry": zi.filename[:120]},
                        )
                # 중첩 아카이브 재귀 — 이름이 아카이브인 엔트리만, 메모리 폭발 방지 상한(max_nested_read)
                # 이내에서 1개만 해제해 재귀 검사. 깊이 초과는 자식 호출의 상단 가드가 archive_bomb 로 차단.
                if _entry_is_nested_archive(zi) and zi.file_size <= limits.max_nested_read:
                    try:
                        nested = zf.read(zi)  # 이 엔트리 1개만 해제(상한 검증 후)
                    except Exception:  # noqa: BLE001 — 손상 중첩은 거부(fail-closed)
                        return InspectionResult(
                            allowed=False, code="archive_corrupt",
                            reason=f"중첩 압축 해제 실패(손상 의심): {zi.filename[:80]}",
                            detected_type="zip", details={"entry": zi.filename[:120]},
                        )
                    if nested[:2] == b"PK":
                        sub = _inspect_archive_depth(nested, limits, depth + 1)
                        if not sub.allowed:
                            return sub
            return InspectionResult(
                allowed=True, code="ok", reason="아카이브 한도 통과.",
                detected_type="zip",
                details={"entries": len(infos), "total_uncompressed": total_uncompressed, "depth": depth},
            )
    except zipfile.BadZipFile:
        # PK 시그니처인데 zip 파싱 실패 = 손상/위장 → fail-closed.
        return InspectionResult(
            allowed=False, code="archive_corrupt",
            reason="손상되었거나 유효하지 않은 압축 파일입니다.",
            detected_type="zip", details={},
        )


def _entry_is_nested_archive(zi: zipfile.ZipInfo) -> bool:
    name = (zi.filename or "").lower()
    return name.endswith((".zip", ".xlsx", ".docx", ".pptx", ".hwpx", ".jar"))


def av_scan(data: bytes) -> dict:
    """ClamAV 데몬이 있으면 스캔, 없으면 '미수행'을 **정직하게** 반환한다(날조 clean 금지).

    반환:
      {"status": "clean"|"infected"|"error"|"not_scanned", "engine": ..., "reason"/"signature": ...}
    데몬 미설치(사용자 결정 D4)가 기본값이라 실제 운영에서는 대개 not_scanned 다. not_scanned 는
    그 자체로 거부 사유가 아니다(Gate-OFF) — 호출부는 매직바이트·아카이브 한도로 차단한다.
    """
    try:
        import clamd  # type: ignore
    except Exception:  # noqa: BLE001 — 라이브러리 미설치
        return {"status": "not_scanned", "reason": "clamd_library_unavailable"}
    try:
        try:
            cd = clamd.ClamdUnixSocket()  # type: ignore[attr-defined]
            cd.ping()
        except Exception:  # noqa: BLE001 — 유닉스 소켓 실패 시 네트워크 소켓 시도
            cd = clamd.ClamdNetworkSocket()  # type: ignore[attr-defined]
            cd.ping()
    except Exception:  # noqa: BLE001 — 데몬 미기동/미설치 → 정직하게 미수행
        return {"status": "not_scanned", "reason": "clamav_daemon_unavailable"}
    try:
        res = cd.instream(io.BytesIO(data))  # {'stream': ('FOUND'|'OK', sig|None)}
        status, sig = res.get("stream", ("ERROR", None))
        if status == "OK":
            return {"status": "clean", "engine": "clamav"}
        if status == "FOUND":
            return {"status": "infected", "engine": "clamav", "signature": sig}
        return {"status": "error", "engine": "clamav", "reason": str(status)}
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "engine": "clamav", "reason": str(e)[:120]}


def inspect_upload(
    data: bytes,
    filename: str = "",
    declared_content_type: str | None = None,
    *,
    expected_kinds: set[str] | None = None,
    max_bytes: int | None = None,
    allow_archive: bool = True,
    archive_limits: ArchiveLimits = _DEFAULT_LIMITS,
    run_av: bool = True,
) -> InspectionResult:
    """업로드 바이트를 종합 검증한다. **절대 예외를 던지지 않는다**(항상 InspectionResult).

    검사 순서(빠른 거부 우선):
      1) 빈 파일 / 크기 상한
      2) 실행/스크립트(시그니처·확장자) → 거부
      3) 파일명 경로 순회 → 거부
      4) 매직바이트 실측 + 선언 MIME 위장 탐지(선언 계열 ≠ 실측 계열) → 거부
      5) expected_kinds 지정 시 실측 계열이 허용목록 밖 → 거부
      6) 아카이브(zip 계열)면 한도 검사(zip bomb·zip slip)
      7) AV 스캔(있으면) — 감염만 거부, 미수행은 통과(Gate-OFF, 정직 기록)

    Args:
        expected_kinds: 허용 형식 계열 집합(예: {"pdf","png","jpeg","dxf","ifc","zip"}). None 이면
            형식 화이트리스트 검사 생략(실행/위장/bomb 검사는 그대로 수행).
        max_bytes: 크기 상한(None 이면 검사 안 함 — 라우터가 이미 검사하는 경우).
    """
    try:
        return _inspect_upload_impl(
            data, filename, declared_content_type,
            expected_kinds=expected_kinds, max_bytes=max_bytes,
            allow_archive=allow_archive, archive_limits=archive_limits, run_av=run_av,
        )
    except Exception as e:  # noqa: BLE001 — 헬퍼 내부 오류는 500 이 아니라 fail-closed 거부로.
        logger.warning("content_inspection 내부 오류(fail-closed 거부)", error=str(e)[:160])
        return InspectionResult(
            allowed=False, code="inspection_error",
            reason="콘텐츠 검증 중 오류가 발생해 안전을 확인할 수 없습니다(업로드 거부).",
            details={"error": str(e)[:160]},
        )


def _inspect_upload_impl(
    data: bytes,
    filename: str,
    declared_content_type: str | None,
    *,
    expected_kinds: set[str] | None,
    max_bytes: int | None,
    allow_archive: bool,
    archive_limits: ArchiveLimits,
    run_av: bool,
) -> InspectionResult:
    data = data or b""
    declared_kind = _canon_kind(_MIME_TO_KIND.get((declared_content_type or "").split(";")[0].strip().lower()))

    # 1) 빈 파일 / 크기
    if not data:
        return InspectionResult(False, "empty", "빈 파일입니다.", declared_type=declared_kind)
    if max_bytes is not None and len(data) > max_bytes:
        return InspectionResult(
            False, "too_large", f"파일이 너무 큽니다({len(data)} > {max_bytes} bytes).",
            declared_type=declared_kind, details={"size": len(data)},
        )

    # 2) 실행/스크립트 차단
    exe = _detect_executable(data, filename)
    if exe:
        return InspectionResult(
            False, "executable",
            "실행·스크립트 파일은 업로드할 수 없습니다.",
            declared_type=declared_kind, detected_type=exe, details={"executable": exe},
        )

    # 3) 파일명 경로 순회
    if _has_traversal(filename):
        return InspectionResult(
            False, "path_traversal", f"파일명에 경로 순회가 포함됩니다: {filename[:80]}",
            declared_type=declared_kind, details={"filename": filename[:120]},
        )

    # 4) 매직바이트 실측 + 위장 탐지
    detected = _canon_kind(sniff_type(data))
    libmagic = _libmagic_mime(data)  # 부가 신호(정본 아님)
    if declared_kind is not None and detected is not None and declared_kind != detected:
        return InspectionResult(
            False, "mime_mismatch",
            (f"선언한 형식({declared_content_type})과 실제 내용({detected})이 다릅니다"
             " — 위장 파일로 판단해 거부합니다."),
            declared_type=declared_kind, detected_type=detected,
            av={}, details={"libmagic": libmagic},
        )

    # 5) 형식 화이트리스트(호출부가 지정한 허용 계열)
    if expected_kinds is not None:
        allowed_kinds = {_canon_kind(k) for k in expected_kinds}
        if detected is None:
            return InspectionResult(
                False, "unsupported_type",
                "지원하지 않거나 판별할 수 없는 파일 형식입니다(매직바이트 미인식).",
                declared_type=declared_kind, detected_type=None, details={"libmagic": libmagic},
            )
        if detected not in allowed_kinds:
            return InspectionResult(
                False, "unsupported_type",
                f"허용되지 않는 파일 형식입니다(실측: {detected}).",
                declared_type=declared_kind, detected_type=detected,
                details={"expected": sorted(k for k in allowed_kinds if k), "libmagic": libmagic},
            )

    # 6) 아카이브 한도(zip bomb·zip slip)
    if detected == "zip" and allow_archive:
        arc = inspect_archive(data, archive_limits)
        if not arc.allowed:
            arc.declared_type = declared_kind
            arc.details.setdefault("libmagic", libmagic)
            return arc

    # 7) AV 스캔(있으면) — 감염만 차단. 미수행/에러는 통과(Gate-OFF, 정직 기록).
    av = av_scan(data) if run_av else {"status": "skipped"}
    if av.get("status") == "infected":
        return InspectionResult(
            False, "av_infected",
            f"악성코드가 탐지되었습니다({av.get('signature')}).",
            declared_type=declared_kind, detected_type=detected, av=av,
        )

    return InspectionResult(
        allowed=True, code="ok", reason="검증 통과.",
        declared_type=declared_kind, detected_type=detected, av=av,
        details={"size": len(data), "libmagic": libmagic},
    )
