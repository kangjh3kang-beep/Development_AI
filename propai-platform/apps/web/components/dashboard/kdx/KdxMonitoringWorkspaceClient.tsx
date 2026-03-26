"use client";

import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardTitle } from "@propai/ui";
import { WorkspaceQueryErrorCard } from "@/components/analytics/WorkspaceQueryErrorCard";
import KdxRealtimeChart from "@/components/dashboard/kdx/KdxRealtimeChart";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import { ApiClientError, apiClient } from "@/lib/api-client";

type KdxOverviewResponse = {
  connection_status: string;
  throughput_tps: number;
  data_sync_latency_ms: number;
  latest_metric: {
    region_code: string;
    metric_type: string;
    value: number;
    currency: string;
    recorded_at: string;
  } | null;
  recent_logs: Array<{
    id: string;
    source: string;
    event_type: string;
    status: string;
    created_at: string;
  }>;
};

function getQueryErrorMessage(error: unknown) {
  if (error instanceof ApiClientError && (error.status === 401 || error.status === 403)) {
    return "API authentication is required for live KDX monitoring.";
  }

  if (error instanceof Error) {
    return error.message;
  }

  return "Request failed.";
}

function formatMetricValue(metric: KdxOverviewResponse["latest_metric"]) {
  if (!metric) {
    return "No metric received";
  }

  if (metric.currency === "KRW") {
    return new Intl.NumberFormat("ko-KR", {
      style: "currency",
      currency: "KRW",
      maximumFractionDigits: 0,
    }).format(metric.value);
  }

  return `${metric.value.toFixed(2)} ${metric.currency}`;
}

export function KdxMonitoringWorkspaceClient() {
  const overviewQuery = useQuery({
    queryKey: ["kdx", "overview"],
    queryFn: () =>
      apiClient.get<KdxOverviewResponse>("/kdx/overview", {
        useMock: false,
      }),
  });

  const errorMessage = overviewQuery.error
    ? getQueryErrorMessage(overviewQuery.error)
    : "";

  return (
    <div className="min-h-screen bg-slate-50 p-6 font-sans dark:bg-slate-950 md:p-10">
      <div className="mx-auto max-w-7xl space-y-6">
        <header className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.28em] text-slate-500 dark:text-slate-400">
              Live monitoring
            </p>
            <h1 className="mt-3 text-3xl font-extrabold tracking-tight text-slate-900 dark:text-white">
              KDX Monitoring Center
            </h1>
            <p className="mt-2 max-w-3xl text-sm leading-7 text-slate-500 dark:text-slate-400">
              Inspect the live KDX ingestion surface through persisted telemetry,
              latest metric snapshots, and the websocket property index stream.
            </p>
          </div>
          <span className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200">
            {overviewQuery.data?.connection_status ?? "loading"}
          </span>
        </header>

        {overviewQuery.isLoading ? (
          <SkeletonLoader
            count={4}
            className="grid gap-4 md:grid-cols-4"
            itemClassName="h-28"
          />
        ) : null}

        {overviewQuery.isError ? (
          <WorkspaceQueryErrorCard
            title="KDX overview is unavailable."
            description="The KDX live monitoring read model failed. Retry after restoring API connectivity or access token state."
            message={errorMessage}
            actionLabel="Retry"
            onRetry={() => {
              void overviewQuery.refetch();
            }}
          />
        ) : null}

        {overviewQuery.data ? (
          <>
            <div className="grid gap-4 md:grid-cols-4">
              <Card className="rounded-[1.5rem] border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
                <CardContent className="p-6">
                  <p className="text-sm text-slate-500 dark:text-slate-400">
                    Connection status
                  </p>
                  <p className="mt-3 text-2xl font-bold uppercase text-slate-900 dark:text-slate-100">
                    {overviewQuery.data.connection_status}
                  </p>
                </CardContent>
              </Card>
              <Card className="rounded-[1.5rem] border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
                <CardContent className="p-6">
                  <p className="text-sm text-slate-500 dark:text-slate-400">
                    Ingestion throughput
                  </p>
                  <p className="mt-3 text-2xl font-bold text-blue-600 dark:text-blue-400">
                    {overviewQuery.data.throughput_tps}
                    <span className="ml-2 text-sm font-medium text-slate-400">
                      txn/s
                    </span>
                  </p>
                </CardContent>
              </Card>
              <Card className="rounded-[1.5rem] border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
                <CardContent className="p-6">
                  <p className="text-sm text-slate-500 dark:text-slate-400">
                    Data sync latency
                  </p>
                  <p className="mt-3 text-2xl font-bold text-slate-900 dark:text-slate-100">
                    {overviewQuery.data.data_sync_latency_ms}
                    <span className="ml-2 text-sm font-medium text-slate-400">
                      ms
                    </span>
                  </p>
                </CardContent>
              </Card>
              <Card className="rounded-[1.5rem] border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
                <CardContent className="p-6">
                  <p className="text-sm text-slate-500 dark:text-slate-400">
                    Latest metric
                  </p>
                  <p className="mt-3 text-lg font-bold text-emerald-600 dark:text-emerald-400">
                    {formatMetricValue(overviewQuery.data.latest_metric)}
                  </p>
                  <p className="mt-2 text-xs text-slate-400">
                    {overviewQuery.data.latest_metric
                      ? `${overviewQuery.data.latest_metric.metric_type} · ${overviewQuery.data.latest_metric.region_code}`
                      : "No persisted metric snapshot yet"}
                  </p>
                </CardContent>
              </Card>
            </div>

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
              <div className="lg:col-span-2">
                <KdxRealtimeChart />
              </div>

              <Card className="rounded-[1.5rem] border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
                <CardContent className="p-6">
                  <CardTitle className="text-lg text-slate-900 dark:text-slate-100">
                    Recent pipeline logs
                  </CardTitle>
                  <div className="mt-5 space-y-4">
                    {overviewQuery.data.recent_logs.length > 0 ? (
                      overviewQuery.data.recent_logs.map((log) => (
                        <div
                          key={log.id}
                          className="rounded-xl border border-slate-100 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950/60"
                        >
                          <div className="flex items-center justify-between gap-3">
                            <span className="text-xs font-semibold uppercase tracking-[0.2em] text-blue-500">
                              {log.event_type}
                            </span>
                            <span className="text-[11px] uppercase text-slate-400">
                              {log.status}
                            </span>
                          </div>
                          <p className="mt-3 text-sm font-medium text-slate-700 dark:text-slate-200">
                            {log.source}
                          </p>
                          <p className="mt-1 text-xs text-slate-400">
                            {new Date(log.created_at).toLocaleString("ko-KR")}
                          </p>
                        </div>
                      ))
                    ) : (
                      <div className="rounded-xl border border-dashed border-slate-200 px-4 py-8 text-center text-sm text-slate-400 dark:border-slate-800">
                        No telemetry logs have been ingested yet.
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}
