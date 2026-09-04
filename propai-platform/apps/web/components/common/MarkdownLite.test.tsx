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

  describe("M3(PR#316 리뷰) — 번호 목록 재번호 왜곡 방지", () => {
    it("날짜형 줄('2025. 7. 16. 착공')은 번호 목록으로 오인하지 않고 연도를 그대로 보존한다", () => {
      const { container } = render(<MarkdownLite text={"2025. 7. 16. 착공"} />);
      // 목록으로 재번호(1.)되지 않고 원문 문단으로 남아야 한다.
      expect(container.querySelector("ol")).toBeNull();
      expect(container.textContent ?? "").toContain("2025. 7. 16. 착공");
    });

    it("진짜 번호 목록 안에 날짜형 줄이 섞이면 목록을 끊고 날짜는 별도 문단으로 보존한다", () => {
      const { container } = render(
        <MarkdownLite text={"1. 첫째\n2025. 7. 16. 착공\n2. 둘째"} />,
      );
      const text = container.textContent ?? "";
      // 연도가 온전히 보존되고, 목록 항목 텍스트로 흡수돼 "1."이 잘려나가는 재번호 왜곡이 없어야 한다.
      expect(text).toContain("2025. 7. 16. 착공");
      // 날짜 줄은 <li> 안이 아니라 별도 문단(<p>)으로 렌더돼야 한다(목록에 흡수되지 않음).
      const dateInListItem = Array.from(container.querySelectorAll("li")).some((li) =>
        (li.textContent ?? "").includes("2025"),
      );
      expect(dateInListItem).toBe(false);
    });

    it("원문 시작번호(<ol start>)를 보존해 3.부터 시작하는 목록이 1.로 재번호되지 않는다", () => {
      const { container } = render(<MarkdownLite text={"3. 셋째\n4. 넷째"} />);
      const ol = container.querySelector("ol");
      expect(ol).not.toBeNull();
      expect(ol?.getAttribute("start")).toBe("3");
      const items = container.querySelectorAll("ol li");
      expect(items[0].textContent).toBe("셋째");
    });

    it("일반 번호 목록(1.부터)은 종전과 동일하게 렌더된다(무회귀)", () => {
      const { container } = render(<MarkdownLite text={"1. 하나\n2. 둘"} />);
      const ol = container.querySelector("ol");
      expect(ol?.getAttribute("start")).toBe("1");
      expect(container.querySelectorAll("ol li")).toHaveLength(2);
    });
  });

  describe("L2(PR#316 리뷰) — safeHref 오픈 리다이렉트 경화", () => {
    it("프로토콜 상대 URL(//evil.com)은 앵커를 만들지 않는다", () => {
      const { container } = render(<MarkdownLite text={"[클릭](//evil.com)"} />);
      expect(container.querySelectorAll("a")).toHaveLength(0);
      expect(container.textContent ?? "").toContain("클릭");
    });

    it("백슬래시 우회(/\\evil.com)는 앵커를 만들지 않는다", () => {
      const { container } = render(<MarkdownLite text={"[클릭](/\\evil.com)"} />);
      expect(container.querySelectorAll("a")).toHaveLength(0);
    });

    it("data: 스킴은 앵커를 만들지 않는다", () => {
      const { container } = render(
        <MarkdownLite text={"[클릭](data:text/html,<script>alert(1)</script>)"} />,
      );
      expect(container.querySelectorAll("a")).toHaveLength(0);
    });

    it("정상 단일 슬래시 상대경로·앵커는 여전히 허용한다(무회귀)", () => {
      const { container } = render(
        <MarkdownLite text={"[내부](/projects/1) 및 [앵커](#section)"} />,
      );
      const links = container.querySelectorAll("a");
      expect(links).toHaveLength(2);
      expect(links[0].getAttribute("href")).toBe("/projects/1");
      expect(links[1].getAttribute("href")).toBe("#section");
    });
  });

  describe("L1(PR#316 리뷰) — 테이블형 줄 모노스페이스 fallback", () => {
    it("파이프 구분 표 행을 <pre> 모노스페이스 블록으로 렌더하고 구분선 행은 생략한다", () => {
      const { container } = render(
        <MarkdownLite text={"| 항목 | 값 |\n| --- | --- |\n| 용적률 | 250% |"} />,
      );
      const pre = container.querySelector("pre");
      expect(pre).not.toBeNull();
      expect(pre?.textContent).toContain("용적률");
      expect(pre?.textContent).toContain("250%");
      // 구분선 행(|---|---|)은 시각 잡음이라 출력에서 제외.
      expect(pre?.textContent ?? "").not.toMatch(/---/);
    });
  });
});
