"use client";

import React, { useState } from "react";
import { motion } from "framer-motion";
import { useAIAnalyze, useAIReady } from "@/lib/ai-analyze-client";

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

export default function InvestmentPage() {
  const { isReady } = useAIReady();
  const { mutate, data: aiResult, isPending, error } = useAIAnalyze<FeasibilityResult>();

  const [form, setForm] = useState({
    investmentAmount: "",
    purchasePrice: "",
    expectedRent: "",
    holdingPeriod: "5",
    ltvRatio: "60",
  });

  const handleAnalyze = () => {
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

  return (
    <div className="space-y-8 p-6">
      <motion.div initial={{ y: -20, opacity: 0 }} animate={{ y: 0, opacity: 1 }}>
        <h1 className="text-3xl font-black tracking-tight text-[var(--text-primary)]">투자 수익성 분석 (ROI)</h1>
        <p className="text-sm text-[var(--text-secondary)] mt-1">NPV, IRR, ROI 기반 투자 타당성을 AI가 종합 분석합니다</p>
      </motion.div>

      {/* Input Form */}
      <motion.div initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: 0.1 }}
        className="glass rounded-3xl p-8 border border-[var(--line-strong)]"
      >
        <h2 className="text-lg font-black text-[var(--text-primary)] mb-6">투자 조건 설정</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <div>
            <label className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)] mb-2 block">투자금액 (억원)</label>
            <input type="number" placeholder="10" value={form.investmentAmount}
              onChange={e => setForm(f => ({ ...f, investmentAmount: e.target.value }))}
              className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-4 py-3 text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-strong)]/50"
            />
          </div>
          <div>
            <label className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)] mb-2 block">매입가격 (억원)</label>
            <input type="number" placeholder="30" value={form.purchasePrice}
              onChange={e => setForm(f => ({ ...f, purchasePrice: e.target.value }))}
              className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-4 py-3 text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-strong)]/50"
            />
          </div>
          <div>
            <label className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)] mb-2 block">예상 월 임대료 (만원)</label>
            <input type="number" placeholder="200" value={form.expectedRent}
              onChange={e => setForm(f => ({ ...f, expectedRent: e.target.value }))}
              className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-4 py-3 text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-strong)]/50"
            />
          </div>
          <div>
            <label className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)] mb-2 block">보유기간: {form.holdingPeriod}년</label>
            <input type="range" min="1" max="30" value={form.holdingPeriod}
              onChange={e => setForm(f => ({ ...f, holdingPeriod: e.target.value }))}
              className="w-full accent-[var(--accent-strong)]"
            />
          </div>
          <div>
            <label className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)] mb-2 block">대출비율 (LTV): {form.ltvRatio}%</label>
            <input type="range" min="0" max="80" step="5" value={form.ltvRatio}
              onChange={e => setForm(f => ({ ...f, ltvRatio: e.target.value }))}
              className="w-full accent-[var(--accent-strong)]"
            />
          </div>
        </div>

        <button onClick={handleAnalyze} disabled={isPending || !isReady}
          className="mt-6 w-full rounded-2xl bg-gradient-to-r from-emerald-600 to-teal-600 py-4 font-black text-white shadow-lg transition-all hover:scale-[1.01] hover:shadow-xl active:scale-[0.99] disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isPending ? "🔄 AI 분석 중..." : !isReady ? "⚙️ API 키를 먼저 등록하세요" : "📊 투자 수익성 AI 분석 실행"}
        </button>
      </motion.div>

      {error && (
        <div className="rounded-2xl bg-red-500/10 border border-red-500/20 p-4">
          <p className="text-sm text-red-400 font-bold">⚠️ {error.message}</p>
        </div>
      )}

      {/* Results */}
      {ai && (
        <motion.div initial={{ y: 30, opacity: 0 }} animate={{ y: 0, opacity: 1 }} className="space-y-6">
          {/* KPI Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              { label: "NPV", value: ai.npv?.value, unit: ai.npv?.unit || "억원", color: "text-blue-400" },
              { label: "IRR", value: ai.irr?.value, unit: ai.irr?.unit || "%", color: "text-emerald-400" },
              { label: "ROI", value: ai.roi?.value, unit: ai.roi?.unit || "%", color: "text-purple-400" },
              { label: "수익률", value: ai.profitMargin?.value, unit: ai.profitMargin?.unit || "%", color: "text-amber-400" },
            ].map((kpi) => (
              <div key={kpi.label} className="glass rounded-2xl p-5 border border-[var(--line)] text-center">
                <p className={`text-xs font-bold uppercase tracking-widest ${kpi.color} mb-2`}>{kpi.label}</p>
                <p className="text-2xl font-black text-[var(--text-primary)]">{kpi.value ?? "—"}<span className="text-xs ml-1">{kpi.unit}</span></p>
              </div>
            ))}
          </div>

          {/* Revenue/Cost */}
          {(ai.totalRevenue || ai.totalCost) && (
            <div className="grid grid-cols-2 gap-4">
              <div className="glass rounded-2xl p-5 border border-[var(--line)]">
                <p className="text-xs font-bold text-emerald-400 uppercase tracking-widest mb-1">총 수익</p>
                <p className="text-2xl font-black text-emerald-400">{ai.totalRevenue?.value?.toLocaleString() ?? "—"} <span className="text-xs">{ai.totalRevenue?.unit}</span></p>
              </div>
              <div className="glass rounded-2xl p-5 border border-[var(--line)]">
                <p className="text-xs font-bold text-red-400 uppercase tracking-widest mb-1">총 비용</p>
                <p className="text-2xl font-black text-red-400">{ai.totalCost?.value?.toLocaleString() ?? "—"} <span className="text-xs">{ai.totalCost?.unit}</span></p>
              </div>
            </div>
          )}

          {/* Risks */}
          {ai.risks && ai.risks.length > 0 && (
            <div className="glass rounded-2xl p-6 border border-[var(--line)]">
              <h3 className="text-lg font-black text-[var(--text-primary)] mb-4">⚡ 리스크 분석</h3>
              <div className="space-y-2">
                {ai.risks.map((r, i) => (
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
          )}

          {/* AI Summary */}
          {ai.summary && (
            <div className="glass rounded-2xl p-6 border border-emerald-500/20 bg-emerald-500/5">
              <h3 className="text-lg font-black text-emerald-400 mb-2">🤖 AI 투자 판단</h3>
              <p className="text-sm text-[var(--text-secondary)] leading-relaxed">{ai.summary}</p>
              {ai.recommendation && <p className="text-sm font-bold text-[var(--text-primary)] mt-3">💡 {ai.recommendation}</p>}
            </div>
          )}
        </motion.div>
      )}

      {aiResult && !ai && aiResult.text && (
        <div className="glass rounded-2xl p-6 border border-[var(--line)]">
          <h3 className="text-lg font-black text-[var(--text-primary)] mb-2">AI 분석 결과</h3>
          <p className="text-sm text-[var(--text-secondary)] whitespace-pre-wrap leading-relaxed">{aiResult.text}</p>
        </div>
      )}
    </div>
  );
}
