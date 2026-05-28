"use client";

import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardTitle } from "@propai/ui";
import { WorkspaceQueryErrorCard } from "@/components/analytics/WorkspaceQueryErrorCard";
import KdxRealtimeChart from "@/components/dashboard/kdx/KdxRealtimeChart";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
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
      (async () => ({} as KdxOverviewResponse))(),
  });

  const errorMessage = overviewQuery.error
    ? getQueryErrorMessage(overviewQuery.error)
    : "";

  return (
    <div className="min-h-screen bg-[var(--surface)] p-6 font-sans md:p-10">
      <div className="mx-auto max-w-7xl space-y-8">
        <header className="flex flex-wrap items-end justify-between gap-6 border-b border-[var(--line)] pb-8">
          <div>
            <p className="text-[10px] font-black uppercase tracking-[0.4em] text-[var(--accent-strong)] mb-2">
              Telemetric Engine / LIVE
            </p>
            <h1 className="text-4xl font-[1000] tracking-tighter text-[var(--text-primary)]">
              KDX Monitoring Center
            </h1>
            <p className="mt-4 max-w-2xl text-sm font-medium leading-relaxed text-[var(--text-secondary)]">
              국가 데이터 거점(KDX)의 실시간 수집 모델을 모니터링합니다.<br/>웹소켓 기반 자산 인덱싱 스트림과 영구 텔레메트리 스냅샷을 통합 검증합니다.
            </p>
          </div>
          <div className="flex items-center gap-2 rounded-full border border-[var(--line-strong)] bg-[var(--surface-strong)] px-5 py-2.5 shadow-[var(--shadow-sm)]">
             <div className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
             <span className="text-[10px] font-black uppercase tracking-widest text-[var(--text-secondary)]">
               {overviewQuery.data?.connection_status ?? "CONNECTING"}
             </span>
          </div>
        </header>

        {overviewQuery.isLoading ? (
          <SkeletonLoader
            count={4}
            className="grid gap-6 md:grid-cols-4"
            itemClassName="h-32 rounded-[var(--radius-2xl)]"
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
            <div className="grid gap-6 md:grid-cols-4">
              <Card className="rounded-[var(--radius-2xl)] border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-sm)]">
                <CardContent className="p-6">
                  <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-tertiary)]">
                    Connection status
                  </p>
                  <p className="mt-4 text-2xl font-[1000] uppercase text-[var(--text-primary)] tracking-tighter">
                    {overviewQuery.data.connection_status}
                  </p>
                </CardContent>
              </Card>
              <Card className="rounded-[var(--radius-2xl)] border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-sm)]">
                <CardContent className="p-6">
                  <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-tertiary)]">
                    Ingestion throughput
                  </p>
                  <p className="mt-4 text-2xl font-[1000] text-[var(--accent-strong)] tracking-tighter">
                    {overviewQuery.data.throughput_tps}
                    <span className="ml-2 text-xs font-bold text-[var(--text-hint)] uppercase">
                      txn/s
                    </span>
                  </p>
                </CardContent>
              </Card>
              <Card className="rounded-[var(--radius-2xl)] border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-sm)]">
                <CardContent className="p-6">
                  <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-tertiary)]">
                    Data sync latency
                  </p>
                  <p className="mt-4 text-2xl font-[1000] text-[var(--text-primary)] tracking-tighter">
                    {overviewQuery.data.data_sync_latency_ms}
                    <span className="ml-2 text-xs font-bold text-[var(--text-hint)] uppercase">
                      ms
                    </span>
                  </p>
                </CardContent>
              </Card>
              <Card className="rounded-[var(--radius-2xl)] border border-[var(--accent-strong)]/20 bg-[var(--accent-soft)] shadow-[var(--shadow-sm)]">
                <CardContent className="p-6">
                  <p className="text-[10px] font-black uppercase tracking-widest text-[var(--accent-strong)]/60">
                    Latest metric
                  </p>
                  <p className="mt-4 text-lg font-black text-[var(--accent-strong)] tracking-tight">
                    {formatMetricValue(overviewQuery.data.latest_metric)}
                  </p>
                  <p className="mt-2 text-[10px] font-bold text-[var(--accent-strong)]/40 italic">
                    {overviewQuery.data.latest_metric
                      ? `${overviewQuery.data.latest_metric.metric_type} · ${overviewQuery.data.latest_metric.region_code}`
                      : "No persisted metric snapshot yet"}
                  </p>
                </CardContent>
              </Card>
            </div>

            <div className="grid grid-cols-1 gap-8 lg:grid-cols-3 mt-8">
              <div className="lg:col-span-2">
                <div className="rounded-[var(--radius-3xl)] border border-[var(--line-strong)] bg-[var(--surface-strong)] p-1 overflow-hidden shadow-[var(--shadow-lg)]">
                  <KdxRealtimeChart />
                </div>
              </div>

              <Card className="rounded-[var(--radius-3xl)] border border-[var(--line-strong)] bg-[var(--surface-strong)] flex flex-col shadow-[var(--shadow-lg)]">
                <CardContent className="p-8 flex flex-col h-full">
                  <CardTitle className="text-sm font-black uppercase tracking-[0.2em] text-[var(--text-primary)] mb-8">
                    Recent pipeline logs
                  </CardTitle>
                  <div className="space-y-4 overflow-y-auto max-h-[600px] pr-2 custom-scrollbar">
                    {overviewQuery.data.recent_logs.length > 0 ? (
                      overviewQuery.data.recent_logs.map((log) => (
                        <div
                          key={log.id}
                          className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-5 transition-all hover:border-[var(--accent-strong)]/30 group"
                        >
                          <div className="flex items-center justify-between gap-3 mb-3">
                            <span className="text-[9px] font-black uppercase tracking-[0.2em] text-[var(--accent-strong)]">
                              {log.event_type}
                            </span>
                            <span className="text-[9px] font-black uppercase text-[var(--text-hint)]">
                              {log.status}
                            </span>
                          </div>
                          <p className="text-xs font-bold text-[var(--text-primary)] italic">
                            {log.source}
                          </p>
                          <p className="mt-2 text-[9px] font-bold text-[var(--text-tertiary)] uppercase tracking-tighter">
                            {new Date(log.created_at).toLocaleString("ko-KR")}
                          </p>
                        </div>
                      ))
                    ) : (
                      <div className="rounded-2xl border border-dashed border-[var(--line-strong)] px-8 py-12 text-center">
                        <p className="text-xs font-bold text-[var(--text-hint)] italic">No telemetry logs ingested yet.</p>
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
