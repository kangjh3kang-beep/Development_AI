"use client";

import React, { useState } from "react";
import { motion } from "framer-motion";
import { useAIAnalyze, useAIReady } from "@/lib/ai-analyze-client";
import { ProjectAddressInput } from "@/components/common/ProjectAddressInput";
import { NumberInput } from "@/components/common/NumberInput";

type AuctionResult = {
  propertyType?: string;
  appraisalValue?: { value: number; unit: string };
  estimatedBidPrice?: { value: number; rate: number; unit: string };
  rightsAnalysis?: {
    priority?: string;
    risks?: Array<{ type: string; description: string; level: string }>;
  };
  profitAnalysis?: {
    rentalYield?: number;
    capitalGain?: number;
    totalROI?: number;
  };
  recommendation?: string;
  summary?: string;
};

export default function AuctionPage() {
  const { isReady } = useAIReady();
  const { mutate, data: aiResult, isPending, error } = useAIAnalyze<AuctionResult>();

  const [form, setForm] = useState({
    address: "",
    appraisalValue: "",
    propertyType: "아파트",
    failedBids: "0",
  });

  const handleAnalyze = () => {
    if (!form.address) return;
    mutate({
      domain: "auction",
      context: {
        address: form.address,
        appraisalValue: form.appraisalValue ? `${form.appraisalValue}만원` : "미입력",
        propertyType: form.propertyType,
        failedBidCount: form.failedBids,
      },
    });
  };

  const ai = aiResult?.data;
  const riskColor = (level: string) =>
    level === "high" ? "text-red-400 bg-red-500/10" : level === "medium" ? "text-amber-400 bg-amber-500/10" : "text-emerald-400 bg-emerald-500/10";

  return (
    <div className="space-y-8 p-6">
      {/* Header */}
      <motion.div initial={{ y: -20, opacity: 0 }} animate={{ y: 0, opacity: 1 }}>
        <h1 className="text-3xl font-black tracking-tight text-[var(--text-primary)]">경공매 AI 분석</h1>
        <p className="text-sm text-[var(--text-secondary)] mt-1">법원 경매/공매 물건의 권리 분석 및 수익성을 AI가 분석합니다</p>
      </motion.div>

      {/* Input Form */}
      <motion.div initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: 0.1 }}
        className="glass rounded-3xl p-8 border border-[var(--line-strong)]"
      >
        <h2 className="text-lg font-black text-[var(--text-primary)] mb-6">물건 정보 입력</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <ProjectAddressInput
            value={form.address}
            onChange={(address) => setForm(f => ({ ...f, address }))}
            label="물건 소재지"
            placeholder="물건 소재지를 검색하세요"
          />
          <div>
            <label className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)] mb-2 block">감정가 (만원)</label>
            <NumberInput placeholder="50000" value={form.appraisalValue === "" ? null : Number(form.appraisalValue)}
              onChange={n => setForm(f => ({ ...f, appraisalValue: n != null ? String(n) : "" }))}
              className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-4 py-3 text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-strong)]/50"
            />
          </div>
          <div>
            <label className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)] mb-2 block">물건 유형</label>
            <select value={form.propertyType} onChange={e => setForm(f => ({ ...f, propertyType: e.target.value }))}
              className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-4 py-3 text-sm text-[var(--text-primary)] focus:outline-none appearance-none cursor-pointer"
            >
              {["아파트", "오피스텔", "상가", "토지", "빌라", "다세대", "단독주택"].map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)] mb-2 block">유찰 횟수</label>
            <select value={form.failedBids} onChange={e => setForm(f => ({ ...f, failedBids: e.target.value }))}
              className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-4 py-3 text-sm text-[var(--text-primary)] focus:outline-none appearance-none cursor-pointer"
            >
              {[0, 1, 2, 3, 4, 5].map(n => <option key={n} value={String(n)}>{n}회</option>)}
            </select>
          </div>
        </div>

        <button onClick={handleAnalyze} disabled={isPending || !isReady || !form.address}
          className="mt-6 w-full rounded-2xl bg-gradient-to-r from-purple-600 to-indigo-600 py-4 font-black text-white shadow-lg transition-all hover:scale-[1.01] hover:shadow-xl active:scale-[0.99] disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isPending ? "🔄 AI 분석 중..." : !isReady ? "⚙️ API 키를 먼저 등록하세요" : "🔍 경매 AI 분석 실행"}
        </button>
      </motion.div>

      {/* Error */}
      {error && (
        <div className="rounded-2xl bg-red-500/10 border border-red-500/20 p-4">
          <p className="text-sm text-red-400 font-bold">⚠️ {error.message}</p>
        </div>
      )}

      {/* AI Results */}
      {ai && (
        <motion.div initial={{ y: 30, opacity: 0 }} animate={{ y: 0, opacity: 1 }} className="space-y-6">
          {/* KPIs */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="glass rounded-2xl p-6 border border-[var(--line)]">
              <p className="text-xs font-bold text-purple-400 uppercase tracking-widest mb-1">예상 낙찰가</p>
              <p className="text-3xl font-black text-[var(--text-primary)]">{ai.estimatedBidPrice?.value?.toLocaleString() ?? "—"}<span className="text-sm ml-1">{ai.estimatedBidPrice?.unit ?? "만원"}</span></p>
              <p className="text-xs text-[var(--text-hint)] mt-1">감정가 대비 {ai.estimatedBidPrice?.rate ?? 0}%</p>
            </div>
            <div className="glass rounded-2xl p-6 border border-[var(--line)]">
              <p className="text-xs font-bold text-emerald-400 uppercase tracking-widest mb-1">예상 총 ROI</p>
              <p className="text-3xl font-black text-emerald-400">{ai.profitAnalysis?.totalROI ?? 0}%</p>
              <p className="text-xs text-[var(--text-hint)] mt-1">임대수익 {ai.profitAnalysis?.rentalYield ?? 0}% + 시세차익 {ai.profitAnalysis?.capitalGain ?? 0}%</p>
            </div>
            <div className="glass rounded-2xl p-6 border border-[var(--line)]">
              <p className="text-xs font-bold text-amber-400 uppercase tracking-widest mb-1">물건 유형</p>
              <p className="text-3xl font-black text-[var(--text-primary)]">{ai.propertyType ?? form.propertyType}</p>
            </div>
          </div>

          {/* Rights Analysis */}
          {ai.rightsAnalysis && (
            <div className="glass rounded-2xl p-6 border border-[var(--line)]">
              <h3 className="text-lg font-black text-[var(--text-primary)] mb-4">📋 권리 분석</h3>
              {ai.rightsAnalysis.priority && (
                <p className="text-sm text-[var(--text-secondary)] mb-4 bg-[var(--surface-muted)] rounded-xl p-3"><strong>말소기준권리:</strong> {ai.rightsAnalysis.priority}</p>
              )}
              {ai.rightsAnalysis.risks && ai.rightsAnalysis.risks.length > 0 && (
                <div className="space-y-2">
                  {ai.rightsAnalysis.risks.map((r, i) => (
                    <div key={i} className="flex items-start gap-3 rounded-xl bg-[var(--surface-muted)] p-3">
                      <span className={`text-[10px] font-black px-2 py-1 rounded-full ${riskColor(r.level)}`}>{r.level.toUpperCase()}</span>
                      <div>
                        <p className="text-sm font-bold text-[var(--text-primary)]">{r.type}</p>
                        <p className="text-xs text-[var(--text-secondary)]">{r.description}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* AI Summary */}
          {ai.summary && (
            <div className="glass rounded-2xl p-6 border border-emerald-500/20 bg-emerald-500/5">
              <h3 className="text-lg font-black text-emerald-400 mb-2">🤖 AI 종합 판단</h3>
              <p className="text-sm text-[var(--text-secondary)] leading-relaxed">{ai.summary}</p>
              {ai.recommendation && <p className="text-sm font-bold text-[var(--text-primary)] mt-3">💡 {ai.recommendation}</p>}
            </div>
          )}
        </motion.div>
      )}

      {/* AI Result Text Fallback */}
      {aiResult && !ai && aiResult.text && (
        <div className="glass rounded-2xl p-6 border border-[var(--line)]">
          <h3 className="text-lg font-black text-[var(--text-primary)] mb-2">AI 분석 결과</h3>
          <p className="text-sm text-[var(--text-secondary)] whitespace-pre-wrap leading-relaxed">{aiResult.text}</p>
        </div>
      )}
    </div>
  );
}
