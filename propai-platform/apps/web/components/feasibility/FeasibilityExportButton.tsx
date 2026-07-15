"use client";

import { useState } from "react";
import { Button } from "@propai/ui";
import { useFeasibilityV2Store } from "@/store/use-feasibility-v2-store";

/**
 * 수지분석 결과 원본 데이터(JSON) 내보내기.
 *
 * 이름 이력: 기존 `ExcelExportButton` 이었으나 실제 산출물은 엑셀도 CSV도 아닌
 * `application/json` 이었다(이름과 실제가 불일치). 데이터가 중첩 구조라
 * (summary/costBreakdown/input/taxDetail/monteCarlo/recommendations)
 * 표로 평탄화하려면 백엔드에 없는 표 구조를 발명해야 하므로,
 * 산출물을 바꾸지 않고 이름·라벨을 실제에 맞췄다.
 *
 * 표 형태(CSV)가 필요해지면 DESIGN.md B5.2 계약을 따른다:
 * 한글 BOM + CRLF + 파일명에 프로젝트·시나리오 포함.
 * (현재 앱 전체 CSV 내보내기 0건 — 도입 시 공용 헬퍼부터 만들 것.)
 */
export function FeasibilityExportButton() {
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
      variant={"outline" as any}
      size="sm"
      onClick={handleExport}
      disabled={!result || isExporting}
    >
      {isExporting ? "내보내기 중..." : "JSON 내보내기"}
    </Button>
  );
}
