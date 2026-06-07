"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Card, CardContent, CardTitle } from "@propai/ui";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import { apiClient } from "@/lib/api-client";
import type { ParkingDashboardData, ParkingRecord } from "@/components/cad/types";

const EVENT_BADGE: Record<ParkingRecord["event_type"], { bg: string; text: string; label: string }> = {
  entry: { bg: "bg-emerald-500/10", text: "text-emerald-400", label: "입차" },
  exit: { bg: "bg-sky-500/10", text: "text-sky-400", label: "출차" },
};

export function ParkingLogView() {
  const { data, isLoading } = useQuery({
    queryKey: ["parking", "dashboard"],
    queryFn: () => apiClient.get<ParkingDashboardData>("/parking/dashboard"),
    refetchInterval: 15_000,
  });

  const [filter, setFilter] = useState<"all" | "entry" | "exit">("all");

  const filteredRecords = useMemo(() => {
    if (!data) return [];
    const records = filter === "all"
      ? (data.records ?? [])
      : (data.records ?? []).filter((r) => r.event_type === filter);
    return [...records].sort(
      (a, b) => new Date(b.recorded_at).getTime() - new Date(a.recorded_at).getTime(),
    );
  }, [data, filter]);

  if (isLoading) {
    return <SkeletonLoader count={2} itemClassName="h-48" />;
  }

  if (!data) return null;

  const { stats } = data;
  const occupancyPercent = Math.round(stats.occupancy_rate * 100);

  return (
    <section className="grid gap-6" aria-label="주차 관제 대시보드">
      {/* KPI 카드 */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[
          { label: "오늘 출입차", value: stats.total_today, unit: "건" },
          { label: "현재 주차", value: stats.currently_parked, unit: "대" },
          { label: "총 수용", value: stats.capacity, unit: "면" },
          { label: "점유율", value: occupancyPercent, unit: "%" },
        ].map((kpi, i) => (
          <motion.div
            key={kpi.label}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: i * 0.05 }}
          >
            <Card className="border-white/5 bg-gradient-to-br from-[#0f172a] to-[#1e293b] backdrop-blur-xl">
              <CardContent className="p-5">
                <p className="text-xs uppercase tracking-widest text-slate-400">{kpi.label}</p>
                <p className="mt-2 text-3xl font-bold text-slate-100">
                  {kpi.value}
                  <span className="ml-1 text-sm font-normal text-slate-500">{kpi.unit}</span>
                </p>
              </CardContent>
            </Card>
          </motion.div>
        ))}
      </div>

      {/* 점유율 프로그레스 */}
      <Card className="border-white/5 bg-gradient-to-br from-[#0f172a] to-[#1e293b] backdrop-blur-xl">
        <CardContent className="p-5">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base text-slate-200">주차장 점유율</CardTitle>
            <span className="text-sm font-mono text-slate-400">{stats.currently_parked} / {stats.capacity}</span>
          </div>
          <div className="mt-3 h-3 overflow-hidden rounded-full bg-white/5">
            <motion.div
              className={`h-full rounded-full ${occupancyPercent > 85 ? "bg-red-500" : occupancyPercent > 60 ? "bg-amber-500" : "bg-emerald-500"}`}
              initial={{ width: 0 }}
              animate={{ width: `${occupancyPercent}%` }}
              transition={{ duration: 1, ease: "easeOut" }}
            />
          </div>
        </CardContent>
      </Card>

      {/* 출입차 로그 */}
      <Card className="border-white/5 bg-gradient-to-br from-[#0f172a] to-[#1e293b] backdrop-blur-xl">
        <CardContent className="p-5">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <CardTitle className="text-base text-slate-200">출입차 기록</CardTitle>
            <div className="flex gap-1.5">
              {(["all", "entry", "exit"] as const).map((f) => (
                <button
                  key={f}
                  onClick={() => setFilter(f)}
                  className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${
                    filter === f
                      ? "bg-cyan-500/20 text-cyan-400"
                      : "text-slate-500 hover:bg-white/5 hover:text-slate-300"
                  }`}
                >
                  {f === "all" ? "전체" : f === "entry" ? "입차" : "출차"}
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-2">
            {filteredRecords.map((record, i) => {
              const badge = EVENT_BADGE[record.event_type];
              return (
                <motion.div
                  key={record.id}
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.3, delay: i * 0.03 }}
                  className="flex items-center justify-between rounded-xl border border-white/5 bg-white/[0.02] px-4 py-3"
                >
                  <div className="flex items-center gap-3">
                    <span className={`rounded-full ${badge.bg} px-2.5 py-0.5 text-[10px] font-bold ${badge.text}`}>
                      {badge.label}
                    </span>
                    <span className="font-mono text-sm font-semibold text-slate-200 tracking-wider">
                      {record.plate_number}
                    </span>
                  </div>
                  <div className="flex items-center gap-4 text-xs text-slate-500">
                    <span>{record.zone}</span>
                    <span className="font-mono">
                      {new Date(record.recorded_at).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" })}
                    </span>
                  </div>
                </motion.div>
              );
            })}
          </div>
        </CardContent>
      </Card>
    </section>
  );
}
