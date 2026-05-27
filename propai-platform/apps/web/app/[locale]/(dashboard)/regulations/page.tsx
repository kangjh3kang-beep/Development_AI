"use client";

import React, { useState } from "react";
import { motion } from "framer-motion";
import { useAIAnalyze, useAIReady } from "@/lib/ai-analyze-client";

type RegulationResult = {
  applicableRegulations?: Array<{ law: string; article: string; impact: string; level: string }>;
  restrictions?: { buildingCoverage?: { max: number; unit: string }; floorAreaRatio?: { max: number; unit: string }; heightLimit?: { value: number; unit: string } };
  specialZones?: string[];
  recommendations?: string[];
  summary?: string;
};

export default function RegulationsPage() {
  const { isReady } = useAIReady();
  const { mutate, data: aiResult, isPending, error } = useAIAnalyze<RegulationResult>();
  const [form, setForm] = useState({ address: "", pnu: "", zoning: "제2종일반주거지역" });

  const handleAnalyze = () => {
    if (!form.address) return;
    mutate({ domain: "regulation", context: { address: form.address, pnu: form.pnu || "미입력", zoningDistrict: form.zoning } });
  };

  const ai = aiResult?.data;
  const levelBadge = (l: string) => l === "high" ? "bg-red-500/20 text-red-400" : l === "medium" ? "bg-amber-500/20 text-amber-400" : "bg-emerald-500/20 text-emerald-400";

  return (
    <div className="space-y-8 p-6">
      <motion.div initial={{ y: -20, opacity: 0 }} animate={{ y: 0, opacity: 1 }}>
        <h1 className="text-3xl font-black tracking-tight text-[var(--text-primary)]">부동산 규제 분석</h1>
        <p className="text-sm text-[var(--text-secondary)] mt-1">해당 토지에 적용되는 법규와 건축 제한을 AI가 분석합니다</p>
      </motion.div>

      <motion.div initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: 0.1 }} className="glass rounded-3xl p-8 border border-[var(--line-strong)]">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)] mb-2 block">주소</label>
            <input type="text" placeholder="서울시 강남구 역삼동 123" value={form.address} onChange={e => setForm(f => ({ ...f, address: e.target.value }))}
              className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-4 py-3 text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-strong)]/50" />
          </div>
          <div>
            <label className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)] mb-2 block">PNU 코드 (선택)</label>
            <input type="text" placeholder="1168010100..." value={form.pnu} onChange={e => setForm(f => ({ ...f, pnu: e.target.value }))}
              className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-4 py-3 text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-strong)]/50" />
          </div>
          <div>
            <label className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)] mb-2 block">용도지역</label>
            <select value={form.zoning} onChange={e => setForm(f => ({ ...f, zoning: e.target.value }))}
              className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-4 py-3 text-sm text-[var(--text-primary)] appearance-none cursor-pointer">
              {["제1종전용주거지역","제2종전용주거지역","제1종일반주거지역","제2종일반주거지역","제3종일반주거지역","준주거지역","일반상업지역","근린상업지역","준공업지역","자연녹지지역","보전녹지지역"].map(z => <option key={z} value={z}>{z}</option>)}
            </select>
          </div>
        </div>
        <button onClick={handleAnalyze} disabled={isPending || !isReady || !form.address}
          className="mt-6 w-full rounded-2xl bg-gradient-to-r from-orange-600 to-red-600 py-4 font-black text-white shadow-lg transition-all hover:scale-[1.01] active:scale-[0.99] disabled:opacity-50 disabled:cursor-not-allowed">
          {isPending ? "🔄 규제 분석 중..." : !isReady ? "⚙️ API 키를 먼저 등록하세요" : "📜 규제 AI 분석 실행"}
        </button>
      </motion.div>

      {error && <div className="rounded-2xl bg-red-500/10 border border-red-500/20 p-4"><p className="text-sm text-red-400 font-bold">⚠️ {error.message}</p></div>}

      {ai && (
        <motion.div initial={{ y: 30, opacity: 0 }} animate={{ y: 0, opacity: 1 }} className="space-y-6">
          {/* Restrictions */}
          {ai.restrictions && (
            <div className="grid grid-cols-3 gap-4">
              <div className="glass rounded-2xl p-5 border border-[var(--line)] text-center">
                <p className="text-xs font-bold text-orange-400 uppercase tracking-widest mb-2">건폐율 한도</p>
                <p className="text-3xl font-black text-[var(--text-primary)]">{ai.restrictions.buildingCoverage?.max ?? "—"}<span className="text-sm ml-1">{ai.restrictions.buildingCoverage?.unit ?? "%"}</span></p>
              </div>
              <div className="glass rounded-2xl p-5 border border-[var(--line)] text-center">
                <p className="text-xs font-bold text-blue-400 uppercase tracking-widest mb-2">용적률 한도</p>
                <p className="text-3xl font-black text-[var(--text-primary)]">{ai.restrictions.floorAreaRatio?.max ?? "—"}<span className="text-sm ml-1">{ai.restrictions.floorAreaRatio?.unit ?? "%"}</span></p>
              </div>
              <div className="glass rounded-2xl p-5 border border-[var(--line)] text-center">
                <p className="text-xs font-bold text-purple-400 uppercase tracking-widest mb-2">높이 제한</p>
                <p className="text-3xl font-black text-[var(--text-primary)]">{ai.restrictions.heightLimit?.value ?? "—"}<span className="text-sm ml-1">{ai.restrictions.heightLimit?.unit ?? "m"}</span></p>
              </div>
            </div>
          )}

          {/* Applicable Regulations Table */}
          {ai.applicableRegulations && ai.applicableRegulations.length > 0 && (
            <div className="glass rounded-2xl p-6 border border-[var(--line)] overflow-x-auto">
              <h3 className="text-lg font-black text-[var(--text-primary)] mb-4">📋 적용 법규</h3>
              <table className="w-full text-sm">
                <thead><tr className="text-left text-xs font-bold text-[var(--text-tertiary)] uppercase tracking-widest">
                  <th className="pb-3">법률</th><th className="pb-3">조항</th><th className="pb-3">영향</th><th className="pb-3">영향도</th>
                </tr></thead>
                <tbody>
                  {ai.applicableRegulations.map((r, i) => (
                    <tr key={i} className="border-t border-[var(--line)]">
                      <td className="py-3 font-bold text-[var(--text-primary)]">{r.law}</td>
                      <td className="py-3 text-[var(--text-secondary)]">{r.article}</td>
                      <td className="py-3 text-[var(--text-secondary)]">{r.impact}</td>
                      <td className="py-3"><span className={`text-[10px] font-black px-2 py-1 rounded-full ${levelBadge(r.level)}`}>{r.level.toUpperCase()}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Special Zones */}
          {ai.specialZones && ai.specialZones.length > 0 && (
            <div className="glass rounded-2xl p-6 border border-[var(--line)]">
              <h3 className="text-sm font-bold text-[var(--text-primary)] mb-3">🏷️ 해당 특별구역/지구</h3>
              <div className="flex flex-wrap gap-2">
                {ai.specialZones.map((z, i) => <span key={i} className="text-xs font-bold bg-orange-500/10 text-orange-400 px-3 py-1.5 rounded-full border border-orange-500/20">{z}</span>)}
              </div>
            </div>
          )}

          {/* Recommendations */}
          {ai.recommendations && ai.recommendations.length > 0 && (
            <div className="glass rounded-2xl p-6 border border-[var(--line)]">
              <h3 className="text-sm font-bold text-[var(--text-primary)] mb-3">💡 규제 대응 전략</h3>
              <ul className="space-y-2">
                {ai.recommendations.map((r, i) => <li key={i} className="text-sm text-[var(--text-secondary)] flex items-start gap-2"><span className="text-emerald-400 mt-0.5">✓</span>{r}</li>)}
              </ul>
            </div>
          )}

          {ai.summary && (
            <div className="glass rounded-2xl p-6 border border-orange-500/20 bg-orange-500/5">
              <h3 className="text-lg font-black text-orange-400 mb-2">🤖 AI 규제 종합 분석</h3>
              <p className="text-sm text-[var(--text-secondary)] leading-relaxed">{ai.summary}</p>
            </div>
          )}
        </motion.div>
      )}

      {aiResult && !ai && aiResult.text && (
        <div className="glass rounded-2xl p-6 border border-[var(--line)]">
          <h3 className="text-lg font-black text-[var(--text-primary)] mb-2">AI 규제 분석 결과</h3>
          <p className="text-sm text-[var(--text-secondary)] whitespace-pre-wrap leading-relaxed">{aiResult.text}</p>
        </div>
      )}
    </div>
  );
}
