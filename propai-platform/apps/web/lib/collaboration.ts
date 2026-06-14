/**
 * SP2 프로젝트 회의방(F3) 프론트 순수코어 — 역할/심의카테고리 라벨·이메일검증·선택토글·상태배지.
 *
 * 백엔드 app/models/collaboration.py(PROJECT_ROLES·REVIEW_CATEGORIES)와 정합. UI(컴포넌트)에서
 * 분리해 vitest로 결정론 검증한다(네트워크·DOM 무관).
 */

export type ProjectRole =
  | "owner"
  | "manager"
  | "contributor"
  | "reviewer_internal"
  | "external_reviewer"
  | "viewer";

export type ReviewCategory =
  | "traffic"
  | "environment"
  | "civil"
  | "landscape"
  | "architecture"
  | "fire";

export const REVIEW_CATEGORIES: ReviewCategory[] = [
  "traffic",
  "environment",
  "civil",
  "landscape",
  "architecture",
  "fire",
];
const REVIEW_CATEGORY_SET = new Set<string>(REVIEW_CATEGORIES);

export const PROJECT_ROLE_LABELS: Record<string, string> = {
  owner: "소유자",
  manager: "관리자(PM)",
  contributor: "실무자",
  reviewer_internal: "내부심의",
  external_reviewer: "외부 협력업체",
  viewer: "열람",
};

export const REVIEW_CATEGORY_LABELS: Record<string, string> = {
  traffic: "교통영향평가",
  environment: "환경",
  civil: "토목",
  landscape: "경관",
  architecture: "건축",
  fire: "소방",
};

/** 역할 한글 라벨 — 미지값은 원문 폴백(가짜 라벨 금지). */
export function roleLabel(role: string): string {
  return PROJECT_ROLE_LABELS[role] ?? role;
}

/** 심의 카테고리 한글 라벨 — 미지값은 원문 폴백. */
export function categoryLabel(cat: string): string {
  return REVIEW_CATEGORY_LABELS[cat] ?? cat;
}

/** 클라이언트 이메일 검증(서버 build_invite_fields가 1차, 본 함수는 입력단 즉시 피드백). */
export function isValidEmail(email: string): boolean {
  const e = (email ?? "").trim();
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e);
}

/** 초대 폼 카테고리 체크박스 토글 — 유효 카테고리만 추가(순서 보존). */
export function toggleCategory(selected: string[], cat: string): string[] {
  if (!REVIEW_CATEGORY_SET.has(cat)) return [...selected];
  return selected.includes(cat) ? selected.filter((c) => c !== cat) : [...selected, cat];
}

export type StatusTone = "ok" | "warn" | "muted";

/** 멤버 상태 → 배지(라벨·톤). 미지 상태는 원문·muted(가짜 표기 금지). */
export function memberStatusBadge(status: string): { label: string; tone: StatusTone } {
  switch (status) {
    case "active":
      return { label: "활성", tone: "ok" };
    case "suspended":
      return { label: "정지", tone: "warn" };
    case "removed":
      return { label: "해제", tone: "muted" };
    default:
      return { label: status, tone: "muted" };
  }
}

// ── SP3 자료교환 ──

/** 설계파일(8엔진 자동검증 대상) 여부 — design만 8엔진 실투입(나머지는 표기용). */
export function isDesignKind(docKind: string): boolean {
  return docKind === "design";
}

/** 8엔진 audit 상태 → 배지. design 파일에만 의미. document는 'unsupported'(자동검증 아님). */
export function auditStatusBadge(
  status: string | null | undefined,
): { label: string; tone: StatusTone } | null {
  switch (status) {
    case "completed":
      return { label: "8엔진 검증완료", tone: "ok" };
    case "pending":
      return { label: "검증 대기", tone: "muted" };
    case "failed":
      return { label: "검증 실패", tone: "warn" };
    case "unsupported":
      return { label: "자동검증 미지원 형식", tone: "muted" };
    case "skipped":
      return { label: "검증 생략", tone: "muted" };
    default:
      return null; // null/미지 → 배지 없음(과대표기 금지)
  }
}

/** 표기용 심의 상태 → 배지(사람 심의자 주도, 자동판정 아님). */
export function reviewStateBadge(state: string): { label: string; tone: StatusTone } {
  switch (state) {
    case "requested":
      return { label: "검토요청", tone: "warn" };
    case "acknowledged":
      return { label: "확인됨", tone: "muted" };
    case "addressed":
      return { label: "처리완료", tone: "ok" };
    default:
      return { label: state, tone: "muted" };
  }
}

/** 다음 심의 상태(전진 전용) — requested→acknowledged→addressed. 더 없으면 null. 백엔드 규칙과 정합. */
export function nextReviewState(current: string): string | null {
  if (current === "requested") return "acknowledged";
  if (current === "acknowledged") return "addressed";
  return null;
}

/** 바이트 → 사람이 읽는 크기(결정론). 음수·비정상은 "—". */
export function formatBytes(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n) || n < 0) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}
