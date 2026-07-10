import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CostPage from "../analytics/cost/page";
import ESGPage from "../analytics/esg/page";
import InvestmentPage from "../analytics/investment/page";
import AuctionPage from "../auction/page";
import DashboardPage from "../page";
import ProjectsPage from "../projects/page";
import { useProjectContextStore } from "@/store/useProjectContextStore";

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

vi.mock("@/components/onboarding/OnboardingWizard", () => ({
  OnboardingWizard: () => <div data-testid="onboarding-wizard" />,
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

// 9c4a120d: 홈이 SatongMapShell을 실렌더하면 산출물 링크 라벨("시장·분양 리포트")이
// creationProducts 카드와 중복돼 getByText 단일매치가 깨짐 — 셸은 스텁으로 대체.
vi.mock("@/components/precheck/SatongMapShell", () => ({
  SatongMapShell: ({ locale }: { locale: string }) => (
    <div data-testid="satong-map-shell">{locale}</div>
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

vi.mock("@/components/analytics/InvestmentAnalyticsWorkspaceClient", () => ({
  InvestmentAnalyticsWorkspaceClient: ({
    locale,
  }: {
    locale: string;
  }) => <div data-testid="investment-workspace">{locale}</div>,
}));

vi.mock("@/components/analytics/CostEstimationClient", () => ({
  CostEstimationClient: () => <div data-testid="cost-workspace">cost</div>,
}));

vi.mock("@/components/analytics/OperationsIntelligenceWorkspaceClient", () => ({
  OperationsIntelligenceWorkspaceClient: ({
    locale,
  }: {
    locale: string;
  }) => <div data-testid="ops-intelligence-workspace">{locale}</div>,
}));

vi.mock("@/components/safety/ParkingLogView", () => ({
  ParkingLogView: () => <div data-testid="parking-log-view">Parking log view</div>,
}));

vi.mock("@/features/webrtc/RemoteSupervisionRoom", () => ({
  RemoteSupervisionRoom: () => (
    <div data-testid="remote-supervision-room">Remote supervision room</div>
  ),
}));

vi.mock("@/lib/ai-analyze-client", () => ({
  useAIReady: () => ({ isReady: false }),
  useAIAnalyze: () => ({
    mutate: vi.fn(),
    data: null,
    isPending: false,
    error: null,
  }),
  cleanFenceText: (value: string | null | undefined) => value ?? "",
  extractStructuredFromText: () => null,
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

  it("renders the dashboard home as an operations console", async () => {
    render(await DashboardPage({ params: Promise.resolve({ locale: "en" }) }));

    expect(screen.getByText("Intelligence Control Room")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "필요한 결과물을 고르면 입력부터 보고서까지 이어집니다" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /후보지 진단서 만들기/ })).toHaveAttribute("href", "/en/precheck");
    expect(screen.getByText("시장·분양 리포트").closest("a")).toHaveAttribute("href", "/en/market-insights");
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

  it("renders the investment analytics shell with the honest project gate (no project)", async () => {
    // 새 계약: 프로젝트 미선택이면 리스크 시뮬(워크스페이스)은 빈 패널 대신 정직 게이트로 숨긴다(무목업).
    render(<InvestmentPage />);

    expect(screen.getByText("투자수익성 분석")).toBeInTheDocument();
    expect(screen.getByText("LIVE")).toBeInTheDocument();
    expect(screen.queryByTestId("investment-workspace")).not.toBeInTheDocument();
    expect(screen.getByText("먼저 프로젝트를 선택하세요.")).toBeInTheDocument();
  });

  it("renders the investment risk workspace once a project is selected", async () => {
    // 프로젝트 선택 시 STEP2·3(요약·리스크 시뮬)이 이어진다 — 게이트 해제 경로.
    useProjectContextStore.setState({ projectId: "proj-shell-test" });
    try {
      render(<InvestmentPage />);

      expect(screen.getByTestId("investment-workspace")).toHaveTextContent("en");
    } finally {
      // 전역 zustand 상태 원복 — 다른 라우트 셸 테스트로의 누수 방지.
      useProjectContextStore.setState({ projectId: null });
    }
  });

  it("renders the ESG analytics shell with the energy workspace", async () => {
    render(<ESGPage />);

    expect(screen.getByText("ESG / 탄소 경영")).toBeInTheDocument();
    expect(screen.getByText("LIVE")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "API 키를 먼저 등록하세요" })).toBeDisabled();
  });

  it("renders the cost analytics shell with the cost workspace", async () => {
    render(<CostPage />);

    expect(screen.getByText("적산·공사비 관리")).toBeInTheDocument();
    expect(screen.getByText("LIVE")).toBeInTheDocument();
    expect(screen.getByTestId("cost-workspace")).toHaveTextContent("cost");
  });

});
