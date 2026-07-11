import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithQueryClient } from "@/test/render-with-query-client";
import DigitalTwinPage from "../digital-twin/page";
import MaintenancePage from "../maintenance/page";
import TenantPage from "../tenant/page";

vi.mock("@/components/layout/ModulePlaceholder", () => ({
  ModulePlaceholder: ({
    title,
    statusLabel,
    items,
  }: {
    title: string;
    statusLabel: string;
    items: string[];
  }) => (
    <div data-testid="module-placeholder">
      <h1>{title}</h1>
      <p>{statusLabel}</p>
      <ul>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  ),
}));

vi.mock("@/components/analytics/OperationsIntelligenceWorkspaceClient", () => ({
  OperationsIntelligenceWorkspaceClient: ({
    sections,
    showHero,
  }: {
    sections: string[];
    showHero: boolean;
  }) => (
    <div data-testid="operations-workspace">
      <span>{sections.join(",")}</span>
      <span>{showHero ? "hero-on" : "hero-off"}</span>
    </div>
  ),
}));

vi.mock("@/components/digital-twin/DigitalTwinControlTowerWorkspaceClient", () => ({
  DigitalTwinControlTowerWorkspaceClient: ({
    locale,
  }: {
    locale: string;
  }) => <div data-testid="digital-twin-control-tower">{locale}</div>,
}));

vi.mock("@/components/digital-twin/DigitalTwinAnomalyDashboard", () => ({
  DigitalTwinAnomalyDashboard: () => (
    <div data-testid="digital-twin-dashboard">anomaly-dashboard</div>
  ),
}));

// P2-3: maintenance 페이지에 접힘 마운트된 ParkingLogView는 실제로는 react-query
// useQuery를 사용하므로(QueryClientProvider 필요), 이 셸 스모크 테스트에서는
// dashboard-route-shells.test.tsx와 동일하게 스텁으로 대체한다.
vi.mock("@/components/safety/ParkingLogView", () => ({
  ParkingLogView: () => <div data-testid="parking-log-view">Parking log view</div>,
}));

vi.mock("next/navigation", () => {
  return {
    useParams: () => ({ locale: "en" }),
    usePathname: () => "/en",
    useRouter: () => ({
      push: vi.fn(),
      replace: vi.fn(),
      back: vi.fn(),
      prefetch: vi.fn(),
    }),
  };
});

vi.mock("@/i18n/get-dictionary", () => ({
  getDictionary: vi.fn(async () => ({
    workspace: {
      modeLive: "실연동",
      modeMock: "MOCK",
    },
    nav: {},
    pages: {
      projectDetail: {
        summary: {
          hub: "HUB",
          name: "NAME",
          pnu: "PNU",
          zone: "ZONE",
          npv: "NPV",
          roi: "ROI",
        },
      },
    },
    deepIntegration: {
      lifecycle: {
        title: "Lifecycle",
      },
    },
    modulePlaceholders: {
      maintenance: { title: "예지정비 운영센터", eyebrow: "MAINTENANCE", description: "Desc", items: [] },
      tenant: { title: "테넌트 경험 센터", eyebrow: "TENANT", description: "Desc", items: [] },
    },
  })),
}));

describe("Operations live pages", () => {
  beforeEach(() => {
    vi.stubEnv("NEXT_PUBLIC_USE_MOCKS", "false");
  });

  it("renders the maintenance page with the maintenance-only workspace", async () => {
    render(await MaintenancePage({ params: Promise.resolve({ locale: "en" }) }));

    expect(screen.getByText("예지정비 운영센터")).toBeInTheDocument();
    expect(screen.getByText("실연동")).toBeInTheDocument();
    expect(screen.getByText("maintenance")).toBeInTheDocument();
    expect(screen.getByText("hero-off")).toBeInTheDocument();
  });

  it("mounts ParkingLogView on the maintenance page as a collapsed section (P2-3)", async () => {
    // ★G7 최우선 마운트: 유일하게 라이브 API(/parking/dashboard)를 실호출하는 완성
    // 오펀 컴포넌트를 additive 접힘 섹션으로 마운트했는지 확인(기본 닫힘 상태 유지).
    render(await MaintenancePage({ params: Promise.resolve({ locale: "en" }) }));

    const toggle = screen.getByRole("button", { name: "Parking Control (Live)" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByTestId("parking-log-view")).toHaveTextContent(
      "Parking log view",
    );
  });

  it("renders the tenant page with the tenant management live workspace", async () => {
    renderWithQueryClient(
      (await TenantPage({ params: Promise.resolve({ locale: "en" }) }))!,
    );

    // Page now renders TenantWorkspaceClient (a live useQuery workspace) only —
    // no ModulePlaceholder / OperationsIntelligenceWorkspaceClient.
    expect(
      screen.getByText(
        "View project-based tenant lists, lease status, and payment overview.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Payment overview")).toBeInTheDocument();
    expect(screen.getByText("Tenant list")).toBeInTheDocument();
  });

  it("renders the digital twin page with the v53 control tower", async () => {
    render(await DigitalTwinPage({ params: Promise.resolve({ locale: "en" }) }));

    expect(screen.getByTestId("digital-twin-control-tower")).toHaveTextContent("en");
    expect(screen.getByTestId("digital-twin-dashboard")).toHaveTextContent(
      "anomaly-dashboard",
    );
  });
});
