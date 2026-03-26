"use client";

import Link from "next/link";
import { Card, CardContent, CardTitle } from "@propai/ui";
import { usePwaRuntime } from "@/components/pwa/PwaRuntimeProvider";

type PwaLabels = {
  eyebrow: string;
  title: string;
  description: string;
  runtimeLabel: string;
  runtimeReady: string;
  runtimeRegistering: string;
  runtimeError: string;
  runtimeUnsupported: string;
  installLabel: string;
  installAvailable: string;
  installInstalled: string;
  installUnavailable: string;
  notificationsLabel: string;
  notificationsGranted: string;
  notificationsDefault: string;
  notificationsDenied: string;
  notificationsUnsupported: string;
  cacheLabel: string;
  cacheReady: string;
  cachePending: string;
  cacheUnsupported: string;
  updateTitle: string;
  updateDescription: string;
  installAction: string;
  enableNotificationsAction: string;
  testNotificationAction: string;
  refreshAction: string;
  offlineAction: string;
  errorTitle: string;
  testNotificationTitle: string;
  testNotificationBody: string;
};

type PwaStatusCardProps = {
  labels: PwaLabels;
};

function getRuntimeLabel(
  runtimeState: ReturnType<typeof usePwaRuntime>["serviceWorkerState"],
  labels: PwaLabels,
) {
  if (runtimeState === "ready") {
    return labels.runtimeReady;
  }

  if (runtimeState === "registering") {
    return labels.runtimeRegistering;
  }

  if (runtimeState === "error") {
    return labels.runtimeError;
  }

  return labels.runtimeUnsupported;
}

function getInstallLabel(
  installState: ReturnType<typeof usePwaRuntime>["installState"],
  labels: PwaLabels,
) {
  if (installState === "available") {
    return labels.installAvailable;
  }

  if (installState === "installed") {
    return labels.installInstalled;
  }

  return labels.installUnavailable;
}

function getNotificationLabel(
  notificationPermission: ReturnType<typeof usePwaRuntime>["notificationPermission"],
  labels: PwaLabels,
) {
  if (notificationPermission === "granted") {
    return labels.notificationsGranted;
  }

  if (notificationPermission === "denied") {
    return labels.notificationsDenied;
  }

  if (notificationPermission === "default") {
    return labels.notificationsDefault;
  }

  return labels.notificationsUnsupported;
}

export function PwaStatusCard({ labels }: PwaStatusCardProps) {
  const {
    serviceWorkerState,
    installState,
    notificationPermission,
    updateReady,
    cacheReady,
    lastError,
    requestInstall,
    requestNotificationPermission,
    sendTestNotification,
    applyUpdate,
    refreshRuntime,
  } = usePwaRuntime();

  return (
    <Card className="bg-[var(--surface)]">
      <CardContent className="p-6">
        <p className="text-xs uppercase tracking-[0.24em] text-[rgba(19,33,47,0.64)]">
          {labels.eyebrow}
        </p>
        <div className="mt-3 flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-3xl">
            <CardTitle className="text-2xl">{labels.title}</CardTitle>
            <p className="mt-3 text-sm leading-7 text-[rgba(19,33,47,0.7)]">
              {labels.description}
            </p>
          </div>
          <button
            type="button"
            onClick={() => {
              void refreshRuntime();
            }}
            className="rounded-full border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-2 text-sm font-semibold text-[var(--foreground)] transition hover:border-[var(--accent)] hover:text-[var(--accent-strong)]"
          >
            {labels.refreshAction}
          </button>
        </div>
        <div className="mt-6 grid gap-3 lg:grid-cols-4">
          <Card className="rounded-[1.5rem] bg-[var(--surface-soft)] shadow-none">
            <CardContent className="p-5">
              <p className="text-sm text-[rgba(19,33,47,0.68)]">{labels.runtimeLabel}</p>
              <p className="mt-3 text-xl font-semibold text-[var(--foreground)]">
                {getRuntimeLabel(serviceWorkerState, labels)}
              </p>
            </CardContent>
          </Card>
          <Card className="rounded-[1.5rem] bg-[var(--surface-soft)] shadow-none">
            <CardContent className="p-5">
              <p className="text-sm text-[rgba(19,33,47,0.68)]">{labels.installLabel}</p>
              <p className="mt-3 text-xl font-semibold text-[var(--foreground)]">
                {getInstallLabel(installState, labels)}
              </p>
            </CardContent>
          </Card>
          <Card className="rounded-[1.5rem] bg-[var(--surface-soft)] shadow-none">
            <CardContent className="p-5">
              <p className="text-sm text-[rgba(19,33,47,0.68)]">
                {labels.notificationsLabel}
              </p>
              <p className="mt-3 text-xl font-semibold text-[var(--foreground)]">
                {getNotificationLabel(notificationPermission, labels)}
              </p>
            </CardContent>
          </Card>
          <Card className="rounded-[1.5rem] bg-[var(--surface-soft)] shadow-none">
            <CardContent className="p-5">
              <p className="text-sm text-[rgba(19,33,47,0.68)]">{labels.cacheLabel}</p>
              <p className="mt-3 text-xl font-semibold text-[var(--foreground)]">
                {serviceWorkerState === "unsupported"
                  ? labels.cacheUnsupported
                  : cacheReady
                    ? labels.cacheReady
                    : labels.cachePending}
              </p>
            </CardContent>
          </Card>
        </div>
        {updateReady ? (
          <div
            className="mt-5 rounded-[1.5rem] border border-[rgba(13,148,136,0.2)] bg-[rgba(240,253,250,0.9)] p-5"
            role="status"
          >
            <p className="text-sm font-semibold text-[var(--foreground)]">
              {labels.updateTitle}
            </p>
            <p className="mt-2 text-sm leading-7 text-[rgba(19,33,47,0.68)]">
              {labels.updateDescription}
            </p>
            <button
              type="button"
              onClick={applyUpdate}
              className="mt-4 rounded-full border border-[var(--line)] bg-white px-4 py-2 text-sm font-semibold text-[var(--foreground)] transition hover:border-[var(--accent)] hover:text-[var(--accent-strong)]"
            >
              {labels.refreshAction}
            </button>
          </div>
        ) : null}
        {lastError ? (
          <div
            className="mt-5 rounded-[1.5rem] border border-[rgba(217,119,6,0.24)] bg-[rgba(255,247,237,0.92)] p-5"
            role="alert"
          >
            <p className="text-sm font-semibold text-[var(--foreground)]">
              {labels.errorTitle}
            </p>
            <p className="mt-2 text-sm leading-7 text-[var(--spot)]">{lastError}</p>
          </div>
        ) : null}
        <div className="mt-5 flex flex-wrap gap-3">
          {installState === "available" ? (
            <button
              type="button"
              onClick={() => {
                void requestInstall();
              }}
              className="rounded-full border border-[var(--line)] bg-[#ffffff] px-4 py-2 text-sm font-semibold text-[var(--foreground)] shadow-[0_8px_20px_rgba(19,33,47,0.08)]"
            >
              {labels.installAction}
            </button>
          ) : null}
          {notificationPermission === "default" ? (
            <button
              type="button"
              onClick={() => {
                void requestNotificationPermission();
              }}
              className="rounded-full border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-2 text-sm font-semibold text-[var(--foreground)]"
            >
              {labels.enableNotificationsAction}
            </button>
          ) : null}
          {notificationPermission === "granted" ? (
            <button
              type="button"
              onClick={() => {
                void sendTestNotification(
                  labels.testNotificationTitle,
                  labels.testNotificationBody,
                );
              }}
              className="rounded-full border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-2 text-sm font-semibold text-[var(--foreground)]"
            >
              {labels.testNotificationAction}
            </button>
          ) : null}
          <Link
            href="/offline"
            className="rounded-full border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-2 text-sm font-semibold text-[var(--foreground)]"
          >
            {labels.offlineAction}
          </Link>
        </div>
      </CardContent>
    </Card>
  );
}
