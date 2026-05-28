"use client";

import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { KpiGrid } from "@/components/dashboard/DashboardDynamicElements";

type DashboardOverview = {
  total_assets: number;
  avg_roi: number;
  carbon_reduction: number;
  total_assets_trend?: string;
  avg_roi_trend?: string;
  carbon_reduction_trend?: string;
};

const FALLBACK: DashboardOverview = {
  total_assets: 3500.2,
  avg_roi: 18.4,
  carbon_reduction: 24.9,
  total_assets_trend: "+12.5%",
  avg_roi_trend: "+2.1%",
  carbon_reduction_trend: "-1.5%",
};

export function DashboardKpiLoader() {
  const [data, setData] = useState<DashboardOverview | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function fetchOverview() {
      try {
        const res = await apiClient.get<DashboardOverview>("/dashboard/overview");
        if (!cancelled) setData(res);
      } catch {
        if (!cancelled) setData(FALLBACK);
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
            className="h-[160px] animate-pulse rounded-[2.5rem] bg-[var(--surface-soft)] border border-[var(--line)]"
          />
        ))}
      </div>
    );
  }

  const d = data ?? FALLBACK;

  return (
    <KpiGrid
      items={[
        {
          label: "전체 포트폴리오 자산",
          value: d.total_assets,
          decimals: 1,
          unit: "B",
          trend: d.total_assets_trend ?? "+12.5%",
          sub: "Total Assets Under Management",
          color: "text-[var(--chart-1)]",
          bg: "bg-[var(--chart-1)]/5",
          border: "border-[var(--chart-1)]/20",
        },
        {
          label: "평균 프로젝트 ROI",
          value: d.avg_roi,
          decimals: 1,
          unit: "%",
          trend: d.avg_roi_trend ?? "+2.1%",
          sub: "12개 주요 프로젝트 기준",
          color: "text-[var(--status-info)]",
          bg: "bg-[var(--status-info)]/5",
          border: "border-[var(--status-info)]/20",
        },
        {
          label: "탄소 배출 절감률",
          value: d.carbon_reduction,
          decimals: 1,
          unit: "%",
          trend: d.carbon_reduction_trend ?? "-1.5%",
          sub: "전과정평가 (LCA) 기반",
          color: "text-[var(--status-success)]",
          bg: "bg-[var(--status-success)]/5",
          border: "border-[var(--status-success)]/20",
        },
      ]}
    />
  );
}
