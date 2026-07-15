import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { MarkdownLite } from "./MarkdownLite";

describe("MarkdownLite — 경량 안전 마크다운 렌더러", () => {
  it("빈/공백/null 텍스트는 아무것도 렌더하지 않는다(무목업)", () => {
    const { container: c1 } = render(<MarkdownLite text={null} />);
    expect(c1.firstChild).toBeNull();
    const { container: c2 } = render(<MarkdownLite text="   " />);
    expect(c2.firstChild).toBeNull();
    const { container: c3 } = render(<MarkdownLite text={undefined} />);
    expect(c3.firstChild).toBeNull();
  });

  it("헤딩(##)을 제목 요소로 렌더하고 원문 '##' 기호는 노출하지 않는다", () => {
    const { container } = render(<MarkdownLite text={"## 설계 개요\n본문"} />);
    const text = container.textContent ?? "";
    expect(text).toContain("설계 개요");
    expect(text).not.toContain("##");
  });

  it("굵게(**)를 <strong>으로 렌더하고 '**' 기호는 노출하지 않는다", () => {
    const { container } = render(<MarkdownLite text={"**중요** 항목"} />);
    expect(container.querySelector("strong")?.textContent).toBe("중요");
    expect(container.textContent ?? "").not.toContain("**");
  });

  it("불릿 목록(-)을 <ul><li>로 렌더한다", () => {
    const { container } = render(<MarkdownLite text={"- 첫째\n- 둘째"} />);
    const items = container.querySelectorAll("ul li");
    expect(items).toHaveLength(2);
    expect(items[0].textContent).toBe("첫째");
    expect(container.textContent ?? "").not.toMatch(/^-\s/);
  });

  it("번호 목록(1.)을 <ol><li>로 렌더한다", () => {
    const { container } = render(<MarkdownLite text={"1. 하나\n2. 둘"} />);
    const items = container.querySelectorAll("ol li");
    expect(items).toHaveLength(2);
    expect(items[1].textContent).toBe("둘");
  });

  it("구분선(---)을 <hr>로 렌더한다", () => {
    const { container } = render(<MarkdownLite text={"위\n\n---\n\n아래"} />);
    expect(container.querySelector("hr")).not.toBeNull();
    expect(container.textContent ?? "").not.toContain("---");
  });

  it("XSS 안전: <script>/HTML은 실행되지 않고 텍스트로 표시된다", () => {
    const { container } = render(
      <MarkdownLite text={"<script>alert('x')</script> 안전"} />,
    );
    // script 태그가 DOM에 실제 삽입되지 않아야 한다(innerHTML 미사용).
    expect(container.querySelector("script")).toBeNull();
    expect(container.textContent ?? "").toContain("안전");
  });

  it("위험 스킴 링크(javascript:)는 <a>를 만들지 않고 텍스트만 남긴다", () => {
    const { container } = render(
      <MarkdownLite text={"[클릭](javascript:alert(1)) 및 [정상](https://ex.com)"} />,
    );
    const links = container.querySelectorAll("a");
    // 정상 https 링크 1개만 앵커가 되고, javascript: 링크는 앵커가 아니어야 한다.
    expect(links).toHaveLength(1);
    expect(links[0].getAttribute("href")).toBe("https://ex.com");
    expect(container.textContent ?? "").toContain("클릭");
  });

  it("래퍼 className을 상속용으로 그대로 얹는다(글자 크기·색 유지)", () => {
    const { container } = render(
      <MarkdownLite text={"본문"} className="text-sm text-[var(--text-secondary)]" />,
    );
    const root = container.firstChild as HTMLElement;
    expect(root.className).toContain("text-sm");
  });
});
