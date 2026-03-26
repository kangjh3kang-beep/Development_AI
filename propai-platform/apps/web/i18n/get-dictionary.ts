import { readFile } from "node:fs/promises";
import path from "node:path";
import { cache } from "react";
import { defaultLocale, type Locale } from "@/i18n/config";

type ItemGroup = {
  first: string;
  second: string;
  third: string;
};

export type CommonDictionary = {
  meta: {
    title: string;
    siteName: string;
    description: string;
  };
  hero: {
    badge: string;
    title: string;
    description: string;
    primaryCta: string;
    secondaryCta: string;
  };
  nav: {
    locale: string;
    dashboard: string;
    projects: string;
    contracts: string;
    design: string;
    bim: string;
    finance: string;
    drone: string;
    blockchain: string;
    report: string;
    agent: string;
    tax: string;
    auction: string;
    inspection: string;
    login: string;
    register: string;
  };
  dashboard: {
    title: string;
    description: string;
    summaryTitle: string;
    summaryDesign: string;
    summaryFinance: string;
    summaryBlockchain: string;
  };
  auth: {
    loginEyebrow: string;
    loginTitle: string;
    loginDescription: string;
    loginPlaceholder: string;
    registerEyebrow: string;
    registerTitle: string;
    registerDescription: string;
    registerPlaceholder: string;
  };
  pages: {
    projects: {
      eyebrow: string;
      title: string;
      description: string;
      items: ItemGroup;
    };
    projectDetail: {
      eyebrow: string;
      title: string;
      description: string;
      items: ItemGroup;
    };
    design: {
      eyebrow: string;
      title: string;
      description: string;
      items: ItemGroup;
    };
    bim: {
      eyebrow: string;
      title: string;
      description: string;
      items: ItemGroup;
    };
    finance: {
      eyebrow: string;
      title: string;
      description: string;
      items: ItemGroup;
    };
    drone: {
      eyebrow: string;
      title: string;
      description: string;
      items: ItemGroup;
    };
    blockchain: {
      eyebrow: string;
      title: string;
      description: string;
      items: ItemGroup;
    };
    report: {
      eyebrow: string;
      title: string;
      description: string;
      items: ItemGroup;
    };
    agent: {
      eyebrow: string;
      title: string;
      description: string;
      items: ItemGroup;
    };
    tax: {
      eyebrow: string;
      title: string;
      description: string;
      items: ItemGroup;
    };
    auction: {
      eyebrow: string;
      title: string;
      description: string;
      items: ItemGroup;
    };
    inspection: {
      eyebrow: string;
      title: string;
      description: string;
      items: ItemGroup;
    };
  };
  status: {
    ready: string;
    mock: string;
  };
  workspace: {
    connectionTitle: string;
    sourceLabel: string;
    onlineLabel: string;
    offlineLabel: string;
    featuredProjectLabel: string;
    openProjectLabel: string;
    lastUpdatedLabel: string;
    nextActionLabel: string;
    viewGridLabel: string;
    viewListLabel: string;
    selectProjectLabel: string;
    selectedLabel: string;
    modulesLabel: string;
    emptyStateTitle: string;
    emptyStateDescription: string;
    errorStateTitle: string;
    errorStateDescription: string;
    retryLabel: string;
    timelineTitle: string;
    nextStepsTitle: string;
    budgetLabel: string;
    scheduleLabel: string;
    riskLabel: string;
    integrationRestLabel: string;
    integrationGraphqlLabel: string;
    integrationRealtimeLabel: string;
    modeMock: string;
    modeLive: string;
    modeWaiting: string;
  };
  pwa: {
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
  a11y: {
    screenReaderRegion: string;
    skipToContent: string;
  };
};

async function loadDictionary(locale: Locale): Promise<CommonDictionary> {
  const filePath = path.join(
    process.cwd(),
    "public",
    "locales",
    locale,
    "common.json",
  );

  try {
    const file = await readFile(filePath, "utf8");
    return JSON.parse(file) as CommonDictionary;
  } catch {
    const fallbackPath = path.join(
      process.cwd(),
      "public",
      "locales",
      defaultLocale,
      "common.json",
    );
    const file = await readFile(fallbackPath, "utf8");
    return JSON.parse(file) as CommonDictionary;
  }
}

export const getDictionary = cache(loadDictionary);
