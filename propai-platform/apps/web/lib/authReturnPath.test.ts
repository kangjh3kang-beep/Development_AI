import { describe, it, expect } from "vitest";
import { resolveNextPath } from "./authReturnPath";

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
});
