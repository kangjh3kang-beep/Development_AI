import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import DashboardPage from "../page";

vi.mock("@/components/onboarding/OnboardingWizard", () => ({
  OnboardingWizard: () => <div data-testid="onboarding-wizard" />,
}));

vi.mock("@/components/dashboard/DashboardKpiLoader", () => ({
  DashboardKpiLoader: () => <div data-testid="dashboard-kpi-loader">KPI</div>,
}));

vi.mock("@/components/dashboard/DashboardProjectLoader", () => ({
  DashboardProjectLoader: ({ locale }: { locale: string }) => (
    <div data-testid="dashboard-project-loader">{locale}</div>
  ),
}));

vi.mock("@/components/dashboard/DashboardEsgScore", () => ({
  DashboardEsgScore: () => <div data-testid="dashboard-esg-score">ESG</div>,
}));

vi.mock("@/components/pipeline/PipelinePanelClient", () => ({
  PipelinePanelClient: () => <div data-testid="pipeline-panel">Pipeline</div>,
}));

describe("Dashboard home navigation", () => {
  it("renders the operations console entry links", async () => {
    render(await DashboardPage({ params: Promise.resolve({ locale: "en" }) }));

    expect(screen.getByText("사업 관제")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "개발사업의 다음 액션을 한 화면에서 결정합니다." })).toBeInTheDocument();

    expect(screen.getByRole("link", { name: "프로젝트 생성" })).toHaveAttribute("href", "/en/projects/new");
    expect(screen.getByRole("link", { name: "90초 진단" })).toHaveAttribute("href", "/en/precheck");
    expect(screen.getAllByRole("link", { name: "프로젝트 전체 보기" })[0]).toHaveAttribute("href", "/en/projects");
  });

  it("renders lifecycle rail, action queue, and data status wiring", async () => {
    render(await DashboardPage({ params: Promise.resolve({ locale: "en" }) }));

    expect(screen.getByRole("link", { name: /01\s+부지/ })).toHaveAttribute("href", "/en/land-schedule");
    expect(screen.getByRole("link", { name: /02\s+권리/ })).toHaveAttribute("href", "/en/registry-analysis");
    expect(screen.getByRole("link", { name: /07\s+획득/ })).toHaveAttribute("href", "/en/auction");
    expect(screen.getByRole("link", { name: /08\s+운영/ })).toHaveAttribute("href", "/en/digital-twin");

    expect(screen.getByRole("link", { name: /신규 후보지 검토/ })).toHaveAttribute("href", "/en/precheck");
    expect(screen.getByRole("link", { name: /종합 부지분석/ })).toHaveAttribute("href", "/en/analysis");
    expect(screen.getByRole("link", { name: /공공입찰연결/ })).toHaveAttribute("href", "/en/g2b");
    expect(screen.getByTestId("dashboard-project-loader")).toHaveTextContent("en");
  });
});
