"use client";

import { Card, CardContent } from "@propai/ui";

type LawChange = {
  id: string;
  law_name: string;
  change_date: string;
  summary: string;
  affected_codes: string[];
};

const MOCK_CHANGES: LawChange[] = [
  {
    id: "1",
    law_name: "지방세법 시행령",
    change_date: "2026-01-01",
    summary: "취득세 중과세율 조정 (다주택자 12% → 8%)",
    affected_codes: ["A01", "A02"],
  },
  {
    id: "2",
    law_name: "재건축초과이익 환수에 관한 법률",
    change_date: "2025-12-15",
    summary: "초과이익 부과기준금액 상향 (3000만원 → 5000만원)",
    affected_codes: ["D05"],
  },
  {
    id: "3",
    law_name: "개발이익 환수에 관한 법률",
    change_date: "2025-11-01",
    summary: "개발부담금 부과율 조정 (25% → 20%)",
    affected_codes: ["A10"],
  },
];

export function LawChangeMonitor() {
  return (
    <Card className="rounded-[var(--radius-xl)] border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <CardContent className="p-6">
        <h4 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-200">
          법령변경 모니터링
        </h4>
        <div className="space-y-4">
          {MOCK_CHANGES.map((change) => (
            <div
              key={change.id}
              className="relative flex gap-4 pb-4 border-b border-slate-100 dark:border-slate-800 last:border-0"
            >
              <div className="flex flex-col items-center">
                <div className="h-3 w-3 rounded-full bg-amber-400" />
                <div className="w-px flex-1 bg-slate-200 dark:bg-slate-700" />
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-sm font-medium text-slate-900 dark:text-slate-100">
                    {change.law_name}
                  </span>
                  <span className="text-xs text-slate-400">{change.change_date}</span>
                </div>
                <p className="text-sm text-slate-600 dark:text-slate-300">{change.summary}</p>
                <div className="mt-1 flex gap-1">
                  {change.affected_codes.map((code) => (
                    <span
                      key={code}
                      className="inline-block rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-700 dark:bg-amber-900 dark:text-amber-300"
                    >
                      {code}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
