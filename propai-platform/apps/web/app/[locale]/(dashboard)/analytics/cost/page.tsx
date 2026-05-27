"use client";

import React, { useState } from "react";
import { motion } from "framer-motion";
import { useAIAnalyze, useAIReady } from "@/lib/ai-analyze-client";

type CostResult = { estimatedCost?: { total: number; perUnit: number; unit: string }; breakdown?: Array<{ category: string; amount: number; ratio: number }>; marketComparison?: string; summary?: string };

export default function CostPage() {
  const { isReady } = useAIReady();
  const { mutate, data: aiResult, isPending, error } = useAIAnalyze<CostResult>();
  const [form, setForm] = useState({ buildingType: "공동주택", grossArea: "", floors: "", structure: "RC조" });

  const handleAnalyze = () => {
    mutate({ domain: "construction", context: { buildingType: form.buildingType, grossArea: `${form.grossArea}㎡`, floors: `${form.floors}층`, structure: form.structure } });
  };

  const ai = aiResult?.data;

  return (
    <div className="space-y-8 p-6">
      <motion.div initial={{ y: -20, opacity: 0 }} animate={{ y: 0, opacity: 1 }}>
        <h1 className="text-3xl font-black tracking-tight text-[var(--text-primary)]">공사비 AI 분석</h1>
        <p className="text-sm text-[var(--text-secondary)] mt-1">건물 사양 기반 정밀 공사비를 AI가 추정합니다</p>
      </motion.div>
      <motion.div initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: 0.1 }} className="glass rounded-3xl p-8 border border-[var(--line-strong)]">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div><label className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)] mb-2 block">건물유형</label>
            <select value={form.buildingType} onChange={e => setForm(f => ({ ...f, buildingType: e.target.value }))} className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-4 py-3 text-sm text-[var(--text-primary)] appearance-none cursor-pointer">
              {["공동주택","업무시설","근린생활시설","숙박시설","물류시설"].map(t => <option key={t}>{t}</option>)}</select></div>
          <div><label className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)] mb-2 block">연면적 (㎡)</label>
            <input type="number" placeholder="5000" value={form.grossArea} onChange={e => setForm(f => ({ ...f, grossArea: e.target.value }))} className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-4 py-3 text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-strong)]/50" /></div>
          <div><label className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)] mb-2 block">층수</label>
            <input type="number" placeholder="15" value={form.floors} onChange={e => setForm(f => ({ ...f, floors: e.target.value }))} className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-4 py-3 text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-strong)]/50" /></div>
          <div><label className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)] mb-2 block">구조</label>
            <select value={form.structure} onChange={e => setForm(f => ({ ...f, structure: e.target.value }))} className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-4 py-3 text-sm text-[var(--text-primary)] appearance-none cursor-pointer">
              {["RC조","SRC조","S조","PC조","목구조"].map(s => <option key={s}>{s}</option>)}</select></div>
        </div>
        <button onClick={handleAnalyze} disabled={isPending || !isReady || !form.grossArea} className="mt-6 w-full rounded-2xl bg-gradient-to-r from-amber-600 to-orange-600 py-4 font-black text-white shadow-lg transition-all hover:scale-[1.01] active:scale-[0.99] disabled:opacity-50 disabled:cursor-not-allowed">
          {isPending ? "🔄 분석 중..." : !isReady ? "⚙️ API 키를 먼저 등록하세요" : "🏗️ 공사비 AI 분석"}
        </button>
      </motion.div>
      {error && <div className="rounded-2xl bg-red-500/10 border border-red-500/20 p-4"><p className="text-sm text-red-400 font-bold">⚠️ {error.message}</p></div>}
      {ai && (
        <motion.div initial={{ y: 30, opacity: 0 }} animate={{ y: 0, opacity: 1 }} className="space-y-6">
          {ai.estimatedCost && (
            <div className="grid grid-cols-2 gap-4">
              <div className="glass rounded-2xl p-6 border border-[var(--line)] text-center"><p className="text-xs font-bold text-amber-400 uppercase tracking-widest mb-2">총 공사비</p><p className="text-3xl font-black text-[var(--text-primary)]">{ai.estimatedCost.total?.toLocaleString()}<span className="text-sm ml-1">{ai.estimatedCost.unit}</span></p></div>
              <div className="glass rounded-2xl p-6 border border-[var(--line)] text-center"><p className="text-xs font-bold text-blue-400 uppercase tracking-widest mb-2">단위면적당</p><p className="text-3xl font-black text-[var(--text-primary)]">{ai.estimatedCost.perUnit?.toLocaleString()}<span className="text-sm ml-1">원/㎡</span></p></div>
            </div>
          )}
          {ai.breakdown && ai.breakdown.length > 0 && (
            <div className="glass rounded-2xl p-6 border border-[var(--line)]"><h3 className="text-lg font-black text-[var(--text-primary)] mb-4">📊 비용 항목별 내역</h3>
              {ai.breakdown.map((b, i) => (<div key={i} className="flex items-center gap-3 mb-3"><span className="text-sm font-bold text-[var(--text-primary)] w-24">{b.category}</span><div className="flex-1 h-3 rounded-full bg-[var(--line)]"><div className="h-3 rounded-full bg-amber-400" style={{ width: `${b.ratio}%` }} /></div><span className="text-xs font-bold text-[var(--text-secondary)] w-20 text-right">{b.amount?.toLocaleString()}</span></div>))}
            </div>
          )}
          {ai.summary && (<div className="glass rounded-2xl p-6 border border-amber-500/20 bg-amber-500/5"><h3 className="text-lg font-black text-amber-400 mb-2">🤖 AI 공사비 분석</h3><p className="text-sm text-[var(--text-secondary)] leading-relaxed">{ai.summary}</p></div>)}
        </motion.div>
      )}
      {aiResult && !ai && aiResult.text && (<div className="glass rounded-2xl p-6 border border-[var(--line)]"><p className="text-sm text-[var(--text-secondary)] whitespace-pre-wrap">{aiResult.text}</p></div>)}
    </div>
  );
}
