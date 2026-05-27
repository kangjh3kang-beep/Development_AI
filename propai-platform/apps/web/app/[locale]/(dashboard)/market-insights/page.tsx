"use client";

import React, { useState } from "react";
import { motion } from "framer-motion";
import { useAIAnalyze, useAIReady } from "@/lib/ai-analyze-client";

type MarketResult = { marketOverview?: string; priceIndex?: { current: number; yoy: number; unit: string }; supplyDemand?: { supply: number; demand: number; absorptionRate: number }; investmentGrade?: string; forecast?: string; summary?: string };

export default function MarketInsightsPage() {
  const { isReady } = useAIReady();
  const { mutate, data: aiResult, isPending, error } = useAIAnalyze<MarketResult>();
  const [form, setForm] = useState({ region: "", propertyType: "아파트", analysisScope: "매매" });

  const handleAnalyze = () => {
    if (!form.region) return;
    mutate({ domain: "market", context: { region: form.region, propertyType: form.propertyType, analysisScope: form.analysisScope } });
  };
  const ai = aiResult?.data;
  const gradeColor = (g?: string) => g === "A" ? "bg-emerald-500" : g === "B" ? "bg-blue-500" : g === "C" ? "bg-amber-500" : "bg-red-500";

  return (
    <div className="space-y-8 p-6">
      <motion.div initial={{ y: -20, opacity: 0 }} animate={{ y: 0, opacity: 1 }}>
        <h1 className="text-3xl font-black tracking-tight text-[var(--text-primary)]">마켓 인텔리전스</h1>
        <p className="text-sm text-[var(--text-secondary)] mt-1">지역별 부동산 시장 동향을 AI가 분석합니다</p>
      </motion.div>
      <motion.div initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: 0.1 }} className="glass rounded-3xl p-8 border border-[var(--line-strong)]">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div><label className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)] mb-2 block">분석 지역</label>
            <input type="text" placeholder="서울시 강남구" value={form.region} onChange={e => setForm(f => ({ ...f, region: e.target.value }))} className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-4 py-3 text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-strong)]/50" /></div>
          <div><label className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)] mb-2 block">부동산 유형</label>
            <select value={form.propertyType} onChange={e => setForm(f => ({ ...f, propertyType: e.target.value }))} className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-4 py-3 text-sm text-[var(--text-primary)] appearance-none cursor-pointer">
              {["아파트","오피스텔","상가","오피스","토지"].map(t => <option key={t}>{t}</option>)}</select></div>
          <div><label className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)] mb-2 block">분석 범위</label>
            <select value={form.analysisScope} onChange={e => setForm(f => ({ ...f, analysisScope: e.target.value }))} className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-4 py-3 text-sm text-[var(--text-primary)] appearance-none cursor-pointer">
              {["매매","전세","월세","종합"].map(s => <option key={s}>{s}</option>)}</select></div>
        </div>
        <button onClick={handleAnalyze} disabled={isPending || !isReady || !form.region} className="mt-6 w-full rounded-2xl bg-gradient-to-r from-indigo-600 to-violet-600 py-4 font-black text-white shadow-lg transition-all hover:scale-[1.01] active:scale-[0.99] disabled:opacity-50 disabled:cursor-not-allowed">
          {isPending ? "🔄 시장 분석 중..." : !isReady ? "⚙️ API 키를 먼저 등록하세요" : "📈 마켓 AI 분석"}
        </button>
      </motion.div>
      {error && <div className="rounded-2xl bg-red-500/10 border border-red-500/20 p-4"><p className="text-sm text-red-400 font-bold">⚠️ {error.message}</p></div>}
      {ai && (
        <motion.div initial={{ y: 30, opacity: 0 }} animate={{ y: 0, opacity: 1 }} className="space-y-6">
          <div className="grid grid-cols-3 gap-4">
            <div className="glass rounded-2xl p-5 border border-[var(--line)] text-center"><p className="text-xs font-bold text-indigo-400 uppercase tracking-widest mb-2">가격 지수</p><p className="text-2xl font-black text-[var(--text-primary)]">{ai.priceIndex?.current ?? "—"}</p><p className="text-xs text-[var(--text-hint)]">전년비 {ai.priceIndex?.yoy ?? 0}%</p></div>
            <div className="glass rounded-2xl p-5 border border-[var(--line)] text-center"><p className="text-xs font-bold text-cyan-400 uppercase tracking-widest mb-2">흡수율</p><p className="text-2xl font-black text-[var(--text-primary)]">{ai.supplyDemand?.absorptionRate ?? "—"}%</p></div>
            <div className="glass rounded-2xl p-5 border border-[var(--line)] text-center"><p className="text-xs font-bold text-purple-400 uppercase tracking-widest mb-2">투자등급</p><span className={`inline-block rounded-full px-4 py-2 text-lg font-black text-white ${gradeColor(ai.investmentGrade)}`}>{ai.investmentGrade ?? "—"}</span></div>
          </div>
          {ai.marketOverview && (<div className="glass rounded-2xl p-6 border border-[var(--line)]"><h3 className="text-sm font-bold text-[var(--text-primary)] mb-2">시장 현황</h3><p className="text-sm text-[var(--text-secondary)] leading-relaxed">{ai.marketOverview}</p></div>)}
          {ai.forecast && (<div className="glass rounded-2xl p-6 border border-[var(--line)]"><h3 className="text-sm font-bold text-[var(--text-primary)] mb-2">향후 전망</h3><p className="text-sm text-[var(--text-secondary)] leading-relaxed">{ai.forecast}</p></div>)}
          {ai.summary && (<div className="glass rounded-2xl p-6 border border-indigo-500/20 bg-indigo-500/5"><h3 className="text-lg font-black text-indigo-400 mb-2">🤖 AI 시장 분석</h3><p className="text-sm text-[var(--text-secondary)] leading-relaxed">{ai.summary}</p></div>)}
        </motion.div>
      )}
      {aiResult && !ai && aiResult.text && (<div className="glass rounded-2xl p-6 border border-[var(--line)]"><p className="text-sm text-[var(--text-secondary)] whitespace-pre-wrap">{aiResult.text}</p></div>)}
    </div>
  );
}
