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
import { apiClient } from "@/lib/api-client";
import type { ESGDashboardData, ESGMetric } from "@/components/cad/types";

const TREND_ICONS: Record<ESGMetric["trend"], string> = {
  up: "\u2191",
  down: "\u2193",
  stable: "\u2192",
};

function getTrendColor(metric: ESGMetric): string {
  // 배출량 등은 down이 좋고, 비율 등은 up이 좋음
  const lowerIsBetter = metric.unit === "tCO2e" || metric.label.includes("사고율");
  if (metric.trend === "stable") return "text-[rgba(19,33,47,0.48)]";
  if (lowerIsBetter) {
    return metric.trend === "down" ? "text-emerald-600" : "text-red-600";
  }
  return metric.trend === "up" ? "text-emerald-600" : "text-red-600";
}

function getTargetStatus(metric: ESGMetric): boolean {
  const lowerIsBetter = metric.unit === "tCO2e" || metric.label.includes("사고율");
  return lowerIsBetter ? metric.value <= metric.target : metric.value >= metric.target;
}

export function ESGDashboard() {
  const { data, isLoading } = useQuery({
    queryKey: ["analytics", "esg"],
    queryFn: () => apiClient.get<ESGDashboardData>("/analytics/esg"),
  });

  if (isLoading) {
    return <SkeletonLoader count={3} itemClassName="h-48" />;
  }

  if (!data) return null;

  return (
    <section className="grid gap-6" aria-label="ESG/Climate 대시보드">
      {/* 종합 점수 + GRESB */}
      <div className="grid gap-4 sm:grid-cols-2">
        <Card className="bg-[var(--surface-strong)]">
          <CardContent className="p-6 text-center">
            <p className="text-xs uppercase tracking-widest text-[rgba(19,33,47,0.56)]">
              ESG 종합 점수
            </p>
            <p className="mt-3 text-5xl font-bold text-[var(--accent)]">
              {data.overall_score.toFixed(1)}
            </p>
            <p className="mt-1 text-sm text-[rgba(19,33,47,0.52)]">/ 100</p>
          </CardContent>
        </Card>
        <Card className="bg-[var(--surface-strong)]">
          <CardContent className="p-6 text-center">
            <p className="text-xs uppercase tracking-widest text-[rgba(19,33,47,0.56)]">
              GRESB 등급
            </p>
            <p className="mt-3 text-5xl font-bold text-[var(--spot)]">
              {data.gresb_rating}
            </p>
            <p className="mt-1 text-sm text-[rgba(19,33,47,0.52)]">
              글로벌 부동산 지속가능성 벤치마크
            </p>
          </CardContent>
        </Card>
      </div>

      {/* KPI 카드 그리드 */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {data.metrics.map((metric) => {
          const met = getTargetStatus(metric);
          return (
            <Card key={metric.id}>
              <CardContent className="p-5">
                <p className="text-xs text-[rgba(19,33,47,0.56)]">
                  {metric.label}
                </p>
                <div className="mt-2 flex items-end gap-2">
                  <span className="text-2xl font-semibold text-[var(--foreground)]">
                    {metric.value.toLocaleString("ko-KR")}
                  </span>
                  {metric.unit && (
                    <span className="mb-0.5 text-sm text-[rgba(19,33,47,0.52)]">
                      {metric.unit}
                    </span>
                  )}
                  <span className={`mb-0.5 text-sm font-medium ${getTrendColor(metric)}`}>
                    {TREND_ICONS[metric.trend]}
                  </span>
                </div>
                <div className="mt-2 flex items-center gap-2">
                  <div className="h-1.5 flex-1 rounded-full bg-[var(--surface-muted)]">
                    <div
                      className={`h-full rounded-full transition-all ${met ? "bg-emerald-500" : "bg-amber-500"}`}
                      style={{
                        width: `${Math.min(100, (metric.value / metric.target) * 100)}%`,
                      }}
                    />
                  </div>
                  <span className="text-[10px] text-[rgba(19,33,47,0.44)]">
                    목표 {metric.target}
                    {metric.unit}
                  </span>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Scope별 탄소 배출 차트 */}
      <Card>
        <CardContent className="p-6">
          <CardTitle className="mb-4 text-lg">Scope별 탄소 배출량</CardTitle>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={data.carbon_by_scope}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(19,33,47,0.06)" />
              <XAxis dataKey="scope" tick={{ fontSize: 12 }} />
              <YAxis
                tick={{ fontSize: 11 }}
                label={{
                  value: "tCO2e",
                  angle: -90,
                  position: "insideLeft",
                  style: { fontSize: 11, fill: "rgba(19,33,47,0.5)" },
                }}
              />
              <Tooltip
                formatter={(v) => [`${v} tCO2e`, "배출량"]}
                contentStyle={{
                  borderRadius: 12,
                  border: "1px solid var(--line)",
                  fontSize: 13,
                }}
              />
              <Bar dataKey="tco2e" fill="#0e7490" radius={[8, 8, 0, 0]} barSize={48} />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
    </section>
  );
}
