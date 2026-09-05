import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

vi.mock("@/lib/registry-rights-ask", async (orig) => {
  const real = await orig<typeof import("@/lib/registry-rights-ask")>();
  return { ...real, askRightsQuestion: vi.fn() };
});
import { askRightsQuestion } from "@/lib/registry-rights-ask";
import { RegistryRightsAsk } from "../RegistryRightsAsk";

const ask = askRightsQuestion as unknown as ReturnType<typeof vi.fn>;
const ANALYSIS = { generated: true, ownership: "공유" };

describe("권리분석 추가질의 UI — 근거와 사유가 화면까지 온다", () => {
  beforeEach(() => ask.mockReset());

  it("★질문을 보내고 **답·근거·주의**를 모두 렌더한다", async () => {
    ask.mockResolvedValue({
      ok: true, answer: "근저당 비율 21.6%", basis: "derived.근저당_대_공시지가_비율_퍼센트=21.6",
      caveat: "공시지가는 실거래가와 다를 수 있습니다",
    });
    render(<RegistryRightsAsk analysis={ANALYSIS} />);
    fireEvent.change(screen.getByTestId("rights-ask-input"), { target: { value: "비율은?" } });
    fireEvent.click(screen.getByTestId("rights-ask-submit"));

    await waitFor(() => expect(screen.getByTestId("rights-ask-answer")).toBeTruthy());
    expect(screen.getByTestId("rights-ask-answer").textContent).toContain("21.6%");
    // ★근거는 **항상** 보여야 한다 — 답만 보이면 검산 불가.
    //   이 경로의 LLM 이 실제로 산술을 4.4배 틀린 적이 있다(라이브 실측).
    expect(screen.getByTestId("rights-ask-basis").textContent).toContain("21.6");
    // ★한계 사유도 화면까지 — 무언 실패 금지
    expect(screen.getByTestId("rights-ask-caveat").textContent).toContain("실거래가");
    // 전달 인자 — 분석 JSON 이 그대로 간다
    expect(ask.mock.calls[0][0]).toBe(ANALYSIS);
    expect(ask.mock.calls[0][1]).toBe("비율은?");
  });

  it("★실패해도 **사유가 보인다**(답이 없어도 화면이 비지 않는다)", async () => {
    ask.mockResolvedValue({ ok: false, answer: "", basis: "", caveat: "권리분석이 완료되지 않았습니다" });
    render(<RegistryRightsAsk analysis={ANALYSIS} />);
    fireEvent.change(screen.getByTestId("rights-ask-input"), { target: { value: "질문" } });
    fireEvent.click(screen.getByTestId("rights-ask-submit"));

    await waitFor(() => expect(screen.getByTestId("rights-ask-caveat")).toBeTruthy());
    expect(screen.queryByTestId("rights-ask-answer"), "답이 없는데 답 영역이 있다").toBeNull();
  });

  it("★빈 질문으로는 보낼 수 없다(버튼 비활성 · 쿼터 낭비 방지)", () => {
    render(<RegistryRightsAsk analysis={ANALYSIS} />);
    const btn = screen.getByTestId("rights-ask-submit") as HTMLButtonElement;
    expect(btn.disabled, "빈 질문인데 보낼 수 있다").toBe(true);
    fireEvent.change(screen.getByTestId("rights-ask-input"), { target: { value: "x" } });
    expect(btn.disabled, "질문이 있는데 못 보낸다").toBe(false);
  });

  it("★질문 길이 상한이 입력에 걸려 있다", () => {
    render(<RegistryRightsAsk analysis={ANALYSIS} />);
    const input = screen.getByTestId("rights-ask-input") as HTMLInputElement;
    expect(Number(input.maxLength)).toBe(500);
  });
});
