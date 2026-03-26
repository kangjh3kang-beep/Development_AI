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
import { apiClient } from "@/lib/api-client";
import type { InvestmentMetrics } from "@/components/cad/types";

function formatKrw(value: number) {
  if (value >= 1_0000_0000) {
    return `${(value / 1_0000_0000).toFixed(0)}억`;
  }
  if (value >= 1_0000) {
    return `${(value / 1_0000).toFixed(0)}만`;
  }
  return value.toLocaleString("ko-KR");
}

export function InvestmentDashboard() {
  const { data, isLoading } = useQuery({
    queryKey: ["analytics", "investment"],
    queryFn: () => apiClient.get<InvestmentMetrics>("/analytics/investment"),
  });

  if (isLoading) {
    return <SkeletonLoader count={4} itemClassName="h-48" />;
  }

  if (!data) return null;

  return (
    <section className="grid gap-6" aria-label="투자 분석 대시보드">
      {/* KPI 카드 */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          label="AVM 감정가"
          value={`${formatKrw(data.avm_estimate_krw)}원`}
          sub={`신뢰도 ${(data.avm_confidence * 100).toFixed(0)}%`}
        />
        <KpiCard
          label="IRR"
          value={`${data.irr_percent.toFixed(1)}%`}
          sub="내부수익률"
        />
        <KpiCard
          label="Cap Rate"
          value={`${data.cap_rate_percent.toFixed(1)}%`}
          sub="자본환원율"
        />
        <KpiCard
          label="NOI"
          value={`${formatKrw(data.noi_krw)}원`}
          sub="순운영소득 (연)"
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* 16특성 레이더 차트 */}
        <Card>
          <CardContent className="p-6">
            <CardTitle className="mb-4 text-lg">16대 투자 특성 분석</CardTitle>
            <ResponsiveContainer width="100%" height={360}>
              <RadarChart data={data.features} outerRadius="72%">
                <PolarGrid stroke="rgba(19,33,47,0.08)" />
                <PolarAngleAxis
                  dataKey="feature"
                  tick={{ fontSize: 11, fill: "rgba(19,33,47,0.64)" }}
                />
                <PolarRadiusAxis
                  angle={90}
                  domain={[0, 100]}
                  tick={{ fontSize: 10, fill: "rgba(19,33,47,0.4)" }}
                />
                <Radar
                  name="점수"
                  dataKey="score"
                  stroke="#0e7490"
                  fill="rgba(14,116,144,0.22)"
                  strokeWidth={2}
                />
                <Tooltip
                  contentStyle={{
                    borderRadius: 12,
                    border: "1px solid var(--line)",
                    fontSize: 13,
                  }}
                />
              </RadarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* 특성별 막대 차트 */}
        <Card>
          <CardContent className="p-6">
            <CardTitle className="mb-4 text-lg">특성별 점수 비교</CardTitle>
            <ResponsiveContainer width="100%" height={360}>
              <BarChart
                data={data.features}
                layout="vertical"
                margin={{ left: 60, right: 16 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(19,33,47,0.06)" />
                <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 11 }} />
                <YAxis
                  type="category"
                  dataKey="feature"
                  tick={{ fontSize: 11, fill: "rgba(19,33,47,0.64)" }}
                  width={56}
                />
                <Tooltip
                  contentStyle={{
                    borderRadius: 12,
                    border: "1px solid var(--line)",
                    fontSize: 13,
                  }}
                />
                <Bar
                  dataKey="score"
                  fill="#0e7490"
                  radius={[0, 6, 6, 0]}
                  barSize={14}
                />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      {/* 월별 가치 추이 */}
      <Card>
        <CardContent className="p-6">
          <CardTitle className="mb-4 text-lg">월별 AVM 추이</CardTitle>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={data.monthly_trend}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(19,33,47,0.06)" />
              <XAxis dataKey="month" tick={{ fontSize: 11 }} />
              <YAxis
                tickFormatter={(v: number) => formatKrw(v)}
                tick={{ fontSize: 11 }}
              />
              <Tooltip
                formatter={(v) => [`${formatKrw(Number(v))}원`, "감정가"]}
                contentStyle={{
                  borderRadius: 12,
                  border: "1px solid var(--line)",
                  fontSize: 13,
                }}
              />
              <Line
                type="monotone"
                dataKey="value"
                stroke="#d97706"
                strokeWidth={2}
                dot={{ r: 4, fill: "#d97706" }}
              />
            </LineChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
    </section>
  );
}

function KpiCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub: string;
}) {
  return (
    <Card className="bg-[var(--surface-strong)]">
      <CardContent className="p-5">
        <p className="text-xs uppercase tracking-widest text-[rgba(19,33,47,0.56)]">
          {label}
        </p>
        <p className="mt-2 text-2xl font-semibold text-[var(--foreground)]">
          {value}
        </p>
        <p className="mt-1 text-xs text-[rgba(19,33,47,0.52)]">{sub}</p>
      </CardContent>
    </Card>
  );
}
