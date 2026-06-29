import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import DashboardPage from "../page";

vi.mock("@/components/onboarding/OnboardingWizard", () => ({
  OnboardingWizard: () => <div data-testid="onboarding-wizard" />,
}));

vi.mock("@/components/dashboard/DashboardProjectLoader", () => ({
  DashboardProjectLoader: ({ locale }: { locale: string }) => (
    <div data-testid="dashboard-project-loader">{locale}</div>
  ),
}));

vi.mock("@/components/pipeline/PipelinePanelClient", () => ({
  PipelinePanelClient: () => <div data-testid="pipeline-panel">Pipeline</div>,
}));

describe("Dashboard home navigation", () => {
  it("renders the result-generation control room entry links", async () => {
    render(await DashboardPage({ params: Promise.resolve({ locale: "en" }) }));

    expect(screen.getByText("Intelligence Control Room")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "필요한 결과물을 고르면 입력부터 보고서까지 이어집니다" }),
    ).toBeInTheDocument();

    expect(screen.getByRole("link", { name: /후보지 진단서 만들기/ })).toHaveAttribute("href", "/en/precheck");
    expect(screen.getByRole("link", { name: "프로젝트 불러오기" })).toHaveAttribute("href", "/en/projects");
    expect(screen.getByRole("link", { name: /전체 흐름 보기/ })).toHaveAttribute("href", "/en/guide");
  });

  it("wires creation products to their source workflows", async () => {
    render(await DashboardPage({ params: Promise.resolve({ locale: "en" }) }));

    expect(screen.getByText("무엇을 만들까요?")).toBeInTheDocument();
    expect(screen.getAllByText("입력").length).toBeGreaterThan(1);
    expect(screen.getAllByText("결과").length).toBeGreaterThan(1);

    expect(screen.getByText("후보지 진단서").closest("a")).toHaveAttribute("href", "/en/precheck");
    expect(screen.getByText("사업성 검토서").closest("a")).toHaveAttribute("href", "/en/analytics/investment");
    expect(screen.getByText("시장·분양 리포트").closest("a")).toHaveAttribute("href", "/en/market-insights");
    expect(screen.getByText("인허가 체크리스트").closest("a")).toHaveAttribute("href", "/en/permits");
    expect(screen.getByText("AI 설계 검토서").closest("a")).toHaveAttribute("href", "/en/design-audit");
    expect(screen.getByText("투자 의사결정 브리프").closest("a")).toHaveAttribute("href", "/en/projects");
    expect(screen.getByTestId("dashboard-project-loader")).toHaveTextContent("en");
  });
});
