import type { ReactNode } from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import FeasibilityPage from "../[locale]/(dashboard)/projects/[id]/feasibility/page";
import OfflinePage from "../offline/page";

vi.mock("@/components/feasibility/FeasibilityEditorV2", () => ({
  FeasibilityEditorV2: () => (
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
  it("renders the feasibility live route shell", async () => {
    render(await FeasibilityPage({ params: Promise.resolve({ locale: "en", id: "p001" }) }));

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
      screen.getByRole("link", { name: "Open precheck workspace" }),
    ).toHaveAttribute("href", "/ko/precheck");
  });
});
