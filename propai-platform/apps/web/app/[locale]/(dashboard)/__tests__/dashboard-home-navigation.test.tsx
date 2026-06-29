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

vi.mock("@/components/pipeline/PipelinePanelClient", () => ({
  PipelinePanelClient: () => <div data-testid="pipeline-panel">Pipeline</div>,
}));

describe("Dashboard home navigation", () => {
  it("renders the operations console entry links", async () => {
    render(await DashboardPage({ params: Promise.resolve({ locale: "en" }) }));

    expect(screen.getByText("오늘의 워크스페이스")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "다음 액션만 남긴 개발사업 운영판" })).toBeInTheDocument();

    expect(screen.getByRole("link", { name: "프로젝트 생성" })).toHaveAttribute("href", "/en/projects/new");
    expect(screen.getByRole("link", { name: "90초 진단" })).toHaveAttribute("href", "/en/precheck");
    expect(screen.getByRole("link", { name: "프로젝트 보기" })).toHaveAttribute("href", "/en/projects");
    expect(screen.getByRole("link", { name: "흐름 보기" })).toHaveAttribute("href", "/en/guide");
  });

  it("renders simplified lifecycle and priority action wiring", async () => {
    render(await DashboardPage({ params: Promise.resolve({ locale: "en" }) }));

    expect(screen.getByRole("link", { name: /01\s+후보지/ })).toHaveAttribute("href", "/en/precheck");
    expect(screen.getByRole("link", { name: /02\s+분석/ })).toHaveAttribute("href", "/en/analysis");
    expect(screen.getByRole("link", { name: /03\s+사업성/ })).toHaveAttribute("href", "/en/analytics/investment");
    expect(screen.getByRole("link", { name: /06\s+운영/ })).toHaveAttribute("href", "/en/digital-twin");

    expect(screen.getByRole("link", { name: /후보지 진단/ })).toHaveAttribute("href", "/en/precheck");
    expect(screen.getByRole("link", { name: /프로젝트 관리/ })).toHaveAttribute("href", "/en/projects");
    expect(screen.getByRole("link", { name: /시장·획득 보기/ })).toHaveAttribute("href", "/en/market-insights");
    expect(screen.getByTestId("dashboard-project-loader")).toHaveTextContent("en");
  });
});
