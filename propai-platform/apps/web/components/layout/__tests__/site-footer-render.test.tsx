import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  BUSINESS_INFO,
  LEGAL_DISCLOSURE_KEYS,
  SiteFooter,
} from "@/components/layout/SiteFooter";

/**
 * ★행위 락 — 「값이 있다」와 「실제로 그려진다」는 다른 축이다.
 *
 *   재료 락(값 존재 + 전역 배선)만 있었을 때 **푸터 JSX 에서 통신판매업 줄을 지우는 변이가
 *   SURVIVED** 했다. 검수자는 소스가 아니라 **화면**을 본다.
 */
describe("SiteFooter 렌더", () => {
  it("★전자상거래법 표시항목이 **전수** 화면에 그려진다(정본 목록에서 파생)", () => {
    render(<SiteFooter locale="ko" />);
    const footer = screen.getByTestId("site-footer");
    // ★손으로 세 개를 고르던 자리다. 그래서 소재지·대표번호 줄을 지우는 변이가 SURVIVED 했다.
    //   이제 목록에서 파생하므로 항목이 늘면 자동으로 편입된다.
    expect(LEGAL_DISCLOSURE_KEYS.length, "표시항목 목록이 비었다 — 조회기 사망").toBeGreaterThanOrEqual(6);
    for (const k of LEGAL_DISCLOSURE_KEYS) {
      const v = BUSINESS_INFO[k];
      expect(v.trim(), `${k} 값이 비었다`).not.toBe("");
      expect(footer.textContent, `${k}(${v}) 가 화면에 없다`).toContain(v);
    }
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
