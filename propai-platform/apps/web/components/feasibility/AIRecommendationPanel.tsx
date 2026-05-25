"use client";

import { useEffect } from "react";
import { Card, CardContent, Badge } from "@propai/ui";
import { useFeasibilityV2Store } from "@/store/use-feasibility-v2-store";

const SEVERITY_STYLES: Record<string, string> = {
  critical: "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300",
  warning: "bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300",
  info: "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300",
};

export function AIRecommendationPanel() {
  const { recommendations, fetchRecommendations, result } = useFeasibilityV2Store();

  useEffect(() => {
    if (result) {
      fetchRecommendations();
    }
  }, [result, fetchRecommendations]);

  if (!result) return null;

  return (
    <Card className="rounded-[var(--radius-xl)] border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <CardContent className="p-6">
        <h4 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-200">
          AI 진단 권고
        </h4>
        {recommendations.length === 0 ? (
          <p className="text-sm text-slate-500 dark:text-slate-400">
            모든 지표가 정상 범위입니다.
          </p>
        ) : (
          <div className="space-y-3">
            {recommendations.map((rec) => (
              <div
                key={rec.rule_code}
                className="rounded-xl border border-slate-200 p-4 dark:border-slate-700"
              >
                <div className="flex items-center gap-2 mb-2">
                  <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${SEVERITY_STYLES[rec.severity] ?? SEVERITY_STYLES.info}`}>
                    {rec.severity === "critical" ? "위험" : rec.severity === "warning" ? "주의" : "정보"}
                  </span>
                  <span className="text-xs font-mono text-slate-400">{rec.rule_code}</span>
                  <span className="text-sm font-medium text-slate-900 dark:text-slate-100">
                    {rec.rule_name}
                  </span>
                </div>
                <p className="text-sm text-slate-600 dark:text-slate-300">{rec.message}</p>
                <p className="mt-1 text-sm text-blue-600 dark:text-blue-400">{rec.suggestion}</p>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
