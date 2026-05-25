"use client";

import { useState } from "react";
import { Button, Card, CardContent, Input } from "@propai/ui";
import { apiClient } from "@/lib/api-client";

type RegionResult = {
  sido_name: string;
  base_acquisition_rate: number;
  sigungu_overrides: Array<{
    sigungu_name: string;
    override_rate?: number;
    metro_transport_charge?: number;
  }>;
};

function pctFormat(rate: number): string {
  return `${(rate * 100).toFixed(2)}%`;
}

export function RegionTaxSearchPanel() {
  const [sido, setSido] = useState("서울");
  const [result, setResult] = useState<RegionResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleSearch = async () => {
    setIsLoading(true);
    try {
      const data = await apiClient.getV2<RegionResult>(`/tax/regions/${encodeURIComponent(sido)}`);
      setResult(data);
    } catch {
      setResult(null);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Card className="rounded-[var(--radius-xl)] border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <CardContent className="p-6">
        <h4 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-200">
          지역별 세율 조회
        </h4>
        <div className="flex gap-3 mb-4">
          <Input
            value={sido}
            onChange={(e) => setSido(e.target.value)}
            placeholder="시/도 입력 (예: 서울, 경기)"
            className="max-w-xs"
          />
          <Button onClick={handleSearch} disabled={isLoading}>
            {isLoading ? "조회 중..." : "조회"}
          </Button>
        </div>

        {result && (
          <div className="space-y-3">
            <div className="flex items-center gap-4 text-sm">
              <span className="font-medium text-slate-900 dark:text-slate-100">{result.sido_name}</span>
              <span className="text-slate-500">
                기본 취득세율: {pctFormat(result.base_acquisition_rate)}
              </span>
            </div>
            {result.sigungu_overrides.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 dark:border-slate-700">
                      <th className="px-3 py-2 text-left font-medium text-slate-500">시군구</th>
                      <th className="px-3 py-2 text-right font-medium text-slate-500">취득세율 오버라이드</th>
                      <th className="px-3 py-2 text-right font-medium text-slate-500">광역교통부담금</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.sigungu_overrides.map((o) => (
                      <tr key={o.sigungu_name} className="border-b border-slate-100 dark:border-slate-800">
                        <td className="px-3 py-2 text-slate-900 dark:text-slate-100">{o.sigungu_name}</td>
                        <td className="px-3 py-2 text-right">
                          {o.override_rate != null ? pctFormat(o.override_rate) : "-"}
                        </td>
                        <td className="px-3 py-2 text-right">
                          {o.metro_transport_charge != null
                            ? `${(o.metro_transport_charge / 10000).toFixed(1)}만원/세대`
                            : "-"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
