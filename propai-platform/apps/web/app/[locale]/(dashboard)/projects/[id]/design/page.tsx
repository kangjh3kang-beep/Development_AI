"use client";

import React, { useState, useMemo } from "react";
import { motion } from "framer-motion";
import { useParams } from "next/navigation";
import { useAIAnalyze, useAIReady } from "@/lib/ai-analyze-client";
import { getZoningSpec, calcMaxGrossArea, calcParkingRequired } from "@/lib/kr-building-regulations";

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
    landArea: "500",
    zoning: "제2종일반주거지역",
    buildingUse: "공동주택",
  });

  // ── 로컬 계산 (즉시) ──
  const localCalc = useMemo(() => {
    const area = Number(form.landArea) || 0;
    const spec = getZoningSpec(form.zoning);
    if (!spec || area <= 0) return null;

    const maxGross = calcMaxGrossArea(area, form.zoning);
    const parking = calcParkingRequired(maxGross, form.buildingUse);
    const buildableArea = area * (spec.buildingCoverageMax / 100);
    const maxFloors = spec.floorAreaRatioMax > 0 ? Math.floor(maxGross / buildableArea) : 1;
    const heightPerFloor = 3.3;
    const maxHeight = spec.heightLimit || (maxFloors * heightPerFloor);

    return {
      buildingCoverage: spec.buildingCoverageMax,
      floorAreaRatio: spec.floorAreaRatioMax,
      maxFloors,
      maxHeight: Math.round(maxHeight * 10) / 10,
      buildableArea: Math.round(buildableArea * 10) / 10,
      maxGrossArea: Math.round(maxGross * 10) / 10,
      parking,
      setbacks: { front: 6, side: 1.5, rear: 2, unit: "m" },
      massingOptions: [
        { name: "판상형", description: `${maxFloors}층 2개동, 남향 배치`, efficiency: 78 },
        { name: "타워형", description: `${maxFloors + 2}층 1개동, 중앙코어`, efficiency: 72 },
        { name: "ㄱ자형", description: `${maxFloors}층, 소음차폐 배치`, efficiency: 75 },
      ],
    };
  }, [form.landArea, form.zoning, form.buildingUse]);

  const handleAIAnalyze = () => {
    mutate({
      domain: "design",
      context: { landArea: `${form.landArea}㎡`, zoningDistrict: form.zoning, buildingUse: form.buildingUse, projectId },
    });
  };

  // AI > 로컬 통합
  const ai = aiResult?.data;
  const calc = localCalc;

  return (
    <div className="space-y-8 p-6">
      <motion.div initial={{ y: -20, opacity: 0 }} animate={{ y: 0, opacity: 1 }}>
        <h1 className="text-3xl font-black tracking-tight text-[var(--text-primary)]">AI 건축 설계</h1>
        <p className="text-sm text-[var(--text-secondary)] mt-1">한국 건축법 기반 즉시 계산 + AI 심층 분석</p>
      </motion.div>

      {/* Input */}
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
        <button onClick={handleAIAnalyze} disabled={isPending || !isReady || !form.landArea}
          className="mt-6 w-full rounded-2xl bg-gradient-to-r from-blue-600 to-cyan-600 py-4 font-black text-white shadow-lg transition-all hover:scale-[1.01] active:scale-[0.99] disabled:opacity-50 disabled:cursor-not-allowed">
          {isPending ? "🔄 AI 심층 분석 중..." : !isReady ? "⚙️ API 키를 먼저 등록하세요 (아래 법규 계산은 즉시 가능)" : "🤖 AI 심층 설계 분석 실행"}
        </button>
      </motion.div>

      {error && <div className="rounded-2xl bg-red-500/10 border border-red-500/20 p-4"><p className="text-sm text-red-400 font-bold">⚠️ {error.message}</p></div>}

      {/* Results — 로컬 계산 즉시 표시 */}
      {calc && (
        <motion.div initial={{ y: 30, opacity: 0 }} animate={{ y: 0, opacity: 1 }} className="space-y-6">
          {/* Source indicator */}
          <div className="flex items-center gap-2">
            <span className={`inline-block h-2 w-2 rounded-full ${ai ? "bg-emerald-400" : "bg-blue-400"}`} />
            <span className="text-xs font-bold text-[var(--text-secondary)]">{ai ? "AI 분석 결과 반영됨" : "한국 건축법/국토계획법 기반 자동 계산"}</span>
          </div>

          {/* KPI Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              { label: "건폐율", val: `${ai?.buildingCoverage?.value ?? calc.buildingCoverage}%`, sub: `최대 ${ai?.buildingCoverage?.max ?? calc.buildingCoverage}%`, color: "text-blue-400" },
              { label: "용적률", val: `${ai?.floorAreaRatio?.value ?? calc.floorAreaRatio}%`, sub: `최대 ${ai?.floorAreaRatio?.max ?? calc.floorAreaRatio}%`, color: "text-emerald-400" },
              { label: "최고 층수", val: `${ai?.maxFloors ?? calc.maxFloors}층`, sub: `${ai?.maxHeight?.value ?? calc.maxHeight}m`, color: "text-purple-400" },
              { label: "주차 대수", val: `${ai?.parkingRequired ?? calc.parking}대`, sub: "주차장법 기준", color: "text-amber-400" },
            ].map(k => (
              <div key={k.label} className="glass rounded-2xl p-5 border border-[var(--line)] text-center">
                <p className={`text-xs font-bold uppercase tracking-widest ${k.color} mb-2`}>{k.label}</p>
                <p className="text-2xl font-black text-[var(--text-primary)]">{k.val}</p>
                <p className="text-[10px] text-[var(--text-hint)]">{k.sub}</p>
              </div>
            ))}
          </div>

          {/* Gross Area & Buildable Area */}
          <div className="grid grid-cols-2 gap-4">
            <div className="glass rounded-2xl p-5 border border-[var(--line)]">
              <p className="text-xs font-bold text-cyan-400 uppercase tracking-widest mb-1">최대 연면적</p>
              <p className="text-3xl font-black text-[var(--text-primary)]">{(ai?.totalGrossArea?.value ?? calc.maxGrossArea).toLocaleString()} <span className="text-sm">㎡</span></p>
            </div>
            <div className="glass rounded-2xl p-5 border border-[var(--line)]">
              <p className="text-xs font-bold text-orange-400 uppercase tracking-widest mb-1">건축가능면적</p>
              <p className="text-3xl font-black text-[var(--text-primary)]">{calc.buildableArea.toLocaleString()} <span className="text-sm">㎡</span></p>
            </div>
          </div>

          {/* Setbacks */}
          <div className="glass rounded-2xl p-6 border border-[var(--line)]">
            <h3 className="text-sm font-black text-[var(--text-primary)] mb-3">📏 건축선 이격거리</h3>
            <div className="grid grid-cols-3 gap-4 text-center">
              {[
                { label: "전면", val: ai?.setbacks?.front ?? calc.setbacks.front },
                { label: "측면", val: ai?.setbacks?.side ?? calc.setbacks.side },
                { label: "후면", val: ai?.setbacks?.rear ?? calc.setbacks.rear },
              ].map(s => (
                <div key={s.label} className="rounded-xl bg-[var(--surface-muted)] p-3 border border-[var(--line)]">
                  <p className="text-[10px] font-bold text-[var(--text-hint)] uppercase">{s.label}</p>
                  <p className="text-xl font-black text-[var(--text-primary)]">{s.val}<span className="text-xs ml-0.5">m</span></p>
                </div>
              ))}
            </div>
          </div>

          {/* Massing Options */}
          <div className="glass rounded-2xl p-6 border border-[var(--line)]">
            <h3 className="text-lg font-black text-[var(--text-primary)] mb-4">📐 매싱 옵션</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {(ai?.massingOptions || calc.massingOptions).map((m, i) => (
                <div key={i} className="rounded-xl bg-[var(--surface-muted)] border border-[var(--line)] p-4">
                  <p className="text-sm font-bold text-[var(--text-primary)]">{m.name}</p>
                  <p className="text-xs text-[var(--text-secondary)] mt-1">{m.description}</p>
                  <div className="mt-2 flex items-center gap-2">
                    <div className="h-2 flex-1 rounded-full bg-[var(--line)]"><div className="h-2 rounded-full bg-blue-400" style={{ width: `${m.efficiency}%` }} /></div>
                    <span className="text-xs font-bold text-blue-400">{m.efficiency}%</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* AI Summary */}
          {ai?.summary && (
            <div className="glass rounded-2xl p-6 border border-blue-500/20 bg-blue-500/5">
              <h3 className="text-lg font-black text-blue-400 mb-2">🤖 AI 설계 의견</h3>
              <p className="text-sm text-[var(--text-secondary)] leading-relaxed">{ai.summary}</p>
            </div>
          )}

          {aiResult && !ai && aiResult.text && (
            <div className="glass rounded-2xl p-6 border border-[var(--line)]">
              <h3 className="text-sm font-black text-[var(--text-primary)] mb-2">AI 설계 결과</h3>
              <p className="text-sm text-[var(--text-secondary)] whitespace-pre-wrap leading-relaxed">{aiResult.text}</p>
            </div>
          )}
        </motion.div>
      )}
    </div>
  );
}
