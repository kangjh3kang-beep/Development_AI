/**
 * 서명 URL 만료를 **네트워크 없이** 읽는 계약.
 *
 * 【실측이 만든 요구 — 2026-08-24】저장된 등기 PDF 서명 URL 79건 중 표본 3건에서
 * **2건이 이미 만료**였는데(`InvalidJWT: "exp" claim timestamp check failed`)
 * 화면은 `PDF ↗` 를 똑같이 그렸다. 누르면 JSON 오류 덩어리가 열린다.
 *
 * ★이 모듈은 **검증이 아니다** — 서명을 확인하지 않고 주장을 읽을 뿐이다.
 *   그래서 판정을 한 방향으로만 쓴다: 만료로 **읽히면** 미리 알리고,
 *   못 읽으면 **링크를 감추지 않는다**(살아 있는 링크를 죽은 것으로 만들지 않는다).
 */
import { describe, expect, it } from "vitest";

import { isSignedUrlExpired, signedUrlExpiry, signedUrlExpiryDay } from "@/lib/signed-url";

/** 실제 Supabase 서명 URL 과 같은 모양으로 토큰을 만든다(서명은 검증하지 않으므로 무의미해도 된다). */
function makeUrl(payload: Record<string, unknown>): string {
  const b64 = (o: unknown) =>
    Buffer.from(JSON.stringify(o)).toString("base64")
      .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  const token = `${b64({ alg: "HS256" })}.${b64(payload)}.c2ln`;
  return `https://x.supabase.co/storage/v1/object/sign/propai-registry/registry/20260623/a.pdf?token=${token}`;
}

const EXP = 1784775871; // 2026-07-23 무렵 — 실측 표본의 만료값

describe("signedUrlExpiry", () => {
  it("★토큰 페이로드의 exp 를 읽는다(요청 없이)", () => {
    expect(signedUrlExpiry(makeUrl({ url: "x", exp: EXP }))).toBe(EXP);
  });

  it("★못 읽으면 null — **만료 아님이 아니라 '모른다'** 다", () => {
    expect(signedUrlExpiry("https://x/y.pdf")).toBeNull();          // 토큰 없음
    expect(signedUrlExpiry("https://x/y.pdf?token=abc")).toBeNull(); // JWT 아님
    expect(signedUrlExpiry(makeUrl({ url: "x" }))).toBeNull();       // exp 없음
    expect(signedUrlExpiry("")).toBeNull();
    expect(signedUrlExpiry(null)).toBeNull();
  });

  it("exp 가 숫자가 아니면 읽지 않는다(문자열을 숫자로 밀지 않는다)", () => {
    expect(signedUrlExpiry(makeUrl({ exp: "1784775871" }))).toBeNull();
  });

  it("URL 로 파싱되지 않는 형태도 쿼리에서 집는다", () => {
    const u = makeUrl({ exp: EXP });
    const rel = u.slice(u.indexOf("/storage"));
    expect(signedUrlExpiry(rel)).toBe(EXP);
  });
});

describe("isSignedUrlExpired — 한 방향으로만 판정한다", () => {
  it("★지난 것은 만료로 읽는다", () => {
    expect(isSignedUrlExpired(makeUrl({ exp: EXP }), (EXP + 1) * 1000)).toBe(true);
  });

  it("★대조군 — 아직 남은 것은 만료가 아니다", () => {
    expect(isSignedUrlExpired(makeUrl({ exp: EXP }), (EXP - 86400) * 1000)).toBe(false);
  });

  it("경계: exp 와 같은 순간은 만료로 본다(서버가 거부하는 쪽에 맞춘다)", () => {
    expect(isSignedUrlExpired(makeUrl({ exp: EXP }), EXP * 1000)).toBe(true);
  });

  it("★★못 읽으면 **만료로 몰지 않는다** — 살아 있는 링크를 죽이지 않는다", () => {
    expect(isSignedUrlExpired("https://x/y.pdf", Date.now())).toBe(false);
    expect(isSignedUrlExpired(null, Date.now())).toBe(false);
  });

  it("판정 시각을 **인자로 받는다**(모듈이 시계를 몰래 읽지 않는다 — 테스트가 고정할 수 있어야 한다)", () => {
    const u = makeUrl({ exp: EXP });
    expect(isSignedUrlExpired(u, (EXP - 1) * 1000)).toBe(false);
    expect(isSignedUrlExpired(u, (EXP + 1) * 1000)).toBe(true);
  });
});

describe("signedUrlExpiryDay", () => {
  it("사람이 읽는 날짜를 준다", () => {
    expect(signedUrlExpiryDay(makeUrl({ exp: EXP }))).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
  it("모르면 null", () => {
    expect(signedUrlExpiryDay("https://x/y.pdf")).toBeNull();
  });
});
