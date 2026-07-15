"use client";

import { useState } from "react";
import { Button } from "@propai/ui";
import { resolveApiOrigin } from "@/lib/api-client";
import { useFeasibilityV2Store } from "@/store/use-feasibility-v2-store";

/**
 * 수지분석 결과 내보내기 — Excel(백엔드 산출) + 원본 데이터(JSON).
 *
 * 이름 이력: 기존 `ExcelExportButton` 이었으나 실제 산출물은 엑셀도 CSV도 아닌
 * `application/json` 이었다(이름과 실제가 불일치 — PR#281에서 이름·라벨 정직화).
 *
 * ★P4(2026-07-15 감사): 백엔드에 진짜 수지분석표 Excel 엔진
 * (POST /api/v2/feasibility/export-excel — ExcelExportService.feasibility_to_xlsx)이
 * 있었으나 어떤 프론트도 호출하지 않는 고아였다. 현재 폼 입력(store.input)을 그대로
 * 보내 서버가 재계산·표 구성한 .xlsx를 내려받는 버튼을 배선한다(표 구조 발명 없음 —
 * 표 형태는 백엔드 산출물이 정본). JSON 내보내기는 원본 데이터 용도로 유지.
 */
export function FeasibilityExportButton() {
  const { result, input, monteCarloResult, recommendations } = useFeasibilityV2Store();
  const [exporting, setExporting] = useState<"" | "xlsx" | "json">("");
  const [excelError, setExcelError] = useState<string | null>(null);

  // ★리뷰 R1-P2: 백엔드 FeasibilityCalculateRequest는 면적·GFA가 gt=0 필수 —
  //   auto-baseline(부지 미완입력) 상태의 result로 버튼이 활성되면 422가 난다.
  //   유효 입력일 때만 Excel 활성(정직 고지 — riskNote 계약과 동일 패턴).
  const canExcel =
    !!result && !result.is_baseline
    && (input.total_land_area_sqm ?? 0) > 0 && (input.total_gfa_sqm ?? 0) > 0;

  const handleExcelExport = async () => {
    if (!result) return;
    setExporting("xlsx");
    setExcelError(null);
    try {
      // /feasibility/calculate와 동일 계약(FeasibilityCalculateRequest) — store.input 그대로.
      const token =
        (typeof window !== "undefined" && localStorage.getItem("propai_access_token")?.trim()) || "";
      // 직접 fetch(blob 다운로드 — apiClient.parseResponse는 바이너리를 손상시킴)에도
      // apiClient 기본과 동일한 120s 타임아웃을 건다(무응답 시 버튼 영구 고착 방지).
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 120_000);
      let res: Response;
      try {
        res = await fetch(`${resolveApiOrigin()}/api/v2/feasibility/export-excel`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({ ...input, params: input.params ?? {} }),
          signal: controller.signal,
        });
      } finally {
        clearTimeout(timeout);
      }
      if (!res.ok) throw new Error(`Excel 내보내기 실패 (${res.status})`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `feasibility-${result.development_type}-${new Date().toISOString().slice(0, 10)}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setExcelError(e instanceof Error ? e.message : "Excel 내보내기 실패");
    } finally {
      setExporting("");
    }
  };

  const handleJsonExport = () => {
    if (!result) return;
    setExporting("json");

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
      setExporting("");
    }
  };

  return (
    <span className="inline-flex items-center gap-2">
      <span title={canExcel ? undefined : "정식 수지 계산(면적·연면적 입력) 후 활성화됩니다"}>
        <Button
          variant={"outline" as any}
          size="sm"
          onClick={handleExcelExport}
          disabled={!canExcel || exporting !== ""}
        >
          {exporting === "xlsx" ? "Excel 생성 중..." : "Excel 내보내기"}
        </Button>
      </span>
      <Button
        variant={"outline" as any}
        size="sm"
        onClick={handleJsonExport}
        disabled={!result || exporting !== ""}
      >
        {exporting === "json" ? "내보내기 중..." : "JSON 내보내기"}
      </Button>
      {excelError && (
        <span className="text-[11px] text-[var(--status-error,#ef4444)]">{excelError}</span>
      )}
    </span>
  );
}
