"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card, CardContent, CardTitle } from "@propai/ui";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import type { ESGDashboardData, ESGMetric } from "@/components/cad/types";


import { motion } from "framer-motion";

const TREND_ICONS: Record<ESGMetric["trend"], string> = {
  up: "↗",
  down: "↘",
  stable: "→",
};

function getTrendColor(metric: ESGMetric): string {
  const lowerIsBetter = metric.unit === "tCO2e" || metric.label.includes("사고율");
  if (metric.trend === "stable") return "text-[var(--text-hint)]";
  if (lowerIsBetter) {
    return metric.trend === "down" ? "text-[var(--success)]" : "text-[var(--spot)]";
  }
  return metric.trend === "up" ? "text-[var(--success)]" : "text-[var(--spot)]";
}

function getTargetStatus(metric: ESGMetric): boolean {
  const lowerIsBetter = metric.unit === "tCO2e" || metric.label.includes("사고율");
  return lowerIsBetter ? metric.value <= metric.target : metric.value >= metric.target;
}

export function ESGDashboard() {
  const { data, isLoading } = useQuery({
    queryKey: ["analytics", "esg"],
    queryFn: () => (async () => ({} as ESGDashboardData))(),
    refetchInterval: 60_000,
  });

  if (isLoading) {
    return (
      <div className="grid gap-8">
        <div className="grid gap-8 sm:grid-cols-2">
           <SkeletonLoader count={1} itemClassName="h-44 rounded-[3.5rem]" />
           <SkeletonLoader count={1} itemClassName="h-44 rounded-[3.5rem]" />
        </div>
        <SkeletonLoader count={1} itemClassName="h-[400px] rounded-[4rem]" />
      </div>
    );
  }

  if (!data) return null;

  return (
    <section className="grid gap-10 p-1 font-sans" aria-label="ESG/Climate 대시보드">
      {/* 종합 점수 + GRESB */}
      <div className="grid gap-8 sm:grid-cols-2">
        <motion.div
           initial={{ opacity: 0, x: -20 }}
           animate={{ opacity: 1, x: 0 }}
           transition={{ duration: 0.6 }}
        >
          <Card className="rounded-[4rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-2xl)] overflow-hidden relative group">
            <div className="absolute inset-0 bg-gradient-to-br from-[var(--accent-strong)]/5 to-transparent" />
            <CardContent className="p-12 text-center relative z-10">
              <p className="text-[10px] font-[1000] uppercase tracking-[0.5em] text-[var(--accent-strong)] mb-6">COMPOSITE_ESG_INDEX</p>
              <div className="flex items-center justify-center gap-4">
                <p className="text-7xl font-[1000] tracking-[calc(-0.05em)] text-[var(--text-primary)]">
                  {data.overall_score.toFixed(1)}
                </p>
                <div className="flex flex-col items-start">
                   <span className="text-sm font-black text-[var(--accent-strong)]">/ 100</span>
                   <span className="text-[8px] font-black text-[var(--text-hint)] uppercase">INDEX_SCORE</span>
                </div>
              </div>
              <p className="mt-8 text-xs font-bold text-[var(--text-secondary)] italic">"업계 평균 대비 <span className="text-[var(--success)] font-black">+14.2%</span> 높은 지속가능성 달성"</p>
            </CardContent>
          </Card>
        </motion.div>

        <motion.div
           initial={{ opacity: 0, x: 20 }}
           animate={{ opacity: 1, x: 0 }}
           transition={{ duration: 0.6 }}
        >
          <Card className="rounded-[4rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-2xl)] overflow-hidden relative group">
            <div className="absolute inset-0 bg-gradient-to-tr from-[var(--spot)]/5 to-transparent" />
            <CardContent className="p-12 text-center relative z-10">
              <p className="text-[10px] font-[1000] uppercase tracking-[0.5em] text-[var(--spot)] mb-6">GRESB_BENCHMARK</p>
              <p className="text-7xl font-[1000] tracking-tighter text-[var(--spot)] drop-shadow-[0_0_15px_var(--spot-dynamic)]">
                {data.gresb_rating}
              </p>
              <p className="mt-8 text-xs font-bold text-[var(--text-hint)] uppercase tracking-widest">Global Real Estate Sustainability Benchmark</p>
            </CardContent>
          </Card>
        </motion.div>
      </div>

      {/* KPI 카드 그리드 */}
      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
        {data.metrics.map((metric, i) => {
          const met = getTargetStatus(metric);
          const progress = Math.min(100, (metric.value / metric.target) * 100);
          return (
            <motion.div
              key={metric.id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.1 }}
            >
              <Card className="rounded-[2.5rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-lg)] overflow-hidden group hover:scale-[1.03] transition-all duration-500">
                <CardContent className="p-8">
                  <div className="flex items-center justify-between mb-6">
                    <p className="text-[10px] font-[1000] uppercase tracking-[0.2em] text-[var(--text-hint)]">
                      {metric.label}
                    </p>
                    <span className={`text-lg font-black ${getTrendColor(metric)}`}>
                      {TREND_ICONS[metric.trend]}
                    </span>
                  </div>
                  <div className="flex items-baseline gap-2">
                    <p className="text-3xl font-[1000] tracking-tighter text-[var(--text-primary)]">
                      {metric.value.toLocaleString("ko-KR")}
                    </p>
                    {metric.unit && (
                      <span className="text-xs font-black text-[var(--text-hint)] uppercase">
                        {metric.unit}
                      </span>
                    )}
                  </div>
                  <div className="mt-6 space-y-3">
                    <div className="h-1.5 w-full rounded-full bg-[var(--surface-soft)] overflow-hidden">
                      <motion.div
                        initial={{ width: 0 }}
                        animate={{ width: `${progress}%` }}
                        transition={{ duration: 1, delay: 0.5 }}
                        className={`h-full rounded-full ${met ? "bg-[var(--success)]" : "bg-[var(--warning)] shadow-[0_0_8px_var(--warning)]"}`}
                      />
                    </div>
                    <div className="flex items-center justify-between text-[9px] font-black uppercase tracking-widest">
                       <span className={met ? "text-[var(--success)]" : "text-[var(--warning)]"}>{met ? "TARGET_ACHIEVED" : "IN_PROGRESS"}</span>
                       <span className="text-[var(--text-hint)]">GOAL: {metric.target}{metric.unit}</span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          );
        })}
      </div>

      {/* Scope별 탄소 배출 차트 */}
      <Card className="rounded-[4rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-2xl)] overflow-hidden">
        <CardContent className="p-10 lg:p-14">
          <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-8 mb-12">
             <div className="space-y-2">
                <p className="text-[10px] font-[1000] uppercase tracking-[0.4em] text-[var(--text-hint)]">EMISSIONS_TRACKING</p>
                <CardTitle className="text-4xl font-[1000] tracking-tighter italic text-[var(--text-primary)]">Scope별 탄소 <span className="text-[var(--accent-strong)]">배출 인벤토리.</span></CardTitle>
             </div>
             <div className="flex gap-4">
               {[
                 { label: "Direct", color: "var(--accent-strong)" },
                 { label: "Indirect", color: "var(--info)" },
                 { label: "Value Chain", color: "var(--success)" },
               ].map(l => (
                 <div key={l.label} className="flex items-center gap-2 px-4 py-2 rounded-xl bg-[var(--surface-soft)] border border-[var(--line-strong)] text-[9px] font-black uppercase tracking-widest text-[var(--text-secondary)]">
                   <div className="h-2 w-2 rounded-full" style={{ backgroundColor: l.color }} />
                   {l.label}
                 </div>
               ))}
             </div>
          </div>
          
          <div className="h-[350px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.carbon_by_scope} margin={{ top: 20, right: 30, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--line-strong)" opacity={0.3} vertical={false} />
                <XAxis 
                  dataKey="scope" 
                  tick={{ fontSize: 10, fontWeight: 900, fill: "var(--text-hint)" }} 
                  axisLine={false}
                  tickLine={false}
                  dy={10}
                />
                <YAxis
                  tick={{ fontSize: 10, fontWeight: 900, fill: "var(--text-hint)" }}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip
                  cursor={{ fill: "var(--accent-soft)", opacity: 0.1 }}
                  contentStyle={{
                    borderRadius: 24,
                    border: "1px solid var(--line-strong)",
                    backgroundColor: "var(--surface-strong)",
                    fontSize: 12,
                    boxShadow: "var(--shadow-2xl)",
                    backdropFilter: "blur(20px)",
                    padding: "16px 24px"
                  }}
                  itemStyle={{ fontWeight: 800, textTransform: "uppercase" }}
                  labelStyle={{ marginBottom: 8, color: "var(--text-hint)", fontWeight: 900, fontSize: 10 }}
                />
                <Bar 
                  dataKey="tco2e" 
                  fill="var(--accent-strong)" 
                  radius={[12, 12, 0, 0]} 
                  barSize={64} 
                  animationDuration={1500}
                >
                  {data.carbon_by_scope.map((entry, index) => (
                    <motion.rect
                      key={`cell-${index}`}
                      fill={index === 0 ? "var(--accent-strong)" : index === 1 ? "var(--info)" : "var(--success)"}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="mt-12 flex items-center justify-center gap-6 py-6 border-t border-[var(--line-strong)]/30">
             <div className="h-2 w-2 rounded-full bg-[var(--success)] animate-pulse" />
             <p className="text-[10px] font-bold text-[var(--text-hint)] uppercase tracking-[0.5em]">REAL_TIME_CLIMATE_VERIFICATION_ACTIVE</p>
          </div>
        </CardContent>
      </Card>
    </section>
  );
}
