"use client";

import { useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Button, Card, CardContent, CardTitle } from "@propai/ui";

type CostResult = {
  total_project_cost: number;
  direct_material_cost: number;
  direct_labor_cost: number;
  direct_expense_cost: number;
  net_construction_cost: number;
  vat: number;
  category_totals: Record<string, number>;
  applied_rates: Record<string, number>;
  [key: string]: unknown;
};

type MCResult = {
  p10: number;
  p50: number;
  p80: number;
  p90: number;
  mean: number;
  cv: number;
  converged: boolean;
  risk_contributions: Record<string, number>;
};

type Rate = {
  year: number;
  rates: Record<string, number>;
  pension_note: string;
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

function fmt(n: number): string {
  return new Intl.NumberFormat("ko-KR").format(Math.round(n));
}

export default function BimCostDashboard({ projectId }: { projectId: string }) {
  const [costResult, setCostResult] = useState<CostResult | null>(null);
  const [mcResult, setMcResult] = useState<MCResult | null>(null);
  const [rates, setRates] = useState<Rate | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchRates = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/rates/current`);
      if (res.ok) setRates(await res.json());
    } catch {
      /* silent */
    }
  }, []);

  const handleCalculate = useCallback(async () => {
    setLoading(true);
    try {
      const items = [
        {
          work_code: "A01", item_name: "철근콘크리트", spec: "25-240",
          unit: "m3", quantity: 2000, mat_unit: 82000,
          labor_unit: 45000, exp_unit: 15000,
        },
        {
          work_code: "A05", item_name: "창호", spec: "AL 시스템",
          unit: "set", quantity: 500, mat_unit: 350000,
          labor_unit: 80000, exp_unit: 20000,
        },
      ];

      const calcRes = await fetch(
        `${API_BASE}/api/v1/cost/${projectId}/calculate`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ items }),
        },
      );
      if (calcRes.ok) {
        const data = await calcRes.json();
        setCostResult(data);

        const mcRes = await fetch(
          `${API_BASE}/api/v1/cost/${projectId}/monte-carlo`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              base_result: data,
              iterations: 5000,
              seed: 42,
            }),
          },
        );
        if (mcRes.ok) setMcResult(await mcRes.json());
      }
    } catch {
      /* silent */
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  return (
    <div className="grid gap-8">
      {/* Simulation Control Header */}
      <Card className="border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-xl)] overflow-hidden">
        <div className="bg-[var(--surface-soft)] p-6 border-b border-[var(--line)] flex items-center justify-between">
           <CardTitle className="text-[12px] font-black uppercase tracking-[0.3em] text-[var(--text-primary)]">
             BIM 기반 공사비 시뮬레이션 & 리스크 분석
           </CardTitle>
           <div className="flex gap-4">
              <Button
                variant="outline"
                onClick={fetchRates}
                className="h-10 border-[var(--line)] text-[11px] font-black uppercase tracking-widest text-[var(--text-secondary)]"
              >
                법정요율 조회
              </Button>
              <Button
                onClick={handleCalculate}
                disabled={loading}
                className="h-10 bg-[var(--accent)] hover:bg-[var(--accent-strong)] text-white text-[11px] font-black uppercase tracking-widest shadow-[var(--shadow-glow)]"
              >
                {loading ? "CALCULATING..." : "공사비 정밀 분석 실행"}
              </Button>
           </div>
        </div>
        
        <AnimatePresence>
          {rates && (
            <motion.div 
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="bg-[var(--surface-soft)]/50 border-b border-[var(--line)] px-8 py-6"
            >
              <div className="flex items-center gap-4 mb-4">
                <span className="w-2 h-2 rounded-full bg-[var(--warning)] animate-pulse" />
                <p className="text-[11px] font-black uppercase tracking-widest text-[var(--text-primary)]">
                  {rates.year}년 국가 법정 요율 데이터 (12종 반영됨)
                </p>
              </div>
              <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
                {Object.entries(rates.rates).map(([key, val]) => (
                  <div key={key} className="bg-[var(--surface-strong)] border border-[var(--line-strong)] rounded-xl p-3 flex flex-col items-center justify-center">
                    <p className="text-[9px] font-black text-[var(--text-tertiary)] uppercase">{key}</p>
                    <p className="mt-1 text-[13px] font-[1000] text-[var(--text-primary)]">
                      {(Number(val) * 100).toFixed(2)}%
                    </p>
                  </div>
                ))}
              </div>
              <p className="mt-4 text-[10px] font-bold text-[var(--text-hint)] italic">{rates.pension_note}</p>
            </motion.div>
          )}
        </AnimatePresence>
      </Card>

      <div className="grid gap-8 lg:grid-cols-2">
        {/* Core Financial Results */}
        <AnimatePresence>
          {costResult && (
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              className="space-y-6"
            >
              <Card className="border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-2xl)]">
                <div className="bg-[var(--surface-soft)] p-6 border-b border-[var(--line)]">
                  <p className="text-[10px] font-black text-[var(--text-tertiary)] uppercase tracking-[0.2em]">원가계산서 요약 (Summary)</p>
                </div>
                <CardContent className="p-8">
                  <div className="grid grid-cols-2 gap-6">
                    <KPI 
                      label="총 공사비 (TOTAL)" 
                      value={fmt(costResult.total_project_cost)} 
                      unit="KRW" 
                      highlight 
                    />
                    <KPI 
                      label="순공사원가" 
                      value={fmt(costResult.net_construction_cost)} 
                      unit="KRW" 
                    />
                    <KPI 
                      label="직접재료비" 
                      value={fmt(costResult.direct_material_cost)} 
                      unit="KRW" 
                    />
                    <KPI 
                      label="직접노무비" 
                      value={fmt(costResult.direct_labor_cost)} 
                      unit="KRW" 
                    />
                    <KPI 
                      label="직접경비" 
                      value={fmt(costResult.direct_expense_cost)} 
                      unit="KRW" 
                    />
                    <KPI 
                      label="부가가치세 (VAT)" 
                      value={fmt(costResult.vat)} 
                      unit="KRW" 
                    />
                  </div>

                  {/* Progressive Cost Breakdown */}
                  {costResult.category_totals && (
                    <div className="mt-10 pt-8 border-t border-[var(--line)]">
                      <p className="text-[10px] font-black text-[var(--text-tertiary)] uppercase tracking-widest mb-6">공종별 직접비 분포 (Direct Cost Distribution)</p>
                      <div className="space-y-4">
                        {Object.entries(costResult.category_totals).map(([cat, amt]) => {
                          const total = Object.values(costResult.category_totals).reduce((s, v) => s + v, 0);
                          const pct = total > 0 ? (amt / total) * 100 : 0;
                          return (
                            <div key={cat} className="group">
                              <div className="flex justify-between items-center mb-2">
                                <span className="text-[11px] font-black text-[var(--text-secondary)] uppercase tracking-wider">{cat}</span>
                                <span className="text-[11px] font-[1000] text-[var(--text-primary)]">{fmt(amt)} KRW</span>
                              </div>
                              <div className="h-2 w-full bg-[var(--surface-soft)] rounded-full overflow-hidden border border-[var(--line)]">
                                <motion.div 
                                  initial={{ width: 0 }}
                                  animate={{ width: `${pct}%` }}
                                  transition={{ duration: 1, ease: "easeOut" }}
                                  className="h-full bg-gradient-to-r from-[var(--accent)] to-[var(--accent-strong)] rounded-full"
                                />
                              </div>
                              <p className="mt-1 text-right text-[9px] font-black text-[var(--accent)]">{pct.toFixed(2)}% CONTRIBUTION</p>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Risk & Monte Carlo Analysis */}
        <AnimatePresence>
          {mcResult && (
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: 0.2 }}
              className="space-y-6"
            >
              <Card className="border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-2xl)]">
                <div className="bg-[var(--surface-soft)] p-6 border-b border-[var(--line)] flex items-center justify-between">
                  <p className="text-[10px] font-black text-[var(--text-tertiary)] uppercase tracking-[0.2em]">리스크 기반 공사비 분석 (Monte Carlo)</p>
                  <span className={`text-[9px] font-black uppercase px-3 py-1 rounded-full border ${
                    mcResult.converged 
                      ? "bg-[var(--success-soft)] text-[var(--success)] border-[var(--success-strong)]/20" 
                      : "bg-[var(--error-soft)] text-[var(--error)] border-[var(--error-strong)]/20"
                  }`}>
                    {mcResult.converged ? "CONVERGED" : "ANALYSIS IN PROGRESS"}
                  </span>
                </div>
                <CardContent className="p-8">
                  <div className="grid grid-cols-2 gap-6">
                    <KPI 
                      label="P10 (최저 예상)" 
                      value={fmt(mcResult.p10)} 
                      unit="KRW" 
                      sub="10% 확률로 달성 가능"
                    />
                    <KPI 
                      label="P50 (중앙값)" 
                      value={fmt(mcResult.p50)} 
                      unit="KRW" 
                      sub="50% 확률 (표준 예측치)"
                    />
                    <KPI 
                      label="P80 (안전 자산)" 
                      value={fmt(mcResult.p80)} 
                      unit="KRW" 
                      sub="80% 확률로 방어 가능"
                    />
                    <KPI 
                      label="P90 (최대 위험)" 
                      value={fmt(mcResult.p90)} 
                      unit="KRW" 
                      sub="90% 확률 (보수적 접근)"
                    />
                  </div>

                  <div className="mt-8 p-6 rounded-2xl bg-[var(--surface-soft)] border border-[var(--line)]">
                     <div className="flex justify-between items-end">
                       <div>
                         <p className="text-[10px] font-black text-[var(--text-tertiary)] uppercase tracking-widest">평균(MEAN) 및 변동계수(CV)</p>
                         <p className="mt-2 text-xl font-[1000] text-[var(--text-primary)]">{fmt(mcResult.mean)} KRW</p>
                       </div>
                       <p className="text-xl font-[1000] text-[var(--accent)]">{(mcResult.cv * 100).toFixed(2)}% <span className="text-[10px] font-black text-[var(--text-hint)] uppercase">COEFF. VAR</span></p>
                     </div>
                  </div>

                  {mcResult.risk_contributions && (
                    <div className="mt-10 pt-8 border-t border-[var(--line)]">
                      <p className="text-[10px] font-black text-[var(--text-tertiary)] uppercase tracking-widest mb-6">변동성 리스크 기여도 (Risk Contribution)</p>
                      <div className="flex flex-wrap gap-3">
                        {Object.entries(mcResult.risk_contributions).map(([key, pct]) => (
                          <div 
                            key={key} 
                            className="px-4 py-3 rounded-xl bg-[var(--surface-soft)] border border-[var(--line)] flex flex-col"
                          >
                            <span className="text-[10px] font-black text-[var(--text-tertiary)] uppercase tracking-tighter mb-1">{key}</span>
                            <span className="text-[14px] font-[1000] text-[var(--text-primary)]">{pct}%</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

function KPI({ 
  label, 
  value, 
  unit, 
  highlight = false,
  sub 
}: { 
  label: string; 
  value: string; 
  unit: string;
  highlight?: boolean;
  sub?: string;
}) {
  return (
    <div className={`p-6 rounded-2xl border transition-all ${
      highlight 
        ? "bg-[var(--accent-soft)]/20 border-[var(--accent-strong)]/30 shadow-[var(--shadow-md)]" 
        : "bg-[var(--surface-soft)] border-[var(--line)]"
    }`}>
      <div className="text-[10px] font-black uppercase tracking-widest text-[var(--text-tertiary)] mb-2">{label}</div>
      <div className="flex items-baseline gap-2">
        <span className={`text-2xl font-[1000] tracking-tighter ${
          highlight ? "text-[var(--accent)]" : "text-[var(--text-primary)]"
        }`}>
          {value}
        </span>
        <span className="text-[10px] font-black text-[var(--text-hint)]">{unit}</span>
      </div>
      {sub && <p className="mt-2 text-[9px] font-bold text-[var(--text-hint)] opacity-80">{sub}</p>}
    </div>
  );
}
