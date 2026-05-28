"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card, CardContent, CardTitle } from "@propai/ui";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import type { InvestmentMetrics } from "@/components/cad/types";

import { motion } from "framer-motion";

function formatKrw(value: number) {
  if (value >= 1_0000_0000) {
    return `${(value / 1_0000_0000).toFixed(1)}억`;
  }
  if (value >= 1_0000) {
    return `${(value / 1_0000).toFixed(0)}만`;
  }
  return value.toLocaleString("ko-KR");
}

export function InvestmentDashboard() {
  const { data, isLoading } = useQuery({
    queryKey: ["analytics", "investment"],
    queryFn: () => (async () => ({} as InvestmentMetrics))(),
    refetchInterval: 300_000, // 5 min
  });

  if (isLoading) {
    return (
      <div className="grid gap-8">
        <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
           {Array.from({ length: 4 }).map((_, i) => (
             <SkeletonLoader key={i} count={1} itemClassName="h-32 rounded-[2.5rem]" />
           ))}
        </div>
        <div className="grid gap-8 lg:grid-cols-2">
           <SkeletonLoader count={1} itemClassName="h-[450px] rounded-[4rem]" />
           <SkeletonLoader count={1} itemClassName="h-[450px] rounded-[4rem]" />
        </div>
      </div>
    );
  }

  if (!data) return null;

  return (
    <section className="grid gap-10 p-1 font-sans" aria-label="투자 분석 대시보드">
      {/* KPI 카드 */}
      <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
        {[
          { label: "AVM 감정가", value: `${formatKrw(data.avm_estimate_krw)}원`, sub: `신뢰도 ${(data.avm_confidence * 100).toFixed(0)}%`, dot: "var(--accent-strong)" },
          { label: "IRR", value: `${data.irr_percent.toFixed(1)}%`, sub: "내부수익률", dot: "var(--success)" },
          { label: "Cap Rate", value: `${data.cap_rate_percent.toFixed(1)}%`, sub: "자본환원율", dot: "var(--info)" },
          { label: "NOI", value: `${formatKrw(data.noi_krw)}원`, sub: "순운영소득 (연)", dot: "var(--spot)" },
        ].map((kpi, i) => (
          <motion.div
            key={kpi.label}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.1 }}
          >
            <Card className="rounded-[2.5rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-lg)] overflow-hidden group hover:scale-[1.02] transition-all duration-500">
              <CardContent className="p-8 relative">
                <div className="absolute top-4 right-6 h-2 w-2 rounded-full" style={{ backgroundColor: kpi.dot }} />
                <p className="text-[10px] font-[1000] uppercase tracking-[0.3em] text-[var(--text-hint)]">{kpi.label}</p>
                <p className="mt-4 text-3xl font-[1000] tracking-tighter text-[var(--text-primary)]">
                  {kpi.value}
                </p>
                <p className="mt-3 text-[10px] font-black text-[var(--text-hint)] uppercase tracking-widest">{kpi.sub}</p>
              </CardContent>
            </Card>
          </motion.div>
        ))}
      </div>

      <div className="grid gap-10 lg:grid-cols-12">
        {/* 16특성 레이더 차트 */}
        <Card className="lg:col-span-12 xl:col-span-7 rounded-[4rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-2xl)] overflow-hidden">
          <CardContent className="p-10 lg:p-14">
            <div className="mb-12">
               <p className="text-[10px] font-[1000] uppercase tracking-[0.4em] text-[var(--text-hint)]">MULTI_DIMENSIONAL_ANALYSIS</p>
               <CardTitle className="mt-2 text-4xl font-[1000] tracking-tighter italic text-[var(--text-primary)]">
                 16대 투자 <span className="text-[var(--accent-strong)]">특성 분석.</span>
               </CardTitle>
            </div>
            
            <div className="h-[450px]">
              <ResponsiveContainer width="100%" height="100%">
                <RadarChart data={data.features} outerRadius="80%">
                  <PolarGrid stroke="var(--line-strong)" strokeDasharray="4 4" opacity={0.5} />
                  <PolarAngleAxis
                    dataKey="feature"
                    tick={{ fontSize: 10, fontWeight: 900, fill: "var(--text-hint)" }}
                  />
                  <PolarRadiusAxis
                    angle={90}
                    domain={[0, 100]}
                    tick={{ fontSize: 9, fontWeight: 900, fill: "var(--text-hint)", opacity: 0.5 }}
                    axisLine={false}
                  />
                  <Radar
                    name="SCORE"
                    dataKey="score"
                    stroke="var(--accent-strong)"
                    fill="var(--accent-strong)"
                    fillOpacity={0.15}
                    strokeWidth={4}
                    animationDuration={2000}
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
                  />
                </RadarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        {/* 특성별 점수 비교 차트 */}
        <Card className="lg:col-span-12 xl:col-span-5 rounded-[4rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-2xl)] overflow-hidden">
          <CardContent className="p-10 lg:p-12">
            <p className="text-[10px] font-[1000] uppercase tracking-[0.4em] text-[var(--text-hint)]">FEATURE_RANKING</p>
            <CardTitle className="mt-2 text-2xl font-[1000] tracking-tighter italic text-[var(--text-primary)]">속성별 <span className="text-[var(--info)]">상세 지표.</span></CardTitle>
            
            <div className="mt-12 h-[500px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={[...data.features].sort((a, b) => b.score - a.score)}
                  layout="vertical"
                  margin={{ left: 20, right: 30, top: 0, bottom: 0 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--line-strong)" opacity={0.2} horizontal={false} />
                  <XAxis type="number" domain={[0, 100]} hide />
                  <YAxis
                    type="category"
                    dataKey="feature"
                    tick={{ fontSize: 10, fontWeight: 900, fill: "var(--text-primary)" }}
                    width={80}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip
                    cursor={{ fill: "var(--info-soft)", opacity: 0.1 }}
                    contentStyle={{
                      borderRadius: 12,
                      border: "none",
                      backgroundColor: "var(--surface-soft)",
                      fontSize: 11,
                      fontWeight: 900
                    }}
                  />
                  <Bar
                    dataKey="score"
                    fill="var(--info)"
                    radius={[0, 12, 12, 0]}
                    barSize={12}
                    animationDuration={1500}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* 월별 가치 추이 */}
      <Card className="rounded-[4rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-2xl)] overflow-hidden">
        <CardContent className="p-10 lg:p-14">
          <div className="flex items-center justify-between mb-12">
            <div className="space-y-1">
              <p className="text-[10px] font-[1000] uppercase tracking-[0.4em] text-[var(--text-hint)]">VALUATION_TREND</p>
              <CardTitle className="text-3xl font-[1000] tracking-tighter italic text-[var(--text-primary)]">월별 AVM <span className="text-[var(--spot)]">추이.</span></CardTitle>
            </div>
            <div className="flex items-center gap-6">
               <div className="text-right">
                  <p className="text-[8px] font-black text-[var(--text-hint)] uppercase tracking-widest mb-1">CURRENT_VALUATION</p>
                  <p className="text-xl font-[1000] text-[var(--spot)]">{formatKrw(data.avm_estimate_krw)}원</p>
               </div>
            </div>
          </div>
          
          <div className="h-[300px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data.monthly_trend} margin={{ top: 10, right: 10, left: 10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--line-strong)" opacity={0.3} vertical={false} />
                <XAxis 
                  dataKey="month" 
                  tick={{ fontSize: 10, fontWeight: 900, fill: "var(--text-hint)" }} 
                  axisLine={false}
                  tickLine={false}
                  dy={10}
                />
                <YAxis
                  tickFormatter={(v: number) => formatKrw(v)}
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
                  formatter={(v) => [`${formatKrw(Number(v))}원`, "ESTIMATED_VALUE"]}
                />
                <Line
                  type="monotone"
                  dataKey="value"
                  stroke="var(--spot)"
                  strokeWidth={4}
                  dot={{ r: 6, strokeWidth: 3, stroke: "var(--surface-strong)", fill: "var(--spot)" }}
                  activeDot={{ r: 8, strokeWidth: 0 }}
                  animationDuration={2000}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>
    </section>
  );
}
