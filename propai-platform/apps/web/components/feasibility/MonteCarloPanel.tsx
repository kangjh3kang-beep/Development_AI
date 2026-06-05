"use client";

import { useState } from "react";
import { Button, Card, CardContent, Input } from "@propai/ui";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useFeasibilityV2Store } from "@/store/use-feasibility-v2-store";
import { NumberInput } from "@/components/common/NumberInput";

const DEFAULT_VARIABLES = [
  { name: "revenue", mean: 1000, std: 100 },
  { name: "cost", mean: 800, std: 50 },
  { name: "land_price", mean: 500, std: 80 },
  { name: "interest_rate", mean: 5, std: 1 },
  { name: "sale_ratio", mean: 95, std: 5 },
];

function formatWon(value: number): string {
  if (Math.abs(value) >= 1e8) return `${(value / 1e8).toFixed(0)}억`;
  if (Math.abs(value) >= 1e4) return `${(value / 1e4).toFixed(0)}만`;
  return value.toLocaleString();
}

export function MonteCarloPanel() {
  const { monteCarloResult, runMonteCarlo, isCalculating } = useFeasibilityV2Store();
  const [variables, setVariables] = useState(DEFAULT_VARIABLES);
  const [nSim, setNSim] = useState(10000);

  const updateVar = (index: number, field: string, value: number) => {
    setVariables((prev) =>
      prev.map((v, i) => (i === index ? { ...v, [field]: value } : v))
    );
  };

  return (
    <div className="space-y-6">
      {/* 입력 */}
      <Card className="rounded-[var(--radius-xl)] border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <CardContent className="p-6">
          <h4 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-200">
            시뮬레이션 변수 설정
          </h4>
          <div className="space-y-3">
            {variables.map((v, i) => (
              <div key={v.name} className="grid grid-cols-4 gap-3 items-end">
                <label className="text-sm">
                  <span className="text-xs text-slate-500">변수명</span>
                  <Input value={v.name} disabled className="mt-1" />
                </label>
                <label className="text-sm">
                  <span className="text-xs text-slate-500">평균</span>
                  <Input
                    type="number"
                    value={v.mean}
                    onChange={(e) => updateVar(i, "mean", Number(e.target.value))}
                    className="mt-1"
                  />
                </label>
                <label className="text-sm">
                  <span className="text-xs text-slate-500">표준편차</span>
                  <Input
                    type="number"
                    value={v.std}
                    onChange={(e) => updateVar(i, "std", Number(e.target.value))}
                    className="mt-1"
                  />
                </label>
                <div />
              </div>
            ))}
          </div>
          <div className="mt-4 flex items-center gap-4">
            <label className="text-sm">
              <span className="text-xs text-slate-500">시뮬레이션 횟수</span>
              <NumberInput
                value={nSim}
                onChange={(n) => setNSim(n ?? 0)}
                className="mt-1 w-32 flex h-11 rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
              />
            </label>
            <Button
              onClick={() => runMonteCarlo(variables, nSim)}
              disabled={isCalculating}
              className="mt-auto"
            >
              {isCalculating ? "실행 중..." : "몬테카를로 실행"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* 결과 */}
      {monteCarloResult && (
        <>
          <div className="grid gap-4 md:grid-cols-4">
            {[
              { label: "평균 NPV", value: formatWon(monteCarloResult.mean) },
              { label: "양수 확률", value: `${(monteCarloResult.probability_positive * 100).toFixed(1)}%` },
              { label: "P5/P95", value: `${formatWon(monteCarloResult.p5)} ~ ${formatWon(monteCarloResult.p95)}` },
              { label: "수렴비율", value: `${(monteCarloResult.convergence_ratio * 100).toFixed(2)}%` },
            ].map((stat) => (
              <Card key={stat.label} className="rounded-[var(--radius-xl)] border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
                <CardContent className="p-4">
                  <p className="text-xs text-slate-500 dark:text-slate-400">{stat.label}</p>
                  <p className="mt-1 text-lg font-bold text-slate-900 dark:text-slate-100">{stat.value}</p>
                </CardContent>
              </Card>
            ))}
          </div>

          {/* 히스토그램 */}
          <Card className="rounded-[var(--radius-xl)] border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
            <CardContent className="p-6">
              <h4 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-200">
                NPV 분포 히스토그램 ({monteCarloResult.n_simulations.toLocaleString()}회)
              </h4>
              <div className="h-[300px]">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={monteCarloResult.histogram}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#cbd5e1" />
                    <XAxis
                      dataKey="bin_start"
                      tickFormatter={(v: number | string) => formatWon(Number(v))}
                      stroke="#64748b"
                      fontSize={11}
                    />
                    <YAxis stroke="#64748b" />
                    <Tooltip
                      formatter={(v) => [Number(v ?? 0), "빈도"]}
                      labelFormatter={(v) => `구간: ${formatWon(Number(v ?? 0))}`}
                    />
                    <Bar dataKey="count" fill="#3b82f6" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
