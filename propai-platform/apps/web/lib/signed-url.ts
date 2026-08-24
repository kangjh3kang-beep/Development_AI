/**
 * 서명 URL 의 **만료 시각을 네트워크 없이 읽는다**.
 *
 * ## 왜 필요한가 (2026-08-24 라이브 실측)
 *
 * 등기부 PDF 는 비공개 버킷에 저장되고 **30일 서명 URL** 로 전달된다. 그 링크가 만료돼도
 * 화면은 `PDF ↗` 를 **똑같이** 그렸다 — 누르면 JSON 오류 덩어리가 열린다.
 * 저장된 79건 중 표본 3건에서 **2건이 이미 만료**였다(`InvalidJWT: "exp" claim …`).
 *
 * 서명 URL 의 토큰은 JWT 이고 만료 시각(`exp`)이 **페이로드에 그대로 들어 있다.**
 * 즉 **한 번도 요청하지 않고** 만료를 알 수 있다 — 77필지 묶음이면 헛요청 77건을 아낀다.
 *
 * ## ★이것은 검증이 아니다
 *
 * 서명을 확인하지 않는다(그건 서버가 한다). **주장(claim)을 읽을 뿐**이다.
 * 그래서 판정은 한 방향으로만 쓴다 — "만료됐다"고 **읽히면** 미리 알리고,
 * 읽지 못하면 **링크를 감추지 않는다**(살아 있는 링크를 죽은 것으로 만들지 않는다).
 */

/** base64url → 문자열. 실패하면 null(추측하지 않는다). */
function decodeSegment(seg: string): string | null {
  try {
    const b64 = seg.replace(/-/g, "+").replace(/_/g, "/");
    const pad = b64.length % 4 === 0 ? b64 : b64 + "=".repeat(4 - (b64.length % 4));
    return typeof atob === "function"
      ? decodeURIComponent(escape(atob(pad)))
      : Buffer.from(pad, "base64").toString("utf8");
  } catch {
    return null;
  }
}

/**
 * 서명 URL 의 `exp`(초 단위 epoch). 읽지 못하면 **null**.
 *
 * null 은 "만료되지 않았다"가 아니라 **"모른다"** 다 — 호출측이 그 둘을 섞으면 안 된다.
 */
export function signedUrlExpiry(url: string | null | undefined): number | null {
  const raw = (url || "").trim();
  if (!raw) return null;
  let token: string | null = null;
  try {
    token = new URL(raw).searchParams.get("token");
  } catch {
    // 상대경로 등 URL 로 못 읽는 형태 — 쿼리에서 직접 집는다.
    const m = raw.match(/[?&]token=([^&]+)/);
    token = m ? decodeURIComponent(m[1]) : null;
  }
  if (!token) return null;
  const parts = token.split(".");
  if (parts.length < 2) return null;
  const json = decodeSegment(parts[1]);
  if (!json) return null;
  try {
    const exp = (JSON.parse(json) as { exp?: unknown }).exp;
    return typeof exp === "number" && Number.isFinite(exp) ? exp : null;
  } catch {
    return null;
  }
}

/**
 * 이 링크가 **이미 만료로 읽히는가**. 읽지 못하면 `false`(모르는 것을 만료로 몰지 않는다).
 *
 * @param nowMs 판정 기준 시각(테스트가 고정한다 — 시계를 모듈이 몰래 읽지 않는다).
 */
export function isSignedUrlExpired(url: string | null | undefined, nowMs: number): boolean {
  const exp = signedUrlExpiry(url);
  return exp !== null && exp * 1000 <= nowMs;
}

/** 만료 시각을 `YYYY-MM-DD` 로. 모르면 null. */
export function signedUrlExpiryDay(url: string | null | undefined): string | null {
  const exp = signedUrlExpiry(url);
  return exp === null ? null : new Date(exp * 1000).toISOString().slice(0, 10);
}
