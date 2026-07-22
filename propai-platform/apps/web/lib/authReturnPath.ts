/**
 * 로그인 복귀경로(?next=) 안전 해석 — 앱 컨텍스트 복귀의 단일 헬퍼.
 *
 * ★배경(2026-07-23 사용자 버그리포트): 분양 현장앱에서 로그아웃 후 재로그인하면 현장앱이 아니라
 *   플랫폼 메인 대시보드로 떨어졌다. 원인은 3중 배선 단절 — ①로그인 성공 핸들러가 ?next= 를
 *   무시하고 무조건 /{locale} 로 push, ②로그아웃(AuthButton)·미인증 가드(AuthGuard)가 현재
 *   경로를 next 로 싣지 않음, ③현장앱 전용 manifest 부재(설치 앱도 start_url=/ko 로 시작).
 *   이 헬퍼는 ①의 소비 지점을 한 곳으로 모으고 오픈 리다이렉트를 차단한다.
 *
 * 안전 규칙(오픈 리다이렉트 차단):
 *  - 같은 오리진의 절대경로("/...")만 허용.
 *  - "//host" (프로토콜 상대 URL)·백슬래시 변종("/\host")은 외부 이탈 가능 → 거부.
 *  - 그 외(빈 값·스킴 포함 URL 등)는 전부 기본 홈(/{locale})으로 폴백.
 */
export function resolveNextPath(raw: string | null | undefined, locale: string): string {
  const fallback = `/${locale}`;
  if (!raw) return fallback;
  if (!raw.startsWith("/")) return fallback; // 상대·스킴 URL(https:, javascript: 등) 거부
  if (raw.startsWith("//")) return fallback; // 프로토콜 상대 URL(//evil.com) 거부
  if (raw.includes("\\")) return fallback; // 백슬래시 변종(/\evil.com — 브라우저가 //로 정규화) 거부
  return raw;
}

/** 현재 위치(경로+쿼리)를 next 파라미터로 실은 로그인 URL — 로그아웃/미인증 가드 공용. */
export function loginUrlWithReturn(locale: string): string {
  if (typeof window === "undefined") return `/${locale}/login`;
  const current = window.location.pathname + window.location.search;
  // 로그인/가입 화면 자체로의 복귀는 무의미(루프) — next 생략.
  if (current.startsWith(`/${locale}/login`) || current.startsWith(`/${locale}/register`)) {
    return `/${locale}/login`;
  }
  return `/${locale}/login?next=${encodeURIComponent(current)}`;
}
