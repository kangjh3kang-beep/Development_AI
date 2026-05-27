"use client";

import { useEffect, useState } from "react";
import { Card, CardContent } from "@propai/ui";

type MatrixEntry = {
  development_type: string;
  applicable_codes: string[];
  count: number;
};

const MODULE_LABELS: Record<string, string> = {
  M01: "재개발", M02: "재건축", M03: "역세권", M04: "주택조합",
  M05: "임대협동", M06: "일반분양", M07: "주상복합", M08: "오피스텔",
  M09: "지산센터", M10: "단독주택", M11: "전원주택", M12: "타운하우스",
  M13: "도시형", M14: "공공임대", M15: "민간리츠",
};

export function DevTypeTaxMatrix() {
  const [matrix, setMatrix] = useState<MatrixEntry[]>([]);

  useEffect(() => {
    const localMatrix: MatrixEntry[] = [
      { development_type: "M01", applicable_codes: ["ACQ", "REG", "VAT"], count: 3 },
      { development_type: "M02", applicable_codes: ["ACQ", "REG", "PROP", "CGT"], count: 4 },
      { development_type: "M03", applicable_codes: ["ACQ", "REG"], count: 2 },
      { development_type: "M06", applicable_codes: ["ACQ", "REG", "PROP", "CGT", "COMP"], count: 5 },
      { development_type: "M07", applicable_codes: ["ACQ", "REG", "PROP", "CGT"], count: 4 },
      { development_type: "M08", applicable_codes: ["ACQ", "REG", "PROP"], count: 3 },
    ];
    setMatrix(localMatrix);
  }, []);

  if (matrix.length === 0) {
    return (
      <Card className="rounded-[var(--radius-xl)] border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <CardContent className="p-6 text-center text-sm text-slate-500">
          매트릭스 데이터를 불러오는 중...
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="rounded-[var(--radius-xl)] border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <CardContent className="p-6">
        <h4 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-200">
          개발유형별 세금 매트릭스
        </h4>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-700">
                <th className="px-3 py-2 text-left font-medium text-slate-500">유형</th>
                <th className="px-3 py-2 text-left font-medium text-slate-500">명칭</th>
                <th className="px-3 py-2 text-center font-medium text-slate-500">세금 수</th>
                <th className="px-3 py-2 text-left font-medium text-slate-500">적용 코드</th>
              </tr>
            </thead>
            <tbody>
              {matrix.map((entry) => (
                <tr key={entry.development_type} className="border-b border-slate-100 dark:border-slate-800">
                  <td className="px-3 py-2 font-mono text-xs text-blue-600 dark:text-blue-400">
                    {entry.development_type}
                  </td>
                  <td className="px-3 py-2 text-slate-900 dark:text-slate-100">
                    {MODULE_LABELS[entry.development_type] ?? entry.development_type}
                  </td>
                  <td className="px-3 py-2 text-center font-medium">{entry.count}</td>
                  <td className="px-3 py-2">
                    <div className="flex flex-wrap gap-1">
                      {entry.applicable_codes.slice(0, 10).map((code) => (
                        <span key={code} className="inline-block rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-400">
                          {code}
                        </span>
                      ))}
                      {entry.applicable_codes.length > 10 && (
                        <span className="text-xs text-slate-400">
                          +{entry.applicable_codes.length - 10}
                        </span>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
