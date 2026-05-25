"use client";

import { useState } from "react";
import { Button } from "@propai/ui";
import { useFeasibilityV2Store } from "@/store/use-feasibility-v2-store";

export function ExcelExportButton() {
  const { result, input, monteCarloResult, recommendations } = useFeasibilityV2Store();
  const [isExporting, setIsExporting] = useState(false);

  const handleExport = async () => {
    if (!result) return;
    setIsExporting(true);

    try {
      const data = {
        summary: {
          module: result.module_name,
          grade: result.grade,
          revenue: result.total_revenue_won,
          cost: result.total_cost_won,
          profit: result.net_profit_won,
          profitRate: result.profit_rate_pct,
          roi: result.roi_pct,
          npv: result.npv_won,
        },
        costBreakdown: result.cost_breakdown_won,
        input,
        taxDetail: result.tax_detail,
        monteCarlo: monteCarloResult,
        recommendations,
      };

      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `feasibility-${result.development_type}-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <Button
      variant={"outline" as any} // eslint-disable-line @typescript-eslint/no-explicit-any
      size="sm"
      onClick={handleExport}
      disabled={!result || isExporting}
    >
      {isExporting ? "내보내기 중..." : "내보내기"}
    </Button>
  );
}
