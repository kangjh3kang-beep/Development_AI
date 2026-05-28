"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card, CardContent, CardTitle } from "@propai/ui";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import type { IoTDashboardData, MaintenanceAlert } from "@/components/cad/types";
import { motion } from "framer-motion";

const SEVERITY_TOKENS: Record<
  MaintenanceAlert["severity"],
  { color: string; label: string; icon: string }
> = {
  critical: { color: "var(--spot)", label: "긴급", icon: "🚨" },
  warning: { color: "var(--warning)", label: "주의", icon: "⚡" },
  info: { color: "var(--info)", label: "정보", icon: "ℹ️" },
};

const LINE_COLORS: Record<string, string> = {
  temperature: "var(--spot)",
  humidity: "var(--info)",
  co2: "var(--accent-strong)",
  energy: "var(--success)",
};

const SENSOR_ICONS: Record<string, string> = {
  temperature: "🌡️",
  humidity: "💧",
  co2: "🍃",
  energy: "⚡",
};

export function IoTDashboard() {
  const { data, isLoading } = useQuery({
    queryKey: ["analytics", "iot"],
    queryFn: () => (async () => ({} as IoTDashboardData))(),
    refetchInterval: 15_000,
  });

  // 센서 데이터를 타임스탬프 기준으로 피벗
  const chartData = useMemo(() => {
    if (!data) return [];
    const byTime = new Map<string, Record<string, number | string>>();
    for (const s of data.sensors) {
      const hour = new Date(s.timestamp).toLocaleTimeString("ko-KR", {
        hour: "2-digit",
        minute: "2-digit",
      });
      const existing = byTime.get(hour) ?? { time: hour };
      existing[s.sensor_type] = s.value;
      byTime.set(hour, existing);
    }
    return Array.from(byTime.values());
  }, [data]);

  const sensorTypes = useMemo(() => {
    if (!data) return [];
    return [...new Set(data.sensors.map((s) => s.sensor_type))];
  }, [data]);

  if (isLoading) {
    return (
      <div className="grid gap-6">
        <SkeletonLoader count={1} itemClassName="h-32 rounded-[2rem]" />
        <SkeletonLoader count={2} itemClassName="h-64 rounded-[3rem]" />
      </div>
    );
  }

  if (!data) return null;

  return (
    <section className="grid gap-10 p-1 font-sans" aria-label="IoT/Proptech 대시보드">
      {/* 센서 요약 KPI */}
      <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
        {data.sensor_summary.map((s, i) => (
          <motion.div
            key={s.type}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: i * 0.1 }}
          >
            <Card className="rounded-[2.5rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-lg)] overflow-hidden group hover:scale-[1.02] transition-all duration-500">
              <CardContent className="p-8 relative">
                <div className="absolute top-4 right-6 text-2xl opacity-20 grayscale group-hover:grayscale-0 group-hover:opacity-100 transition-all duration-500">
                  {SENSOR_ICONS[s.type] ?? "📡"}
                </div>
                <p className="text-[10px] font-[1000] uppercase tracking-[0.3em] text-[var(--text-hint)]">{s.type}</p>
                <div className="mt-4 flex items-baseline gap-2">
                  <p className="text-4xl font-[1000] tracking-tighter text-[var(--text-primary)]">
                    {s.avg_value.toFixed(1)}
                  </p>
                  <span className="text-sm font-black text-[var(--text-hint)] uppercase tracking-widest">{s.unit}</span>
                </div>
                <div className="mt-4 flex items-center justify-between">
                   <p className="text-[10px] font-bold text-[var(--text-hint)]">ACTIVE_NODES: {s.count}</p>
                   <div className="h-1 w-12 rounded-full bg-[var(--line-strong)]" />
                </div>
              </CardContent>
            </Card>
          </motion.div>
        ))}
      </div>

      <div className="grid gap-10 lg:grid-cols-12">
        {/* 실시간 센서 추이 차트 */}
        <Card className="lg:col-span-8 rounded-[4rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-2xl)] overflow-hidden min-h-[500px]">
          <CardContent className="p-10 lg:p-14 h-full flex flex-col">
            <div className="flex items-center justify-between mb-12">
              <div className="space-y-2">
                <p className="text-[10px] font-[1000] uppercase tracking-[0.4em] text-[var(--text-hint)]">STREAM_ANALYTICS</p>
                <CardTitle className="text-3xl font-[1000] tracking-tighter italic text-[var(--text-primary)]">
                  실시간 센서 <span className="text-[var(--accent-strong)]">추이 데이터.</span>
                </CardTitle>
              </div>
              <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] px-5 py-3 flex items-center gap-3">
                 <div className="h-2 w-2 rounded-full bg-[var(--accent-strong)] animate-ping" />
                 <span className="text-[10px] font-black uppercase tracking-widest text-[var(--text-primary)]">LIVE_DATA</span>
              </div>
            </div>

            <div className="flex-grow min-h-0">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--line-strong)" opacity={0.3} vertical={false} />
                  <XAxis 
                    dataKey="time" 
                    tick={{ fontSize: 10, fontWeight: 900, fill: "var(--text-hint)" }} 
                    axisLine={false}
                    tickLine={false}
                    dy={15}
                  />
                  <YAxis 
                    tick={{ fontSize: 10, fontWeight: 900, fill: "var(--text-hint)" }} 
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip
                    contentStyle={{
                      borderRadius: 24,
                      border: "1px solid var(--line-strong)",
                      backgroundColor: "var(--surface-strong)",
                      fontSize: 12,
                      boxShadow: "var(--shadow-2xl)",
                      backdropFilter: "blur(20px)",
                      padding: "16px 24px"
                    }}
                    itemStyle={{ fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.1em" }}
                    labelStyle={{ marginBottom: 8, color: "var(--text-hint)", fontWeight: 900, fontSize: 10 }}
                  />
                  <Legend 
                    verticalAlign="top" 
                    align="right"
                    iconType="circle"
                    wrapperStyle={{ paddingTop: -20, paddingBottom: 40, fontSize: 10, fontWeight: 900, textTransform: "uppercase", letterSpacing: "0.2em" }}
                  />
                  {sensorTypes.map((type) => (
                    <Line
                      key={type}
                      type="monotone"
                      dataKey={type}
                      stroke={LINE_COLORS[type] ?? "var(--accent-strong)"}
                      strokeWidth={4}
                      dot={{ r: 4, strokeWidth: 2, stroke: "var(--surface-strong)", fill: LINE_COLORS[type] ?? "var(--accent-strong)" }}
                      activeDot={{ r: 6, strokeWidth: 0 }}
                      name={type}
                      animationDuration={1500}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        {/* 예측 정비 알림 리스트 */}
        <Card className="lg:col-span-4 rounded-[4rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-2xl)] overflow-hidden flex flex-col">
          <CardContent className="p-10 lg:p-12 h-full flex flex-col">
            <p className="text-[10px] font-[1000] uppercase tracking-[0.4em] text-[var(--text-hint)]">MAINTENANCE_AI</p>
            <CardTitle className="mt-3 text-2xl font-[1000] tracking-tighter italic text-[var(--text-primary)]">AI 정비 <span className="text-[var(--spot)]">알림.</span></CardTitle>
            
            <div className="mt-10 flex-grow space-y-6 overflow-y-auto pr-2 custom-scrollbar">
              {data.alerts.map((alert, i) => {
                const token = SEVERITY_TOKENS[alert.severity];
                return (
                  <motion.div
                    key={alert.id}
                    initial={{ opacity: 0, x: 20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.1 }}
                    className="group rounded-3xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-6 transition-all duration-300 hover:border-transparent hover:shadow-[var(--shadow-lg)] relative overflow-hidden"
                  >
                    <div className="absolute top-0 left-0 w-1.5 h-full transition-all group-hover:w-full opacity-10" style={{ backgroundColor: token.color }} />
                    <div className="relative z-10 flex items-start justify-between gap-4">
                      <div className="space-y-2">
                        <div className="flex items-center gap-2">
                           <span className="text-lg">{token.icon}</span>
                           <p className="text-xs font-[1000] text-[var(--text-primary)] uppercase tracking-tighter">
                             {alert.equipment_name}
                           </p>
                        </div>
                        <p className="text-[11px] leading-relaxed text-[var(--text-secondary)] font-medium">
                          {alert.message}
                        </p>
                      </div>
                      <span
                        className="shrink-0 rounded-xl px-3 py-1 text-[9px] font-[1000] uppercase tracking-widest border border-[var(--line-strong)]"
                        style={{ color: token.color, borderColor: `${token.color}40` }}
                      >
                        {token.label}
                      </span>
                    </div>
                    <div className="relative z-10 mt-6 pt-4 border-t border-[var(--line-strong)]/50 flex flex-wrap gap-4 text-[9px] font-black text-[var(--text-hint)] uppercase tracking-widest">
                      <span className="flex items-center gap-1.5">
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>
                        EXPIRE: {alert.predicted_failure_date}
                      </span>
                      <span className="flex items-center gap-1.5">
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"/></svg>
                        CONF: {(alert.confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                  </motion.div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      </div>
    </section>
  );
}
