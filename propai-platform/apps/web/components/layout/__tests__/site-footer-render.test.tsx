import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BUSINESS_INFO, SiteFooter } from "@/components/layout/SiteFooter";

/**
 * ★행위 락 — 「값이 있다」와 「실제로 그려진다」는 다른 축이다.
 *
 *   재료 락(값 존재 + 전역 배선)만 있었을 때 **푸터 JSX 에서 통신판매업 줄을 지우는 변이가
 *   SURVIVED** 했다. 검수자는 소스가 아니라 **화면**을 본다.
 */
describe("SiteFooter 렌더", () => {
  it("★전자상거래법 3종이 화면에 실제로 그려진다", () => {
    render(<SiteFooter locale="ko" />);
    const footer = screen.getByTestId("site-footer");
    // ★세 항목을 각각 태운다 — 하나라도 빠지면 네이버 검수가 반려한다
    expect(footer.textContent).toContain(BUSINESS_INFO.representative);
    expect(footer.textContent).toContain(BUSINESS_INFO.businessNumber);
    expect(footer.textContent).toContain(BUSINESS_INFO.mailOrderNumber);
    // 라벨도 함께 — 값만 있고 무엇인지 안 쓰면 검수자가 못 찾는다
    expect(footer.textContent).toContain("통신판매업 신고번호");
    expect(footer.textContent).toContain("사업자등록번호");
  });

  it("★대조군: 존재하지 않는 값은 안 나온다(공허한 통과 방지)", () => {
    render(<SiteFooter locale="ko" />);
    const footer = screen.getByTestId("site-footer");
    expect(footer.textContent).not.toContain("ZZZ-NOT-PRESENT");
  });

  it("약관·개인정보 링크가 로케일을 따라간다", () => {
    const { rerender } = render(<SiteFooter locale="ko" />);
    expect(screen.getByText("이용약관").getAttribute("href")).toBe("/ko/legal/terms");
    rerender(<SiteFooter locale="en" />);
    expect(screen.getByText("개인정보처리방침").getAttribute("href")).toBe(
      "/en/legal/privacy",
    );
  });
});
