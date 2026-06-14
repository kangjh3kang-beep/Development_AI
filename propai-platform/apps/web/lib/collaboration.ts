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
