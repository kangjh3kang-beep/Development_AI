import type { ReactNode } from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import KdxDashboardPage from "../dashboard/kdx/page";
import FeasibilityPage from "../feasibility/page";
import OfflinePage from "../offline/page";

vi.mock("@/components/dashboard/kdx/KdxMonitoringWorkspaceClient", () => ({
  KdxMonitoringWorkspaceClient: () => (
    <div data-testid="kdx-monitoring-workspace">KDX monitoring workspace</div>
  ),
}));

vi.mock("@/components/feasibility/FeasibilityWorkspaceClient", () => ({
  FeasibilityWorkspaceClient: () => (
    <div data-testid="feasibility-workspace">Feasibility workspace</div>
  ),
}));

vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: ReactNode }) => (
    <div data-testid="recharts-responsive">{children}</div>
  ),
  BarChart: ({ children }: { children: ReactNode }) => (
    <div data-testid="recharts-bar-chart">{children}</div>
  ),
  CartesianGrid: () => null,
  Legend: () => null,
  Tooltip: () => null,
  XAxis: () => null,
  YAxis: () => null,
  Bar: () => null,
}));

describe("Auxiliary route shells", () => {
  it("renders the KDX monitoring route shell", () => {
    render(<KdxDashboardPage />);

    expect(screen.getByTestId("kdx-monitoring-workspace")).toBeInTheDocument();
  });

  it("renders the feasibility live route shell", () => {
    render(<FeasibilityPage />);

    expect(screen.getByTestId("feasibility-workspace")).toBeInTheDocument();
  });

  it("renders the offline fallback route shell", () => {
    render(<OfflinePage />);

    expect(screen.getByText("Offline workspace is ready.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open dashboard" })).toHaveAttribute(
      "href",
      "/ko",
    );
    expect(
      screen.getByRole("link", { name: "Open inspection workspace" }),
    ).toHaveAttribute("href", "/ko/inspection");
  });
});
