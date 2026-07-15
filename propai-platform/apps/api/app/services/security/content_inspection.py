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

import contextlib
import io
import zipfile
from dataclasses import dataclass, field
from urllib.parse import unquote

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
    (0, b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "ole2"),  # 레거시 OLE2 CFBF(.xls/.doc/.ppt 97-2003)
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

# 실행 확장자(zip 기반 .jar 포함) + 웹 활성 콘텐츠 확장자 — 시그니처가 무해해 보여도 확장자로
# 차단한다. HTML/SVG/JS 등은 브라우저가 그대로 실행·렌더링할 수 있는 콘텐츠라, 이미지·문서로
# 위장해 공개 버킷에 올라가면 저장형 XSS(stored XSS) 매개체가 된다(리뷰 우회 PoC #4 반영).
_BLOCKED_EXTS = frozenset({
    # 실행/스크립트
    "exe", "dll", "so", "dylib", "bat", "cmd", "com", "scr", "msi", "sh", "ps1", "jar", "app", "bin",
    # 웹 활성 콘텐츠(저장형 XSS 방지)
    "html", "htm", "xhtml", "svg", "svgz", "js", "mjs", "xml", "py", "rb", "pl", "php", "phtml",
})

# 선언 MIME 만으로도 활성 콘텐츠로 간주해 거부 — 파일명 확장자를 무해하게(예: photo.png) 지어도
# content_type 을 svg/html 등으로 선언하면 차단한다(확장자 위장의 역방향 우회 방지).
_ACTIVE_CONTENT_MIMES = frozenset({
    "image/svg+xml", "text/html", "application/xhtml+xml",
    "application/javascript", "text/javascript", "application/x-javascript",
})

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
    #            unsupported_type|archive_bomb|archive_corrupt|av_infected|inspection_error
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
    """경로 순회/절대경로/드라이브 지정이면 True. 아카이브 내부 이름·업로드 파일명 공통.

    ★퍼센트 인코딩 우회 방어(권장 반영): 판정 전에 1회 unquote 한다(예: '%2e%2e%2f' →
    '../'). unquote 는 잘못된 인코딩이어도 예외 없이 원문을 최대한 그대로 반환하므로 안전하다.
    """
    if not name:
        return False
    n = unquote(name).replace("\\", "/")
    if n.startswith("/") or n.startswith("~"):
        return True
    if len(n) >= 2 and n[1] == ":":  # 윈도우 드라이브(C:\ …)
        return True
    parts = n.split("/")
    return ".." in parts  # 세그먼트 단위 '..' (부분문자열 오탐 방지: '..foo' 는 정상)


def _active_content_mime_reason(declared_content_type: str | None) -> str | None:
    """선언 MIME 만으로 웹 활성 콘텐츠(svg/html/js 등)인지 판별한다. 확장자 쪽은 이미
    `_detect_executable`(_BLOCKED_EXTS 확장)이 담당하므로 여기선 MIME 전용(확장자 위장의
    역방향 우회 — 무해한 파일명 + 활성 MIME 선언 — 방지). 아니면 None.
    """
    ct = (declared_content_type or "").split(";")[0].strip().lower()
    return f"mime:{ct}" if ct in _ACTIVE_CONTENT_MIMES else None


def _canon_kind(kind: str | None) -> str | None:
    if kind is None:
        return None
    return _KIND_ALIASES.get(kind, kind)


def _has_archive_structure(data: bytes) -> bool:
    """폴리글랏 방어(리뷰 우회 PoC #1): 선두 매직바이트와 무관하게 데이터 안에 유효한 zip 구조
    (EOCD 레코드)가 있는지 확인한다.

    `zipfile.is_zipfile`은 파일 끝에서부터 EOCD 시그니처를 찾아 판정하므로, 앞부분에 PNG 등
    다른 형식의 헤더를 붙이고 뒤에 zip 을 이어붙인 폴리글랏(self-extracting 형식과 동일 원리)도
    탐지한다. 과거 코드는 `sniff_type()`이 선두 매직만 보고 "png"를 반환하면 아카이브 검사
    자체가 생략됐다 — 이 함수는 detected 타입과 무관하게 별도로 호출해 그 구멍을 막는다.
    """
    try:
        return zipfile.is_zipfile(io.BytesIO(data))
    except Exception:  # noqa: BLE001 — 판별 실패는 "아카이브 아님"으로 보수적 처리(호출부가 이어서 판단)
        return False


def inspect_archive(data: bytes, limits: ArchiveLimits = _DEFAULT_LIMITS) -> InspectionResult:
    """zip 계열 아카이브를 **풀지 않고** 중앙 디렉터리 메타로 한도 검사한다(zip bomb 방어).

    검사: 엔트리 수·전개 총량·엔트리별 압축비·내부 경로 순회·중첩 아카이브 재귀 깊이.
    zipfile 은 각 엔트리의 file_size(전개크기)/compress_size 를 central directory 에서
    바로 읽으므로, 실제 압축해제(디스크·메모리 폭발) 없이 bomb 여부를 판정할 수 있다.
    중첩 아카이브 후보만은 그 엔트리 바이트를 상한 이내로 읽어야 하나(부분 해제), 읽기 전에
    선언 전개크기를 상한(max_nested_read)으로 걸러 재귀 bomb 도 막는다.

    ★정직한 한계(central directory 신뢰의 한계 — 항목 5 반영): 전개총량·압축비 판정은 central
    directory 가 **선언**하는 file_size/compress_size 를 신뢰한다. 이 메타데이터 자체가
    조작된 zip(로컬 헤더와 central directory 불일치, data-descriptor 트릭 등)에 대해서는
    이 정적 검사가 advisory(참고용)이며 절대적 백스톱이 아니다 — 진짜 최종 방어선은 **실제
    소비자(압축해제 코드)가 CRC 검증 + 바이트 상한 truncate 로 읽는 것**이다(예: 스트리밍
    압축해제 중 상한 초과 시 즉시 중단). 이 헬퍼는 "명백한 bomb 조기 차단"이 목적이며, 완전한
    무결성 보증을 대체하지 않는다.
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
                # 중첩 아카이브 재귀 — ★확장자가 아니라 내용(PK 매직)으로 판별한다(리뷰 우회 PoC #1
                # 반영: 내부 zip 을 .bin 등으로 리네임해 확장자 검사를 우회하는 공격 방어). 먼저
                # 4바이트만 저비용 peek(ZipExtFile 스트리밍 — 전체 압축해제 없이 앞부분만 뽑아냄)
                # 하고, PK 매직이 맞을 때만 상한(max_nested_read) 이내에서 전체를 읽어 재귀 검사한다.
                peek = _peek_entry(zf, zi, 4)
                if peek is not None and peek[:2] == b"PK" and zi.file_size <= limits.max_nested_read:
                    try:
                        with zf.open(zi) as fh:
                            nested = fh.read(limits.max_nested_read + 1)
                    except Exception:  # noqa: BLE001 — 손상 중첩은 거부(fail-closed)
                        return InspectionResult(
                            allowed=False, code="archive_corrupt",
                            reason=f"중첩 압축 해제 실패(손상 의심): {zi.filename[:80]}",
                            detected_type="zip", details={"entry": zi.filename[:120]},
                        )
                    if len(nested) > limits.max_nested_read:
                        # 선언 file_size(central directory)는 상한 이내였는데 실제 읽은 바이트가
                        # 더 많다 — 메타데이터 스푸핑 의심(위 docstring의 "정직한 한계" 사례).
                        # 여기선 실제 읽은 바이트 기준으로 fail-closed(advisory 판단에 안주하지 않음).
                        return InspectionResult(
                            allowed=False, code="archive_bomb",
                            reason=(f"중첩 엔트리 실제 전개크기가 선언과 불일치(스푸핑 의심): "
                                    f"{zi.filename[:80]}"),
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


def _peek_entry(zf: zipfile.ZipFile, zi: zipfile.ZipInfo, n: int) -> bytes | None:
    """엔트리의 첫 n바이트만 저비용으로 peek 한다(확장자가 아닌 내용으로 중첩 아카이브 판별).

    zipfile.ZipExtFile 은 스트리밍 압축해제라 read(n)은 n바이트를 만드는 데 필요한 만큼만
    압축해제한다 — 전체 엔트리를 풀지 않으므로 엔트리 수가 많아도(최대 max_entries) 비용이
    작다. 읽기 실패(손상·미지원 압축방식·암호화 등)면 None — 그 경우 이 엔트리는 중첩판별을
    보류할 뿐, 이미 계산된 전개총량·압축비 상한은 계속 방어선으로 작동한다.
    """
    try:
        with zf.open(zi) as fh:
            return fh.read(n)
    except Exception:  # noqa: BLE001
        return None


# ── 안전 추출(zip slip·bomb 방어) — extractall() 대체 공용 헬퍼 ─────────────
@dataclass
class ExtractResult:
    """안전 추출 결과(구조화). ok=False 면 추출을 거부했다(fail-closed — 부분 추출물은 정리)."""

    ok: bool
    code: str  # ok|path_traversal|archive_bomb|archive_corrupt|extract_error
    reason: str
    extracted: int = 0  # 실제 디스크에 쓴 파일 수
    total_bytes: int = 0  # 전개 총 바이트(실측)
    details: dict = field(default_factory=dict)


def safe_extract_archive(
    source,
    dest_dir,
    *,
    limits: ArchiveLimits = _DEFAULT_LIMITS,
    allowed_exts: frozenset[str] | None = None,
):
    """zip 아카이브를 **경로순회·압축폭탄 방어**하며 dest_dir 아래로 안전 추출한다.

    `zipfile.extractall()` 직접 호출을 대체하는 공용 헬퍼다(★전역 전파방지 — 어떤 내부/외부
    소스라도 이 함수만 쓰면 zip slip/bomb 이 구조적으로 불가능). 방어 심층 2겹:
      1) 엔트리 메타 사전검사(엔트리별): 경로순회(`_has_traversal`)·엔트리 수·전개 총량·압축비.
      2) 추출 직전 경로 재검증: 각 엔트리를 dest_dir 로 join 한 **실경로(resolve)** 가 dest_dir
         **안**에 있는지 재확인한다(심볼릭/상대경로 우회 대비 — advisory 메타를 믿지 않는 백스톱).
    스트리밍 복사로 엔트리를 풀되 누적 전개량이 상한을 넘으면 즉시 중단·정리(부분 추출물 삭제).

    Args:
        source: zip 경로(str/Path) 또는 바이트(bytes). 경로면 zipfile 이 부분 스트리밍으로 열어
            전체를 메모리에 올리지 않는다(대형 신뢰 아카이브도 안전).
        dest_dir: 추출 대상 디렉터리(없으면 생성).
        limits: 아카이브 한도(엔트리 수·전개 총량·압축비·깊이는 여기선 미사용).
        allowed_exts: 지정 시 이 확장자(소문자, 점 없이)만 추출(그 외 엔트리는 건너뜀 —
            거부가 아니라 선별). None 이면 모든 파일 엔트리 추출.

    Returns: ExtractResult. ok=False 면 위반이며 이미 쓴 파일은 정리(best-effort)한다.
    """
    from pathlib import Path as _Path

    dest = _Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    dest_root = dest.resolve()
    written: list[_Path] = []
    total = 0

    # bytes 는 파일객체가 아니므로 BytesIO 로 감싼다(경로면 zipfile 이 부분 스트리밍으로 연다).
    zsrc = io.BytesIO(source) if isinstance(source, (bytes, bytearray)) else source

    def _cleanup() -> None:
        for p in written:
            with contextlib.suppress(Exception):
                p.unlink()

    try:
        with zipfile.ZipFile(zsrc) as zf:
            infos = [zi for zi in zf.infolist() if not zi.is_dir()]
            if len(infos) > limits.max_entries:
                return ExtractResult(
                    False, "archive_bomb",
                    f"압축 내부 파일 수 초과({len(infos)} > {limits.max_entries}).",
                    details={"entries": len(infos)},
                )
            for zi in infos:
                name = zi.filename
                # (1) 메타 사전검사 — 경로순회.
                if _has_traversal(name):
                    _cleanup()
                    return ExtractResult(
                        False, "path_traversal",
                        f"압축 내부에 경로 순회 항목이 있습니다: {name[:80]}",
                        extracted=len(written), total_bytes=total,
                        details={"entry": name[:120]},
                    )
                # 전개 총량(선언 file_size 기준 조기 차단).
                if total + zi.file_size > limits.max_total_uncompressed:
                    _cleanup()
                    return ExtractResult(
                        False, "archive_bomb",
                        f"압축 전개 총량 초과(> {limits.max_total_uncompressed} bytes) — 압축폭탄 의심.",
                        extracted=len(written), total_bytes=total,
                        details={"total_bytes": total + zi.file_size},
                    )
                # 압축비(작은 엔트리 제외).
                if zi.compress_size >= limits.ratio_min_compressed:
                    ratio = zi.file_size / max(zi.compress_size, 1)
                    if ratio > limits.max_ratio:
                        _cleanup()
                        return ExtractResult(
                            False, "archive_bomb",
                            f"압축비 초과({ratio:.0f} > {limits.max_ratio:.0f}) — 압축폭탄 의심: {name[:80]}",
                            extracted=len(written), total_bytes=total,
                            details={"ratio": round(ratio, 1), "entry": name[:120]},
                        )
                # 확장자 선별(지정 시).
                if allowed_exts is not None and _ext(name) not in allowed_exts:
                    continue
                # (2) 추출 직전 경로 재검증 — join 후 실경로가 dest 안인지.
                target = (dest / name).resolve()
                if dest_root != target and dest_root not in target.parents:
                    _cleanup()
                    return ExtractResult(
                        False, "path_traversal",
                        f"추출 경로가 대상 폴더를 벗어납니다: {name[:80]}",
                        extracted=len(written), total_bytes=total,
                        details={"entry": name[:120]},
                    )
                target.parent.mkdir(parents=True, exist_ok=True)
                # 스트리밍 복사 + 누적 상한(실측 바이트로 truncate 방어 — advisory 메타 불신).
                remaining = limits.max_total_uncompressed - total
                try:
                    with zf.open(zi) as src, open(target, "wb") as dst:
                        while True:
                            chunk = src.read(1024 * 256)
                            if not chunk:
                                break
                            remaining -= len(chunk)
                            if remaining < 0:
                                dst.close()
                                with contextlib.suppress(Exception):
                                    target.unlink()
                                _cleanup()
                                return ExtractResult(
                                    False, "archive_bomb",
                                    f"실제 전개 바이트가 상한을 초과(스푸핑 의심): {name[:80]}",
                                    extracted=len(written), total_bytes=total,
                                    details={"entry": name[:120]},
                                )
                            dst.write(chunk)
                            total += len(chunk)
                except (zipfile.BadZipFile, OSError, EOFError) as e:
                    _cleanup()
                    return ExtractResult(
                        False, "archive_corrupt",
                        f"압축 해제 실패(손상 의심): {name[:80]} — {str(e)[:80]}",
                        extracted=len(written), total_bytes=total,
                        details={"entry": name[:120]},
                    )
                written.append(target)
            return ExtractResult(
                True, "ok", "안전 추출 완료.",
                extracted=len(written), total_bytes=total,
                details={"entries": len(infos)},
            )
    except zipfile.BadZipFile:
        _cleanup()
        return ExtractResult(False, "archive_corrupt", "손상되었거나 유효하지 않은 압축 파일입니다.")
    except Exception as e:  # noqa: BLE001 — 예상외 오류도 fail-closed(부분물 정리).
        _cleanup()
        return ExtractResult(False, "extract_error", f"추출 중 오류: {str(e)[:120]}")


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
      2) 실행/스크립트(시그니처·확장자, 웹 활성 콘텐츠 확장자 포함) → 거부
      2b) 선언 MIME 만으로 웹 활성 콘텐츠(svg/html/js 등) → 거부(확장자 위장의 역방향 우회 방지)
      3) 파일명 경로 순회 → 거부(퍼센트 인코딩 1회 정규화 후 판정)
      4) 매직바이트 실측 + 선언 MIME 위장 탐지(선언 계열 ≠ 실측 계열) → 거부
      5) expected_kinds 지정 시 실측 계열이 허용목록 밖 → 거부
      6) 아카이브 한도 검사(zip bomb·zip slip) — ★선두 매직이 zip 이 아니어도 데이터 안에 유효한
         zip 구조(EOCD)가 있으면 검사한다(폴리글랏 방어: 예 — PNG로 위장한 뒤 zip 을 붙인 파일).
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

    # 2) 실행/스크립트 차단(웹 활성 콘텐츠 확장자 포함 — html/svg/js 등, 리뷰 PoC #4)
    exe = _detect_executable(data, filename)
    if exe:
        return InspectionResult(
            False, "executable",
            "실행·스크립트 파일은 업로드할 수 없습니다.",
            declared_type=declared_kind, detected_type=exe, details={"executable": exe},
        )

    # 2b) 선언 MIME 만으로 웹 활성 콘텐츠 차단(확장자는 무해해도 content_type 을 svg/html 등으로
    #     선언하는 역방향 우회 방지).
    active_mime = _active_content_mime_reason(declared_content_type)
    if active_mime:
        return InspectionResult(
            False, "executable",
            f"활성 웹 콘텐츠는 업로드할 수 없습니다({active_mime}).",
            declared_type=declared_kind, details={"executable": active_mime},
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

    # 6) 아카이브 한도(zip bomb·zip slip) — ★폴리글랏 방어(리뷰 우회 PoC #1): 선두 매직이 "zip"으로
    #    판별되지 않았어도(예: PNG 헤더로 시작) 데이터 안에 유효한 zip 구조(EOCD)가 있으면 검사한다.
    #    과거엔 `detected == "zip"` 에만 걸려, PNG로 위장한 뒤 zip을 붙인 폴리글랏이 검사 전무 통과했다.
    if allow_archive and (detected == "zip" or _has_archive_structure(data)):
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


# ── 거부 코드 → HTTP 상태 매핑(리뷰 필수 #2) ────────────────────────────────
# 콘텐츠 검증 실패는 **클라이언트 귀책(4xx)**이다 — 스토리지 인프라 장애(502)와는 구분해야
# 자동재시도·모니터링 오분류를 막는다. 알 수 없는 코드는 400(안전측 기본값)으로 수렴.
_STATUS_BY_CODE: dict[str, int] = {
    "empty": 400,
    "too_large": 413,
    "executable": 400,
    "path_traversal": 400,
    "mime_mismatch": 415,
    "unsupported_type": 415,
    "archive_bomb": 400,
    "archive_corrupt": 400,
    "av_infected": 400,
    "inspection_error": 400,
}


def http_status_for(code: str) -> int:
    """검사 코드에 대응하는 권장 HTTP 상태를 반환한다(호출부가 ContentRejectedError 등에서 사용).

    스토리지 계층(storage_service)의 `ContentRejectedError`가 이 값을 `http_status` 속성으로
    실어 나르고, 라우터는 그것을 그대로 응답 상태코드로 쓴다 — 진짜 인프라 실패(502)와
    콘텐츠 거부(4xx)를 코드 경로에서 명확히 분리한다.
    """
    return _STATUS_BY_CODE.get(code, 400)
