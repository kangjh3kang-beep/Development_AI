import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithQueryClient } from "@/test/render-with-query-client";
import CostPage from "../analytics/cost/page";
import ESGPage from "../analytics/esg/page";
import InvestmentPage from "../analytics/investment/page";
import AuctionPage from "../auction/page";
import DashboardPage from "../page";
import ProjectsPage from "../projects/page";

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

vi.mock("@/components/auction/AuctionWorkspace", () => ({
  AuctionWorkspace: ({
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
    meta: {
      siteName: "PropAI",
    },
    dashboard: {
      title: "Dashboard home",
      welcome: "Welcome to PropAI",
      description: "Live operating center",
      summaryTitle: "Summary panel",
    },
    workspace: {
      modeLive: "실연동",
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
    modulePlaceholders: {
      agent: { title: "Agent orchestration center", eyebrow: "AGENT", description: "Desc", items: [] },
      auction: { title: "Auction live center", eyebrow: "AUCTION", description: "Desc", items: [] },
      blockchain: { title: "Blockchain", eyebrow: "BLOCKCHAIN", description: "Desc", items: [] },
      projects: { title: "Projects overview", eyebrow: "PROJECTS", description: "Desc", items: [] },
      tax: { title: "세금 라이브 센터", eyebrow: "TAX", description: "Desc", items: [] },
      inspection: { title: "현장 점검 라이브 센터", eyebrow: "INSPECTION", description: "Desc", items: [] },
      energy: { title: "에너지 인증 작업 공간", eyebrow: "ENERGY", description: "Desc", items: [] },
      esg: { title: "에너지 인증 작업 공간", eyebrow: "ENERGY", description: "Desc", items: [] },
      cost: { title: "공사비 분석 허브", eyebrow: "COST", description: "Desc", items: [] },
      investment: { title: "투자 운영 컨트롤타워", eyebrow: "INVESTMENT", description: "Desc", items: [] },
      iot: { title: "운영 분석 작업 공간", eyebrow: "IOT", description: "Desc", items: [] },
      sre: { title: "SRE", eyebrow: "SRE", description: "Desc", items: [] },
      webrtc: { title: "WebRTC", eyebrow: "WEBRTC", description: "Desc", items: [] },
      safety: { title: "Safety", eyebrow: "SAFETY", description: "Desc", items: [] },
      maintenance: { title: "예지정비 운영센터", eyebrow: "MAINTENANCE", description: "Desc", items: [] },
      tenant: { title: "테넌트 경험 센터", eyebrow: "TENANT", description: "Desc", items: [] },
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
        stageSite: "Site",
        stageLegal: "Legal",
        stageDesignAI: "Design AI",
        stageFeasibility: "Feasibility",
        stageESG: "ESG",
        stagePermits: "Permits",
        stageConstruction: "Construction",
        stageOperations: "Operations",
      },
      cadBim: {
        title: "CAD/BIM",
      },
      feasibility: {
        title: "Feasibility",
      },
      cost: {
        title: "Cost",
      },
      schedule: {
        title: "Schedule",
      },
    },
  })),
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

  it("renders the dashboard home with the command-center hero and project entry CTAs", async () => {
    render(await DashboardPage({ params: Promise.resolve({ locale: "en" }) }));

    // 히어로: 차분한 분야 라벨 + 가치제안 헤드라인(딕셔너리 비의존 하드카피)
    expect(screen.getByText("부동산 개발 분석")).toBeInTheDocument();
    expect(
      screen.getByText(
        "개발사업의 필수 플랫폼! 주소만 입력하면, 시장조사·사업성·수지 분석을 한 번에.",
      ),
    ).toBeInTheDocument();
    // 활성 진행 단계 섹션 헤더
    expect(screen.getByText("활성 진행 단계")).toBeInTheDocument();
    // 핵심 행동: 프로젝트 생성(accent) → /en/projects/new
    expect(
      screen.getByRole("link", { name: /프로젝트 생성/ }),
    ).toHaveAttribute("href", "/en/projects/new");
    // 활성 진행 단계 "전체 보기" → /en/projects
    expect(screen.getByRole("link", { name: "전체 보기" })).toHaveAttribute(
      "href",
      "/en/projects",
    );
  });

  it("renders the projects list page with the overview client", async () => {
    render(await ProjectsPage({ params: Promise.resolve({ locale: "en" }) }));

    // 목업 배너 제거(무목업): 실 목록 헤더(제목) + 생성 CTA + 오버뷰 클라이언트만 노출
    expect(screen.getByText("Projects overview")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /새 프로젝트/ }),
    ).toHaveAttribute("href", "/en/projects/new");
    expect(screen.getByTestId("projects-overview-client")).toHaveTextContent(
      "en",
    );
  });

  it("renders the auction route shell with the live workspace", async () => {
    render(<AuctionPage />);

    expect(screen.getByTestId("auction-workspace")).toHaveTextContent("en");
  });

  it("renders the investment analytics shell with the feasibility console header", async () => {
    render(<InvestmentPage />);

    // 페이지 셸: 콘솔 메타 라벨 + LIVE 칩 + 한국어 제목
    expect(
      screen.getByText("INVESTMENT · FEASIBILITY CONSOLE"),
    ).toBeInTheDocument();
    expect(screen.getAllByText("LIVE").length).toBeGreaterThan(0);
    expect(screen.getByText("투자수익성 분석")).toBeInTheDocument();
  });

  it("renders the ESG analytics shell with the carbon console header and input form", async () => {
    // ESGPage가 useAIAnalyze(useMutation)를 사용하므로 QueryClientProvider 필요
    renderWithQueryClient(<ESGPage />);

    // 페이지 셸: 콘솔 메타 라벨 + LIVE 칩 + 한국어 제목 + 입력 폼 라벨
    expect(screen.getByText("ESG · CARBON CONSOLE")).toBeInTheDocument();
    expect(screen.getByText("LIVE")).toBeInTheDocument();
    expect(screen.getByText("ESG / 탄소 경영")).toBeInTheDocument();
    expect(screen.getByText("건물 정보 / INPUT")).toBeInTheDocument();
  });

  it("renders the cost analytics shell with the estimation console header and tabs", async () => {
    render(<CostPage />);

    // 페이지 셸: 콘솔 메타 라벨 + LIVE 칩 + 한국어 제목 + 탭 버튼
    expect(
      screen.getByText("COST · ESTIMATION CONSOLE"),
    ).toBeInTheDocument();
    expect(screen.getByText("LIVE")).toBeInTheDocument();
    expect(screen.getByText("공사비 분석")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "단계별 분석" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "기성·실적관리(EVM)" }),
    ).toBeInTheDocument();
  });

});
