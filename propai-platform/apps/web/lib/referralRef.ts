/**
 * Phase C — 추천(MGM) 랜딩 추적 유틸.
 *
 * 공유링크로 진입한 방문자(URL `?ref=CODE`)를 감지해 백엔드에 click/visit 퍼널 이벤트를
 * 무파괴·공개 호출한다(백엔드 _workspace/63 §7: `POST /sales/referral/track`, 인증불필요·무효코드 조용히 무시).
 *
 * 정직성:
 *   - 추적은 best-effort. 네트워크/무효코드 실패는 본 흐름을 절대 막지 않는다.
 *   - 방문자 식별은 익명 ref(visitor_ref) 1개를 localStorage에 보관(개인식별정보 아님).
 *   - 같은 코드의 click 이벤트는 세션당 1회만 보낸다(중복 추적 방지).
 */
import { apiClient } from "@/lib/api-client";

const REF_CODE_KEY = "propai_ref_code";
const VISITOR_REF_KEY = "propai_visitor_ref";
const CLICK_SENT_PREFIX = "propai_ref_click:";

export type ReferralEvent = "click" | "visit" | "lead";

/** URL(?ref=)에서 추천코드를 추출한다. 없으면 null. */
export function readRefFromUrl(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const code = new URLSearchParams(window.location.search).get("ref");
    return code && code.trim() ? code.trim() : null;
  } catch {
    return null;
  }
}

/** 최근 진입한 추천코드(있으면)를 localStorage에서 조회 — 방문/리드 귀속용. */
export function getStoredRefCode(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(REF_CODE_KEY);
  } catch {
    return null;
  }
}

/** 익명 방문자 ref를 보장(없으면 생성). 개인식별정보 아님. */
function ensureVisitorRef(): string {
  if (typeof window === "undefined") return "";
  try {
    let v = window.localStorage.getItem(VISITOR_REF_KEY);
    if (!v) {
      v =
        typeof crypto !== "undefined" && "randomUUID" in crypto
          ? crypto.randomUUID()
          : `v_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;
      window.localStorage.setItem(VISITOR_REF_KEY, v);
    }
    return v;
  } catch {
    return "";
  }
}

/** 퍼널 이벤트 1건을 공개 호출(best-effort, 실패 무해). */
export function trackReferral(code: string, event: ReferralEvent): void {
  if (!code) return;
  const visitor_ref = ensureVisitorRef();
  apiClient
    .post("/sales/referral/track", { body: { code, event, visitor_ref: visitor_ref || undefined } })
    .catch(() => {
      /* 무효코드/네트워크 실패는 본 흐름 무중단 */
    });
}

/**
 * 앱 진입 시 1회 호출 — `?ref=` 감지 → 코드 보관 + click 이벤트(세션당 1회).
 * 반환: 감지된 코드(있으면). 컴포넌트가 추가 visit 추적에 활용 가능.
 */
export function captureLandingRef(): string | null {
  const code = readRefFromUrl();
  if (!code) return getStoredRefCode();
  try {
    window.localStorage.setItem(REF_CODE_KEY, code);
  } catch {
    /* localStorage 비활성 무시 */
  }
  // click은 세션당 1회만(새 탭/재진입 중복 방지).
  let alreadySent = false;
  try {
    alreadySent = window.sessionStorage.getItem(CLICK_SENT_PREFIX + code) === "1";
  } catch {
    /* noop */
  }
  if (!alreadySent) {
    trackReferral(code, "click");
    try {
      window.sessionStorage.setItem(CLICK_SENT_PREFIX + code, "1");
    } catch {
      /* noop */
    }
  }
  return code;
}
