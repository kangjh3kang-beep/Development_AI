"use client";

import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type PropsWithChildren,
} from "react";

type BeforeInstallPromptChoice = {
  outcome: "accepted" | "dismissed";
  platform: string;
};

type BeforeInstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<BeforeInstallPromptChoice>;
};

type ServiceWorkerRuntimeState = "unsupported" | "registering" | "ready" | "error";
type InstallRuntimeState = "available" | "installed" | "unavailable";
type NotificationRuntimeState = NotificationPermission | "unsupported";

type PwaRuntimeContextValue = {
  serviceWorkerState: ServiceWorkerRuntimeState;
  installState: InstallRuntimeState;
  notificationPermission: NotificationRuntimeState;
  updateReady: boolean;
  standalone: boolean;
  cacheReady: boolean;
  lastError: string | null;
  requestInstall: () => Promise<void>;
  requestNotificationPermission: () => Promise<void>;
  sendTestNotification: (title: string, body: string) => Promise<void>;
  applyUpdate: () => void;
  refreshRuntime: () => Promise<void>;
};

const defaultContextValue: PwaRuntimeContextValue = {
  serviceWorkerState: "unsupported",
  installState: "unavailable",
  notificationPermission: "unsupported",
  updateReady: false,
  standalone: false,
  cacheReady: false,
  lastError: null,
  requestInstall: async () => {},
  requestNotificationPermission: async () => {},
  sendTestNotification: async () => {},
  applyUpdate: () => {},
  refreshRuntime: async () => {},
};

const PwaRuntimeContext = createContext<PwaRuntimeContextValue>(defaultContextValue);

type StandaloneNavigator = Navigator & {
  standalone?: boolean;
};

function getStandaloneState() {
  if (typeof window === "undefined") {
    return false;
  }

  const navigatorWithStandalone = window.navigator as StandaloneNavigator;
  const mediaQuery = window.matchMedia?.("(display-mode: standalone)");

  return mediaQuery?.matches === true || navigatorWithStandalone.standalone === true;
}

function getPermissionState(): NotificationRuntimeState {
  if (typeof Notification === "undefined") {
    return "unsupported";
  }

  return Notification.permission;
}

function hasServiceWorkerSupport() {
  return typeof window !== "undefined" && "serviceWorker" in navigator;
}

export function PwaRuntimeProvider({ children }: PropsWithChildren) {
  const [serviceWorkerState, setServiceWorkerState] =
    useState<ServiceWorkerRuntimeState>(() =>
      hasServiceWorkerSupport() ? "registering" : "unsupported",
    );
  const [installState, setInstallState] = useState<InstallRuntimeState>(() =>
    getStandaloneState() ? "installed" : "unavailable",
  );
  const [notificationPermission, setNotificationPermission] =
    useState<NotificationRuntimeState>(() => getPermissionState());
  const [updateReady, setUpdateReady] = useState(false);
  const [standalone, setStandalone] = useState(() => getStandaloneState());
  const [cacheReady, setCacheReady] = useState(false);
  const [lastError, setLastError] = useState<string | null>(null);
  const registrationRef = useRef<ServiceWorkerRegistration | null>(null);
  const installPromptRef = useRef<BeforeInstallPromptEvent | null>(null);
  const updateRequestedRef = useRef(false);
  const controllerReloadedRef = useRef(false);

  useEffect(() => {
    if (!hasServiceWorkerSupport()) {
      return;
    }

    let cancelled = false;
    let updateFoundHandler: (() => void) | null = null;
    // 등록 시점에 이미 제어 중인 SW가 있었는가(=재방문자). 첫 방문의 최초 clients.claim에
    // 의한 controllerchange는 이미 최신이라 새로고침이 불필요하므로 구분한다.
    const hadControllerAtStart = !!navigator.serviceWorker.controller;

    const syncRegistrationState = (registration: ServiceWorkerRegistration) => {
      registrationRef.current = registration;
      setServiceWorkerState("ready");
      setCacheReady(true);
      setUpdateReady(Boolean(registration.waiting));

      updateFoundHandler = () => {
        const installingWorker = registration.installing;

        if (!installingWorker) {
          return;
        }

        installingWorker.addEventListener("statechange", () => {
          if (
            installingWorker.state === "installed" &&
            navigator.serviceWorker.controller
          ) {
            setUpdateReady(true);
          }
        });
      };

      registration.addEventListener("updatefound", updateFoundHandler);
    };

    const registerServiceWorker = async () => {
      try {
        const registration = await navigator.serviceWorker.register("/sw.js", {
          scope: "/",
          // ★sw.js 업데이트 체크 시 HTTP 캐시를 우회한다. 이게 없으면 브라우저가 CDN의
          //   max-age(과거 4h) 동안 새 sw.js를 다시 받지 않아, 새 버전 배포가 감지조차 안 된다.
          updateViaCache: "none",
        });

        if (cancelled) {
          return;
        }

        syncRegistrationState(registration);
        await registration.update().catch(() => null);
      } catch (error) {
        if (cancelled) {
          return;
        }

        setServiceWorkerState("error");
        setCacheReady(false);
        setLastError(error instanceof Error ? error.message : "PWA bootstrap failed.");
      }
    };

    const handleControllerChange = () => {
      if (controllerReloadedRef.current) {
        return; // 무한 새로고침 방지(페이지 로드당 1회만)
      }
      // 새 서비스워커가 제어를 넘겨받음(skipWaiting 활성). 재방문자이거나 사용자가 직접
      // 업데이트를 요청한 경우, 최신 프론트 즉시 반영을 위해 1회 새로고침한다.
      // 첫 방문(기존 컨트롤러 없음)의 최초 claim은 이미 최신이라 새로고침하지 않는다.
      // ★이게 없으면 새 sw가 활성화돼도 페이지가 구버전 코드를 계속 실행한다(수동 새로고침 전까지).
      if (!hadControllerAtStart && !updateRequestedRef.current) {
        return;
      }
      controllerReloadedRef.current = true;
      window.location.reload();
    };

    void registerServiceWorker();

    navigator.serviceWorker.ready
      .then((registration) => {
        if (cancelled) {
          return;
        }

        syncRegistrationState(registration);
      })
      .catch(() => null);

    navigator.serviceWorker.addEventListener("controllerchange", handleControllerChange);

    return () => {
      cancelled = true;
      if (registrationRef.current && updateFoundHandler) {
        registrationRef.current.removeEventListener("updatefound", updateFoundHandler);
      }
      navigator.serviceWorker.removeEventListener(
        "controllerchange",
        handleControllerChange,
      );
    };
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    const updateStandaloneState = () => {
      const nextStandalone = getStandaloneState();
      setStandalone(nextStandalone);
      if (nextStandalone) {
        setInstallState("installed");
      }
    };

    const handleBeforeInstallPrompt = (event: Event) => {
      const promptEvent = event as BeforeInstallPromptEvent;
      promptEvent.preventDefault();
      installPromptRef.current = promptEvent;
      setInstallState("available");
    };

    const handleAppInstalled = () => {
      installPromptRef.current = null;
      setStandalone(true);
      setInstallState("installed");
    };

    const mediaQuery = window.matchMedia?.("(display-mode: standalone)");

    window.addEventListener("beforeinstallprompt", handleBeforeInstallPrompt);
    window.addEventListener("appinstalled", handleAppInstalled);
    mediaQuery?.addEventListener?.("change", updateStandaloneState);

    return () => {
      window.removeEventListener("beforeinstallprompt", handleBeforeInstallPrompt);
      window.removeEventListener("appinstalled", handleAppInstalled);
      mediaQuery?.removeEventListener?.("change", updateStandaloneState);
    };
  }, []);

  const requestInstall = async () => {
    const promptEvent = installPromptRef.current;

    if (!promptEvent) {
      return;
    }

    await promptEvent.prompt();
    const choice = await promptEvent.userChoice;
    installPromptRef.current = null;
    setInstallState(choice.outcome === "accepted" ? "installed" : "unavailable");
  };

  const requestNotificationPermission = async () => {
    if (typeof Notification === "undefined") {
      setNotificationPermission("unsupported");
      return;
    }

    const result = await Notification.requestPermission();
    setNotificationPermission(result);
  };

  const sendTestNotification = async (title: string, body: string) => {
    const registration = registrationRef.current;

    if (!registration || notificationPermission !== "granted") {
      return;
    }

    try {
      const message = {
        type: "SHOW_NOTIFICATION",
        payload: {
          title,
          body,
          tag: "propai-pwa-test",
          url: "/ko/inspection",
        },
      };

      const runtimeWorker =
        registration.active ?? registration.waiting ?? registration.installing;

      if (runtimeWorker) {
        runtimeWorker.postMessage(message);
        return;
      }

      await registration.showNotification(title, {
        body,
        tag: "propai-pwa-test",
        data: { url: "/ko/inspection" },
      });
    } catch (error) {
      setLastError(
        error instanceof Error ? error.message : "Notification dispatch failed.",
      );
    }
  };

  const applyUpdate = () => {
    const waitingWorker = registrationRef.current?.waiting;

    if (!waitingWorker) {
      return;
    }

    updateRequestedRef.current = true;
    setUpdateReady(false);
    waitingWorker.postMessage({ type: "SKIP_WAITING" });
  };

  const refreshRuntime = async () => {
    try {
      await registrationRef.current?.update();
      setUpdateReady(Boolean(registrationRef.current?.waiting));
    } catch (error) {
      setLastError(error instanceof Error ? error.message : "PWA refresh failed.");
    }
  };

  return (
    <PwaRuntimeContext.Provider
      value={{
        serviceWorkerState,
        installState,
        notificationPermission,
        updateReady,
        standalone,
        cacheReady,
        lastError,
        requestInstall,
        requestNotificationPermission,
        sendTestNotification,
        applyUpdate,
        refreshRuntime,
      }}
    >
      {children}
    </PwaRuntimeContext.Provider>
  );
}

export function usePwaRuntime() {
  return useContext(PwaRuntimeContext);
}
