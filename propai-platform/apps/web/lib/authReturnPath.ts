/**
 * 로그인 복귀경로(?next=) 안전 해석 — 앱 컨텍스트 복귀의 단일 헬퍼.
 *
 * ★배경(2026-07-23 사용자 버그리포트): 분양 현장앱에서 로그아웃 후 재로그인하면 현장앱이 아니라
 *   플랫폼 메인 대시보드로 떨어졌다. 원인은 3중 배선 단절 — ①로그인 성공 핸들러가 ?next= 를
 *   무시하고 무조건 /{locale} 로 push, ②로그아웃(AuthButton)·미인증 가드(AuthGuard)가 현재
 *   경로를 next 로 싣지 않음, ③현장앱 전용 manifest 부재(설치 앱도 start_url=/ko 로 시작).
 *   이 헬퍼는 ①의 소비 지점을 한 곳으로 모으고 오픈 리다이렉트를 차단한다.
 *
 * 안전 규칙(오픈 리다이렉트 차단 — R1 적대리뷰 B1 반영):
 *  - 같은 오리진의 절대경로("/...")만 허용. "//host"(프로토콜 상대)·스킴 URL 거부.
 *  - ★제어문자(탭·개행 등)·백슬래시 일괄 거부 — WHATWG URL 파서는 U+0009/000A/000D 를 파싱 전
 *    제거하므로 "/\t/evil.com" 이 "//evil.com" 으로 정규화되어 접두 검사만으론 우회된다(실증).
 *  - 최종적으로 URL 파서로 정규화해 오리진이 유지되는지 대조(미래 변종까지 방어) 후,
 *    정규화된 경로만 반환한다.
 *  - 로그인/가입 화면 자기참조는 복귀 무의미(재착지 루프) → 기본 홈으로 폴백.
 */
export function resolveNextPath(raw: string | null | undefined, locale: string): string {
  const fallback = `/${locale}`;
  if (!raw) return fallback;
  if (!raw.startsWith("/") || raw.startsWith("//")) return fallback;
  // 제어문자(C0 전역+DEL)·백슬래시 변종 거부 — URL 파서의 사전 제거/정규화를 악용한 우회 차단.
  // eslint-disable-next-line no-control-regex
  if (/[\u0000-\u001F\u007F\\]/.test(raw)) return fallback;
  // 로그인/가입 화면으로의 복귀는 무의미(로그인 후 다시 로그인 화면 착지) → 홈으로.
  if (raw.startsWith(`/${locale}/login`) || raw.startsWith(`/${locale}/register`)) return fallback;
  // 더미 오리진 기준으로 정규화 — 오리진이 바뀌면(어떤 변종이든 외부 이탈) 거부하고,
  // 통과 시엔 파서가 정규화한 경로+쿼리+해시만 사용한다(원문 재사용 금지).
  try {
    const u = new URL(raw, "https://internal.invalid");
    if (u.origin !== "https://internal.invalid") return fallback;
    return u.pathname + u.search + u.hash;
  } catch {
    return fallback;
  }
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
