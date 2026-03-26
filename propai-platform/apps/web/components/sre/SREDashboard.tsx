"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Card, CardContent, CardTitle } from "@propai/ui";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import { apiClient } from "@/lib/api-client";
import type { BackupLogEntry, SREDashboardData, SREMetric } from "@/components/cad/types";

const STATUS_COLOR: Record<SREMetric["status"], { ring: string; bg: string; text: string }> = {
  healthy: { ring: "ring-emerald-500/30", bg: "bg-emerald-500", text: "text-emerald-400" },
  degraded: { ring: "ring-amber-500/30", bg: "bg-amber-500", text: "text-amber-400" },
  critical: { ring: "ring-red-500/30", bg: "bg-red-500", text: "text-red-400" },
};

const BACKUP_STATUS: Record<BackupLogEntry["status"], { bg: string; text: string; label: string }> = {
  success: { bg: "bg-emerald-500/10", text: "text-emerald-400", label: "성공" },
  failed: { bg: "bg-red-500/10", text: "text-red-400", label: "실패" },
  in_progress: { bg: "bg-amber-500/10", text: "text-amber-400", label: "진행 중" },
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

/** RTO 위젯 — Date.now()를 effect에서만 호출하여 purity 규칙 준수. */
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
    <Card className="border-white/5 bg-gradient-to-br from-[#0f172a] to-[#1e293b] backdrop-blur-xl">
      <CardContent className="flex flex-col items-center justify-center p-6 text-center">
        <p className="text-xs uppercase tracking-widest text-slate-400">
          최근 백업 경과 (RTO)
        </p>
        <div className="relative mt-6">
          <svg className="h-32 w-32" viewBox="0 0 120 120">
            <circle cx="60" cy="60" r="52" fill="none" stroke="rgba(255,255,255,0.04)" strokeWidth="6" />
            <motion.circle
              cx="60" cy="60" r="52"
              fill="none"
              stroke={rtoMinutes !== null && rtoMinutes < 120 ? "#10b981" : "#ef4444"}
              strokeWidth="6"
              strokeLinecap="round"
              strokeDasharray={`${CIRCLE_CIRCUMFERENCE}`}
              initial={{ strokeDashoffset: CIRCLE_CIRCUMFERENCE }}
              animate={{
                strokeDashoffset: rtoMinutes !== null
                  ? CIRCLE_CIRCUMFERENCE * (1 - Math.min(rtoMinutes / 360, 1))
                  : CIRCLE_CIRCUMFERENCE,
              }}
              transition={{ duration: 1.2, ease: "easeOut" }}
              transform="rotate(-90 60 60)"
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            {rtoMinutes !== null ? (
              <>
                <span className={`text-2xl font-bold ${rtoMinutes < 120 ? "text-emerald-400" : "text-red-400"}`}>
                  {rtoMinutes < 60 ? `${rtoMinutes}분` : `${Math.floor(rtoMinutes / 60)}시간`}
                </span>
                <span className="mt-0.5 text-[10px] text-slate-500">전</span>
              </>
            ) : (
              <span className="text-sm text-slate-500">데이터 없음</span>
            )}
          </div>
        </div>
        {completedAt && (
          <p className="mt-4 text-xs text-slate-500">
            {new Date(completedAt).toLocaleString("ko-KR")}
          </p>
        )}
        <p className="mt-1 text-[10px] text-slate-500 font-mono">
          {rtoMinutes !== null && rtoMinutes < 120 ? "RTO 목표 이내" : "RTO 목표 초과 경고"}
        </p>
      </CardContent>
    </Card>
  );
}

export function SREDashboard() {
  const { data, isLoading } = useQuery({
    queryKey: ["sre", "dashboard"],
    queryFn: () => apiClient.get<SREDashboardData>("/sre/dashboard"),
    refetchInterval: 30_000,
  });

  if (isLoading) {
    return <SkeletonLoader count={4} itemClassName="h-40" />;
  }

  if (!data) return null;

  const lastSuccessBackup = data.backup_logs.find((b) => b.status === "success");

  return (
    <section className="grid gap-6" aria-label="SRE/DevOps 관제소">
      {/* 상단: 핵심 SLA 위젯 */}
      <div className="grid gap-4 sm:grid-cols-3">
        {/* Uptime */}
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.4 }}
        >
          <Card className="border-white/5 bg-gradient-to-br from-[#0f172a] to-[#1e293b] backdrop-blur-xl">
            <CardContent className="flex flex-col items-center p-6 text-center">
              <p className="text-xs uppercase tracking-widest text-slate-400">가동률 (Uptime)</p>
              <div className="relative mt-4">
                <svg className="h-28 w-28" viewBox="0 0 120 120">
                  <circle cx="60" cy="60" r="52" fill="none" stroke="rgba(255,255,255,0.04)" strokeWidth="8" />
                  <motion.circle
                    cx="60" cy="60" r="52"
                    fill="none"
                    stroke="#10b981"
                    strokeWidth="8"
                    strokeLinecap="round"
                    strokeDasharray={`${CIRCLE_CIRCUMFERENCE}`}
                    initial={{ strokeDashoffset: CIRCLE_CIRCUMFERENCE }}
                    animate={{ strokeDashoffset: CIRCLE_CIRCUMFERENCE * (1 - data.uptime_percent / 100) }}
                    transition={{ duration: 1.2, ease: "easeOut" }}
                    transform="rotate(-90 60 60)"
                  />
                </svg>
                <div className="absolute inset-0 flex items-center justify-center">
                  <span className="text-2xl font-bold text-emerald-400">{data.uptime_percent}%</span>
                </div>
              </div>
            </CardContent>
          </Card>
        </motion.div>

        {/* 평균 응답 */}
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.4, delay: 0.1 }}
        >
          <Card className="border-white/5 bg-gradient-to-br from-[#0f172a] to-[#1e293b] backdrop-blur-xl">
            <CardContent className="flex flex-col items-center p-6 text-center">
              <p className="text-xs uppercase tracking-widest text-slate-400">API 평균 응답</p>
              <p className="mt-6 text-4xl font-bold text-cyan-400">
                {data.avg_response_ms}
                <span className="ml-1 text-base font-normal text-slate-500">ms</span>
              </p>
              <p className="mt-2 text-xs text-slate-500">
                {data.avg_response_ms < 200 ? "양호" : data.avg_response_ms < 500 ? "주의" : "경고"}
              </p>
            </CardContent>
          </Card>
        </motion.div>

        {/* 에러율 */}
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.4, delay: 0.2 }}
        >
          <Card className="border-white/5 bg-gradient-to-br from-[#0f172a] to-[#1e293b] backdrop-blur-xl">
            <CardContent className="flex flex-col items-center p-6 text-center">
              <p className="text-xs uppercase tracking-widest text-slate-400">API 에러율</p>
              <p className={`mt-6 text-4xl font-bold ${data.error_rate_percent < 1 ? "text-emerald-400" : "text-red-400"}`}>
                {data.error_rate_percent}
                <span className="ml-1 text-base font-normal text-slate-500">%</span>
              </p>
              <p className="mt-2 text-xs text-slate-500">
                {data.error_rate_percent < 0.5 ? "정상" : data.error_rate_percent < 1 ? "주의" : "경고"}
              </p>
            </CardContent>
          </Card>
        </motion.div>
      </div>

      {/* Prometheus 메트릭 그리드 */}
      <Card className="border-white/5 bg-gradient-to-br from-[#0f172a] to-[#1e293b] backdrop-blur-xl">
        <CardContent className="p-6">
          <CardTitle className="mb-5 text-base text-slate-200">인프라 메트릭</CardTitle>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {data.metrics.map((metric, i) => {
              const statusStyle = STATUS_COLOR[metric.status];
              return (
                <motion.div
                  key={metric.name}
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3, delay: i * 0.04 }}
                  className={`rounded-xl border border-white/5 bg-white/[0.02] p-4 ring-1 ${statusStyle.ring}`}
                >
                  <div className="flex items-center justify-between">
                    <p className="text-xs text-slate-400">{metric.name}</p>
                    <span className={`inline-block h-2 w-2 rounded-full ${statusStyle.bg}`} />
                  </div>
                  <p className={`mt-2 text-2xl font-bold ${statusStyle.text}`}>
                    {metric.value}
                    <span className="ml-1 text-xs font-normal text-slate-500">{metric.unit}</span>
                  </p>
                  <p className="mt-1 text-[10px] text-slate-500">
                    추세: {metric.trend === "up" ? "↑ 상승" : metric.trend === "down" ? "↓ 하락" : "→ 안정"}
                  </p>
                </motion.div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Grafana 임베딩 영역 */}
      <Card className="border-white/5 bg-gradient-to-br from-[#0f172a] to-[#1e293b] backdrop-blur-xl">
        <CardContent className="p-6">
          <CardTitle className="mb-4 text-base text-slate-200">Grafana 모니터링</CardTitle>
          {data.grafana_embed_url ? (
            <iframe
              src={data.grafana_embed_url}
              className="h-[400px] w-full rounded-xl border border-white/5"
              title="Grafana Dashboard"
              sandbox="allow-scripts allow-same-origin"
            />
          ) : (
            <div className="flex h-[200px] items-center justify-center rounded-xl border border-dashed border-white/10 bg-white/[0.01]">
              <div className="text-center">
                <p className="text-sm text-slate-400">Grafana 대시보드 연결 대기</p>
                <p className="mt-1 text-xs text-slate-500 font-mono">
                  GRAFANA_EMBED_URL 환경 변수를 설정하세요
                </p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* 백업 기록 + RTO 위젯 */}
      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        {/* 백업 로그 */}
        <Card className="border-white/5 bg-gradient-to-br from-[#0f172a] to-[#1e293b] backdrop-blur-xl">
          <CardContent className="p-6">
            <CardTitle className="mb-4 text-base text-slate-200">S3 재난복구 백업 기록</CardTitle>
            <div className="space-y-2">
              {data.backup_logs.map((log, i) => {
                const statusBadge = BACKUP_STATUS[log.status];
                return (
                  <motion.div
                    key={log.id}
                    initial={{ opacity: 0, x: -16 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.3, delay: i * 0.04 }}
                    className="flex items-center justify-between rounded-xl border border-white/5 bg-white/[0.02] px-4 py-3"
                  >
                    <div className="flex items-center gap-3">
                      <span className={`rounded-full ${statusBadge.bg} px-2.5 py-0.5 text-[10px] font-bold ${statusBadge.text}`}>
                        {statusBadge.label}
                      </span>
                      <div>
                        <p className="text-sm text-slate-300 font-mono">{log.backup_type}</p>
                        <p className="text-[10px] text-slate-500">
                          {new Date(log.started_at).toLocaleString("ko-KR")}
                        </p>
                      </div>
                    </div>
                    <div className="text-right text-xs text-slate-500">
                      {log.status !== "failed" && (
                        <>
                          <p>{formatSize(log.size_mb)}</p>
                          <p className="font-mono">{formatDuration(log.duration_seconds)}</p>
                        </>
                      )}
                    </div>
                  </motion.div>
                );
              })}
            </div>
          </CardContent>
        </Card>

        {/* RTO 위젯 */}
        <RTOWidget completedAt={lastSuccessBackup?.completed_at ?? null} />
      </div>
    </section>
  );
}
