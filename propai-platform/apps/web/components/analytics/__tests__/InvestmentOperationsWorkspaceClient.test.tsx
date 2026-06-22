import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { InvestmentOperationsWorkspaceClient } from "@/components/analytics/InvestmentOperationsWorkspaceClient";
import { renderWithQueryClient } from "@/test/render-with-query-client";

// NOTE: This component evolved into a local/synthetic workspace. It no longer
// calls apiClient at all — the project / AI-cost / market-data queries return
// empty static payloads, and the budget/report/portal actions are computed
// locally on submit. The tests below assert that *current* real behavior
// (hero render, empty states, and the synthetic submit results the user sees),
// not the retired live-API contract.

describe("InvestmentOperationsWorkspaceClient", () => {
  it("renders the control tower and computes a local budget gate on save", async () => {
    renderWithQueryClient(<InvestmentOperationsWorkspaceClient locale="ko" />);

    // Hero renders once mounted (past the isMounted skeleton gate).
    expect(
      await screen.findByText("투자 운영 컨트롤타워"),
    ).toBeInTheDocument();

    // Project picker has no live projects -> empty-state label is shown.
    expect(
      await screen.findByText(
        "라이브 프로젝트가 아직 없습니다. 생성된 UUID를 알고 있다면 직접 입력하면 됩니다.",
      ),
    ).toBeInTheDocument();

    // AI cost dashboard renders its tracked-services label (data is present
    // but empty, so the by_service list is empty).
    expect(await screen.findByText("추적 서비스")).toBeInTheDocument();

    // Saving a budget runs the local synthetic computation:
    // budget=150, currentCost=round(150*0.35)=52.5, remaining=97.50.
    await userEvent.click(
      screen.getByRole("button", { name: "예산 저장" }),
    );

    expect(
      await screen.findByText(/잔여 예산: US\$97\.50/i),
    ).toBeInTheDocument();
  });

  it("generates an investor report and publishes portal listings locally", async () => {
    renderWithQueryClient(<InvestmentOperationsWorkspaceClient locale="en" />);

    // English hero confirms locale wiring.
    expect(
      await screen.findByText("Investment operations control tower"),
    ).toBeInTheDocument();

    // Report generation produces variants from the default target languages
    // (ko,en,ja) plus the generated-sections summary line.
    await userEvent.click(
      screen.getByRole("button", { name: "Generate report" }),
    );

    expect(
      await screen.findByText(/Generated sections:/i),
    ).toBeInTheDocument();
    // One variant per default target language (ko, en, ja) -> KO/EN/JA tags.
    expect(await screen.findByText("EN")).toBeInTheDocument();
    expect(await screen.findByText("JA")).toBeInTheDocument();

    // Publishing emits one listing card per portal in the default list
    // (naver, zigbang, dabang), each shown with its "published" status.
    await userEvent.click(
      screen.getByRole("button", { name: "Publish batch" }),
    );

    await waitFor(() => {
      expect(screen.getByText("naver")).toBeInTheDocument();
    });
    const publishedStatuses = await screen.findAllByText("published");
    expect(publishedStatuses).toHaveLength(3);
  });
});
