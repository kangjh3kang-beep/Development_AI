"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Card, CardContent, CardTitle } from "@propai/ui";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import type { BackupLogEntry, SREDashboardData, SREMetric } from "@/components/cad/types";

const STATUS_COLOR: Record<SREMetric["status"], { ring: string; bg: string; text: string }> = {
  healthy: { ring: "ring-[var(--success)]/20", bg: "var(--success)", text: "var(--success)" },
  degraded: { ring: "ring-[var(--warning)]/20", bg: "var(--warning)", text: "var(--warning)" },
  critical: { ring: "ring-[var(--error)]/20", bg: "var(--error)", text: "var(--error)" },
};

const BACKUP_STATUS: Record<BackupLogEntry["status"], { bg: string; text: string; label: string }> = {
  success: { bg: "rgba(16, 185, 129, 0.1)", text: "var(--success)", label: "정상 완료" },
  failed: { bg: "rgba(239, 68, 68, 0.1)", text: "var(--error)", label: "백업 실패" },
  in_progress: { bg: "rgba(245, 158, 11, 0.1)", text: "var(--warning)", label: "진행 중" },
};

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}초`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}분 ${s}초`;
}

function formatSize(mb: number): string {
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
  return `${mb} MB`;
}

const CIRCLE_CIRCUMFERENCE = 2 * Math.PI * 52;

function RTOWidget({ completedAt }: { completedAt: string | null }) {
  const [rtoMinutes, setRtoMinutes] = useState<number | null>(null);

  useEffect(() => {
    if (!completedAt) return;
    const calc = () => {
      const elapsed = Math.round((Date.now() - new Date(completedAt).getTime()) / 60_000);
      setRtoMinutes(elapsed);
    };
    calc();
    const interval = setInterval(calc, 60_000);
    return () => clearInterval(interval);
  }, [completedAt]);

  return (
    <Card className="border-[var(--line-strong)] bg-[var(--surface-strong)]/80 backdrop-blur-xl shadow-[var(--shadow-2xl)] overflow-hidden">
      <CardContent className="flex flex-col items-center justify-center p-8 text-center">
        <p className="text-[10px] font-black uppercase tracking-[0.3em] text-[var(--text-tertiary)]">
          재난복구 목표 (RTO)
        </p>
        <div className="relative mt-8">
          <svg className="h-40 w-40" viewBox="0 0 120 120">
            <circle cx="60" cy="60" r="52" fill="none" stroke="var(--line)" strokeWidth="4" />
            <motion.circle
              cx="60" cy="60" r="52"
              fill="none"
              stroke={rtoMinutes !== null && rtoMinutes < 120 ? "var(--success)" : "var(--error)"}
              strokeWidth="6"
              strokeLinecap="round"
              strokeDasharray={`${CIRCLE_CIRCUMFERENCE}`}
              initial={{ strokeDashoffset: CIRCLE_CIRCUMFERENCE }}
              animate={{
                strokeDashoffset: rtoMinutes !== null
                  ? CIRCLE_CIRCUMFERENCE * (1 - Math.min(rtoMinutes / 360, 1))
                  : CIRCLE_CIRCUMFERENCE,
              }}
              transition={{ duration: 1.5, ease: [0.16, 1, 0.3, 1] }}
              transform="rotate(-90 60 60)"
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            {rtoMinutes !== null ? (
              <>
                <span className={`text-3xl font-[1000] tracking-tighter ${rtoMinutes < 120 ? "text-[var(--success)]" : "text-[var(--error)]"}`}>
                  {rtoMinutes < 60 ? `${rtoMinutes}분` : `${Math.floor(rtoMinutes / 60)}H`}
                </span>
                <span className="mt-1 text-[10px] font-black text-[var(--text-hint)] uppercase tracking-wider">ELAPSED</span>
              </>
            ) : (
              <span className="text-sm font-bold text-[var(--text-hint)]">NO DATA</span>
            )}
          </div>
        </div>
        {completedAt && (
          <p className="mt-6 text-[11px] font-bold text-[var(--text-secondary)] font-mono">
            LAST: {new Date(completedAt).toLocaleString("ko-KR", { hour12: false })}
          </p>
        )}
        <div className={`mt-2 px-3 py-1 rounded-full text-[9px] font-black uppercase tracking-widest ${rtoMinutes !== null && rtoMinutes < 120 ? "bg-[var(--success-soft)] text-[var(--success)]" : "bg-[var(--error-soft)] text-[var(--error)]"}`}>
          {rtoMinutes !== null && rtoMinutes < 120 ? "Compliant" : "RTO Breach Warning"}
        </div>
      </CardContent>
    </Card>
  );
}

export function SREDashboard() {
  const { data, isLoading } = useQuery({
    queryKey: ["sre", "dashboard"],
    queryFn: () => (async () => ({} as SREDashboardData))(),
    refetchInterval: 15_000,
  });

  if (isLoading) {
    return <SkeletonLoader count={4} itemClassName="h-40" />;
  }

  if (!data) return null;

  const lastSuccessBackup = data.backup_logs.find((b) => b.status === "success");

  return (
    <section className="grid gap-8" aria-label="SRE 시스템 성능 관제">
      {/* SLA Core Metrics */}
      <div className="grid gap-4 sm:grid-cols-3">
        {/* Uptime Gauge */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
        >
          <Card className="border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-lg)]">
            <CardContent className="flex flex-col items-center p-8 text-center">
              <p className="text-[10px] font-black uppercase tracking-[0.3em] text-[var(--text-tertiary)]">가동률 (UPTIME)</p>
              <div className="relative mt-6">
                <svg className="h-32 w-32" viewBox="0 0 120 120">
                  <circle cx="60" cy="60" r="52" fill="none" stroke="var(--line)" strokeWidth="8" />
                  <motion.circle
                    cx="60" cy="60" r="52"
                    fill="none"
                    stroke="var(--success)"
                    strokeWidth="8"
                    strokeLinecap="round"
                    strokeDasharray={`${CIRCLE_CIRCUMFERENCE}`}
                    initial={{ strokeDashoffset: CIRCLE_CIRCUMFERENCE }}
                    animate={{ strokeDashoffset: CIRCLE_CIRCUMFERENCE * (1 - data.uptime_percent / 100) }}
                    transition={{ duration: 1.5, ease: [0.16, 1, 0.3, 1] }}
                    transform="rotate(-90 60 60)"
                  />
                </svg>
                <div className="absolute inset-0 flex items-center justify-center">
                  <span className="text-3xl font-[1000] tracking-tighter text-[var(--success)]">{data.uptime_percent}%</span>
                </div>
              </div>
              <p className="mt-4 text-[10px] font-black uppercase text-[var(--text-hint)] tracking-widest">Target: 99.99%</p>
            </CardContent>
          </Card>
        </motion.div>

        {/* Latency Widget */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1 }}
        >
          <Card className="border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-lg)]">
            <CardContent className="flex flex-col items-center p-8 text-center">
              <p className="text-[10px] font-black uppercase tracking-[0.3em] text-[var(--text-tertiary)]">API 평균 응답 속도</p>
              <p className="mt-10 text-5xl font-[1000] tracking-tighter text-[var(--accent)]">
                {data.avg_response_ms}
                <span className="ml-1 text-sm font-bold text-[var(--text-hint)] tracking-normal">ms</span>
              </p>
              <div className="mt-8 flex items-center gap-2">
                <div className={`h-2 w-2 rounded-full ${data.avg_response_ms < 200 ? "bg-[var(--success)]" : data.avg_response_ms < 500 ? "bg-[var(--warning)]" : "bg-[var(--error)]"}`} />
                <span className="text-[11px] font-black uppercase tracking-widest text-[var(--text-secondary)]">
                  {data.avg_response_ms < 200 ? "OPTIMAL" : data.avg_response_ms < 500 ? "DEGRADED" : "CRITICAL"}
                </span>
              </div>
            </CardContent>
          </Card>
        </motion.div>

        {/* Error Rate Widget */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.2 }}
        >
          <Card className="border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-lg)]">
            <CardContent className="flex flex-col items-center p-8 text-center">
              <p className="text-[10px] font-black uppercase tracking-[0.3em] text-[var(--text-tertiary)]">시스템 에러율</p>
              <p className={`mt-10 text-5xl font-[1000] tracking-tighter ${data.error_rate_percent < 1 ? "text-[var(--success)]" : "text-[var(--error)]"}`}>
                {data.error_rate_percent}
                <span className="ml-1 text-sm font-bold text-[var(--text-hint)] tracking-normal">%</span>
              </p>
              <div className="mt-8 flex items-center gap-2">
                <div className={`h-2 w-2 rounded-full ${data.error_rate_percent < 0.5 ? "bg-[var(--success)]" : "bg-[var(--error)]"}`} />
                <span className="text-[11px] font-black uppercase tracking-widest text-[var(--text-secondary)]">
                  {data.error_rate_percent < 0.5 ? "NOMINAL" : "ALERT"}
                </span>
              </div>
            </CardContent>
          </Card>
        </motion.div>
      </div>

      {/* Prometheus Infrastructure Metrics Grid */}
      <Card className="border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-2xl)]">
        <CardContent className="p-8">
          <CardTitle className="mb-8 flex items-center gap-3">
             <div className="h-4 w-1 bg-[var(--accent)]" />
             <span className="text-[12px] font-black uppercase tracking-[0.3em] text-[var(--text-primary)]">인프라 실시간 메트릭</span>
          </CardTitle>
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {data.metrics.map((metric, i) => {
              const statusStyle = STATUS_COLOR[metric.status];
              return (
                <motion.div
                  key={metric.name}
                  initial={{ opacity: 0, scale: 0.98 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ duration: 0.3, delay: i * 0.05 }}
                  className={`relative rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)]/50 p-5 ring-1 ${statusStyle.ring} overflow-hidden`}
                >
                  <div className="flex items-center justify-between mb-4">
                    <p className="text-[10px] font-black uppercase tracking-[0.2em] text-[var(--text-tertiary)]">{metric.name}</p>
                    <span className="h-2 w-2 rounded-full animate-pulse" style={{ backgroundColor: statusStyle.bg }} />
                  </div>
                  <p className="text-3xl font-[1000] tracking-tighter" style={{ color: statusStyle.text }}>
                    {metric.value}
                    <span className="ml-1 text-sm font-bold text-[var(--text-hint)] tracking-normal">{metric.unit}</span>
                  </p>
                  <div className="mt-4 flex justify-between items-center text-[9px] font-black uppercase tracking-widest text-[var(--text-hint)]">
                    <span>TREND: {metric.trend === "up" ? "ASCENDING" : metric.trend === "down" ? "DESCENDING" : "STABLE"}</span>
                    <span className="font-mono">{metric.trend === "up" ? "▲" : metric.trend === "down" ? "▼" : "—"}</span>
                  </div>
                </motion.div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Grafana Integration Area */}
      <Card className="border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-2xl)] overflow-hidden">
        <CardContent className="p-0">
          <div className="bg-[var(--surface-soft)] p-6 border-b border-[var(--line)] flex justify-between items-center">
            <CardTitle className="flex items-center gap-3">
               <div className="h-4 w-1 bg-[#FADE06]" />
               <span className="text-[12px] font-black uppercase tracking-[0.3em] text-[var(--text-primary)]">GRAFANA 시각화 애널리틱스</span>
            </CardTitle>
            <div className="flex gap-2">
               {["CPU", "MEM", "DISK", "NW"].map(t => (
                 <span key={t} className="px-2 py-1 rounded bg-[var(--surface-strong)] text-[8px] font-black text-[var(--text-tertiary)] border border-[var(--line)]">{t}</span>
               ))}
            </div>
          </div>
          <div className="p-8">
            {data.grafana_embed_url ? (
              <iframe
                src={data.grafana_embed_url}
                className="h-[480px] w-full rounded-2xl border border-[var(--line-strong)] shadow-[var(--shadow-inner)]"
                title="Grafana Dashboard"
                sandbox="allow-scripts allow-same-origin"
              />
            ) : (
              <div className="flex h-[320px] flex-col items-center justify-center rounded-2xl border-2 border-dashed border-[var(--line-strong)] bg-[var(--surface-soft)]/30">
                <div className="text-center">
                  <p className="text-sm font-bold text-[var(--text-secondary)] italic">Awaiting Grafana Tunneling...</p>
                  <p className="mt-3 text-[9px] font-black text-[var(--text-hint)] uppercase tracking-[0.3em]">
                    CONFIGURE GRAFANA_EMBED_URL IN SECRETS
                  </p>
                </div>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Disaster Recovery & Logs */}
      <div className="grid gap-8 lg:grid-cols-[1fr_400px]">
        {/* Backup History */}
        <Card className="border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-2xl)] flex flex-col overflow-hidden">
          <CardContent className="flex-1 flex flex-col p-8">
            <CardTitle className="mb-8 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="h-4 w-1 bg-[var(--success)]" />
                <span className="text-[12px] font-black uppercase tracking-[0.3em] text-[var(--text-primary)]">S3 재난복구 동기화 기록</span>
              </div>
              <span className="text-[9px] font-black text-[var(--text-hint)] uppercase tracking-widest font-mono">DR REGION: AP-NORTHEAST-2</span>
            </CardTitle>
            <div className="space-y-3 flex-1 overflow-y-auto pr-2 custom-scrollbar" style={{ maxHeight: "400px" }}>
              {data.backup_logs.map((log, i) => {
                const statusBadge = BACKUP_STATUS[log.status];
                return (
                  <motion.div
                    key={log.id}
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.4, delay: i * 0.05 }}
                    className="flex items-center justify-between rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)]/50 px-6 py-4 hover:bg-[var(--surface)] transition-colors group"
                  >
                    <div className="flex items-center gap-5">
                      <span className="w-20 font-black uppercase text-[9px] tracking-wider text-center py-1.5 rounded-lg border" style={{ backgroundColor: statusBadge.bg, color: statusBadge.text, borderColor: statusBadge.text + "30" }}>
                        {statusBadge.label}
                      </span>
                      <div>
                        <p className="text-[11px] font-[1000] text-[var(--text-primary)] font-mono tracking-tighter uppercase">{log.backup_type}</p>
                        <p className="text-[9px] text-[var(--text-hint)] mt-1">
                          {new Date(log.started_at).toLocaleString("ko-KR", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false })}
                        </p>
                      </div>
                    </div>
                    <div className="text-right">
                      {log.status !== "failed" && (
                        <>
                          <p className="text-[10px] font-black text-[var(--text-secondary)] font-mono">{formatSize(log.size_mb)}</p>
                          <p className="text-[9px] font-bold text-[var(--text-hint)] uppercase mt-0.5">{formatDuration(log.duration_seconds)}</p>
                        </>
                      )}
                    </div>
                  </motion.div>
                );
              })}
            </div>
          </CardContent>
        </Card>

        {/* RTO Visualization Widget */}
        <RTOWidget completedAt={lastSuccessBackup?.completed_at ?? null} />
      </div>
    </section>
  );
}
