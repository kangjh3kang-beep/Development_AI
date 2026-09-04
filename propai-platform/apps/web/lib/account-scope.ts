/**
 * 계정 스코프 저장키 — **한 브라우저를 여러 계정이 쓴다**는 사실을 키에 새긴다.
 *
 * ## 왜 이 파일이 생겼나 (2026-08-26 실측)
 *
 * 계정 격리는 지금까지 **와이프**로 했다(`clearAllProjectData`). 그런데 와이프에는
 * 넣을 수 없는 부류가 있다 — **유료·비가역 산출물**이다:
 *
 *  · `propai-paid-renders`      포토리얼 렌더 **건당 3,000원**
 *  · `propai-registry-analysis` 등기 권리분석 **필지당 1,200원**
 *
 * 지우면 사용자가 **이미 낸 돈이 사라진다.** 안 지우면 같은 브라우저의 **다음 계정이
 * 이전 계정의 유료 산출물을 본다**(등기 쪽은 **소유자 정보**가 들어 있다). 그래서 둘은
 * `#810` 의 `WIPE_EXEMPT` 에 *"★부채"* 로 등재돼 있었고, 그 사유가 처방까지 적어 뒀다:
 * **와이프가 아니라 계정별 키.**
 *
 * ## 선례를 새로 만들지 않았다
 *
 * 이 저장소에는 이미 답이 있었다 — 분석 이력이 `propai_pipeline_history__<userId>` 로
 * **키를 갈라** 격리와 보존을 동시에 만족한다(그래서 와이프 목록의 그 항목은 *레거시 전용*
 * 이라고 적혀 있다). 다만 그 키는 호출부에서 **문자열 조립**으로 만들어져 있어 규칙이
 * 한 곳에 없었다. 여기로 올려 **만드는 쪽과 읽는 쪽이 같은 함수를 보게** 한다.
 *
 * ★`projectSync` 에 두지 않는 이유: 스토어가 이 함수를 쓰고 `projectSync` 는 스토어를
 *   쓰므로, 같은 파일에 두면 **순환 임포트**가 된다. 토큰만 보는 순수 모듈로 분리한다.
 */

/** 계정 구분자 — `<base>__<userId>`. 선례(`propai_pipeline_history__`)와 같은 형태를 쓴다. */
export const ACCOUNT_KEY_SEP = "__";

/** 비로그인 사용자의 스코프. 로그인 사용자와 섞이지 않게 이름을 준다(빈 문자열 금지 —
 *  빈 값이면 `base__` 가 되어 **레거시 공유키와 구별되지 않는 새 공유키**가 생긴다). */
export const GUEST_SCOPE = "guest";

/** JWT payload 에서 사용자 식별자만 꺼낸다(서명 검증 목적이 아니라 **키 분리** 목적). */
export function decodeTokenUser(token: string | null): string | null {
  if (!token) return null;
  try {
    const seg = token.split(".")[1];
    if (!seg) return null;
    const json = atob(seg.replace(/-/g, "+").replace(/_/g, "/"));
    const payload = JSON.parse(json) as Record<string, unknown>;
    const uid = payload.sub ?? payload.user_id ?? payload.uid;
    return uid ? String(uid) : null;
  } catch {
    return null;
  }
}

/** 현재 로그인 사용자 식별자(localStorage 키 분리용). 비로그인이면 `"guest"`. */
export function currentUserId(): string {
  if (typeof window === "undefined") return GUEST_SCOPE;
  return decodeTokenUser(window.localStorage.getItem("propai_access_token")) || GUEST_SCOPE;
}

/**
 * 계정별 저장키를 만든다. `uid` 를 주지 않으면 **호출 시점의** 사용자로 만든다.
 *
 * ★호출 시점인 것이 중요하다 — zustand `persist` 는 이름을 **모듈 로드 시점에 고정**하므로,
 *   계정이 바뀌어도 그 이름은 안 바뀐다. 스코프는 storage 어댑터가 **읽기/쓰기 시점에**
 *   붙여야 한다(`createAccountScopedStorage`).
 */
export function accountScopedKey(base: string, uid: string = currentUserId()): string {
  return `${base}${ACCOUNT_KEY_SEP}${uid}`;
}

/** `base` 의 계정별 키인가(레거시 공유키 자신은 **아니다**). */
export function isAccountScopedKey(key: string, base: string): boolean {
  return key.startsWith(base + ACCOUNT_KEY_SEP) && key.length > base.length + ACCOUNT_KEY_SEP.length;
}
