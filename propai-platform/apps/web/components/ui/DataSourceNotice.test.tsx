import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DataSourceNotice } from "./DataSourceNotice";

describe("DataSourceNotice", () => {
  it("renders source + updatedAt + default note, with token-based style", () => {
    render(<DataSourceNotice source="국토교통부 실거래가" updatedAt="2026-07-12" />);

    const notice = screen.getByText(/출처: 국토교통부 실거래가/);
    // 출처·갱신일·기본 문구가 한 줄로 결합
    expect(notice.textContent).toBe(
      "출처: 국토교통부 실거래가 · 갱신 2026-07-12 · 참고용 · 법적 효력 없음"
    );
    // DESIGN.md B1 계약: 11px · 뮤트 텍스트 토큰 · 상단 1px 뮤트 보더
    expect(notice).toHaveStyle({ fontSize: "11px" });
    expect(notice.getAttribute("style")).toContain("var(--on-surface-muted)");
    expect(notice.getAttribute("style")).toContain("var(--border-muted)");
  });

  it("omits updatedAt when not provided and honors a custom note", () => {
    render(<DataSourceNotice source="VWorld" note="내부 추정치" />);
    const notice = screen.getByText(/출처: VWorld/);
    expect(notice.textContent).toBe("출처: VWorld · 내부 추정치");
    expect(notice.textContent).not.toContain("갱신");
  });
});
