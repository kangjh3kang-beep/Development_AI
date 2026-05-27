"use client";

import React, { useState } from "react";
import { motion } from "framer-motion";
import { useParams } from "next/navigation";
import { useAIAnalyze, useAIReady } from "@/lib/ai-analyze-client";

type DesignResult = {
  buildingCoverage?: { value: number; max: number; unit: string };
  floorAreaRatio?: { value: number; max: number; unit: string };
  maxFloors?: number;
  maxHeight?: { value: number; unit: string };
  totalGrossArea?: { value: number; unit: string };
  parkingRequired?: number;
  setbacks?: { front: number; side: number; rear: number; unit: string };
  massingOptions?: Array<{ name: string; description: string; efficiency: number }>;
  summary?: string;
};

export default function DesignPage() {
  const params = useParams();
  const projectId = (params?.id as string) || "";
  const { isReady } = useAIReady();
  const { mutate, data: aiResult, isPending, error } = useAIAnalyze<DesignResult>();

  const [form, setForm] = useState({
    landArea: "",
    zoning: "제2종일반주거지역",
    buildingUse: "공동주택",
  });

  const handleAnalyze = () => {
    mutate({
      domain: "design",
      context: { landArea: `${form.landArea}㎡`, zoningDistrict: form.zoning, buildingUse: form.buildingUse, projectId },
    });
  };

  const ai = aiResult?.data;

  return (
    <div className="space-y-8 p-6">
      <motion.div initial={{ y: -20, opacity: 0 }} animate={{ y: 0, opacity: 1 }}>
        <h1 className="text-3xl font-black tracking-tight text-[var(--text-primary)]">AI 건축 설계</h1>
        <p className="text-sm text-[var(--text-secondary)] mt-1">법적 한도와 최적 매싱을 AI가 자동 산정합니다</p>
      </motion.div>

      <motion.div initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: 0.1 }} className="glass rounded-3xl p-8 border border-[var(--line-strong)]">
        <h2 className="text-lg font-black text-[var(--text-primary)] mb-6">설계 조건</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)] mb-2 block">대지면적 (㎡)</label>
            <input type="number" placeholder="500" value={form.landArea} onChange={e => setForm(f => ({ ...f, landArea: e.target.value }))}
              className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-4 py-3 text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-strong)]/50" />
          </div>
          <div>
            <label className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)] mb-2 block">용도지역</label>
            <select value={form.zoning} onChange={e => setForm(f => ({ ...f, zoning: e.target.value }))}
              className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-4 py-3 text-sm text-[var(--text-primary)] appearance-none cursor-pointer">
              {["제1종전용주거지역","제2종전용주거지역","제1종일반주거지역","제2종일반주거지역","제3종일반주거지역","준주거지역","일반상업지역","근린상업지역","준공업지역"].map(z => <option key={z} value={z}>{z}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)] mb-2 block">건물용도</label>
            <select value={form.buildingUse} onChange={e => setForm(f => ({ ...f, buildingUse: e.target.value }))}
              className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-4 py-3 text-sm text-[var(--text-primary)] appearance-none cursor-pointer">
              {["공동주택","업무시설","근린생활시설","숙박시설","판매시설","교육연구시설"].map(u => <option key={u} value={u}>{u}</option>)}
            </select>
          </div>
        </div>
        <button onClick={handleAnalyze} disabled={isPending || !isReady || !form.landArea}
          className="mt-6 w-full rounded-2xl bg-gradient-to-r from-blue-600 to-cyan-600 py-4 font-black text-white shadow-lg transition-all hover:scale-[1.01] active:scale-[0.99] disabled:opacity-50 disabled:cursor-not-allowed">
          {isPending ? "🔄 AI 설계 분석 중..." : !isReady ? "⚙️ API 키를 먼저 등록하세요" : "🏗️ AI 설계 분석 실행"}
        </button>
      </motion.div>

      {error && <div className="rounded-2xl bg-red-500/10 border border-red-500/20 p-4"><p className="text-sm text-red-400 font-bold">⚠️ {error.message}</p></div>}

      {ai && (
        <motion.div initial={{ y: 30, opacity: 0 }} animate={{ y: 0, opacity: 1 }} className="space-y-6">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              { label: "건폐율", val: `${ai.buildingCoverage?.value ?? "—"}%`, sub: `최대 ${ai.buildingCoverage?.max ?? "—"}%`, color: "text-blue-400" },
              { label: "용적률", val: `${ai.floorAreaRatio?.value ?? "—"}%`, sub: `최대 ${ai.floorAreaRatio?.max ?? "—"}%`, color: "text-emerald-400" },
              { label: "최고 층수", val: `${ai.maxFloors ?? "—"}층`, sub: `${ai.maxHeight?.value ?? "—"}m`, color: "text-purple-400" },
              { label: "주차 대수", val: `${ai.parkingRequired ?? "—"}대`, sub: "주차장법 기준", color: "text-amber-400" },
            ].map(k => (
              <div key={k.label} className="glass rounded-2xl p-5 border border-[var(--line)] text-center">
                <p className={`text-xs font-bold uppercase tracking-widest ${k.color} mb-2`}>{k.label}</p>
                <p className="text-2xl font-black text-[var(--text-primary)]">{k.val}</p>
                <p className="text-[10px] text-[var(--text-hint)]">{k.sub}</p>
              </div>
            ))}
          </div>

          {ai.totalGrossArea && (
            <div className="glass rounded-2xl p-5 border border-[var(--line)]">
              <p className="text-xs font-bold text-cyan-400 uppercase tracking-widest mb-1">총 연면적</p>
              <p className="text-3xl font-black text-[var(--text-primary)]">{ai.totalGrossArea.value?.toLocaleString()} <span className="text-sm">{ai.totalGrossArea.unit}</span></p>
            </div>
          )}

          {ai.massingOptions && ai.massingOptions.length > 0 && (
            <div className="glass rounded-2xl p-6 border border-[var(--line)]">
              <h3 className="text-lg font-black text-[var(--text-primary)] mb-4">📐 매싱 옵션</h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {ai.massingOptions.map((m, i) => (
                  <div key={i} className="rounded-xl bg-[var(--surface-muted)] border border-[var(--line)] p-4">
                    <p className="text-sm font-bold text-[var(--text-primary)]">{m.name}</p>
                    <p className="text-xs text-[var(--text-secondary)] mt-1">{m.description}</p>
                    <div className="mt-2 flex items-center gap-2">
                      <div className="h-2 flex-1 rounded-full bg-[var(--line)]">
                        <div className="h-2 rounded-full bg-blue-400" style={{ width: `${m.efficiency}%` }} />
                      </div>
                      <span className="text-xs font-bold text-blue-400">{m.efficiency}%</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {ai.summary && (
            <div className="glass rounded-2xl p-6 border border-blue-500/20 bg-blue-500/5">
              <h3 className="text-lg font-black text-blue-400 mb-2">🤖 AI 설계 의견</h3>
              <p className="text-sm text-[var(--text-secondary)] leading-relaxed">{ai.summary}</p>
            </div>
          )}
        </motion.div>
      )}

      {aiResult && !ai && aiResult.text && (
        <div className="glass rounded-2xl p-6 border border-[var(--line)]">
          <h3 className="text-lg font-black text-[var(--text-primary)] mb-2">AI 설계 결과</h3>
          <p className="text-sm text-[var(--text-secondary)] whitespace-pre-wrap leading-relaxed">{aiResult.text}</p>
        </div>
      )}
    </div>
  );
}
