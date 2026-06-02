"use client";

import React, { useState, useMemo } from "react";
import { useParams } from "next/navigation";
import { motion } from "framer-motion";
import { useAIAnalyze, useAIReady } from "@/lib/ai-analyze-client";
import { InvestmentAnalyticsWorkspaceClient } from "@/components/analytics/InvestmentAnalyticsWorkspaceClient";
import { ExpertPanelCard } from "@/components/common/ExpertPanelCard";
import { isValidLocale, type Locale } from "@/i18n/config";

type FeasibilityResult = {
  summary?: string;
  npv?: { value: number; unit: string };
  irr?: { value: number; unit: string };
  roi?: { value: number; unit: string };
  totalRevenue?: { value: number; unit: string };
  totalCost?: { value: number; unit: string };
  profitMargin?: { value: number; unit: string };
  risks?: Array<{ factor: string; level: string; description: string }>;
  recommendation?: string;
};

// ── 로컬 ROI 계산기 ──
function calcROI(investment: number, purchase: number, monthlyRent: number, holdingYears: number, ltv: number) {
  if (investment <= 0 || purchase <= 0) return null;

  const loanAmount = purchase * (ltv / 100);
  const equity = purchase - loanAmount;
  const interestRate = 0.045; // 4.5% 연이율 가정
  const annualRent = monthlyRent * 12;
  const annualInterest = loanAmount * interestRate;
  const annualNetIncome = annualRent - annualInterest;
  const totalRevenue = annualRent * holdingYears;
  const totalInterest = annualInterest * holdingYears;
  const appreciationRate = 0.03; // 연 3% 감정가 상승 가정
  const futureValue = purchase * Math.pow(1 + appreciationRate, holdingYears);
  const capitalGain = futureValue - purchase;
  const totalProfit = annualNetIncome * holdingYears + capitalGain;
  const totalCost = equity + totalInterest;
  const roi = totalProfit > 0 ? (totalProfit / equity) * 100 : 0;
  const irr = annualNetIncome > 0 ? ((annualNetIncome + capitalGain / holdingYears) / equity) * 100 : 0;
  const npv = totalProfit - equity * 0.05 * holdingYears; // 5% 할인율

  return {
    npv: Math.round(npv / 10000) / 10000 * 10000, // 억원 변환을 위한 계산
    npvRaw: npv,
    irr: Math.round(irr * 10) / 10,
    roi: Math.round(roi * 10) / 10,
    totalRevenue: Math.round(totalRevenue),
    totalCost: Math.round(totalCost),
    profitMargin: totalRevenue > 0 ? Math.round((totalProfit / totalRevenue) * 100 * 10) / 10 : 0,
    capitalGain: Math.round(capitalGain),
    equity: Math.round(equity),
    annualNetIncome: Math.round(annualNetIncome),
    risks: [
      { factor: "금리 변동", level: ltv > 60 ? "high" : "medium", description: `LTV ${ltv}%로 금리 1% 상승 시 연간 이자 ${Math.round(loanAmount * 0.01)}만원 증가` },
      { factor: "공실 리스크", level: annualRent > purchase * 0.05 ? "low" : "medium", description: `수익률 ${(annualRent / purchase * 100).toFixed(1)}%로 ${annualRent > purchase * 0.05 ? "양호" : "주의 필요"}` },
      { factor: "시세 하락", level: "medium", description: `${holdingYears}년 보유 중 시세 10% 하락 시 손실 약 ${Math.round(purchase * 0.1)}만원` },
    ],
  };
}

export default function InvestmentPage() {
  const params = useParams();
  const locale = params.locale as string;
  const { isReady } = useAIReady();
  const { mutate, data: aiResult, isPending, error } = useAIAnalyze<FeasibilityResult>();

  const [form, setForm] = useState({
    investmentAmount: "10",
    purchasePrice: "30",
    expectedRent: "200",
    holdingPeriod: "5",
    ltvRatio: "60",
  });

  // ── 로컬 즉시 계산 ──
  const localCalc = useMemo(() => {
    const inv = Number(form.investmentAmount) * 10000; // 억 → 만원
    const price = Number(form.purchasePrice) * 10000;
    const rent = Number(form.expectedRent);
    const years = Number(form.holdingPeriod);
    const ltv = Number(form.ltvRatio);
    return calcROI(inv, price, rent, years, ltv);
  }, [form]);

  const handleAIAnalyze = () => {
    mutate({
      domain: "feasibility",
      context: {
        investmentAmount: `${form.investmentAmount}억원`,
        purchasePrice: `${form.purchasePrice}억원`,
        monthlyRent: `${form.expectedRent}만원`,
        holdingPeriod: `${form.holdingPeriod}년`,
        ltvRatio: `${form.ltvRatio}%`,
      },
    });
  };

  const ai = aiResult?.data;
  const riskColor = (level: string) =>
    level === "high" ? "text-red-400 bg-red-500/10 border-red-500/20" : level === "medium" ? "text-amber-400 bg-amber-500/10 border-amber-500/20" : "text-emerald-400 bg-emerald-500/10 border-emerald-500/20";

  const safeLocale = (isValidLocale(locale) ? locale : "ko") as Locale;
  const projectId = "default";

  return (
    <div className="space-y-8 p-6">
      <motion.div initial={{ y: -20, opacity: 0 }} animate={{ y: 0, opacity: 1 }}>
        <h1 className="text-3xl font-black tracking-tight text-[var(--text-primary)]">투자 수익성 분석 (ROI)</h1>
        <p className="text-sm text-[var(--text-secondary)] mt-1">NPV, IRR, ROI 실시간 자동 계산 + AI 심층 분석</p>
      </motion.div>

      {/* Input Form */}
      <motion.div initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: 0.1 }}
        className="glass rounded-3xl p-8 border border-[var(--line-strong)]">
        <h2 className="text-lg font-black text-[var(--text-primary)] mb-6">투자 조건 설정</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <div>
            <label className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)] mb-2 block">투자금액 (억원)</label>
            <input type="number" placeholder="10" value={form.investmentAmount}
              onChange={e => setForm(f => ({ ...f, investmentAmount: e.target.value }))}
              className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-4 py-3 text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-strong)]/50" />
          </div>
          <div>
            <label className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)] mb-2 block">매입가격 (억원)</label>
            <input type="number" placeholder="30" value={form.purchasePrice}
              onChange={e => setForm(f => ({ ...f, purchasePrice: e.target.value }))}
              className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-4 py-3 text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-strong)]/50" />
          </div>
          <div>
            <label className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)] mb-2 block">예상 월 임대료 (만원)</label>
            <input type="number" placeholder="200" value={form.expectedRent}
              onChange={e => setForm(f => ({ ...f, expectedRent: e.target.value }))}
              className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-4 py-3 text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-strong)]/50" />
          </div>
          <div>
            <label className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)] mb-2 block">보유기간: {form.holdingPeriod}년</label>
            <input type="range" min="1" max="30" value={form.holdingPeriod}
              onChange={e => setForm(f => ({ ...f, holdingPeriod: e.target.value }))} className="w-full accent-[var(--accent-strong)]" />
          </div>
          <div>
            <label className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)] mb-2 block">대출비율 (LTV): {form.ltvRatio}%</label>
            <input type="range" min="0" max="80" step="5" value={form.ltvRatio}
              onChange={e => setForm(f => ({ ...f, ltvRatio: e.target.value }))} className="w-full accent-[var(--accent-strong)]" />
          </div>
        </div>
        <button onClick={handleAIAnalyze} disabled={isPending || !isReady}
          className="mt-6 w-full rounded-2xl bg-gradient-to-r from-emerald-600 to-teal-600 py-4 font-black text-white shadow-lg transition-all hover:scale-[1.01] hover:shadow-xl active:scale-[0.99] disabled:opacity-50 disabled:cursor-not-allowed">
          {isPending ? "AI 분석 중..." : !isReady ? "API 키 없이도 아래 자동 계산됩니다" : "AI 심층 수익성 분석"}
        </button>
      </motion.div>

      {error && <div className="rounded-2xl bg-red-500/10 border border-red-500/20 p-4"><p className="text-sm text-red-400 font-bold">{error.message}</p></div>}

      {/* Results -- 즉시 표시 */}
      {localCalc && (
        <motion.div initial={{ y: 30, opacity: 0 }} animate={{ y: 0, opacity: 1 }} className="space-y-6">
          {/* Source */}
          <div className="flex items-center gap-2">
            <span className={`inline-block h-2 w-2 rounded-full ${ai ? "bg-emerald-400" : "bg-blue-400"}`} />
            <span className="text-xs font-bold text-[var(--text-secondary)]">{ai ? "AI 분석 반영" : "실시간 자동 계산 (슬라이더 조절 시 즉시 업데이트)"}</span>
          </div>

          {/* KPI Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              { label: "NPV", value: ai?.npv?.value ?? `${(localCalc.npvRaw / 10000).toFixed(1)}`, unit: "억원", color: "text-blue-400" },
              { label: "IRR", value: ai?.irr?.value ?? localCalc.irr, unit: "%", color: "text-emerald-400" },
              { label: "ROI", value: ai?.roi?.value ?? localCalc.roi, unit: "%", color: "text-purple-400" },
              { label: "수익률", value: ai?.profitMargin?.value ?? localCalc.profitMargin, unit: "%", color: "text-amber-400" },
            ].map((kpi) => (
              <div key={kpi.label} className="glass rounded-2xl p-5 border border-[var(--line)] text-center">
                <p className={`text-xs font-bold uppercase tracking-widest ${kpi.color} mb-2`}>{kpi.label}</p>
                <p className="text-2xl font-black text-[var(--text-primary)]">{kpi.value}<span className="text-xs ml-1">{kpi.unit}</span></p>
              </div>
            ))}
          </div>

          {/* Revenue/Cost */}
          <div className="grid grid-cols-3 gap-4">
            <div className="glass rounded-2xl p-5 border border-[var(--line)]">
              <p className="text-xs font-bold text-cyan-400 uppercase tracking-widest mb-1">자기자본(에쿼티)</p>
              <p className="text-2xl font-black text-[var(--text-primary)]">{(localCalc.equity / 10000).toFixed(1)} <span className="text-xs">억원</span></p>
            </div>
            <div className="glass rounded-2xl p-5 border border-[var(--line)]">
              <p className="text-xs font-bold text-emerald-400 uppercase tracking-widest mb-1">연간 순수익</p>
              <p className="text-2xl font-black text-emerald-400">{localCalc.annualNetIncome.toLocaleString()} <span className="text-xs">만원</span></p>
            </div>
            <div className="glass rounded-2xl p-5 border border-[var(--line)]">
              <p className="text-xs font-bold text-purple-400 uppercase tracking-widest mb-1">예상 시세차익</p>
              <p className="text-2xl font-black text-purple-400">{(localCalc.capitalGain / 10000).toFixed(1)} <span className="text-xs">억원</span></p>
            </div>
          </div>

          {/* Risks */}
          <div className="glass rounded-2xl p-6 border border-[var(--line)]">
            <h3 className="text-lg font-black text-[var(--text-primary)] mb-4">리스크 분석</h3>
            <div className="space-y-2">
              {(ai?.risks || localCalc.risks).map((r, i) => (
                <div key={i} className={`flex items-start gap-3 rounded-xl border p-3 ${riskColor(r.level)}`}>
                  <span className="text-[10px] font-black px-2 py-1 rounded-full bg-white/10">{r.level.toUpperCase()}</span>
                  <div>
                    <p className="text-sm font-bold">{r.factor}</p>
                    <p className="text-xs opacity-80">{r.description}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* AI Summary */}
          {ai?.summary && (
            <div className="glass rounded-2xl p-6 border border-emerald-500/20 bg-emerald-500/5">
              <h3 className="text-lg font-black text-emerald-400 mb-2">AI 투자 판단</h3>
              <p className="text-sm text-[var(--text-secondary)] leading-relaxed">{ai.summary}</p>
              {ai.recommendation && <p className="text-sm font-bold text-[var(--text-primary)] mt-3">{ai.recommendation}</p>}
            </div>
          )}
        </motion.div>
      )}

      {/* ── 전문가 패널 검증 (계산/AI 결과가 있을 때) ── */}
      {(localCalc || ai) && (
        <div className="px-0">
          <ExpertPanelCard
            analysisType="feasibility"
            context={{
              inputs: {
                investment_eok: form.investmentAmount, purchase_eok: form.purchasePrice,
                monthly_rent_manwon: form.expectedRent, holding_years: form.holdingPeriod, ltv_pct: form.ltvRatio,
              },
              calc: localCalc, ai_result: ai,
            }}
          />
        </div>
      )}

      {/* ── Live Workspace Client ── */}
      <InvestmentAnalyticsWorkspaceClient locale={safeLocale} projectId={projectId} />
    </div>
  );
}
