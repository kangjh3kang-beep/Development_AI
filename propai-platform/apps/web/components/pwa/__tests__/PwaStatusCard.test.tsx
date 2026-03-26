import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PwaRuntimeProvider } from "@/components/pwa/PwaRuntimeProvider";
import { PwaStatusCard } from "@/components/pwa/PwaStatusCard";
import { renderWithQueryClient } from "@/test/render-with-query-client";

const LABELS = {
  eyebrow: "G163 / PWA",
  title: "Offline shell, install prompt, and push baseline",
  description: "PWA runtime surface",
  runtimeLabel: "Service worker",
  runtimeReady: "Ready",
  runtimeRegistering: "Registering",
  runtimeError: "Error",
  runtimeUnsupported: "Unsupported",
  installLabel: "Install state",
  installAvailable: "Ready to install",
  installInstalled: "Installed",
  installUnavailable: "Browser-controlled",
  notificationsLabel: "Notifications",
  notificationsGranted: "Granted",
  notificationsDefault: "Permission required",
  notificationsDenied: "Blocked",
  notificationsUnsupported: "Unsupported",
  cacheLabel: "Offline cache",
  cacheReady: "Shell cached",
  cachePending: "Priming cache",
  cacheUnsupported: "Not available",
  updateTitle: "A cached update is ready.",
  updateDescription: "Apply the waiting worker.",
  installAction: "Install workspace",
  enableNotificationsAction: "Enable notifications",
  testNotificationAction: "Send test notification",
  refreshAction: "Refresh PWA",
  offlineAction: "Open offline page",
  errorTitle: "PWA runtime issue",
  testNotificationTitle: "PropAI field sync",
  testNotificationBody: "Offline workspace ready",
};

const registerMock = vi.fn();
const requestPermissionMock = vi.fn();
const activePostMessageMock = vi.fn();
const waitingPostMessageMock = vi.fn();
const registrationUpdateMock = vi.fn();

function createRegistration(withWaitingWorker = false) {
  return {
    waiting: withWaitingWorker ? { postMessage: waitingPostMessageMock } : null,
    active: { postMessage: activePostMessageMock },
    installing: null,
    showNotification: vi.fn(),
    update: registrationUpdateMock,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  };
}

function renderPwaCard() {
  return renderWithQueryClient(
    <PwaRuntimeProvider>
      <PwaStatusCard labels={LABELS} />
    </PwaRuntimeProvider>,
  );
}

describe("PwaStatusCard", () => {
  beforeEach(() => {
    activePostMessageMock.mockReset();
    waitingPostMessageMock.mockReset();
    registerMock.mockReset();
    registrationUpdateMock.mockReset();
    requestPermissionMock.mockReset();
  });

  it("registers the service worker, exposes install prompt state, and sends a test notification", async () => {
    const registration = createRegistration(false);

    registerMock.mockResolvedValue(registration);
    registrationUpdateMock.mockResolvedValue(undefined);
    requestPermissionMock.mockResolvedValue("granted");

    Object.defineProperty(window.navigator, "serviceWorker", {
      configurable: true,
      value: {
        register: registerMock,
        ready: Promise.resolve(registration),
        controller: {},
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      },
    });

    vi.stubGlobal("Notification", {
      permission: "default",
      requestPermission: requestPermissionMock,
    });

    renderPwaCard();

    expect(await screen.findByText("Ready")).toBeInTheDocument();
    expect(screen.getByText("Shell cached")).toBeInTheDocument();

    const installEvent = new Event("beforeinstallprompt");
    Object.defineProperties(installEvent, {
      prompt: {
        value: vi.fn().mockResolvedValue(undefined),
      },
      userChoice: {
        value: Promise.resolve({
          outcome: "accepted",
          platform: "web",
        }),
      },
    });

    act(() => {
      window.dispatchEvent(installEvent);
    });

    expect(await screen.findByRole("button", { name: "Install workspace" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Install workspace" }));

    expect(await screen.findByText("Installed")).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: "Enable notifications" }),
    );

    await waitFor(() => {
      expect(requestPermissionMock).toHaveBeenCalledTimes(1);
    });

    await waitFor(() => {
      expect(screen.getByText("Granted")).toBeInTheDocument();
    });

    await userEvent.click(
      screen.getByRole("button", { name: "Send test notification" }),
    );

    expect(activePostMessageMock).toHaveBeenCalledWith({
      type: "SHOW_NOTIFICATION",
      payload: {
        title: "PropAI field sync",
        body: "Offline workspace ready",
        tag: "propai-pwa-test",
        url: "/ko/inspection",
      },
    });
  });

  it("surfaces waiting updates and applies the queued service worker", async () => {
    const registration = createRegistration(true);

    registerMock.mockResolvedValue(registration);
    registrationUpdateMock.mockResolvedValue(undefined);

    Object.defineProperty(window.navigator, "serviceWorker", {
      configurable: true,
      value: {
        register: registerMock,
        ready: Promise.resolve(registration),
        controller: {},
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      },
    });

    vi.stubGlobal("Notification", {
      permission: "denied",
      requestPermission: requestPermissionMock,
    });

    renderPwaCard();

    expect(await screen.findByText("A cached update is ready.")).toBeInTheDocument();

    await userEvent.click(screen.getAllByRole("button", { name: "Refresh PWA" })[1]);

    expect(waitingPostMessageMock).toHaveBeenCalledWith({ type: "SKIP_WAITING" });
  });
});
