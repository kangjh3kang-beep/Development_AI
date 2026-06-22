import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ConstructionCostWorkspaceClient } from "@/components/analytics/ConstructionCostWorkspaceClient";
import { renderWithQueryClient } from "@/test/render-with-query-client";

// NOTE: The component evolved into a self-contained local simulation. It no
// longer calls `apiClient` — material prices come from an in-component KCCI
// reference table and escalation results are computed client-side from the
// form inputs. These tests assert that current, real, user-facing behavior:
// the hero copy renders, the refresh action produces material rows, and the
// analyze action produces an escalation summary + impact rows.

describe("ConstructionCostWorkspaceClient", () => {
  it("renders the cost intelligence hero copy", async () => {
    renderWithQueryClient(<ConstructionCostWorkspaceClient locale="ko" />);

    expect(
      await screen.findByText("KCCI 자재가와 PPI 공사비 보정 시뮬레이션"),
    ).toBeInTheDocument();
    expect(
      await screen.findByText(/프로젝트별 자재 노출액과 최신 공사비 보정안/),
    ).toBeInTheDocument();
  });

  it("renders local material price rows after refreshing", async () => {
    renderWithQueryClient(<ConstructionCostWorkspaceClient locale="ko" />);

    await screen.findByText("KCCI 자재가와 PPI 공사비 보정 시뮬레이션");

    const buttons = await screen.findAllByRole("button");
    const refreshBtn = buttons.find((button) =>
      button.textContent?.includes("자재가"),
    );
    if (!refreshBtn) {
      throw new Error("Could not find the material refresh button");
    }

    await userEvent.click(refreshBtn);

    // Default form material codes include ready_mix_concrete -> 레미콘 25-21-15.
    expect(
      (await screen.findAllByText("레미콘 25-21-15")).length,
    ).toBeGreaterThan(0);
    // KCCI source label is surfaced for the rendered snapshot.
    expect(
      await screen.findByText(/KCCI 한국건설자재협회/),
    ).toBeInTheDocument();
  });

  it("computes and renders an escalation summary after analysis", async () => {
    renderWithQueryClient(<ConstructionCostWorkspaceClient locale="ko" />);

    await screen.findByText("KCCI 자재가와 PPI 공사비 보정 시뮬레이션");

    const buttons = await screen.findAllByRole("button");
    const analyzeBtn = buttons.find((button) =>
      button.textContent?.includes("에스컬레이션"),
    );
    if (!analyzeBtn) {
      throw new Error("Could not find the escalation analyze button");
    }

    await userEvent.click(analyzeBtn);

    // Default form: baselineYear 2024 -> targetYear 2027, so the computed
    // summary reflects the material/labor escalation over that span.
    await waitFor(async () => {
      expect(
        await screen.findByText(/기간 자재비.*상승 반영/),
      ).toBeInTheDocument();
    });
    // PPI source attribution rendered alongside the adjusted cost.
    expect(
      await screen.findByText(/한국은행 PPI \+ KCCI 자재가격지수/),
    ).toBeInTheDocument();
  });
});
