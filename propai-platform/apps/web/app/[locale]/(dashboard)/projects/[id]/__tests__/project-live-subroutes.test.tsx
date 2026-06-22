import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

let mockParams = { locale: "en", id: "p001" };
vi.mock("next/navigation", () => {
  return {
    useParams: () => mockParams,
    usePathname: () => `/en/projects/${mockParams.id}`,
    useRouter: () => ({
      push: vi.fn(),
      replace: vi.fn(),
      back: vi.fn(),
      prefetch: vi.fn(),
    }),
  };
});

import BimPage from "../bim/page";
import BlockchainPage from "../blockchain/page";
import ContractsPage from "../contracts/page";
import ProjectDetailPage from "../page";
import DesignPage from "../design/page";
import DronePage from "../drone/page";
import FinancePage from "../finance/page";
import ReportPage from "../report/page";

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

vi.mock("@/components/projects/ProjectFinanceWorkspaceClient", () => ({
  ProjectFinanceWorkspaceClient: ({
    projectId,
  }: {
    projectId: string;
  }) => <div data-testid="project-finance-workspace">{projectId}</div>,
}));

vi.mock("@/components/projects/ProjectContractWorkspaceClient", () => ({
  ProjectContractWorkspaceClient: ({
    projectId,
  }: {
    projectId: string;
  }) => <div data-testid="project-contract-workspace">{projectId}</div>,
}));

vi.mock("@/components/projects/ProjectDroneWorkspaceClient", () => ({
  ProjectDroneWorkspaceClient: ({
    projectId,
  }: {
    projectId: string;
  }) => <div data-testid="project-drone-workspace">{projectId}</div>,
}));

vi.mock("@/components/projects/ProjectDesignWorkspaceClient", () => ({
  ProjectDesignWorkspaceClient: ({
    projectId,
  }: {
    projectId: string;
  }) => <div data-testid="project-design-workspace">{projectId}</div>,
}));

vi.mock("@/components/projects/ProjectBimWorkspaceClient", () => ({
  ProjectBimWorkspaceClient: ({
    projectId,
  }: {
    projectId: string;
  }) => <div data-testid="project-bim-workspace">{projectId}</div>,
}));

vi.mock("@/components/projects/ProjectBlockchainWorkspaceClient", () => ({
  ProjectBlockchainWorkspaceClient: ({
    projectId,
  }: {
    projectId: string;
  }) => <div data-testid="project-blockchain-workspace">{projectId}</div>,
}));

vi.mock("@/components/projects/ProjectReportWorkspaceClient", () => ({
  ProjectReportWorkspaceClient: ({
    projectId,
  }: {
    projectId: string;
  }) => <div data-testid="project-report-workspace">{projectId}</div>,
}));

vi.mock("@/components/projects/ProjectSummaryClient", () => ({
  ProjectSummaryClient: ({
    projectId,
  }: {
    projectId: string;
  }) => <div data-testid="project-summary-workspace">{projectId}</div>,
}));

// 사전(dictionary)은 서버 컴포넌트(getDictionary)와 클라이언트 컴포넌트(useDictionary 훅) 양쪽이
// 공유한다. vi.hoisted로 단일 DICT를 두 mock이 함께 참조(중복 정의 방지).
const { DICT } = vi.hoisted(() => ({
  DICT: {
    workspace: {
      modeLive: "실연동",
      modeMock: "MOCK",
    },
    nav: {
      contracts: "Contracts",
      design: "Design",
      bim: "BIM",
      finance: "Finance",
      drone: "Drone",
      blockchain: "Blockchain",
      report: "Report",
    },
    pages: {
      projectDetail: {
        summary: {
          hub: "Project live overview",
          name: "NAME",
          pnu: "PNU",
          zone: "실연동",
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
    modulePlaceholders: {
      agent: { title: "Agent", eyebrow: "AGENT", description: "Desc", items: [] },
      auction: { title: "Auction", eyebrow: "AUCTION", description: "Desc", items: [] },
      blockchain: { title: "Project blockchain live route", eyebrow: "BLOCKCHAIN", description: "Desc", items: [] },
      projects: { title: "Projects", eyebrow: "PROJECTS", description: "Desc", items: [] },
      finance: { title: "Project finance live route", eyebrow: "FINANCE", description: "Desc", items: [] },
      contracts: { title: "Project contract automation live route", eyebrow: "CONTRACTS", description: "Desc", items: [] },
      report: { title: "Project report live route", eyebrow: "REPORT", description: "Desc", items: [] },
      drone: { title: "Project drone live route", eyebrow: "DRONE", description: "Desc", items: [] },
      design: { title: "Project design live route", eyebrow: "DESIGN", description: "Desc", items: [] },
      bim: { title: "Project BIM live route", eyebrow: "BIM", description: "Desc", items: [] },
    },
  },
}));

vi.mock("@/i18n/get-dictionary", () => ({
  getDictionary: vi.fn(async () => DICT),
}));

// 클라이언트 페이지(design/overview)는 useDictionary 훅의 isLoading 게이트를 통과해야 본문을
// 렌더한다. 동기 로드된 사전을 반환해 로딩 스피너("Initializing…") 정지를 해소한다.
vi.mock("@/hooks/use-dictionary", () => ({
  useDictionary: () => ({ dictionary: DICT, isLoading: false }),
}));

describe("Project live subroutes", () => {
  beforeEach(() => {
    vi.stubEnv("NEXT_PUBLIC_USE_MOCKS", "false");
  });

  it("renders the finance project page with the live workspace", async () => {
    render(
      await FinancePage({
        params: Promise.resolve({ locale: "en", id: "project-finance-001" }),
      }),
    );

    expect(screen.getByText("Project finance live route")).toBeInTheDocument();
    // "실연동"은 커맨드스트립 meta + 플레이스홀더 statusLabel 양쪽에 나타난다(다중 허용).
    expect(screen.getAllByText("실연동").length).toBeGreaterThan(0);
    expect(screen.getByTestId("project-finance-workspace")).toHaveTextContent(
      "project-finance-001",
    );
  });

  it("renders the contracts project page with the live workspace", async () => {
    render(
      await ContractsPage({
        params: Promise.resolve({ locale: "en", id: "project-contract-001" }),
      }),
    );

    expect(
      screen.getByText("Project contract automation live route"),
    ).toBeInTheDocument();
    expect(screen.getAllByText("실연동").length).toBeGreaterThan(0);
    expect(screen.getByTestId("project-contract-workspace")).toHaveTextContent(
      "project-contract-001",
    );
  });

  it("renders the report project page with the live workspace", async () => {
    render(
      await ReportPage({
        params: Promise.resolve({ locale: "en", id: "project-report-001" }),
      }),
    );

    expect(screen.getByText("Project report live route")).toBeInTheDocument();
    expect(screen.getAllByText("실연동").length).toBeGreaterThan(0);
    expect(screen.getByTestId("project-report-workspace")).toHaveTextContent(
      "project-report-001",
    );
  });

  it("renders the drone project page with the live workspace", async () => {
    render(
      await DronePage({
        params: Promise.resolve({ locale: "en", id: "project-drone-001" }),
      }),
    );

    expect(screen.getByText("Project drone live route")).toBeInTheDocument();
    expect(screen.getAllByText("실연동").length).toBeGreaterThan(0);
    expect(screen.getByTestId("project-drone-workspace")).toHaveTextContent(
      "project-drone-001",
    );
  });

  it("renders the design project page with the live studio gate", async () => {
    mockParams = { locale: "en", id: "project-design-001" };
    render(<DesignPage />);

    expect(screen.getByText("Project design live route")).toBeInTheDocument();
    expect(screen.getAllByText("실연동").length).toBeGreaterThan(0);
    // 설계 페이지는 워크스페이스 클라이언트 대신 WebGL 지연마운트 "스튜디오 게이트" CTA를 렌더한다.
    expect(screen.getByText("설계 스튜디오 열기")).toBeInTheDocument();
  });

  it("renders the bim project page with the live workspace", async () => {
    render(
      await BimPage({
        params: Promise.resolve({ locale: "en", id: "project-bim-001" }),
      }),
    );

    expect(screen.getByText("Project BIM live route")).toBeInTheDocument();
    expect(screen.getAllByText("실연동").length).toBeGreaterThan(0);
    expect(screen.getByTestId("project-bim-workspace")).toHaveTextContent(
      "project-bim-001",
    );
  });

  it("renders the blockchain project page with the live workspace", async () => {
    render(
      await BlockchainPage({
        params: Promise.resolve({ locale: "en", id: "project-chain-001" }),
      }),
    );

    expect(screen.getByText("Project blockchain live route")).toBeInTheDocument();
    expect(screen.getAllByText("실연동").length).toBeGreaterThan(0);
    expect(
      screen.getByTestId("project-blockchain-workspace"),
    ).toHaveTextContent("project-chain-001");
  });

  it("renders the project overview page past the loading gate", async () => {
    mockParams = { locale: "en", id: "project-overview-001" };
    render(<ProjectDetailPage />);

    // 클라이언트 허브가 로딩 게이트를 통과해 히어로(허브 라벨 + 프로젝트 ID)를 렌더하는지 확인.
    // (ID는 커맨드스트립 meta + 히어로 양쪽에 나타나므로 다중 허용)
    expect(screen.getByText(/Project live overview/)).toBeInTheDocument();
    expect(screen.getAllByText(/project-overview-001/).length).toBeGreaterThan(0);
  });
});
