"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import { motion } from "framer-motion";
import { Card, CardContent, CardTitle } from "@propai/ui";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import { apiClient } from "@/lib/api-client";
import type { DigitalTwinDashboardData } from "@/components/cad/types";

const SENSOR_COLORS: Record<string, string> = {
  temperature: "#ef4444",
  vibration: "#f59e0b",
  pressure: "#3b82f6",
  humidity: "#10b981",
};

const SENSOR_LABELS: Record<string, string> = {
  temperature: "온도",
  vibration: "진동",
  pressure: "기압",
  humidity: "습도",
};

export function DigitalTwinAnomalyDashboard() {
  const { data, isLoading } = useQuery({
    queryKey: ["digital-twin", "anomalies"],
    queryFn: () => apiClient.get<DigitalTwinDashboardData>("/digital-twin/anomalies"),
    refetchInterval: 30_000,
  });

  const [selectedSensor, setSelectedSensor] = useState<string>("vibration");

  // 선택된 센서 데이터만 필터링
  const chartData = useMemo(() => {
    if (!data) return [];
    return data.anomalies
      .filter((a) => a.sensor_type === selectedSensor)
      .map((a) => ({
        time: new Date(a.timestamp).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" }),
        hour: new Date(a.timestamp).getHours(),
        value: Number(a.value.toFixed(2)),
        anomaly_score: Number(a.anomaly_score.toFixed(4)),
        is_anomaly: a.is_anomaly,
        severity: a.severity,
      }));
  }, [data, selectedSensor]);

  // 이상 포인트만 추출 (빨간점 강조용)
  const anomalyPoints = useMemo(() => {
    return chartData.filter((d) => d.is_anomaly).map((d) => ({
      ...d,
      z: 200,
    }));
  }, [chartData]);

  const sensorTypes = useMemo(() => {
    if (!data) return [];
    return [...new Set(data.anomalies.map((a) => a.sensor_type))];
  }, [data]);

  if (isLoading) {
    return (
      <div className="grid gap-6">
         <SkeletonLoader count={1} itemClassName="h-32 rounded-[2rem]" />
         <div className="grid gap-6 md:grid-cols-2">
            <SkeletonLoader count={2} itemClassName="h-[400px] rounded-[3rem]" />
         </div>
      </div>
    );
  }

  if (!data) return null;

  const { summary } = data;

  return (
    <section className="grid gap-8 p-1 font-sans" aria-label="디지털 트윈 이상 감지">
      {/* KPI 카드 */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[
          { label: "활성 센서", value: summary.total_sensors, unit: "개", color: "text-[var(--info)]", icon: "📡" },
          { label: "이상 감지", value: summary.anomalies_detected, unit: "건", color: "text-[var(--warning)]", icon: "⚠️" },
          { label: "긴급 경고", value: summary.critical_count, unit: "건", color: "text-[var(--spot)]", icon: "🚨" },
          { label: "주의 경고", value: summary.warning_count, unit: "건", color: "text-[var(--warning)]", icon: "⚡" },
        ].map((kpi, i) => (
          <motion.div
            key={kpi.label}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: i * 0.05 }}
          >
            <Card className="rounded-[2.5rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-lg)] overflow-hidden group">
              <CardContent className="p-8 relative">
                 <div className="absolute top-4 right-6 text-2xl opacity-20 grayscale group-hover:grayscale-0 group-hover:opacity-100 transition-all duration-500">{kpi.icon}</div>
                 <p className="text-[10px] font-[1000] uppercase tracking-[0.3em] text-[var(--text-hint)]">{kpi.label}</p>
                 <div className="mt-4 flex items-baseline gap-2">
                   <p className={`text-4xl font-[1000] tracking-tighter ${kpi.color}`}>
                     {kpi.value}
                   </p>
                   <span className="text-sm font-black text-[var(--text-hint)] uppercase tracking-widest">{kpi.unit}</span>
                 </div>
                 <div className="mt-4 h-1 w-12 rounded-full bg-[var(--line-strong)]" />
              </CardContent>
            </Card>
          </motion.div>
        ))}
      </div>

      <div className="grid gap-8 lg:grid-cols-12">
        {/* 센서 필터 및 설정 */}
        <Card className="lg:col-span-12 rounded-[3rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-xl)] overflow-hidden">
          <CardContent className="p-8 lg:p-10 flex flex-wrap items-center justify-between gap-6">
            <div className="space-y-1">
               <h4 className="text-xl font-[1000] tracking-tighter italic text-[var(--text-primary)]">센서 텔레메트리 스트림<span className="text-[var(--accent-strong)]">.</span></h4>
               <p className="text-xs font-bold text-[var(--text-hint)] uppercase tracking-[0.2em]">실시간 데이터 피드 및 이상 징후 모니터링</p>
            </div>
            <div className="flex flex-wrap gap-3">
              {sensorTypes.map((type) => (
                <button
                  key={type}
                  onClick={() => setSelectedSensor(type)}
                  className={`flex items-center gap-3 rounded-2xl px-6 py-3 text-xs font-[1000] uppercase tracking-widest transition-all duration-500 border ${
                    selectedSensor === type
                      ? "border-[var(--accent-strong)] bg-[var(--accent-soft)] text-[var(--accent-strong)] shadow-[var(--shadow-glow)] scale-105"
                      : "border-[var(--line-strong)] text-[var(--text-hint)] hover:border-[var(--text-hint)] hover:text-[var(--text-secondary)]"
                  }`}
                >
                  <span
                    className="inline-block h-2.5 w-2.5 rounded-full shadow-[0_0_8px_currentColor]"
                    style={{ backgroundColor: SENSOR_COLORS[type] ?? "var(--text-hint)" }}
                  />
                  {SENSOR_LABELS[type] ?? type}
                </button>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* 시계열 차트 — 센서 값 추이 + 이상 감지 포인트 */}
        <Card className="lg:col-span-8 rounded-[4rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-2xl)] overflow-hidden aspect-video lg:aspect-auto min-h-[500px]">
          <CardContent className="p-10 lg:p-14 h-full flex flex-col">
            <div className="flex items-center justify-between mb-10">
              <div className="space-y-2">
                <p className="text-[10px] font-[1000] uppercase tracking-[0.4em] text-[var(--text-hint)]">STREAM_ANALYSIS</p>
                <CardTitle className="text-3xl font-[1000] tracking-tighter italic text-[var(--text-primary)]">
                  {SENSOR_LABELS[selectedSensor] ?? selectedSensor} <span className="text-[var(--accent-strong)]">추이 분석.</span>
                </CardTitle>
              </div>
              <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] px-5 py-3 flex items-center gap-3">
                 <div className="h-3 w-3 rounded-full bg-[var(--spot)] animate-ping" />
                 <span className="text-[10px] font-black uppercase tracking-widest text-[var(--text-primary)]">LIVE_FEED</span>
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
                      color: "var(--text-primary)",
                      fontSize: 12,
                      boxShadow: "var(--shadow-2xl)",
                      backdropFilter: "blur(20px)",
                      padding: "16px 24px"
                    }}
                    itemStyle={{ fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.1em" }}
                    labelStyle={{ marginBottom: 8, color: "var(--text-hint)", fontWeight: 900, fontSize: 10, letterSpacing: "0.2em" }}
                  />
                  <Line
                    type="monotone"
                    dataKey="value"
                    stroke={SENSOR_COLORS[selectedSensor] ?? "var(--accent-strong)"}
                    strokeWidth={4}
                    dot={(props: any) => {
                      const { cx, cy, payload } = props;
                      if (payload.is_anomaly) {
                        return (
                          <g key={`dot-${cx}-${cy}`}>
                            <circle cx={cx} cy={cy} r={10} fill="var(--spot)" opacity={0.2} />
                            <circle cx={cx} cy={cy} r={5} fill="var(--spot)" stroke="var(--surface-strong)" strokeWidth={2} />
                          </g>
                        );
                      }
                      return null;
                    }}
                    name={SENSOR_LABELS[selectedSensor] ?? selectedSensor}
                    animationDuration={1500}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
            
            <div className="mt-8 flex items-center justify-between text-[10px] font-black text-[var(--text-hint)] uppercase tracking-[0.2em]">
               <div className="flex gap-6">
                 <div className="flex items-center gap-2">
                   <div className="h-2 w-2 rounded-full border border-[var(--line-strong)]" />
                   <span>정상 범위</span>
                 </div>
                 <div className="flex items-center gap-2">
                   <div className="h-2 w-2 rounded-full bg-[var(--spot)] shadow-[0_0_8px_var(--spot)]" />
                   <span>이상 징후 감지 (IsolationForest)</span>
                 </div>
               </div>
               <p className="italic">마지막 데이터 포인트: {chartData[chartData.length - 1]?.time}</p>
            </div>
          </CardContent>
        </Card>

        {/* 이상 스코어 산점도 */}
        <Card className="lg:col-span-4 rounded-[4rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-2xl)] overflow-hidden min-h-[500px]">
          <CardContent className="p-10 lg:p-12 border-t-[12px] border-[var(--spot)] h-full flex flex-col">
            <p className="text-[10px] font-[1000] uppercase tracking-[0.4em] text-[var(--text-hint)]">LATENT_SPACE</p>
            <CardTitle className="mt-3 text-2xl font-[1000] tracking-tighter italic text-[var(--text-primary)]">이상 스코어 <span className="text-[var(--spot)]">분포.</span></CardTitle>
            <p className="mt-4 text-xs font-bold leading-relaxed text-[var(--text-hint)]">
              IsolationForest 알고리즘에 의해 계산된 이상 징후 확률 밀도입니다. <span className="text-[var(--spot)] italic">임계치(-0.3)</span> 미만 포인트는 즉각적인 점검이 필요합니다.
            </p>
            
            <div className="mt-12 flex-grow min-h-0">
              <ResponsiveContainer width="100%" height="100%">
                <ScatterChart margin={{ top: 20, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--line-strong)" opacity={0.2} vertical={false} />
                  <XAxis
                    dataKey="hour"
                    type="number"
                    domain={[0, 24]}
                    tick={{ fontSize: 9, fontWeight: 900, fill: "var(--text-hint)" }}
                    axisLine={false}
                    tickLine={false}
                    name="시간(H)"
                  />
                  <YAxis
                    dataKey="anomaly_score"
                    tick={{ fontSize: 9, fontWeight: 900, fill: "var(--text-hint)" }}
                    axisLine={false}
                    tickLine={false}
                    domain={[-0.6, 0.6]}
                  />
                  <ZAxis range={[50, 400]} />
                  <ReferenceLine y={-0.3} stroke="var(--spot)" strokeDasharray="8 4" strokeWidth={2} label={{ value: "CRITICAL_THRESHOLD", fill: "var(--spot)", fontSize: 8, fontWeight: 900, position: 'insideTopRight' }} />
                  <ReferenceLine y={0} stroke="var(--line-strong)" strokeOpacity={0.5} />
                  <Tooltip
                    contentStyle={{
                      borderRadius: 20,
                      border: "none",
                      backgroundColor: "var(--surface-soft)",
                      boxShadow: "var(--shadow-xl)",
                      fontSize: 10,
                      padding: "12px 20px"
                    }}
                  />
                  <Scatter
                    data={chartData.filter((d) => !d.is_anomaly)}
                    fill="var(--accent-strong)"
                    opacity={0.4}
                    name="정상"
                  />
                  <Scatter
                    data={anomalyPoints}
                    fill="var(--spot)"
                    opacity={1}
                    name="이상"
                     shape="star"
                  />
                </ScatterChart>
              </ResponsiveContainer>
            </div>

            <div className="mt-8 rounded-3xl bg-[var(--surface-soft)] p-6 border border-[var(--line-subtle)] group hover:border-[var(--spot)] transition-colors duration-500">
               <div className="flex items-center justify-between mb-1">
                 <span className="text-[10px] font-black uppercase tracking-widest text-[var(--spot)]">SYSTEM_HEALTH</span>
                 <span className="text-xs font-[1000] text-[var(--text-primary)]">{(100 - (summary.anomalies_detected / (summary.total_sensors * 24) * 100)).toFixed(2)}%</span>
               </div>
               <div className="h-1.5 w-full bg-[var(--surface-strong)] rounded-full overflow-hidden">
                 <motion.div 
                    initial={{ width: 0 }}
                    animate={{ width: "98.2%" }} 
                    className="h-full bg-gradient-to-r from-[var(--info)] to-[var(--accent-strong)]" 
                 />
               </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* 마지막 스캔 시간 */}
      <div className="flex items-center justify-center gap-4 py-8 border-t border-[var(--line-strong)]/30">
        <div className="h-2 w-2 rounded-full bg-[var(--accent-strong)] animate-pulse" />
        <p className="text-[10px] font-bold text-[var(--text-hint)] uppercase tracking-[0.5em]">
          DATA_INTEGRITY_VERIFIED_AT: {new Date(summary.last_scan_at).toLocaleString("ko-KR")}
        </p>
      </div>
    </section>
  );
}
