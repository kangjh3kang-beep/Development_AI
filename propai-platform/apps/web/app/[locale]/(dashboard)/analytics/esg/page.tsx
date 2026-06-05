"use client";

import React, { useState } from "react";
import { motion } from "framer-motion";
import { useAIAnalyze, useAIReady } from "@/lib/ai-analyze-client";
import { NumberInput } from "@/components/common/NumberInput";

type ESGResult = {
  carbonFootprint?: { construction: number; operation: number; total: number; unit: string };
  energyGrade?: string;
  gSeedGrade?: string;
  zebLevel?: string;
  recommendations?: Array<{ action: string; impact: string; cost: string }>;
  summary?: string;
};

export default function ESGPage() {
  const { isReady } = useAIReady();
  const { mutate, data: aiResult, isPending, error } = useAIAnalyze<ESGResult>();

  const [form, setForm] = useState({ buildingType: "공동주택", grossArea: "", energySource: "도시가스", renewableRatio: "10" });

  const handleAnalyze = () => {
    mutate({ domain: "esg", context: { buildingType: form.buildingType, grossArea: `${form.grossArea}㎡`, energySource: form.energySource, renewableEnergyRatio: `${form.renewableRatio}%` } });
  };

  const ai = aiResult?.data;
  const gradeColor = (g?: string) => !g ? "bg-slate-500" : g.includes("1") || g === "최우수" ? "bg-emerald-500" : g.includes("2") || g === "우수" ? "bg-blue-500" : g.includes("3") || g === "우량" ? "bg-amber-500" : "bg-slate-500";

  return (
    <div className="space-y-8 p-6">
      <motion.div initial={{ y: -20, opacity: 0 }} animate={{ y: 0, opacity: 1 }}>
        <h1 className="text-3xl font-black tracking-tight text-[var(--text-primary)]">ESG / 탄소 경영</h1>
        <p className="text-sm text-[var(--text-secondary)] mt-1">건물 생애주기 탄소 배출량과 녹색 인증 등급을 AI가 분석합니다</p>
      </motion.div>

      <motion.div initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: 0.1 }} className="glass rounded-3xl p-8 border border-[var(--line-strong)]">
        <h2 className="text-lg font-black text-[var(--text-primary)] mb-6">건물 정보</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <div>
            <label className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)] mb-2 block">건물유형</label>
            <select value={form.buildingType} onChange={e => setForm(f => ({ ...f, buildingType: e.target.value }))}
              className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-4 py-3 text-sm text-[var(--text-primary)] appearance-none cursor-pointer">
              {["공동주택","업무시설","근린생활시설","숙박시설","교육시설"].map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)] mb-2 block">연면적 (㎡)</label>
            <NumberInput allowDecimal placeholder="3000" value={form.grossArea === "" ? null : Number(form.grossArea)} onChange={n => setForm(f => ({ ...f, grossArea: n != null ? String(n) : "" }))}
              className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-4 py-3 text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-strong)]/50" />
          </div>
          <div>
            <label className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)] mb-2 block">에너지원</label>
            <select value={form.energySource} onChange={e => setForm(f => ({ ...f, energySource: e.target.value }))}
              className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-4 py-3 text-sm text-[var(--text-primary)] appearance-none cursor-pointer">
              {["도시가스","전기","지열","태양열","복합"].map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)] mb-2 block">재생에너지: {form.renewableRatio}%</label>
            <input type="range" min="0" max="100" step="5" value={form.renewableRatio} onChange={e => setForm(f => ({ ...f, renewableRatio: e.target.value }))} className="w-full accent-emerald-500" />
          </div>
        </div>
        <button onClick={handleAnalyze} disabled={isPending || !isReady || !form.grossArea}
          className="mt-6 w-full rounded-2xl bg-gradient-to-r from-emerald-600 to-green-600 py-4 font-black text-white shadow-lg transition-all hover:scale-[1.01] active:scale-[0.99] disabled:opacity-50 disabled:cursor-not-allowed">
          {isPending ? "🔄 ESG 분석 중..." : !isReady ? "⚙️ API 키를 먼저 등록하세요" : "🌿 ESG AI 분석 실행"}
        </button>
      </motion.div>

      {error && <div className="rounded-2xl bg-red-500/10 border border-red-500/20 p-4"><p className="text-sm text-red-400 font-bold">⚠️ {error.message}</p></div>}

      {ai && (
        <motion.div initial={{ y: 30, opacity: 0 }} animate={{ y: 0, opacity: 1 }} className="space-y-6">
          {/* Carbon Footprint */}
          {ai.carbonFootprint && (
            <div className="grid grid-cols-3 gap-4">
              {[
                { label: "시공 단계", val: ai.carbonFootprint.construction, color: "text-amber-400" },
                { label: "운영 단계", val: ai.carbonFootprint.operation, color: "text-blue-400" },
                { label: "전체", val: ai.carbonFootprint.total, color: "text-red-400" },
              ].map(c => (
                <div key={c.label} className="glass rounded-2xl p-5 border border-[var(--line)] text-center">
                  <p className={`text-xs font-bold uppercase tracking-widest ${c.color} mb-2`}>{c.label}</p>
                  <p className="text-2xl font-black text-[var(--text-primary)]">{c.val?.toLocaleString()}<span className="text-xs ml-1">{ai.carbonFootprint?.unit}</span></p>
                </div>
              ))}
            </div>
          )}

          {/* Grades */}
          <div className="grid grid-cols-3 gap-4">
            {[
              { label: "에너지효율등급", val: ai.energyGrade },
              { label: "G-SEED 등급", val: ai.gSeedGrade },
              { label: "ZEB 수준", val: ai.zebLevel },
            ].map(g => (
              <div key={g.label} className="glass rounded-2xl p-5 border border-[var(--line)] text-center">
                <p className="text-xs font-bold text-emerald-400 uppercase tracking-widest mb-3">{g.label}</p>
                <span className={`inline-block rounded-full px-4 py-2 text-sm font-black text-white ${gradeColor(g.val)}`}>{g.val ?? "—"}</span>
              </div>
            ))}
          </div>

          {/* Recommendations */}
          {ai.recommendations && ai.recommendations.length > 0 && (
            <div className="glass rounded-2xl p-6 border border-[var(--line)]">
              <h3 className="text-lg font-black text-[var(--text-primary)] mb-4">🌱 개선 권고사항</h3>
              <div className="space-y-3">
                {ai.recommendations.map((r, i) => (
                  <div key={i} className="rounded-xl bg-[var(--surface-muted)] border border-[var(--line)] p-4">
                    <p className="text-sm font-bold text-[var(--text-primary)]">{r.action}</p>
                    <div className="flex gap-4 mt-2">
                      <span className="text-xs text-emerald-400">효과: {r.impact}</span>
                      <span className="text-xs text-amber-400">비용: {r.cost}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {ai.summary && (
            <div className="glass rounded-2xl p-6 border border-emerald-500/20 bg-emerald-500/5">
              <h3 className="text-lg font-black text-emerald-400 mb-2">🤖 AI ESG 종합 평가</h3>
              <p className="text-sm text-[var(--text-secondary)] leading-relaxed">{ai.summary}</p>
            </div>
          )}
        </motion.div>
      )}

      {aiResult && !ai && aiResult.text && (
        <div className="glass rounded-2xl p-6 border border-[var(--line)]">
          <h3 className="text-lg font-black text-[var(--text-primary)] mb-2">AI ESG 분석 결과</h3>
          <p className="text-sm text-[var(--text-secondary)] whitespace-pre-wrap leading-relaxed">{aiResult.text}</p>
        </div>
      )}
    </div>
  );
}
