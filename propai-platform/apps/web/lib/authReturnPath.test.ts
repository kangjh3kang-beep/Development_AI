import { describe, it, expect } from "vitest";
import { resolveNextPath, loginUrlWithReturn } from "./authReturnPath";

/**
 * 로그인 복귀경로(?next=) 안전 해석 계약 — 앱 컨텍스트 복귀 + 오픈 리다이렉트 차단.
 *
 * ★배경(2026-07-23): 분양 현장앱에서 재로그인 시 메인 대시보드로 떨어지던 버그의 수정으로
 *   로그인 성공 핸들러가 ?next= 를 소비하게 됐다. 외부 URL 로의 이탈(오픈 리다이렉트 —
 *   피싱에 악용)은 반드시 차단되어야 하므로 허용/거부 규칙을 계약으로 고정한다.
 */
describe("resolveNextPath — 복귀 허용(같은 오리진 절대경로)", () => {
  it("현장앱 경로로 복귀", () => {
    expect(resolveNextPath("/ko/sales/sites", "ko")).toBe("/ko/sales/sites");
    expect(resolveNextPath("/ko/sales/sites/abc-123/workspace", "ko"))
      .toBe("/ko/sales/sites/abc-123/workspace");
  });

  it("쿼리 포함 경로 보존", () => {
    expect(resolveNextPath("/ko/projects?tab=cost", "ko")).toBe("/ko/projects?tab=cost");
  });
});

describe("resolveNextPath — 폴백(값 없음)", () => {
  it("null/undefined/빈 문자열 → /{locale}", () => {
    expect(resolveNextPath(null, "ko")).toBe("/ko");
    expect(resolveNextPath(undefined, "ko")).toBe("/ko");
    expect(resolveNextPath("", "en")).toBe("/en");
  });
});

describe("resolveNextPath — ★오픈 리다이렉트 차단", () => {
  it("스킴 URL(https:, javascript: 등) 거부", () => {
    expect(resolveNextPath("https://evil.com/phish", "ko")).toBe("/ko");
    expect(resolveNextPath("javascript:alert(1)", "ko")).toBe("/ko");
  });

  it("프로토콜 상대 URL(//host) 거부", () => {
    expect(resolveNextPath("//evil.com", "ko")).toBe("/ko");
    expect(resolveNextPath("//evil.com/ko/sales", "ko")).toBe("/ko");
  });

  it("백슬래시 변종(/\\host — 브라우저가 //로 정규화) 거부", () => {
    expect(resolveNextPath("/\\evil.com", "ko")).toBe("/ko");
    expect(resolveNextPath("/ko\\..\\evil", "ko")).toBe("/ko");
  });

  it("상대경로(선행 / 없음) 거부", () => {
    expect(resolveNextPath("ko/sales/sites", "ko")).toBe("/ko");
  });

  it("★제어문자 변종(탭/LF/CR — WHATWG URL 파서가 파싱 전 제거해 //로 정규화) 거부 (R1 B1)", () => {
    // "/\t/evil.com" 은 접두 검사(/·//·\\)를 전부 통과하지만 URL 파서를 거치면
    // https://evil.com 으로 정규화된다 — R1 적대리뷰가 실증한 우회. 회귀 고정.
    expect(resolveNextPath("/\t/evil.com", "ko")).toBe("/ko");
    expect(resolveNextPath("/\n/evil.com", "ko")).toBe("/ko");
    expect(resolveNextPath("/\r/evil.com", "ko")).toBe("/ko");
    // NUL 등 그 외 C0 제어문자도 동일 클래스로 거부(변종 전면 차단).
    expect(resolveNextPath("/\u0000/evil.com", "ko")).toBe("/ko");
  });

  it("로그인/가입 화면 자기참조 → 홈 폴백(재착지 루프 방지)", () => {
    expect(resolveNextPath("/ko/login", "ko")).toBe("/ko");
    expect(resolveNextPath("/ko/login?next=%2Fko", "ko")).toBe("/ko");
    expect(resolveNextPath("/ko/register", "ko")).toBe("/ko");
  });

  it("정규화된 경로만 반환(원문 재사용 금지) — 경로+쿼리+해시 보존", () => {
    expect(resolveNextPath("/ko/sales/sites?tab=a#top", "ko")).toBe("/ko/sales/sites?tab=a#top");
  });
});

describe("loginUrlWithReturn — 현재 경로를 next로 실은 로그인 URL", () => {
  const setLocation = (pathname: string, search = "") => {
    Object.defineProperty(window, "location", {
      value: { pathname, search },
      writable: true,
      configurable: true,
    });
  };

  it("일반 화면 → next에 경로+쿼리 인코딩", () => {
    setLocation("/ko/sales/sites", "");
    expect(loginUrlWithReturn("ko")).toBe(`/ko/login?next=${encodeURIComponent("/ko/sales/sites")}`);
    setLocation("/ko/projects", "?tab=cost");
    expect(loginUrlWithReturn("ko")).toBe(`/ko/login?next=${encodeURIComponent("/ko/projects?tab=cost")}`);
  });

  it("로그인/가입 화면에서는 next 생략(루프 방지)", () => {
    setLocation("/ko/login", "?next=%2Fko%2Fsales%2Fsites");
    expect(loginUrlWithReturn("ko")).toBe("/ko/login");
    setLocation("/ko/register", "");
    expect(loginUrlWithReturn("ko")).toBe("/ko/login");
  });
});
