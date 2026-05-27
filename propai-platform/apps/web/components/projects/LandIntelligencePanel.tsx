"use client";

import React, { useCallback, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { useAIAnalyze, useAIReady } from "@/lib/ai-analyze-client";
import { analyzeLocally } from "@/lib/kr-building-regulations";

// ── Icons ──
const Icons = {
  Sparkles: () => <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m12 3 1.912 5.813a2 2 0 0 0 1.275 1.275L21 12l-5.813 1.912a2 2 0 0 0-1.275 1.275L12 21l-1.912-5.813a2 2 0 0 0-1.275-1.275L3 12l5.813-1.912a2 2 0 0 0 1.275-1.275L12 3Z"/><path d="M5 3v4"/><path d="M19 17v4"/><path d="M3 5h4"/><path d="M17 19h4"/></svg>,
  TrendingUp: () => <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/></svg>,
  ArrowRight: () => <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>,
  Map: () => <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14.106 5.553a2 2 0 0 0 1.788 0l3.659-1.83A1 1 0 0 1 21 4.619v12.764a1 1 0 0 1-.553.894l-4.553 2.277a2 2 0 0 1-1.788 0l-4.212-2.106a2 2 0 0 0-1.788 0l-3.659 1.83A1 1 0 0 1 3 19.381V6.618a1 1 0 0 1 .553-.894l4.553-2.277a2 2 0 0 1 1.788 0z"/><path d="M15 5.764v15"/><path d="M9 3.236v15"/></svg>,
  Layers: () => <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"/><path d="m22.54 12.43-1.42-.65-8.28 3.78a2 2 0 0 1-1.66 0l-8.29-3.78-1.42.65a1 1 0 0 0 0 1.84l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.85Z"/><path d="m22.54 16.43-1.42-.65-8.28 3.78a2 2 0 0 1-1.66 0l-8.29-3.78-1.42.65a1 1 0 0 0 0 1.84l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.85Z"/></svg>,
  Building: () => <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect width="16" height="20" x="4" y="2" rx="2" ry="2"/><path d="M9 22v-4h6v4"/><path d="M8 6h.01"/><path d="M16 6h.01"/><path d="M12 6h.01"/><path d="M12 10h.01"/><path d="M12 14h.01"/><path d="M16 10h.01"/><path d="M16 14h.01"/><path d="M8 10h.01"/><path d="M8 14h.01"/></svg>,
  Check: () => <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6 9 17l-5-5"/></svg>,
};

// ── Types ──
type SiteAnalysisResult = {
  zoning?: { current?: string; target?: string; probability?: number; reason?: string };
  characteristics?: Array<{ label: string; value: string; status: string }>;
  scenarios?: Array<{ title: string; score: number; reason: string }>;
  summary?: string;
};

interface LandIntelligencePanelProps {
  projectId: string;
  data: Record<string, string | undefined>;
}

// ── Status badge colors ──
const statusColors: Record<string, string> = {
  safe: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
  warning: "text-amber-400 bg-amber-500/10 border-amber-500/20",
  danger: "text-red-400 bg-red-500/10 border-red-500/20",
};

// ── Bottom Tab Pages ──
type BottomTab = "pnu" | "price" | "transaction" | "gis";

export function LandIntelligencePanel({ projectId, data }: LandIntelligencePanelProps) {
  const displayAddress = data?.address || "분석 대상 주소를 입력하세요";
  const displayPnu = data?.pnu || "—";
  const { isReady } = useAIReady();
  const { mutate: runAnalysis, data: aiResult, isPending: isAnalyzing, error: aiError } = useAIAnalyze<SiteAnalysisResult>();
  const [activeTab, setActiveTab] = useState<BottomTab>("pnu");

  // ── 1) 로컬 계산 엔진 (LLM 없이 즉시 계산) ──
  const localResult = useMemo(() => {
    if (!data?.address) return null;
    return analyzeLocally(data.address, data.pnu);
  }, [data?.address, data?.pnu]);

  // ── 2) AI 분석 (선택적 보강) ──
  const triggerAnalysis = useCallback(() => {
    if (!data?.address || !isReady) return;
    runAnalysis({
      domain: "site-analysis",
      context: { address: data.address, pnu: data.pnu || "", projectId },
    });
  }, [data?.address, data?.pnu, isReady, projectId, runAnalysis]);

  // ── 3) 데이터 통합: AI 결과 > 로컬 계산 > 기본값 ──
  const aiData = aiResult?.data;
  const analysis = {
    zoning: {
      current: aiData?.zoning?.current || localResult?.zoningName || "용도지역 분석 대기",
      target: aiData?.zoning?.target || (localResult ? `${localResult.zoningCategory}지역 상위 변경` : "—"),
      possibility: aiData?.zoning?.probability ?? (localResult ? 35 : 0),
      reason: aiData?.zoning?.reason || localResult?.summary || "주소를 입력하세요",
    },
    characteristics: aiData?.characteristics?.map(c => ({
      label: c.label,
      value: c.value,
      status: c.status as "safe" | "warning" | "danger",
    })) || localResult?.characteristics || [
      { label: "경사도", value: "—", status: "safe" as const },
      { label: "접도 상태", value: "—", status: "safe" as const },
      { label: "지형", value: "—", status: "safe" as const },
      { label: "높이 제한", value: "—", status: "warning" as const },
    ],
    scenarios: aiData?.scenarios?.map(s => ({
      title: s.title,
      score: s.score,
      reason: s.reason,
    })) || localResult?.scenarios || [],
    summary: aiData?.summary || localResult?.summary || null,
    buildingCoverageMax: localResult?.buildingCoverageMax ?? 0,
    floorAreaRatioMax: localResult?.floorAreaRatioMax ?? 0,
    heightLimit: localResult?.heightLimit,
  };

  const hasData = !!localResult;

  return (
    <div className="relative min-h-[800px] w-full overflow-hidden rounded-[3rem] border border-[var(--line)] bg-[var(--surface-strong)] shadow-[var(--shadow-xl)]">
      {/* Background */}
      <div className="absolute inset-0 opacity-40" style={{ zIndex: 0 }}>
        <div className="absolute inset-0 bg-gradient-to-br from-blue-900/20 via-slate-800/30 to-emerald-900/20" />
        <div className="absolute inset-0 bg-[conic-gradient(from_0deg_at_50%_50%,transparent_0deg,rgba(59,130,246,0.05)_60deg,transparent_120deg,rgba(16,185,129,0.05)_180deg,transparent_240deg,rgba(99,102,241,0.05)_300deg,transparent_360deg)]" />
      </div>
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,transparent_0%,var(--background)_90%)]" style={{ zIndex: 1 }} />
      <div className="absolute inset-0 bg-[linear-gradient(var(--line)_1px,transparent_1px),linear-gradient(90deg,var(--line)_1px,transparent_1px)] bg-[size:40px_40px] opacity-10 dark:opacity-30" style={{ zIndex: 1 }} />

      {/* === LEFT PANEL: Analysis === */}
      <div className="absolute left-8 top-8 z-10 w-[400px] space-y-5" style={{ zIndex: 20 }}>
        <motion.div initial={{ x: -20, opacity: 0 }} animate={{ x: 0, opacity: 1 }}
          className="glass rounded-[2rem] p-7 border border-[var(--line-strong)] shadow-[var(--shadow-xl)]">
          {/* Header */}
          <div className="flex items-center gap-3 mb-5">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[var(--accent-soft)] text-[var(--accent-strong)]"><Icons.Sparkles /></div>
            <div>
              <h4 className="text-lg font-black text-[var(--text-primary)] tracking-tight">지능형 입지 분석</h4>
              <p className="text-[10px] font-black uppercase tracking-[0.2em] flex items-center gap-1">
                {isAnalyzing ? (<><span className="inline-block h-1.5 w-1.5 rounded-full bg-amber-400 animate-pulse" /><span className="text-amber-400">AI 분석 중...</span></>) :
                 aiData ? (<><span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-400" /><span className="text-emerald-400">AI 분석 완료</span></>) :
                 hasData ? (<><span className="inline-block h-1.5 w-1.5 rounded-full bg-blue-400" /><span className="text-blue-400">법규 기반 분석 완료</span></>) :
                 (<><span className="inline-block h-1.5 w-1.5 rounded-full bg-slate-400" /><span className="text-[var(--accent-strong)]">대기 중</span></>)}
              </p>
            </div>
          </div>

          {/* Zoning & Regulation KPI */}
          <div className="space-y-4">
            {/* Building Coverage & FAR */}
            {hasData && (
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-xl bg-[var(--surface-muted)] p-4 border border-[var(--line)] text-center">
                  <p className="text-[9px] font-black text-blue-400 uppercase tracking-widest mb-1">건폐율 한도</p>
                  <p className="text-2xl font-black text-[var(--text-primary)]">{analysis.buildingCoverageMax}<span className="text-xs ml-0.5">%</span></p>
                </div>
                <div className="rounded-xl bg-[var(--surface-muted)] p-4 border border-[var(--line)] text-center">
                  <p className="text-[9px] font-black text-emerald-400 uppercase tracking-widest mb-1">용적률 한도</p>
                  <p className="text-2xl font-black text-[var(--text-primary)]">{analysis.floorAreaRatioMax}<span className="text-xs ml-0.5">%</span></p>
                </div>
              </div>
            )}

            {/* Zoning */}
            <div className="rounded-xl bg-[var(--surface-muted)] p-4 border border-[var(--line)]">
              <p className="text-[9px] font-black text-[var(--accent-strong)] mb-2 uppercase tracking-widest flex items-center gap-1.5"><Icons.TrendingUp />용도지역</p>
              <p className="text-lg font-black text-[var(--text-primary)] mb-1">{analysis.zoning.current}</p>
              <p className="text-[10px] text-[var(--text-secondary)] font-medium leading-relaxed">{analysis.zoning.reason}</p>
            </div>

            {/* Land Characteristics */}
            <div className="rounded-xl bg-[var(--surface-muted)] p-4 border border-[var(--line)]">
              <p className="text-[9px] font-black text-blue-400 mb-3 uppercase tracking-widest">토지 형질 분석</p>
              <div className="grid grid-cols-2 gap-2">
                {analysis.characteristics.slice(0, 4).map((c, i) => (
                  <div key={i} className={`flex flex-col gap-1 rounded-lg border p-2 ${statusColors[c.status] || statusColors.safe}`}>
                    <span className="text-[9px] font-black uppercase tracking-tighter opacity-80">{c.label}</span>
                    <span className="text-xs font-bold">{c.value}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Error */}
          {aiError && (
            <div className="mt-3 rounded-xl bg-red-500/10 border border-red-500/20 p-3">
              <p className="text-xs text-red-400 font-medium">{aiError.message}</p>
            </div>
          )}

          {/* AI Summary (when available) */}
          {aiData?.summary && (
            <div className="mt-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 p-3">
              <p className="text-[9px] font-black text-emerald-400 mb-1 uppercase tracking-widest">🤖 AI 종합 의견</p>
              <p className="text-xs text-[var(--text-secondary)] leading-relaxed">{aiData.summary}</p>
            </div>
          )}

          {/* AI Button */}
          <button onClick={triggerAnalysis} disabled={isAnalyzing || !isReady || !data?.address}
            className="mt-4 flex w-full items-center justify-center gap-2 rounded-2xl bg-teal-500 py-3.5 text-sm font-black text-[#0a0f14] shadow-[0_0_30px_rgba(45,212,191,0.3)] transition-all hover:scale-[1.02] hover:brightness-110 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed">
            {isAnalyzing ? "AI 심층 분석 중..." : isReady ? "🤖 AI 심층 분석 실행" : "⚙️ API 키를 먼저 등록하세요"}
            <Icons.ArrowRight />
          </button>
        </motion.div>
      </div>

      {/* === RIGHT PANEL: Scenarios === */}
      <div className="absolute right-8 top-8 z-10 w-[380px] flex flex-col gap-5" style={{ zIndex: 20 }}>
        <motion.div initial={{ x: 20, opacity: 0 }} animate={{ x: 0, opacity: 1 }} transition={{ delay: 0.15 }}
          className="glass rounded-[2rem] p-7 border border-[var(--line-strong)] shadow-[var(--shadow-xl)]">
          <div className="flex items-center justify-between mb-6">
            <h4 className="text-lg font-black text-[var(--text-primary)] tracking-tight">
              {aiData ? "AI 최적 개발 시나리오" : "법규 기반 개발 시나리오"}
            </h4>
            <div className={`h-2 w-2 rounded-full ${hasData ? "bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,1)]" : "bg-slate-500"} animate-pulse`} />
          </div>

          <div className="space-y-5">
            {analysis.scenarios.length > 0 ? analysis.scenarios.map((s, i) => (
              <div key={i} className="group relative">
                <div className="flex items-start justify-between mb-2">
                  <div className="flex flex-col gap-1 flex-1 mr-3">
                    <span className="text-base font-[900] text-[var(--text-primary)] group-hover:text-[var(--accent-strong)] transition-colors">{s.title}</span>
                    <span className="text-[10px] text-[var(--text-hint)] font-medium leading-snug">{s.reason}</span>
                  </div>
                  <span className={`text-2xl font-black ${s.score >= 80 ? "text-emerald-400" : s.score >= 50 ? "text-amber-400" : "text-red-400"}`}>{s.score}%</span>
                </div>
                <div className="h-1.5 w-full rounded-full bg-[var(--line)] overflow-hidden">
                  <motion.div initial={{ width: 0 }} animate={{ width: `${s.score}%` }} transition={{ duration: 1.2, delay: 0.3 + i * 0.15 }}
                    className={`h-full rounded-full ${s.score >= 80 ? "bg-gradient-to-r from-emerald-500 to-teal-400" : s.score >= 50 ? "bg-gradient-to-r from-amber-500 to-orange-400" : "bg-gradient-to-r from-red-500 to-pink-400"}`} />
                </div>
              </div>
            )) : (
              <p className="text-sm text-[var(--text-hint)] text-center py-6">주소를 입력하면 자동 분석됩니다</p>
            )}
          </div>
        </motion.div>

        {/* Parcel Info */}
        <motion.div initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: 0.3 }}
          className="glass rounded-[2rem] p-5 border border-[var(--line)] bg-[var(--surface-muted)]">
          <div className="flex items-center gap-3 mb-3">
            <div className="h-8 w-8 flex items-center justify-center rounded-lg bg-[var(--line)] text-[var(--text-tertiary)]"><Icons.Map /></div>
            <span className="text-[10px] font-black text-[var(--text-hint)] uppercase tracking-widest">{displayPnu !== "—" ? `PNU: ${displayPnu}` : "PNU: 주소 입력 시 자동 매핑"}</span>
          </div>
          <div className="px-2">
            <p className="text-sm font-bold text-[var(--text-secondary)]">{displayAddress}</p>
            {hasData && <p className="text-[10px] text-emerald-400 mt-1 font-bold">✓ {analysis.zoning.current} · 건폐율 {analysis.buildingCoverageMax}% · 용적률 {analysis.floorAreaRatioMax}%</p>}
          </div>
        </motion.div>
      </div>

      {/* === CENTER: Lot Visualization === */}
      <div className="pointer-events-none absolute inset-0 z-0 flex items-center justify-center" style={{ zIndex: 10 }}>
        <motion.div initial={{ scale: 0.5, opacity: 0, rotate: -20 }} animate={{ scale: 1, opacity: 1, rotate: 15 }} transition={{ type: "spring", stiffness: 100, damping: 15 }} className="relative">
          <div className="absolute inset-0 -m-8 rounded-2xl border-4 border-teal-500/20 blur-xl animate-pulse" />
          <div className="h-56 w-56 rounded-2xl border-[3px] border-teal-400 bg-teal-500/10 backdrop-blur-md flex items-center justify-center relative overflow-hidden">
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(45,212,191,0.2),transparent_70%)]" />
            <Icons.Building />
          </div>
          {hasData && (
            <div className="absolute -top-10 -right-10 glass rounded-xl px-3 py-1.5 text-[10px] font-black text-emerald-400 border border-emerald-500/20 shadow-lg">
              용적률 {analysis.floorAreaRatioMax}%
            </div>
          )}
        </motion.div>
      </div>

      {/* === BOTTOM TABS === */}
      <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-10 w-[calc(100%-64px)]" style={{ zIndex: 20 }}>
        {/* Tab Bar */}
        <div className="flex justify-center gap-1 rounded-2xl bg-[var(--background)]/80 backdrop-blur-xl border border-[var(--line-strong)] p-1.5 shadow-[var(--shadow-xl)] mb-3 w-fit mx-auto">
          {([
            { key: "pnu" as const, label: "상세 지적(PNU)" },
            { key: "price" as const, label: "공시지가 추이" },
            { key: "transaction" as const, label: "인근 실거래가" },
          ]).map(tab => (
            <button key={tab.key} onClick={() => setActiveTab(tab.key)}
              className={`rounded-xl px-4 py-2 text-xs font-black transition-all whitespace-nowrap ${
                activeTab === tab.key ? "text-white bg-[var(--accent-strong)] shadow-md" : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"}`}>
              {tab.label}
            </button>
          ))}
          <div className="w-px h-4 bg-[var(--line-strong)] mx-2 self-center" />
          <button onClick={() => setActiveTab("gis")}
            className={`flex items-center gap-2 rounded-xl px-4 py-2 text-xs font-black whitespace-nowrap ${activeTab === "gis" ? "text-white bg-[var(--accent-strong)] shadow-md" : "text-[var(--accent-strong)]"}`}>
            <Icons.Layers /> GIS layers
          </button>
        </div>

        {/* Tab Content */}
        {hasData && (
          <motion.div initial={{ y: 10, opacity: 0 }} animate={{ y: 0, opacity: 1 }}
            className="glass rounded-2xl p-4 border border-[var(--line)] max-h-[140px] overflow-y-auto">
            {activeTab === "pnu" && (
              <div className="grid grid-cols-4 gap-3 text-xs">
                <div><p className="text-[9px] font-black text-[var(--text-hint)] uppercase">용도지역</p><p className="font-bold text-[var(--text-primary)] mt-1">{analysis.zoning.current}</p></div>
                <div><p className="text-[9px] font-black text-[var(--text-hint)] uppercase">건폐율</p><p className="font-bold text-[var(--text-primary)] mt-1">{analysis.buildingCoverageMax}%</p></div>
                <div><p className="text-[9px] font-black text-[var(--text-hint)] uppercase">용적률</p><p className="font-bold text-[var(--text-primary)] mt-1">{analysis.floorAreaRatioMax}%</p></div>
                <div><p className="text-[9px] font-black text-[var(--text-hint)] uppercase">높이제한</p><p className="font-bold text-[var(--text-primary)] mt-1">{analysis.heightLimit ? `${analysis.heightLimit}m` : "없음"}</p></div>
              </div>
            )}
            {activeTab === "price" && (
              <div className="text-xs text-[var(--text-secondary)]">
                <p className="text-[9px] font-black text-amber-400 uppercase mb-2">공시지가 추이 (추정)</p>
                <div className="flex items-end gap-1 h-16">
                  {[65, 72, 68, 78, 85, 92, 100].map((v, i) => (
                    <div key={i} className="flex-1 flex flex-col items-center gap-1">
                      <div className="w-full bg-gradient-to-t from-amber-500 to-amber-300 rounded-t" style={{ height: `${v}%` }} />
                      <span className="text-[8px] text-[var(--text-hint)]">{2020 + i}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {activeTab === "transaction" && (
              <div className="text-xs">
                <p className="text-[9px] font-black text-blue-400 uppercase mb-2">인근 실거래가 (추정)</p>
                <div className="space-y-1.5">
                  {[
                    { date: "2026.04", type: "토지", area: "330㎡", price: "9.2억" },
                    { date: "2026.02", type: "토지", area: "280㎡", price: "7.8억" },
                    { date: "2025.12", type: "아파트", area: "84㎡", price: "6.1억" },
                  ].map((t, i) => (
                    <div key={i} className="flex items-center justify-between text-[var(--text-secondary)] bg-[var(--surface-muted)] rounded-lg px-3 py-1.5">
                      <span>{t.date}</span><span className="text-[var(--text-hint)]">{t.type} · {t.area}</span><span className="font-bold text-[var(--text-primary)]">{t.price}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {activeTab === "gis" && (
              <div className="flex items-center gap-4 text-xs">
                {[
                  { label: "용도지역", checked: true },
                  { label: "도로망", checked: true },
                  { label: "지적도", checked: false },
                  { label: "항공사진", checked: false },
                  { label: "등고선", checked: false },
                ].map((layer, i) => (
                  <label key={i} className="flex items-center gap-1.5 cursor-pointer">
                    <div className={`h-4 w-4 rounded border flex items-center justify-center ${layer.checked ? "bg-teal-500 border-teal-500 text-white" : "border-[var(--line-strong)]"}`}>
                      {layer.checked && <Icons.Check />}
                    </div>
                    <span className="text-[var(--text-secondary)] font-bold">{layer.label}</span>
                  </label>
                ))}
              </div>
            )}
          </motion.div>
        )}
      </div>
    </div>
  );
}
