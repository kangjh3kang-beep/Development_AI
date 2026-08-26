/**
 * 일괄 등기분석 **한 행의 렌더 락**.
 *
 * 【왜 렌더인가】
 * 이 행은 그동안 거대 클라이언트 안에 인라인이라 소스 grep 으로만 잠갔다. 그 결과
 * 2026-08-24 변이 감사에서 이 행의 렌더 변이가 **줄줄이 생존했다**(className·testid·JSX).
 * 소스 검사는 "무엇이 쓰여 있나"를 보지만 사용자가 보는 것은 "무엇이 그려지나"다.
 * 행을 순수 컴포넌트로 뽑고 여기서 **DOM 을 직접 태운다**.
 *
 * 【실장애 — 이 락이 막는 것】
 * 오산 내삼미동 448-2·347-8 은 등기 PDF 가 **정상 발급**됐는데 화면이
 * **"안전성 주의 · 분석 불가"** 라고 말했다. 백엔드 LLM 폴백이 `safety_grade:"주의"` 를
 * 담아 오는데 화면이 그것을 **존재만으로** 칠했기 때문이다 — 아무것도 판정하지 않은 건에
 * 판정 배지가 붙었고, 진짜 사유(`ai.failure_reason`)는 화면에 한 번도 나온 적이 없다.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RegistryBatchRow, type RegistryBatchRowItem } from "../RegistryBatchRow";

/** 권리분석까지 정상적으로 나온 건. */
const 성공: RegistryBatchRowItem = {
  jibun: "내삼미동 357-2",
  result: {
    status: "ok",
    ai: { generated: true, safety_grade: "안전", summary: "근저당 없음 · 단독소유" },
  },
};

/** 등기는 발급됐는데 **권리분석(LLM)만** 실패한 건 — 실장애의 형태. */
const 폴백: RegistryBatchRowItem = {
  jibun: "내삼미동 448-2",
  result: {
    status: "ok",
    ai: {
      generated: false,
      safety_grade: "주의",
      summary: "분석 불가",
      failure_reason: "JSONDecodeError: Unterminated string",
    },
  },
};

describe("일괄 등기분석 행 — 렌더", () => {
  it("전제: 두 픽스처가 **실제로 다른 화면**을 만든다(공허한 초록 방지)", () => {
    const a = render(<RegistryBatchRow item={성공} />).container.textContent;
    const b = render(<RegistryBatchRow item={폴백} />).container.textContent;
    expect(a).toBeTruthy();
    expect(a).not.toBe(b);
  });

  it("★분석이 나온 건은 등급 배지를 그린다", () => {
    render(<RegistryBatchRow item={성공} />);
    expect(screen.getByTestId("row-grade").textContent).toContain("안전");
    expect(screen.queryByTestId("row-reason")).toBeNull();
  });

  it("★★분석이 안 나온 건은 **등급을 그리지 않는다** — 폴백의 '주의'는 판정이 아니다", () => {
    render(<RegistryBatchRow item={폴백} />);
    expect(screen.queryByTestId("row-grade"), "판정하지 않은 건에 안전성 배지가 붙었다").toBeNull();
    // 화면 어디에도 "안전성 주의" 가 없어야 한다(배지를 다른 자리로 옮겨도 잡힌다).
    expect(document.body.textContent).not.toContain("안전성");
  });

  it("★★실패 사유를 **본문에** 그린다 — '분석 불가' 네 글자로 뭉개지 않는다", () => {
    render(<RegistryBatchRow item={폴백} />);
    const reason = screen.getByTestId("row-reason");
    expect(reason.textContent).toContain("JSONDecodeError");
    // 툴팁에도 같은 사유가 있어야 잘린 문자열을 확인할 수 있다.
    expect(reason.getAttribute("title")).toContain("JSONDecodeError");
  });

  it("★폴백의 `summary`('분석 불가')를 성과처럼 덧붙이지 않는다", () => {
    render(<RegistryBatchRow item={폴백} />);
    expect(screen.queryByTestId("row-summary")).toBeNull();
    expect(document.body.textContent).not.toContain("분석 불가");
  });

  it("성공 건은 요약을 보여 준다(대조군 — 위 규칙이 요약을 통째로 죽인 게 아님)", () => {
    render(<RegistryBatchRow item={성공} />);
    expect(screen.getByTestId("row-summary").textContent).toContain("근저당 없음");
  });

  it("발급 자체가 실패한 건은 그 사유를 그린다", () => {
    render(
      <RegistryBatchRow
        item={{ jibun: "내삼미동 100-1", result: { status: "error", message: "민원캐시 잔액이 부족합니다" } }}
      />,
    );
    expect(screen.getByTestId("row-reason").textContent).toContain("잔액이 부족");
  });

  it("응답 자체가 없으면 요청 실패라고 말한다(사유 없음과 구분)", () => {
    render(<RegistryBatchRow item={{ jibun: "x", result: null }} />);
    expect(screen.getByTestId("row-reason").textContent).toContain("요청 실패");
  });

  it("★'상세'가 콜백을 부른다 — 버튼이 그려지기만 하고 배선이 끊긴 적이 있다", () => {
    let called = 0;
    render(<RegistryBatchRow item={성공} onDetail={() => { called += 1; }} />);
    fireEvent.click(screen.getByRole("button", { name: "상세" }));
    expect(called).toBe(1);
  });

  it("★등급별로 **다른 색**을 칠한다(세 등급이 같은 색이면 배지가 정보가 아니다)", () => {
    const cls = (grade: string) => {
      const { unmount, container } = render(
        <RegistryBatchRow
          item={{ jibun: "x", result: { status: "ok", ai: { generated: true, safety_grade: grade } } }}
        />,
      );
      const c = container.querySelector('[data-testid="row-grade"]')!.className;
      unmount();
      return c;
    };
    const [안전, 주의, 위험] = ["안전", "주의", "위험"].map(cls);
    expect(new Set([안전, 주의, 위험]).size, "등급 색이 겹친다").toBe(3);
    expect(위험).toContain("status-error");
  });

  it("★★권리분석이 실패해도 **발급된 PDF 는 연결한다** — 돈 내고 받은 문서다", () => {
    render(
      <RegistryBatchRow
        item={{ ...폴백, result: { ...폴백.result!, fetched: { pdf_url: "https://x/y.pdf" } } }}
      />,
    );
    const a = screen.getByTestId("row-pdf") as HTMLAnchorElement;
    expect(a.getAttribute("href")).toBe("https://x/y.pdf");
    // 사유는 여전히 보인다 — PDF 링크가 실패 사실을 덮으면 안 된다.
    expect(screen.getByTestId("row-reason").textContent).toContain("JSONDecodeError");
  });

  it("대조군 — PDF 가 없으면 링크를 만들지 않는다(죽은 링크를 그리지 않는다)", () => {
    render(<RegistryBatchRow item={폴백} />);
    expect(screen.queryByTestId("row-pdf")).toBeNull();
  });

  it("★재사용한 등기부는 **언제 발급분인지** 말한다(조용히 옛 등기부를 보여 주지 않는다)", () => {
    render(
      <RegistryBatchRow
        item={{
          ...성공,
          result: {
            ...성공.result!,
            fetched: { reused_issue: true, issued_at: "2026-08-20T01:02:03+00:00" },
          },
        }}
      />,
    );
    expect(screen.getByTestId("row-reused").textContent).toContain("2026-08-20");
  });

  it("대조군 — 새로 발급한 건에는 재사용 표기를 붙이지 않는다", () => {
    render(<RegistryBatchRow item={성공} />);
    expect(screen.queryByTestId("row-reused")).toBeNull();
  });

  it("★★만료된 PDF 링크를 **살아 있는 것처럼 그리지 않는다**", () => {
    // 라이브 실측: 저장 79건 중 표본 3건에서 2건이 이미 만료였는데 화면은 `PDF ↗` 를
    // 똑같이 그렸다 — 누르면 JSON 오류 덩어리가 열린다.
    const b64 = (o: unknown) =>
      Buffer.from(JSON.stringify(o)).toString("base64")
        .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
    const expired = `https://x/a.pdf?token=${b64({ alg: "HS256" })}.${b64({ exp: 1 })}.s`;
    render(
      <RegistryBatchRow item={{ ...성공, result: { ...성공.result!, fetched: { pdf_url: expired } } }} />,
    );
    expect(screen.queryByTestId("row-pdf"), "죽은 링크를 살아 있는 것처럼 그렸다").toBeNull();
    expect(screen.getByTestId("row-pdf-expired").textContent).toContain("PDF 만료");
  });

  it("★대조군 — 아직 남은 링크는 그대로 누를 수 있다", () => {
    const b64 = (o: unknown) =>
      Buffer.from(JSON.stringify(o)).toString("base64")
        .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
    const alive = `https://x/a.pdf?token=${b64({ alg: "HS256" })}.${b64({ exp: 4102444800 })}.s`;
    render(
      <RegistryBatchRow item={{ ...성공, result: { ...성공.result!, fetched: { pdf_url: alive } } }} />,
    );
    expect(screen.getByTestId("row-pdf")).toBeTruthy();
    expect(screen.queryByTestId("row-pdf-expired")).toBeNull();
  });

  it("★만료를 **못 읽는** 링크는 감추지 않는다(살아 있는 링크를 죽이지 않는다)", () => {
    render(
      <RegistryBatchRow item={{ ...성공, result: { ...성공.result!, fetched: { pdf_url: "https://x/plain.pdf" } } }} />,
    );
    expect(screen.getByTestId("row-pdf")).toBeTruthy();
  });

  it("다른 물건을 조회했을 수 있다는 고지는 행에서도 보인다", () => {
    render(
      <RegistryBatchRow
        item={{ ...성공, result: { ...성공.result!, fetched: { select_note: "토지 대신 건물을 열람" } } }}
      />,
    );
    expect(screen.getByTestId("row-select-note").textContent).toContain("물건 확인 필요");
  });
});
