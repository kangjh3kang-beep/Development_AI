"""SP2 협업 순수 규칙 — 초대 라이프사이클·역할검증·심의범위 화이트리스트(결정론·부작용 0).

now를 주입받아 만료 판정을 결정론으로 한다(시계 의존 제거). 접근제어 강제는 라우터 의존성
require_project_member(후속)가 본 규칙을 사용한다.
"""

from datetime import datetime

from app.models.collaboration import PROJECT_ROLES, REVIEW_CATEGORIES


def is_invite_expired(expires_at: datetime, now: datetime) -> bool:
    """초대 만료 여부 — now 주입 결정론."""
    return expires_at < now


def is_invite_acceptable(status: str, expires_at: datetime, now: datetime) -> bool:
    """수락 가능 여부 — pending이고 미만료일 때만(회수·이미수락·만료는 거부)."""
    return status == "pending" and not is_invite_expired(expires_at, now)


def validate_project_role(role: str) -> bool:
    """프로젝트 역할이 허용 집합(PROJECT_ROLES)에 속하는지."""
    return role in PROJECT_ROLES


def filter_scope_categories(requested, allowed) -> list[str]:
    """접근 허용 심의 카테고리 = 요청 ∩ (허용 화이트리스트 ∩ 유효 카테고리).

    순서 보존·중복 제거. allowed가 비면 전부 차단(기밀 기본 비공개). 유효하지 않은 카테고리
    (가짜·범위초과)는 서버측에서 제거한다(클라이언트 숨김에 의존 금지).
    """
    allowed_set = set(allowed or []) & set(REVIEW_CATEGORIES)
    out: list[str] = []
    for c in requested or []:
        if c in allowed_set and c not in out:
            out.append(c)
    return out


# ── SP3 자료교환 순수 규칙 ──

# 8엔진(DesignAuditOrchestrator)이 변환·투입 가능한 설계파일 확장자(parse_dxf_to_shapes/IFC 경로).
# 그 외(PDF·HWP 등 보고서·문서)는 자동검증 불가 → document(사람 심의자 표기용).
_DESIGN_EXTS = ("dxf", "ifc")


def classify_doc_kind(content_type, filename) -> str:
    """업로드 문서를 8엔진 자동검증 라우팅 종류로 분류 — "design"(DXF/IFC) 또는 "document".

    파일명 확장자를 1차 근거로 한다(가장 신뢰도 높음). 확장자가 없을 때만 content_type을 보조로
    본다(dxf/ifc/step 토큰). 모호하면 보수적으로 "document"(과대표기 금지 — 자동검증을 함부로 표방
    하지 않는다).
    """
    name = filename or ""
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext:
        return "design" if ext in _DESIGN_EXTS else "document"
    ct = (content_type or "").lower()
    if "dxf" in ct or "ifc" in ct or "step" in ct:
        return "design"
    return "document"


def normalize_document_category(category) -> str | None:
    """문서 심의 카테고리 정규화 — REVIEW_CATEGORIES 화이트리스트 외/빈값은 None(가짜 금지)."""
    return category if category in REVIEW_CATEGORIES else None


# 업로드 용도 — analysis(8엔진 자동검증 대상)/storage(공유·저장 전용). 미지값은 storage(안전 기본).
UPLOAD_PURPOSES = ("analysis", "storage")


def normalize_purpose(purpose) -> str:
    """업로드 용도 정규화 — analysis/storage 외/빈값은 'storage'(제한 없는 안전 기본)."""
    return purpose if purpose in UPLOAD_PURPOSES else "storage"


def analysis_allows_kind(doc_kind: str) -> bool:
    """분석용(8엔진) 허용 형식 — 설계파일(DXF/IFC=design)만. 그 외(document)는 분석 불가."""
    return doc_kind == "design"


# 악성/실행 파일 1차 차단 — 실행 확장자(zip기반 .jar 포함)·실행 시그니처. ClamAV 아님(시그니처 기반).
_BLOCKED_UPLOAD_EXTS = (
    "exe", "dll", "so", "dylib", "bat", "cmd", "com", "scr", "msi", "sh", "ps1", "jar", "app",
)


def is_blocked_upload(data: bytes, filename: str) -> bool:
    """업로드 파일이 실행/스크립트(악성 가능)인지 — 1차 차단(저장용 무제한 의도는 정상 문서엔 유지).

    실행 확장자 또는 실행 시그니처(PE 'MZ'/ELF/Mach-O/shebang '#!')면 차단. zip기반 문서(docx/xlsx/
    hwpx PK)·PDF·이미지·DXF 등 정상 형식은 통과. 빈 데이터는 차단 아님(빈파일 검증은 별도).
    """
    name = (filename or "").lower()
    ext = name.rsplit(".", 1)[-1] if "." in name else ""
    if ext in _BLOCKED_UPLOAD_EXTS:
        return True
    head = (data or b"")[:4]
    if head[:2] == b"MZ":  # Windows PE(.exe/.dll)
        return True
    if head == b"\x7fELF":  # Linux ELF
        return True
    if head in (b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf", b"\xca\xfe\xba\xbe", b"\xcf\xfa\xed\xfe"):
        return True  # Mach-O / fat binary / java class
    # shell/script shebang
    return (data or b"")[:2] == b"#!"


def document_in_scope(project_role: str, member_scope, doc_category) -> bool:
    """문서가 멤버의 허용 범위 안인지 — 외부 협력업체(external_reviewer)만 scope 제한(보안).

    내부 역할(owner/manager/contributor/reviewer_internal/viewer)은 프로젝트 전체 접근(True).
    external_reviewer는 문서 카테고리가 자신의 허용 scope에 포함될 때만 True — 미분류(category=None)
    문서는 외부 게스트에 비노출(보수적 기본: 명시 허용 범위만 노출, 누출 방지).
    """
    if project_role != "external_reviewer":
        return True
    if not doc_category:
        return False
    return doc_category in set(member_scope or [])


# 표기용 심의 상태(사람 심의자 주도, 자동판정 아님). 전진 전용 선형 상태머신.
REVIEW_STATES = ("requested", "acknowledged", "addressed")
_REVIEW_TRANSITIONS = {
    "requested": {"acknowledged"},
    "acknowledged": {"addressed"},
    "addressed": set(),
}


def is_allowed_review_transition(current: str, target: str) -> bool:
    """심의 상태 전이 허용 여부 — 전진(requested→acknowledged→addressed)만. 스킵·역행·무변경·미지 거부."""
    return target in _REVIEW_TRANSITIONS.get(current, set())
