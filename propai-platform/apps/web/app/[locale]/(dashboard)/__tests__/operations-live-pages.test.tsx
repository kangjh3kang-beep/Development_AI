import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
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

  it("renders the tenant page with the tenant-only workspace", async () => {
    render(await TenantPage({ params: Promise.resolve({ locale: "en" }) }));

    expect(screen.getByText("테넌트 경험 센터")).toBeInTheDocument();
    expect(screen.getByText("tenant")).toBeInTheDocument();
    expect(screen.getByText("hero-off")).toBeInTheDocument();
  });

  it("renders the digital twin page with the v53 control tower", async () => {
    render(await DigitalTwinPage({ params: Promise.resolve({ locale: "en" }) }));

    expect(screen.getByTestId("digital-twin-control-tower")).toHaveTextContent("en");
    expect(screen.getByTestId("digital-twin-dashboard")).toHaveTextContent(
      "anomaly-dashboard",
    );
  });
});
