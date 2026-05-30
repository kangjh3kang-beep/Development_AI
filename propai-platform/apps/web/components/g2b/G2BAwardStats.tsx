"use client";

import { useState, useEffect, useCallback } from "react";
import { apiClient } from "@/lib/api-client";

type AwardStat = {
  stat_period: string;
  bid_type: string;
  region_sido: string | null;
  avg_award_rate: number | null;
  min_award_rate: number | null;
  max_award_rate: number | null;
  bid_count: number;
  avg_competition_ratio: number | null;
};
type AwardStatsResponse = { items: AwardStat[]; total: number };

/**
 * 지역·공종별 낙찰가율 시장동향 패널.
 * 백엔드 GET /g2b/awards/stats 를 호출해 공공사업 낙찰 트렌드를 보여준다.
 */
export function G2BAwardStats({
  bidType,
  regionSido,
}: {
  bidType?: string;
  regionSido?: string;
}) {
  const [stats, setStats] = useState<AwardStat[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (bidType) params.set("bid_type", bidType);
      if (regionSido) params.set("region_sido", regionSido);
      const qs = params.toString();
      const data = await apiClient.get<AwardStatsResponse>(
        `/g2b/awards/stats${qs ? `?${qs}` : ""}`,
      );
      setStats(data.items || []);
    } catch {
      setStats([]);
    } finally {
      setLoading(false);
    }
  }, [bidType, regionSido]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return <div className="text-sm text-[var(--text-hint)] py-4">낙찰 통계 로딩 중…</div>;
  }
  if (stats.length === 0) {
    return (
      <div className="text-sm text-[var(--text-hint)] py-4">
        집계된 낙찰 통계가 없습니다. (낙찰 데이터 수집·집계 후 표시)
      </div>
    );
  }

  const maxRate = Math.max(...stats.map((s) => s.avg_award_rate || 0), 1);

  return (
    <div className="rounded-2xl border border-[var(--border)] p-4">
      <h3 className="text-sm font-black text-[var(--text-primary)] mb-3">
        낙찰가율 시장동향 {regionSido ? `· ${regionSido}` : ""} {bidType ? `· ${bidType}` : ""}
      </h3>
      <div className="space-y-2">
        {stats.map((s, i) => (
          <div key={i} className="flex items-center gap-3">
            <span className="text-xs text-[var(--text-secondary)] w-16 shrink-0">
              {s.stat_period}
            </span>
            <div className="flex-1 h-3 rounded-full bg-[var(--surface-muted)]">
              <div
                className="h-3 rounded-full bg-[var(--accent-strong)]"
                style={{ width: `${((s.avg_award_rate || 0) / maxRate) * 100}%` }}
              />
            </div>
            <span className="text-xs font-bold text-[var(--text-primary)] w-14 text-right">
              {s.avg_award_rate != null ? `${s.avg_award_rate.toFixed(1)}%` : "-"}
            </span>
            <span className="text-[10px] text-[var(--text-hint)] w-12 text-right">
              {s.bid_count}건
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default G2BAwardStats;
