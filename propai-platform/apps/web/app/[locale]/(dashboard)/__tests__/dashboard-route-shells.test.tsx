import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AgentPage from "../agent/page";
import CostPage from "../analytics/cost/page";
import ESGPage from "../analytics/esg/page";
import InvestmentPage from "../analytics/investment/page";
import IoTPage from "../analytics/iot/page";
import ApprovalsPage from "../approvals/page";
import AuctionPage from "../auction/page";
import DashboardPage from "../page";
import InspectionPage from "../inspection/page";
import ProjectsPage from "../projects/page";
import SafetyPage from "../safety/page";
import SREPage from "../sre/page";
import TaxPage from "../tax/page";
import WebRTCPage from "../webrtc/page";

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

vi.mock("@/components/layout/OverviewCard", () => ({
  OverviewCard: ({
    title,
    href,
  }: {
    title: string;
    href: string;
  }) => (
    <div data-testid="overview-card">
      <span>{title}</span>
      <span>{href}</span>
    </div>
  ),
}));

vi.mock("@/components/dashboard/DashboardClientPanel", () => ({
  DashboardClientPanel: ({
    locale,
    summaryTitle,
  }: {
    locale: string;
    summaryTitle: string;
  }) => (
    <div data-testid="dashboard-client-panel">
      <span>{locale}</span>
      <span>{summaryTitle}</span>
    </div>
  ),
}));

vi.mock("@/components/pwa/PwaStatusCard", () => ({
  PwaStatusCard: () => <div data-testid="pwa-status-card">PWA status card</div>,
}));

vi.mock("@/components/projects/ProjectsOverviewClient", () => ({
  ProjectsOverviewClient: ({
    locale,
  }: {
    locale: string;
  }) => <div data-testid="projects-overview-client">{locale}</div>,
}));

vi.mock("@/components/auction/AuctionWorkspaceClient", () => ({
  AuctionWorkspaceClient: ({
    locale,
  }: {
    locale: string;
  }) => <div data-testid="auction-workspace">{locale}</div>,
}));

vi.mock("@/components/analytics/TaxOperationsWorkspaceClient", () => ({
  TaxOperationsWorkspaceClient: ({
    locale,
  }: {
    locale: string;
  }) => <div data-testid="tax-workspace">{locale}</div>,
}));

vi.mock("@/components/analytics/InspectionOperationsWorkspaceClient", () => ({
  InspectionOperationsWorkspaceClient: ({
    locale,
  }: {
    locale: string;
  }) => <div data-testid="inspection-workspace">{locale}</div>,
}));

vi.mock("@/components/analytics/InvestmentOperationsWorkspaceClient", () => ({
  InvestmentOperationsWorkspaceClient: ({
    locale,
  }: {
    locale: string;
  }) => <div data-testid="investment-workspace">{locale}</div>,
}));

vi.mock("@/components/analytics/EnergyOperationsWorkspaceClient", () => ({
  EnergyOperationsWorkspaceClient: ({
    locale,
  }: {
    locale: string;
  }) => <div data-testid="energy-workspace">{locale}</div>,
}));

vi.mock("@/components/analytics/ConstructionCostWorkspaceClient", () => ({
  ConstructionCostWorkspaceClient: ({
    locale,
  }: {
    locale: string;
  }) => <div data-testid="cost-workspace">{locale}</div>,
}));

vi.mock("@/components/analytics/OperationsIntelligenceWorkspaceClient", () => ({
  OperationsIntelligenceWorkspaceClient: ({
    locale,
  }: {
    locale: string;
  }) => <div data-testid="ops-intelligence-workspace">{locale}</div>,
}));

vi.mock("@/components/agent/AgentOrchestrationWorkspaceClient", () => ({
  AgentOrchestrationWorkspaceClient: ({
    locale,
  }: {
    locale: string;
  }) => <div data-testid="agent-workspace">{locale}</div>,
}));

vi.mock("@/components/agent/ApprovalOperationsWorkspaceClient", () => ({
  ApprovalOperationsWorkspaceClient: ({
    locale,
  }: {
    locale: string;
  }) => <div data-testid="approval-ops-workspace">{locale}</div>,
}));

vi.mock("@/components/safety/SafetyCCTVDashboard", () => ({
  SafetyCCTVDashboard: () => (
    <div data-testid="safety-cctv-dashboard">Safety CCTV dashboard</div>
  ),
}));

vi.mock("@/components/safety/ParkingLogView", () => ({
  ParkingLogView: () => <div data-testid="parking-log-view">Parking log view</div>,
}));

vi.mock("@/features/webrtc/RemoteSupervisionRoom", () => ({
  RemoteSupervisionRoom: () => (
    <div data-testid="remote-supervision-room">Remote supervision room</div>
  ),
}));

vi.mock("@/components/sre/SREDashboard", () => ({
  SREDashboard: () => <div data-testid="sre-dashboard">SRE dashboard</div>,
}));

vi.mock("@/i18n/get-dictionary", () => ({
  getDictionary: vi.fn(async () => ({
    hero: {
      badge: "PROP AI",
    },
    dashboard: {
      title: "Dashboard home",
      description: "Live operating center",
      summaryTitle: "Summary panel",
    },
    workspace: {
      modeLive: "LIVE",
      modeMock: "MOCK",
    },
    status: {
      mock: "MOCK",
      ready: "READY",
    },
    nav: {
      projects: "Projects",
      auction: "Auction",
      tax: "Tax",
      inspection: "Inspection",
      design: "Design",
      bim: "BIM",
      finance: "Finance",
      drone: "Drone",
      blockchain: "Blockchain",
      report: "Report",
    },
    pages: {
      agent: {
        eyebrow: "AGENT / LIVE",
        title: "Agent orchestration center",
        description: "Live domain agent orchestration",
        items: {
          first: "Focused domain run",
          second: "Multi-domain orchestration",
          third: "Approval-gated review",
        },
      },
      auction: {
        eyebrow: "AUCTION / LIVE",
        title: "Auction live center",
        description: "Auction chain validation",
        items: {
          first: "Auction analysis",
          second: "Contractor fit",
          third: "Chat assistant",
        },
      },
      projects: {
        eyebrow: "PROJECTS / LIST",
        title: "Projects overview",
        description: "Project list and entry coverage",
        items: {
          first: "Project health",
          second: "Route coverage",
          third: "Module access",
        },
      },
    },
  })),
}));

vi.mock("@/i18n/module-copy", () => ({
  getModuleCopy: vi.fn(() => ({
    agent: {
      timelineTitle: "Agent timeline",
      timelineDescription: "Timeline preview",
      connectionTitle: "Connection",
      reconnectLabel: "Reconnect",
      updatedAtLabel: "Updated",
      connectionLabels: {
        connected: "Connected",
        reconnecting: "Reconnecting",
        idle: "Idle",
      },
      statusLabels: {
        completed: "Completed",
        active: "Active",
        waiting: "Waiting",
      },
    },
  })),
}));

vi.mock("@/mocks/module-data", () => ({
  getMockModuleSnapshot: vi.fn(() => ({
    agent: {
      connection: "connected",
      lastEventAt: "2026-03-22T00:00:00Z",
      stages: [],
    },
  })),
}));

describe("Dashboard route shells", () => {
  beforeEach(() => {
    vi.stubEnv("NEXT_PUBLIC_USE_MOCKS", "false");
  });

  it("renders the dashboard home with the summary panel and overview cards", async () => {
    render(await DashboardPage({ params: Promise.resolve({ locale: "en" }) }));

    expect(screen.getByText("Dashboard home")).toBeInTheDocument();
    expect(screen.getByTestId("dashboard-client-panel")).toHaveTextContent(
      "Summary panel",
    );
    expect(screen.getByTestId("pwa-status-card")).toBeInTheDocument();
    expect(screen.getAllByTestId("overview-card")).toHaveLength(4);
    expect(screen.getByRole("link", { name: "Projects" })).toHaveAttribute(
      "href",
      "/en/projects",
    );
  });

  it("renders the projects list page with the overview client", async () => {
    render(await ProjectsPage({ params: Promise.resolve({ locale: "en" }) }));

    expect(screen.getByText("Projects overview")).toBeInTheDocument();
    expect(screen.getByText("READY")).toBeInTheDocument();
    expect(screen.getByTestId("projects-overview-client")).toHaveTextContent(
      "en",
    );
  });

  it("renders the agent live page with the orchestration workspace", async () => {
    render(await AgentPage({ params: Promise.resolve({ locale: "en" }) }));

    expect(screen.getByText("Agent orchestration center")).toBeInTheDocument();
    expect(screen.getByText("LIVE")).toBeInTheDocument();
    expect(screen.getByTestId("agent-workspace")).toHaveTextContent("en");
  });

  it("renders the auction route shell with the live workspace", async () => {
    render(await AuctionPage({ params: Promise.resolve({ locale: "en" }) }));

    expect(screen.getByText("Auction live center")).toBeInTheDocument();
    expect(screen.getByText("LIVE")).toBeInTheDocument();
    expect(screen.getByTestId("auction-workspace")).toHaveTextContent("en");
  });

  it("renders the approval operations route shell with the live workspace", async () => {
    render(await ApprovalsPage({ params: Promise.resolve({ locale: "en" }) }));

    expect(screen.queryByTestId("module-placeholder")).not.toBeInTheDocument();
    expect(screen.getByText("Approval operations center")).toBeInTheDocument();
    expect(screen.getByText("LIVE")).toBeInTheDocument();
    expect(screen.getByTestId("approval-ops-workspace")).toHaveTextContent("en");
  });

  it("renders the tax route shell with the live workspace", async () => {
    render(await TaxPage({ params: Promise.resolve({ locale: "en" }) }));

    expect(screen.getByText("세금 라이브 센터")).toBeInTheDocument();
    expect(screen.getByText("LIVE")).toBeInTheDocument();
    expect(screen.getByTestId("tax-workspace")).toHaveTextContent("en");
  });

  it("renders the inspection route shell with the live workspace", async () => {
    render(await InspectionPage({ params: Promise.resolve({ locale: "en" }) }));

    expect(screen.getByText("현장 점검 라이브 센터")).toBeInTheDocument();
    expect(screen.getByText("LIVE")).toBeInTheDocument();
    expect(screen.getByTestId("inspection-workspace")).toHaveTextContent("en");
  });

  it("renders the investment analytics shell with the live workspace", async () => {
    render(await InvestmentPage({ params: Promise.resolve({ locale: "en" }) }));

    expect(screen.getByText("투자 운영 컨트롤타워")).toBeInTheDocument();
    expect(screen.getByText("LIVE")).toBeInTheDocument();
    expect(screen.getByTestId("investment-workspace")).toHaveTextContent("en");
  });

  it("renders the ESG analytics shell with the energy workspace", async () => {
    render(await ESGPage({ params: Promise.resolve({ locale: "en" }) }));

    expect(screen.getByText("에너지 인증 워크스페이스")).toBeInTheDocument();
    expect(screen.getByText("LIVE")).toBeInTheDocument();
    expect(screen.getByTestId("energy-workspace")).toHaveTextContent("en");
  });

  it("renders the cost analytics shell with the cost workspace", async () => {
    render(await CostPage({ params: Promise.resolve({ locale: "en" }) }));

    expect(screen.getByText("공사비 인텔리전스 허브")).toBeInTheDocument();
    expect(screen.getByText("LIVE")).toBeInTheDocument();
    expect(screen.getByTestId("cost-workspace")).toHaveTextContent("en");
  });

  it("renders the IoT analytics shell with the operations workspace", async () => {
    render(await IoTPage({ params: Promise.resolve({ locale: "en" }) }));

    expect(
      screen.getByText("운영 인텔리전스 워크스페이스"),
    ).toBeInTheDocument();
    expect(screen.getByText("LIVE")).toBeInTheDocument();
    expect(screen.getByTestId("ops-intelligence-workspace")).toHaveTextContent(
      "en",
    );
  });
  it("renders the safety route shell with the live safety and parking modules", async () => {
    render(await SafetyPage({ params: Promise.resolve({ locale: "en" }) }));

    expect(screen.queryByTestId("module-placeholder")).not.toBeInTheDocument();
    expect(screen.getAllByText("READY")[0]).toBeInTheDocument();
    expect(screen.getByTestId("safety-cctv-dashboard")).toBeInTheDocument();
    expect(screen.getByTestId("parking-log-view")).toBeInTheDocument();
  });

  it("renders the WebRTC route shell with the live supervision room", async () => {
    render(await WebRTCPage({ params: Promise.resolve({ locale: "en" }) }));

    expect(screen.queryByTestId("module-placeholder")).not.toBeInTheDocument();
    expect(screen.getAllByText("READY")[0]).toBeInTheDocument();
    expect(screen.getByTestId("remote-supervision-room")).toBeInTheDocument();
  });

  it("renders the SRE route shell with the live operations dashboard", async () => {
    render(await SREPage({ params: Promise.resolve({ locale: "en" }) }));

    expect(screen.queryByTestId("module-placeholder")).not.toBeInTheDocument();
    expect(screen.getAllByText("READY")[0]).toBeInTheDocument();
    expect(screen.getByTestId("sre-dashboard")).toBeInTheDocument();
  });
});
