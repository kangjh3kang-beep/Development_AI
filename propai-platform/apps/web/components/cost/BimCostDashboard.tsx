"use client";

import { useState, useCallback } from "react";
import { AlertTriangle } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { Button, Card, CardContent, CardTitle } from "@propai/ui";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { UseLlmToggle } from "@/components/common/UseLlmToggle";
import { SeniorVerdictCard, type SeniorConsultation } from "@/components/analysis/SeniorVerdictCard";

type CostResult = {
  total_project_cost: number;
  direct_material_cost: number;
  direct_labor_cost: number;
  direct_expense_cost: number;
  net_construction_cost: number;
  vat: number;
  category_totals: Record<string, number>;
  applied_rates: Record<string, number>;
  ai_cost_analysis?: string | null;
  // P3: 시니어 적산(QS) 자문(with_senior opt-in 시만 채워짐).
  senior_consultation?: SeniorConsultation | null;
  [key: string]: unknown;
};

// origin-cost(bim_quantities) 항목 — /calculate 재제출용(work_code/mat_unit/labor_unit/exp_unit 보유).
type OriginCostItem = {
  work_code: string;
  item_name: string;
  spec?: string;
  unit: string;
  quantity: number;
  mat_unit: number;
  labor_unit: number;
  exp_unit: number;
  priced: boolean;
};

type OriginCostResponse = {
  status: "ok" | "no_bim_quantities";
  items: OriginCostItem[];
};

// /cost/estimate-overview 응답(qto_source 없는 BIM 물량 폴백용 — 건축개요 기반 개산).
type OverviewResult = {
  total_won: number;
  direct_won: number;
  indirect_won: number;
  aboveground_won: number;
  underground_won: number;
  landscape_won: number;
  qto_source?: string;
  // P3: 시니어 적산(QS) 자문(with_senior opt-in 시만 채워짐).
  senior_consultation?: SeniorConsultation | null;
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
  const [overviewResult, setOverviewResult] = useState<OverviewResult | null>(null);
  const [mcResult, setMcResult] = useState<MCResult | null>(null);
  const [rates, setRates] = useState<Rate | null>(null);
  const [loading, setLoading] = useState(false);
  // T6: 물량 출처 배지 — BIM 실측(bim_quantities, T1 영속 배선) 우선, 없으면 건축개요 개산으로 폴백.
  const [qtoSource, setQtoSource] = useState<"bim_quantities" | "estimate_overview" | null>(null);
  const totalGfaSqm = useProjectContextStore((s) => s.designData?.totalGfaSqm ?? null);
  const floorCount = useProjectContextStore((s) => s.designData?.floorCount ?? null);
  const [needDesign, setNeedDesign] = useState(false);
  // T3: use_llm 옵트인 — 기존 동작(AI 원가 해석 항상 포함)을 보존하기 위해 기본 true로 명시 전송.
  const [useLlm, setUseLlm] = useState(true);

  const fetchRates = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/rates/current`);
      if (res.ok) setRates(await res.json());
    } catch {
      /* silent */
    }
  }, []);

  const handleCalculate = useCallback(async () => {
    // 연면적이 없으면 가짜 고정 물량 대신 정직하게 설계 선행을 안내(무목업·가짜값0).
    if (!totalGfaSqm || totalGfaSqm <= 0) { setNeedDesign(true); return; }
    setNeedDesign(false);
    setLoading(true);
    try {
      // 1순위: BIM 실측 물량(bim_quantities, T1로 /bim/generate-ifc 성공경로에 영속 배선됨).
      //   근사 역산·하드코딩 단가(구버전)를 제거하고 실 데이터만 사용한다(무목업).
      let usedBim = false;
      try {
        const originRes = await fetch(
          `${API_BASE}/api/v1/cost/${projectId}/bim-quantities/origin-cost`,
        );
        if (originRes.ok) {
          const originData: OriginCostResponse = await originRes.json();
          const items = (originData.items ?? [])
            .filter((it) => it.priced)
            .map((it) => ({
              work_code: it.work_code, item_name: it.item_name, spec: it.spec,
              unit: it.unit, quantity: it.quantity, mat_unit: it.mat_unit,
              labor_unit: it.labor_unit, exp_unit: it.exp_unit,
            }));
          if (originData.status === "ok" && items.length > 0) {
            const calcRes = await fetch(
              `${API_BASE}/api/v1/cost/${projectId}/calculate`,
              {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ items, use_llm: useLlm, with_senior: true }),
              },
            );
            if (calcRes.ok) {
              const data: CostResult = await calcRes.json();
              setCostResult(data);
              setOverviewResult(null);
              setQtoSource("bim_quantities");
              usedBim = true;

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
          }
        }
      } catch {
        /* BIM 물량 조회 실패 — 아래 폴백으로 계속 진행 */
      }

      // 2순위(폴백): BIM 물량 미확보 — 건축개요 기반 개산(estimate-overview, 실 표준품셈 산출).
      //   리스크 시뮬레이션(MC)은 12단계 원가 분해가 없어 실행하지 않는다(가짜 결과 금지).
      if (!usedBim) {
        setMcResult(null);
        const ovRes = await fetch(`${API_BASE}/api/v1/cost/estimate-overview`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            project_id: projectId,
            total_gfa_sqm: totalGfaSqm,
            floor_count_above: floorCount && floorCount > 0 ? floorCount : 1,
            floor_count_below: 0,
            structure_type: "RC",
            with_senior: true,
          }),
        });
        if (ovRes.ok) {
          const ov: OverviewResult = await ovRes.json();
          setOverviewResult(ov);
          setCostResult(null);
          setQtoSource("estimate_overview");
        }
      }
    } catch {
      /* silent */
    } finally {
      setLoading(false);
    }
  }, [projectId, totalGfaSqm, floorCount, useLlm]);

  return (
    <div className="grid grid-cols-1 gap-8 min-w-0">
      {/* Simulation Control Header */}
      <Card className="border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-xl)] overflow-hidden">
        <div className="bg-[var(--surface-soft)] p-6 border-b border-[var(--line)] flex items-center justify-between">
           <CardTitle className="text-[12px] font-black uppercase tracking-[0.3em] text-[var(--text-primary)]">
             BIM 기반 공사비 시뮬레이션 & 리스크 분석
           </CardTitle>
           <div className="flex flex-wrap items-center gap-4">
              <UseLlmToggle checked={useLlm} onChange={setUseLlm} hint="AI 원가 해석 포함" disabled={loading} />
              <Button
                variant="secondary"
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
                {loading ? "분석 중..." : "공사비 정밀 분석"}
              </Button>
           </div>
        </div>

        {/* T6: 물량 출처 정직 고지 — BIM 실측(bim_quantities) 우선, 없으면 건축개요 개산으로 폴백. */}
        {needDesign ? (
          <div className="flex items-start gap-1.5 px-8 py-5 bg-amber-500/10 border-b border-amber-500/30 text-[12px] leading-relaxed text-amber-700">
            <AlertTriangle className="size-3.5 mt-0.5 shrink-0" aria-hidden /><span>설계 연면적이 없습니다. <b>설계(또는 건축개요)를 먼저 완료</b>하면 공사비를 산정합니다. (가짜 고정 물량은 사용하지 않습니다.)</span>
          </div>
        ) : qtoSource === "bim_quantities" ? (
          <div className="px-8 py-3 bg-emerald-500/10 border-b border-emerald-500/30 text-[11px] text-emerald-700">
            BIM 실측 물량(IFC 생성/분석 결과 · bim_quantities) 기반으로 산정했습니다.
          </div>
        ) : qtoSource === "estimate_overview" ? (
          <div className="px-8 py-3 bg-[var(--surface-soft)] border-b border-[var(--line)] text-[11px] text-[var(--text-hint)]">
            BIM 물량이 아직 없어 건축개요(연면적 {totalGfaSqm ? fmt(totalGfaSqm) : "-"}㎡) 기반 개산으로 산정했습니다. IFC 생성/분석을 실행하면 실측 기반 정밀 원가·리스크 시뮬레이션을 이용할 수 있습니다.
          </div>
        ) : null}

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

      {/* T6 폴백: BIM 물량 미확보 시 건축개요 기반 개산(estimate-overview) 요약 — 12단계 분해가
          없으므로 KPI 구성을 다르게 표기한다(가짜 재료비/노무비 분해 발명 금지). */}
      <AnimatePresence>
        {overviewResult && !costResult && (
          <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}>
            <Card className="border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-2xl)]">
              <div className="bg-[var(--surface-soft)] p-6 border-b border-[var(--line)]">
                <p className="text-[10px] font-black text-[var(--text-tertiary)] uppercase tracking-[0.2em]">개산 공사비 요약 (건축개요 기반)</p>
              </div>
              <CardContent className="p-8">
                <div className="grid grid-cols-2 gap-6 md:grid-cols-3">
                  <KPI label="총 공사비(개산)" value={fmt(overviewResult.total_won)} unit="KRW" highlight />
                  <KPI label="직접공사비" value={fmt(overviewResult.direct_won)} unit="KRW" />
                  <KPI label="간접비" value={fmt(overviewResult.indirect_won)} unit="KRW" />
                  <KPI label="지상 공사비" value={fmt(overviewResult.aboveground_won)} unit="KRW" />
                  <KPI label="지하 공사비" value={fmt(overviewResult.underground_won)} unit="KRW" />
                  <KPI label="조경 공사비" value={fmt(overviewResult.landscape_won)} unit="KRW" />
                </div>
              </CardContent>
            </Card>
          </motion.div>
        )}
      </AnimatePresence>

      {/* P3: 시니어 적산(QS) 자문 verdict(with_senior opt-in) — 정량입력 산출 가능분(법정요율 상한·
          기준선편차·예비비·단가신뢰도·공종구성비) 있을 때만 카드 렌더(SeniorVerdictCard 자체 정직 게이트). */}
      <SeniorVerdictCard
        consultation={costResult?.senior_consultation ?? overviewResult?.senior_consultation}
        title="시니어 적산(QS) 자문"
      />

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

                  {/* T3: use_llm=true일 때만 채워지는 AI 원가 해설 */}
                  {costResult.ai_cost_analysis && (
                    <div className="mt-10 pt-8 border-t border-[var(--line)]">
                      <p className="text-[10px] font-black text-[var(--text-tertiary)] uppercase tracking-widest mb-3">AI 원가 해설</p>
                      <p className="whitespace-pre-wrap text-[12px] leading-relaxed text-[var(--text-secondary)]">
                        {costResult.ai_cost_analysis}
                      </p>
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
