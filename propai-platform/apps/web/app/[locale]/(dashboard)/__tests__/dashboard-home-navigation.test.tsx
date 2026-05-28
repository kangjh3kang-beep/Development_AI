import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import DashboardPage from "../page";

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

vi.mock("@/i18n/get-dictionary", () => ({
  getDictionary: vi.fn(async () => ({
    meta: {
      siteName: "PropAI",
    },
    dashboard: {
      title: "Dashboard home",
      welcome: "Welcome to PropAI",
      description: "Live operating center",
      summaryTitle: "Summary panel",
    },
    nav: {
      projects: "Projects",
      auction: "Auction",
      tax: "Tax",
      approvals: "Approval Ops",
    },
    workspace: {
      connectionTitle: "Connections",
      sourceLabel: "Sources",
      onlineLabel: "Online",
      offlineLabel: "Offline",
      featuredProjectLabel: "Featured project",
      openProjectLabel: "Open project",
      integrationRestLabel: "REST",
      integrationGraphqlLabel: "GraphQL",
      integrationRealtimeLabel: "Realtime",
      modeMock: "MOCK",
      modeLive: "실연동",
      modeWaiting: "WAITING",
    },
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
      maintenance: { title: "Maintenance", eyebrow: "MAINTENANCE", description: "Desc", items: [] },
      tenant: { title: "Tenant", eyebrow: "TENANT", description: "Desc", items: [] },
      tax: { title: "Tax", eyebrow: "TAX", description: "Desc", items: [] },
      approvals: { title: "Approval Ops", eyebrow: "APPROVALS", description: "Desc", items: [] },
      auction: { title: "Auction", eyebrow: "AUCTION", description: "Desc", items: [] },
    },
    pwa: {
      eyebrow: "G163 / PWA",
      title: "PWA status",
      description: "Offline shell",
      runtimeLabel: "Runtime",
      runtimeReady: "Ready",
      runtimeRegistering: "Registering",
      runtimeError: "Error",
      runtimeUnsupported: "Unsupported",
      installLabel: "Install",
      installAvailable: "Ready to install",
      installInstalled: "Installed",
      installUnavailable: "Browser-controlled",
      notificationsLabel: "Notifications",
      notificationsGranted: "Granted",
      notificationsDefault: "Permission required",
      notificationsDenied: "Blocked",
      notificationsUnsupported: "Unsupported",
      cacheLabel: "Cache",
      cacheReady: "Shell cached",
      cachePending: "Priming cache",
      cacheUnsupported: "Not available",
      updateTitle: "Update ready",
      updateDescription: "Apply update",
      installAction: "Install workspace",
      enableNotificationsAction: "Enable notifications",
      testNotificationAction: "Send test notification",
      refreshAction: "Refresh PWA",
      offlineAction: "Open offline page",
      errorTitle: "PWA runtime issue",
      testNotificationTitle: "PropAI field sync",
      testNotificationBody: "Offline workspace ready",
    },
  })),
}));

describe("Dashboard home navigation", () => {
  it("renders the hero entry links and real overview card destinations", async () => {
    render(await DashboardPage({ params: Promise.resolve({ locale: "en" }) }));

    expect(screen.getByText("Dashboard home")).toBeInTheDocument();
    expect(screen.getByText("PropAI")).toBeInTheDocument();
    expect(screen.getByText("Welcome to PropAI")).toBeInTheDocument();

    expect(screen.getByRole("link", { name: "모든 프로젝트 보기" })).toHaveAttribute(
      "href",
      "/en/projects",
    );

    const allLinks = screen.getAllByRole("link");
    expect(allLinks.find((link) => link.getAttribute("href") === "/en/auction")).toBeDefined();
    expect(allLinks.find((link) => link.getAttribute("href") === "/en/tax")).toBeDefined();
    expect(allLinks.find((link) => link.getAttribute("href") === "/en/tenant")).toBeDefined();
    expect(allLinks.find((link) => link.getAttribute("href") === "/en/inspection")).toBeDefined();
    expect(allLinks.find((link) => link.getAttribute("href") === "/en/webrtc")).toBeDefined();
  });

  it("renders the KPI summary and active pipeline cards", async () => {
    render(await DashboardPage({ params: Promise.resolve({ locale: "en" }) }));

    expect(screen.getByText("총 포트폴리오 자산")).toBeInTheDocument();
    expect(screen.getByText("3,500억")).toBeInTheDocument();
    expect(screen.getByText("강남 게이트웨이 신축")).toBeInTheDocument();
    expect(screen.getByText("송도 호라이즌 개발")).toBeInTheDocument();
    expect(screen.getByText("남산 에코타워 리모델링")).toBeInTheDocument();
  });
});
