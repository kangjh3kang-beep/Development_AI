"use client";

import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { KpiGrid } from "@/components/dashboard/DashboardDynamicElements";

// 백엔드 /dashboard/overview 실제 응답 필드(가짜 폴백·트렌드 제거)
type DashboardOverviewApi = {
  total_projects?: number;
  active_projects?: number;
  total_investment_billion?: number;
  avg_roi_pct?: number;
  carbon_reduction_pct?: number;
  portfolio_count?: number;
};

type DashboardKpi = {
  total_assets: number;
  avg_roi: number;
  carbon_reduction: number;
  total_projects: number;
  has_carbon: boolean;
};

const num = (v: unknown): number => (typeof v === "number" && Number.isFinite(v) ? v : 0);

const ZERO: DashboardKpi = {
  total_assets: 0, avg_roi: 0, carbon_reduction: 0, total_projects: 0, has_carbon: false,
};

export function DashboardKpiLoader() {
  const [data, setData] = useState<DashboardKpi | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function fetchOverview() {
      try {
        const res = await apiClient.get<DashboardOverviewApi>("/dashboard/overview");
        if (!cancelled) {
          setData({
            total_assets: num(res.total_investment_billion),
            avg_roi: num(res.avg_roi_pct),
            carbon_reduction: num(res.carbon_reduction_pct),
            total_projects: num(res.total_projects),
            has_carbon: typeof res.carbon_reduction_pct === "number",
          });
        }
      } catch {
        if (!cancelled) setData(ZERO);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchOverview();
    return () => { cancelled = true; };
  }, []);

  if (loading) {
    return (
      <div className="grid gap-8 md:grid-cols-3">
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            className="h-[160px] animate-pulse rounded-[var(--radius-xl)] bg-[var(--surface-soft)] border border-[var(--line)]"
          />
        ))}
      </div>
    );
  }

  const d = data ?? ZERO;

  return (
    <KpiGrid
      items={[
        {
          label: "전체 포트폴리오 자산(추정 총사업비)",
          value: d.total_assets,
          decimals: 1,
          unit: "B",
          trend: "",
          sub: `프로젝트 ${d.total_projects}건 합산`,
          color: "text-[var(--chart-1)]",
          bg: "bg-[var(--chart-1)]/5",
          border: "border-[var(--chart-1)]/20",
        },
        {
          label: "평균 프로젝트 ROI",
          value: d.avg_roi,
          decimals: 1,
          unit: "%",
          trend: "",
          sub: "수지분석 완료 프로젝트 평균",
          color: "text-[var(--status-info)]",
          bg: "bg-[var(--status-info)]/5",
          border: "border-[var(--status-info)]/20",
        },
        {
          label: "탄소 배출 절감률",
          value: d.carbon_reduction,
          decimals: 1,
          unit: "%",
          trend: "",
          sub: d.has_carbon ? "전과정평가 (LCA) 기반" : "LCA 분석 데이터 없음",
          color: "text-[var(--status-success)]",
          bg: "bg-[var(--status-success)]/5",
          border: "border-[var(--status-success)]/20",
        },
      ]}
    />
  );
}
