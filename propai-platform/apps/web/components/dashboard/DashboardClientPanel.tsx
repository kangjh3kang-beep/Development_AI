"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { Card, CardContent, CardTitle } from "@propai/ui";
import { WorkspaceQueryErrorCard } from "@/components/analytics/WorkspaceQueryErrorCard";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import { apiClient } from "@/lib/api-client";
import type {
  DashboardOverviewResponse,
  IntegrationMode,
  IntegrationStatusResponse,
} from "@/mocks/types";
import { useAppStore } from "@/store/use-app-store";
import { useProjectStore } from "@/store/use-project-store";

type DashboardStatsApiResponse = {
  total_projects: number;
  active_webhooks: number;
  active_api_keys: number;
  ai_cost_month_usd: number;
  ai_tokens_month: number;
  projects_by_status: Record<string, number>;
};

type DashboardProjectPickerResponse = {
  items: Array<{
    id: string;
  }>;
};

type SystemVersionApiResponse = {
  app_name: string;
  version: string;
  environment: string;
  api_prefixes: string[];
};

type SystemHealthApiResponse = {
  status: string;
  version: string;
  environment: string;
  services: Record<string, string>;
  checked_at: string;
};

type WorkspaceLabels = {
  connectionTitle: string;
  sourceLabel: string;
  onlineLabel: string;
  offlineLabel: string;
  featuredProjectLabel: string;
  openProjectLabel: string;
  integrationRestLabel: string;
  integrationGraphqlLabel: string;
  integrationRealtimeLabel: string;
  modeMock: string;
  modeLive: string;
  modeWaiting: string;
};

type DashboardClientPanelProps = {
  locale: string;
  summaryTitle: string;
  labels: WorkspaceLabels;
};

type DashboardErrorLabels = {
  authError: string;
  overviewTitle: string;
  overviewDetail: string;
  integrationTitle: string;
  integrationDetail: string;
  retryAction: string;
};

const ERROR_LABELS: Record<string, DashboardErrorLabels> = {
  en: {
    authError: "API authentication is required for live workspace calls.",
    overviewTitle: "Live dashboard data is unavailable.",
    overviewDetail:
      "The dashboard summary query failed. Retry after restoring API connectivity or access token state.",
    integrationTitle: "Integration status is unavailable.",
    integrationDetail:
      "The live integration health query failed. Retry after restoring API connectivity or access token state.",
    retryAction: "Retry",
  },
  ko: {
    authError: "실시간 호출을 위해 API 인증이 필요합니다.",
    overviewTitle: "라이브 대시보드 데이터를 불러올 수 없습니다.",
    overviewDetail:
      "대시보드 요약 조회가 실패했습니다. API 연결 또는 액세스 토큰 상태를 복구한 뒤 다시 시도하세요.",
    integrationTitle: "연동 상태를 불러올 수 없습니다.",
    integrationDetail:
      "라이브 연동 상태 조회가 실패했습니다. API 연결 또는 액세스 토큰 상태를 복구한 뒤 다시 시도하세요.",
    retryAction: "다시 시도",
  },
  "zh-CN": {
    authError: "实时调用需要 API 身份认证。",
    overviewTitle: "无法加载实时仪表盘数据。",
    overviewDetail:
      "仪表盘汇总查询失败。恢复 API 连通性或访问令牌状态后可重试。",
    integrationTitle: "无法加载集成状态。",
    integrationDetail:
      "实时集成健康检查查询失败。恢复 API 连通性或访问令牌状态后可重试。",
    retryAction: "重试",
  },
};

function getModeLabel(mode: IntegrationMode, labels: WorkspaceLabels) {
  if (mode === "live") {
    return labels.modeLive;
  }

  if (mode === "waiting") {
    return labels.modeWaiting;
  }

  return labels.modeMock;
}

function getQueryErrorDetail(error: unknown, authMessage: string) {
  if (
    typeof error === "object" &&
    error !== null &&
    "status" in error &&
    (((error as { status?: unknown }).status === 401) ||
      (error as { status?: unknown }).status === 403)
  ) {
    return authMessage;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return "Request failed.";
}

export function DashboardClientPanel({
  locale,
  summaryTitle,
  labels,
}: DashboardClientPanelProps) {
  const errorLabels = ERROR_LABELS[locale] ?? ERROR_LABELS.en;
  const runtimeConfig = apiClient.getRuntimeConfig();
  const useLiveWorkspaceData =
    runtimeConfig.mode === "live" || runtimeConfig.hasAccessToken;
  const online = useAppStore((state) => state.online);
  const setIntegrationState = useAppStore((state) => state.setIntegrationState);
  const currentProjectId = useProjectStore((state) => state.currentProjectId);
  const setCurrentProject = useProjectStore((state) => state.setCurrentProject);

  const overviewQuery = useQuery({
    queryKey: ["dashboard", "overview"],
    queryFn: async () => {
      if (!useLiveWorkspaceData) {
        return apiClient.get<DashboardOverviewResponse>("/dashboard/overview");
      }

      const stats = await apiClient.get<DashboardStatsApiResponse>("/dashboard/stats");
      let featuredProjectId = currentProjectId ?? "live-workspace";

      if (!currentProjectId) {
        try {
          const projects = await apiClient.get<DashboardProjectPickerResponse>(
            "/projects?page=1&page_size=1",
          );
          featuredProjectId = projects.items[0]?.id ?? featuredProjectId;
        } catch {
          // Keep the dashboard summary resilient even when the project picker read model is unavailable.
        }
      }

      return {
        metrics: [
          {
            id: "projects",
            label: "Projects",
            value: String(stats.total_projects),
          },
          {
            id: "ai-cost",
            label: "AI cost this month",
            value: `$${stats.ai_cost_month_usd.toFixed(2)}`,
          },
          {
            id: "api-keys",
            label: "Active API keys",
            value: String(stats.active_api_keys),
          },
        ],
        featuredProjectId,
      } satisfies DashboardOverviewResponse;
    },
  });

  const integrationQuery = useQuery({
    queryKey: ["integration", "status"],
    queryFn: async () => {
      if (!useLiveWorkspaceData) {
        return apiClient.get<IntegrationStatusResponse>("/integration/status");
      }

      const [version, health] = await Promise.all([
        apiClient.get<SystemVersionApiResponse>("/system/version"),
        apiClient.get<SystemHealthApiResponse>("/system/health/full"),
      ]);

      const qdrantHealthy = health.services.qdrant === "healthy";
      const redisHealthy = health.services.redis === "healthy";

      return {
        channels: [
          {
            id: "rest",
            label: "REST",
            mode: "live",
            detail: `${version.app_name} ${version.version} (${version.environment})`,
          },
          {
            id: "graphql",
            label: "GraphQL",
            mode: "waiting",
            detail: "Hasura live binding is still pending in the dashboard workspace.",
          },
          {
            id: "realtime",
            label: "Realtime",
            mode: qdrantHealthy || redisHealthy ? "live" : "waiting",
            detail: qdrantHealthy || redisHealthy
              ? "Realtime dependencies are reachable for websocket and streaming modules."
              : "Realtime dependencies are not fully healthy yet.",
          },
        ],
      } satisfies IntegrationStatusResponse;
    },
  });

  useEffect(() => {
    if (!overviewQuery.data?.featuredProjectId || currentProjectId) {
      return;
    }

    setCurrentProject(overviewQuery.data.featuredProjectId);
  }, [currentProjectId, overviewQuery.data?.featuredProjectId, setCurrentProject]);

  useEffect(() => {
    if (!integrationQuery.data) {
      return;
    }

    const restChannel = integrationQuery.data.channels.find(
      (channel) => channel.id === "rest",
    );
    const graphqlChannel = integrationQuery.data.channels.find(
      (channel) => channel.id === "graphql",
    );
    const realtimeChannel = integrationQuery.data.channels.find(
      (channel) => channel.id === "realtime",
    );

    setIntegrationState({
      restMode: restChannel?.mode ?? "waiting",
      graphqlEnabled: graphqlChannel?.mode === "live",
      realtimeConnected: realtimeChannel?.mode === "live",
    });
  }, [integrationQuery.data, setIntegrationState]);

  const featuredProjectId =
    overviewQuery.data?.featuredProjectId ?? currentProjectId ?? "sample-project";

  const channelLabelMap = {
    rest: labels.integrationRestLabel,
    graphql: labels.integrationGraphqlLabel,
    realtime: labels.integrationRealtimeLabel,
  } as const;
  const overviewError = overviewQuery.error
    ? getQueryErrorDetail(overviewQuery.error, errorLabels.authError)
    : "";
  const integrationError = integrationQuery.error
    ? getQueryErrorDetail(integrationQuery.error, errorLabels.authError)
    : "";

  return (
    <section className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
      <Card>
        <CardContent className="p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
              {summaryTitle}
            </p>
            <CardTitle className="mt-3 text-2xl">
              {labels.connectionTitle}
            </CardTitle>
          </div>
          <span className="rounded-full border border-[var(--line)] px-4 py-2 text-sm font-medium text-[var(--text-secondary)]">
            {online ? labels.onlineLabel : labels.offlineLabel}
          </span>
        </div>
        <div className="mt-6 grid gap-3 md:grid-cols-3">
          {overviewQuery.isLoading ? (
            <SkeletonLoader
              count={3}
              className="md:col-span-3 md:grid-cols-3"
              itemClassName="h-28"
            />
          ) : null}
          {overviewQuery.isError ? (
            <div className="md:col-span-3">
              <WorkspaceQueryErrorCard
                title={errorLabels.overviewTitle}
                description={errorLabels.overviewDetail}
                message={overviewError}
                actionLabel={errorLabels.retryAction}
                onRetry={() => {
                  void overviewQuery.refetch();
                }}
              />
            </div>
          ) : null}
          {overviewQuery.data?.metrics.map((metric) => (
            <Card
              key={metric.id}
              className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] shadow-none"
            >
              <CardContent className="p-5">
                <p className="text-sm text-[var(--text-secondary)]">{metric.label}</p>
                <p className="mt-4 text-2xl font-semibold text-[var(--text-primary)]">
                  {metric.value}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
        </CardContent>
      </Card>
      <Card className="bg-[var(--surface-strong)]">
        <CardContent className="p-6">
        <p className="text-xs font-bold uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
          {labels.sourceLabel}
        </p>
        <div className="mt-4 grid gap-3">
          {integrationQuery.isLoading ? (
            <SkeletonLoader count={3} itemClassName="h-20" />
          ) : null}
          {integrationQuery.isError ? (
            <WorkspaceQueryErrorCard
              title={errorLabels.integrationTitle}
              description={errorLabels.integrationDetail}
              message={integrationError}
              actionLabel={errorLabels.retryAction}
              onRetry={() => {
                void integrationQuery.refetch();
              }}
            />
          ) : null}
          {integrationQuery.data?.channels.map((channel) => (
            <Card
              key={channel.id}
              className="rounded-[var(--radius-md)] bg-[var(--surface-soft)] shadow-none"
            >
              <CardContent className="p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-[var(--text-primary)]">
                      {channelLabelMap[channel.id]}
                    </p>
                    <p className="mt-2 text-sm leading-6 text-[var(--text-tertiary)]">
                      {channel.detail}
                    </p>
                  </div>
                  <span className="rounded-full bg-[var(--surface-muted)] px-3 py-1 text-xs font-medium text-[var(--accent-strong)]">
                    {getModeLabel(channel.mode, labels)}
                  </span>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
        <Card className="mt-5 rounded-[var(--radius-md)] bg-[var(--surface-soft)] shadow-none">
          <CardContent className="p-4">
          <p className="text-sm text-[var(--text-secondary)]">
            {labels.featuredProjectLabel}
          </p>
          <div className="mt-3 flex items-center justify-between gap-3">
            <p className="text-base font-semibold text-[var(--text-primary)]">
              {featuredProjectId}
            </p>
            <Link
              href={`/${locale}/projects/${featuredProjectId}`}
              className="rounded-full border border-[var(--line)] bg-white px-4 py-2 text-sm font-semibold text-[var(--text-primary)] shadow-[var(--shadow-md)]"
            >
              {labels.openProjectLabel}
            </Link>
          </div>
          </CardContent>
        </Card>
        </CardContent>
      </Card>
    </section>
  );
}
