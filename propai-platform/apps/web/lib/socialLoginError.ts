/**
 * 공급자가 돌려보낸 OAuth 오류를 **사용자에게 말할 수 있는 것**으로 바꾼다.
 *
 * ★왜 필요한가 — 2026-09-06 실측:
 *   콜백 페이지 3사가 `code`·`state` 만 읽고 `error` 를 **버렸다**. 그래서 공급자가 실패를
 *   돌려보내면 `code=null` 이 되고 화면은 **「callback 파라미터가 부족합니다. code를 확인하세요」**
 *   라는 개발자용 문구를 냈다. ***원인은 URL 에 있는데 버리고 다른 것을 말한 것*** —
 *   2026-09-04 실거래 「화면 밖 N곳」과 같은 **무음 절단** 클래스다.
 *
 * ★두 부류를 가른다 — 다음 행동이 다르기 때문이다:
 *   · 사용자 취소  → 정상 흐름이다. 사과하지 말고 다시 시도할 길만 준다.
 *   · 설정 오류    → 사용자가 아무리 다시 해도 안 된다. **관리자 확인이 필요하다고 말하고
 *                    원문 코드를 노출**해 진단 가능하게 한다.
 *   ★이 구분을 안 하면 사용자는 「내가 뭘 잘못했나」로 읽고 무한히 재시도한다.
 */

/** 사용자가 스스로 취소·거부한 경우. 공급자별 표기가 다르다. */
const USER_CANCELLED = new Set([
  "access_denied", // OAuth 2.0 표준 (구글·네이버 공통)
  "user_cancel", // 일부 공급자
  "cancel",
  "user_cancelled_login",
  "consent_required",
]);

export type SocialLoginErrorKind = "none" | "cancelled" | "misconfigured";

export type SocialLoginErrorVerdict = {
  kind: SocialLoginErrorKind;
  /** 공급자가 준 원문 코드. 설정 오류일 때 화면에 노출해 진단 가능하게 한다. */
  rawCode: string | null;
  /** 공급자가 준 원문 설명(있으면). */
  rawDescription: string | null;
};

/**
 * ★`error` 가 없으면 `kind: "none"` 이다 — 그때 호출부는 **종전과 완전히 같은 경로**를 탄다.
 *   (회귀 방지: 이 함수는 기존 성공 흐름을 바꾸지 않는다.)
 */
export function classifySocialLoginError(
  error: string | null | undefined,
  description?: string | null,
): SocialLoginErrorVerdict {
  const raw = typeof error === "string" ? error.trim() : "";
  if (!raw) {
    return { kind: "none", rawCode: null, rawDescription: null };
  }
  const desc =
    typeof description === "string" && description.trim() ? description.trim() : null;
  return {
    kind: USER_CANCELLED.has(raw.toLowerCase()) ? "cancelled" : "misconfigured",
    rawCode: raw,
    rawDescription: desc,
  };
}

type Locale = "ko" | "en" | "zh-CN";

const COPY: Record<Locale, { cancelled: string; misconfigured: (code: string) => string }> = {
  ko: {
    cancelled: "로그인을 취소하셨습니다. 다시 시도하시려면 아래 버튼을 눌러 주세요.",
    misconfigured: (code) =>
      `간편로그인 연동 설정에 문제가 있어 진행할 수 없습니다(오류: ${code}). ` +
      `다시 시도해도 같은 결과가 나옵니다 — 관리자 확인이 필요합니다. ` +
      `이메일로 로그인하시거나 잠시 후 다시 이용해 주세요.`,
  },
  en: {
    cancelled: "You cancelled the sign-in. Press the button below to try again.",
    misconfigured: (code) =>
      `Social sign-in is misconfigured and cannot proceed (error: ${code}). ` +
      `Retrying will produce the same result — an administrator needs to check it. ` +
      `Please sign in with email instead.`,
  },
  "zh-CN": {
    cancelled: "您已取消登录。如需重试，请点击下方按钮。",
    misconfigured: (code) =>
      `第三方登录配置有误，无法继续（错误：${code}）。` +
      `重试也会得到相同结果 — 需要管理员检查。请改用邮箱登录。`,
  },
};

/** 판정을 사용자 언어 문구로. ★설정 오류일 때 **원문 코드를 반드시 싣는다**(진단 가능성). */
export function socialLoginErrorMessage(
  verdict: SocialLoginErrorVerdict,
  locale: string,
): string | null {
  if (verdict.kind === "none") return null;
  const copy = COPY[(locale as Locale) in COPY ? (locale as Locale) : "ko"];
  if (verdict.kind === "cancelled") return copy.cancelled;
  return copy.misconfigured(verdict.rawCode ?? "unknown");
}
