"use client";

import React from "react";
import { motion } from "framer-motion";
const Icons = {
  TrendingUp: () => <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/></svg>,
  Map: () => <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="3 6 9 3 15 6 21 3 21 18 15 21 9 18 3 21"/><line x1="9" y1="3" x2="9" y2="18"/><line x1="15" y1="6" x2="15" y2="21"/></svg>,
  Layers: () => <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>,
  Cpu: () => <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect width="16" height="16" x="4" y="4" rx="2"/><rect width="6" height="6" x="9" y="9" rx="1"/><path d="M15 2v2"/><path d="M15 20v2"/><path d="M2 15h2"/><path d="M2 9h2"/><path d="M20 15h2"/><path d="M20 9h2"/><path d="M9 2v2"/><path d="M9 20v2"/></svg>,
  Help: () => <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><path d="M12 17h.01"/></svg>,
  Alert: () => <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>,
  Check: () => <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>,
  ArrowRight: () => <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>,
  Sparkles: () => <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m12 3 1.912 5.813a2 2 0 0 0 1.275 1.275L21 12l-5.813 1.912a2 2 0 0 0-1.275 1.275L12 21l-1.912-5.813a2 2 0 0 0-1.275-1.275L3 12l5.813-1.912a2 2 0 0 0 1.275-1.275L12 3Z"/><path d="M5 3v4"/><path d="M19 17v4"/><path d="M3 5h4"/><path d="M17 19h4"/></svg>,
  Info: () => <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>,
  AlertTriangle: () => <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>,
};

interface LandIntelligencePanelProps {
  projectId: string;
  data: Record<string, string | undefined>;
}

export function LandIntelligencePanel({ projectId, data }: LandIntelligencePanelProps) {
  const displayAddress = data?.address || "분석 대상 주소를 입력하세요";
  const displayPnu = data?.pnu || "—";
  const analysis = {
    zoning: {
      current: data?.zoning || "용도지역 분석 중",
      target: data?.targetZoning || "일반상업지역",
      possibility: data?.zoningProbability ? Number(data.zoningProbability) : 0,
      reason: data?.address ? `${data.address} 인근 개발 계획 및 지자체 조례 반영` : "API 연동 후 자동 분석됩니다",
    },
    characteristics: [
      { label: "경사도", value: data?.slope || "—", status: "safe" as const },
      { label: "접도 상태", value: data?.roadAccess || "—", status: "safe" as const },
      { label: "지형", value: data?.landShape || "—", status: "safe" as const },
      { label: "고도 제한", value: data?.heightLimit || "—", status: "warning" as const },
    ],
    optimalModes: [
      { title: data?.scenario1Name || "시나리오 1", match: data?.scenario1Score ? Number(data.scenario1Score) : 0, reason: data?.scenario1Reason || "분석 결과 대기 중" },
      { title: data?.scenario2Name || "시나리오 2", match: data?.scenario2Score ? Number(data.scenario2Score) : 0, reason: data?.scenario2Reason || "분석 결과 대기 중" },
      { title: data?.scenario3Name || "시나리오 3", match: data?.scenario3Score ? Number(data.scenario3Score) : 0, reason: data?.scenario3Reason || "분석 결과 대기 중" },
    ],
  };

  return (
    <div className="relative min-h-[800px] w-full overflow-hidden rounded-[3rem] border border-[var(--line)] bg-[var(--surface-strong)] shadow-[var(--shadow-xl)]">
      {/* Background GIS Map Layer (Simulated) */}
      <div className="absolute inset-0 opacity-40 grayscale contrast-125 dark:invert dark:brightness-75" style={{ zIndex: 0 }}>
        <div className="absolute inset-0 bg-[url('https://images.unsplash.com/photo-1477959858617-67f85cf4f1df?auto=format&fit=crop&q=80&w=1600')] bg-cover bg-center" />
        <div className="absolute inset-0 bg-blue-900/10 mix-blend-overlay dark:bg-blue-900/20" />
      </div>

      {/* Grid Overlay */}
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,transparent_0%,var(--background)_90%)]" style={{ zIndex: 1 }} />
      <div className="absolute inset-0 bg-[linear-gradient(var(--line)_1px,transparent_1px),linear-gradient(90deg,var(--line)_1px,transparent_1px)] bg-[size:40px_40px] opacity-10 dark:opacity-30" style={{ zIndex: 1 }} />

      {/* Floating HUD - Left Side: Analysis Note */}
      <div className="absolute left-8 top-8 z-10 w-[380px] space-y-6" style={{ zIndex: 20 }}>
        <motion.div 
          initial={{ x: -20, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          className="glass rounded-[2rem] p-8 border border-[var(--line-strong)] shadow-[var(--shadow-xl)]"
        >
          <div className="flex items-center gap-3 mb-6">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[var(--accent-soft)] text-[var(--accent-strong)] shadow-sm">
              <Icons.Sparkles />
            </div>
            <div>
              <h4 className="text-xl font-black text-[var(--text-primary)] tracking-tight">지능형 입지 분석</h4>
              <p className="text-[10px] font-black text-[var(--accent-strong)] uppercase tracking-[0.2em]">AI Intelligence Node</p>
            </div>
          </div>

          <div className="space-y-4">
             <div className="rounded-2xl bg-[var(--surface-muted)] p-5 border border-[var(--line)]">
                <p className="text-xs font-black text-[var(--accent-strong)] mb-2 uppercase tracking-widest flex items-center gap-2">
                  <Icons.TrendingUp />
                  종변경 예측 (Zoning Change)
                </p>
                <div className="flex items-end gap-3 mb-2">
                   <span className="text-4xl font-black text-[var(--text-primary)]">{analysis.zoning.possibility}%</span>
                   <span className="text-xs font-bold text-[var(--accent-strong)]/60 pb-1">Probability</span>
                </div>
                <p className="text-xs leading-relaxed text-[var(--text-secondary)] font-medium">
                  {analysis.zoning.reason}
                </p>
             </div>

             <div className="rounded-2xl bg-[var(--surface-muted)] p-5 border border-[var(--line)]">
                <p className="text-xs font-black text-blue-500 mb-3 uppercase tracking-widest">토지 형질 요약</p>
                <div className="grid grid-cols-2 gap-3">
                   {analysis.characteristics.slice(0, 4).map((c, i) => (
                     <div key={i} className="flex flex-col gap-1">
                        <span className="text-[9px] font-black text-[var(--text-hint)] uppercase tracking-tighter">{c.label}</span>
                        <span className="text-xs font-bold text-[var(--text-primary)]/90">{c.value}</span>
                     </div>
                   ))}
                </div>
             </div>
          </div>

          <button className="mt-8 flex w-full items-center justify-center gap-3 rounded-2xl bg-teal-500 py-4 font-black text-[#0a0f14] shadow-[0_0_30px_rgba(45,212,191,0.4)] transition-all hover:scale-[1.02] hover:brightness-110 active:scale-[0.98]">
             심층 데이터 리포트 (PDF)
             <Icons.ArrowRight />
          </button>
        </motion.div>
      </div>

      {/* Floating HUD - Right Side: Optimal Strategy */}
      <div className="absolute right-8 top-8 z-10 w-[400px] flex flex-col gap-6" style={{ zIndex: 20 }}>
        <motion.div 
          initial={{ x: 20, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          transition={{ delay: 0.2 }}
          className="glass rounded-[2rem] p-8 border border-[var(--line-strong)] shadow-[var(--shadow-xl)]"
        >
          <div className="flex items-center justify-between mb-8">
            <h4 className="text-xl font-black text-[var(--text-primary)] tracking-tight">AI 권장 개발 시나리오</h4>
            <div className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse shadow-[0_0_10px_rgba(16,185,129,1)]" />
          </div>

          <div className="space-y-6">
            {analysis.optimalModes.map((mode, i) => (
              <div key={i} className="group relative">
                <div className="flex items-start justify-between mb-2">
                  <div className="flex flex-col gap-1">
                    <span className="text-lg font-[900] text-[var(--text-primary)] group-hover:text-[var(--accent-strong)] transition-colors">{mode.title}</span>
                    <span className="text-[10px] text-[var(--text-hint)] font-medium leading-tight">{mode.reason}</span>
                  </div>
                  <span className="text-2xl font-black text-[var(--accent-strong)]">{mode.match}%</span>
                </div>
                <div className="h-1.5 w-full rounded-full bg-[var(--line)] overflow-hidden">
                  <motion.div 
                    initial={{ width: 0 }}
                    animate={{ width: `${mode.match}%` }}
                    transition={{ duration: 1.5, delay: 0.5 + i * 0.1 }}
                    className="h-full bg-gradient-to-r from-[var(--accent-strong)] to-blue-500"
                  />
                </div>
              </div>
            ))}
          </div>
        </motion.div>

        {/* Parcel Information Detail */}
        <motion.div
           initial={{ y: 20, opacity: 0 }}
           animate={{ y: 0, opacity: 1 }}
           transition={{ delay: 0.4 }}
           className="glass rounded-[2rem] p-6 border border-[var(--line)] bg-[var(--surface-muted)]"
        >
           <div className="flex items-center gap-3 mb-4">
              <div className="h-8 w-8 flex items-center justify-center rounded-lg bg-[var(--line)] text-[var(--text-tertiary)] hover:text-[var(--text-primary)] transition-colors">
                <Icons.Map />
              </div>
              <span className="text-[10px] font-black text-[var(--text-hint)] uppercase tracking-widest">{displayPnu !== "—" ? `PNU: ${displayPnu}` : "PNU: API 연동 대기"}</span>
           </div>
           <div className="px-2">
              <p className="text-sm font-bold text-[var(--text-secondary)]">{displayAddress}</p>
              <p className="text-[9px] text-[var(--text-hint)] mt-1 uppercase font-black">Official Lot Address (KDX Data Synced)</p>
           </div>
        </motion.div>
      </div>

      {/* Center Focus: parcel shape (Simplified SVG) */}
      <div className="pointer-events-none absolute inset-0 z-0 flex items-center justify-center" style={{ zIndex: 10 }}>
         <motion.div
            initial={{ scale: 0.5, opacity: 0, rotate: -20 }}
            animate={{ scale: 1, opacity: 1, rotate: 15 }}
            transition={{ type: "spring", stiffness: 100, damping: 15 }}
            className="relative"
         >
            {/* Pulsing effect */}
            <div className="absolute inset-0 -m-8 rounded-2xl border-4 border-teal-500/20 blur-xl animate-pulse" />
            
            {/* The Actual Lot Shape (Iconized) */}
            <div className="h-64 w-64 rounded-2xl border-[3px] border-teal-400 bg-teal-500/10 backdrop-blur-md flex items-center justify-center relative overflow-hidden group">
               <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(45,212,191,0.2),transparent_70%)]" />
               <Icons.Cpu />
               <div className="absolute top-4 left-4 text-[10px] font-black text-teal-400 rotate-[-15deg]">Subject_A1</div>
            </div>

            {/* Corner tags */}
            <div className="absolute -top-12 -right-12 glass rounded-xl px-4 py-2 text-[10px] font-black text-white border border-white/10 shadow-lg">
               Lot Area: 3,500.2㎡
            </div>
         </motion.div>
      </div>

      {/* Bottom GIS Controls */}
      <div className="absolute bottom-10 left-1/2 -translate-x-1/2 z-10 flex items-center gap-4" style={{ zIndex: 20 }}>
         <div className="flex gap-1 rounded-2xl bg-[var(--background)]/80 backdrop-blur-xl border border-[var(--line-strong)] p-1.5 shadow-[var(--shadow-xl)]">
            <button className="rounded-xl px-4 py-2 text-xs font-black text-white bg-[var(--accent-strong)] shadow-md whitespace-nowrap">상세 지적(PNU)</button>
            <button className="rounded-xl px-4 py-2 text-xs font-black text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors whitespace-nowrap">공시지가 추이</button>
            <button className="rounded-xl px-4 py-2 text-xs font-black text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors whitespace-nowrap">인근 실거래가</button>
            <div className="w-px h-4 bg-[var(--line-strong)] mx-2 self-center" />
            <button className="flex items-center gap-2 rounded-xl px-4 py-2 text-xs font-black text-[var(--accent-strong)] whitespace-nowrap">
               <Icons.Layers />
               GIS layers
            </button>
         </div>
      </div>
    </div>
  );
}
