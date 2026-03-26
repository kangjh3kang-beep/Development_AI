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
    hero: {
      badge: "PROP AI",
    },
    dashboard: {
      title: "Dashboard home",
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
      modeLive: "LIVE",
      modeWaiting: "WAITING",
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
    expect(screen.getByTestId("dashboard-client-panel")).toHaveTextContent(
      "Summary panel",
    );
    expect(screen.getByTestId("pwa-status-card")).toBeInTheDocument();

    expect(screen.getByRole("link", { name: "Projects" })).toHaveAttribute(
      "href",
      "/en/projects",
    );

    const allLinks = screen.getAllByRole("link");
    const auctionLinks = allLinks.filter(
      (link) => link.getAttribute("href") === "/en/auction",
    );
    expect(auctionLinks).toHaveLength(2);
    for (const link of auctionLinks) {
      expect(link).toHaveAttribute("href", "/en/auction");
    }

    expect(
      allLinks.find((link) => link.getAttribute("href") === "/en/tax"),
    ).toBeDefined();
    expect(
      allLinks.find((link) => link.getAttribute("href") === "/en/maintenance"),
    ).toBeDefined();
    expect(
      allLinks.find((link) => link.getAttribute("href") === "/en/tax"),
    ).toHaveTextContent("Tax");
    expect(
      allLinks.find((link) => link.getAttribute("href") === "/en/maintenance"),
    ).toHaveTextContent("Maintenance");
    expect(
      allLinks.find((link) => link.getAttribute("href") === "/en/approvals"),
    ).toHaveTextContent("Approval Ops");
  });

  it("renders the live overview card descriptions for the home entry modules", async () => {
    render(await DashboardPage({ params: Promise.resolve({ locale: "en" }) }));

    expect(
      screen.getByText(
        "Calculate project-linked tax scenarios through the live tax API.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Validate auction analysis, contractor matching, and chatbot queries through live APIs.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Jump into the live maintenance, tenant-signal, and asset-intelligence chain.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Review tenant-wide approval queues, resolved decisions, and batch actions from one live control surface.",
      ),
    ).toBeInTheDocument();
  });
});
