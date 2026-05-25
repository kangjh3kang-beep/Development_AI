"use client";

import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useCadStore } from "@/store/use-cad-store";

export function DrawingAnalysisPanel() {
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const setAnalysis = useCadStore((s) => s.setAnalysis);
  const resetCanvas = useCadStore((s) => s.resetCanvas);
  
  const [analysisResult, setAnalysisResult] = useState<{
    score: number;
    issues: Array<{ id: string; type: string; desc: string; severity: "high" | "med" | "low" }>;
  } | null>(null);

  const startAnalysis = () => {
    setIsAnalyzing(true);
    setAnalysisResult(null);
    
    // AI Analysis Simulation
    setTimeout(() => {
      setIsAnalyzing(false);
      const results = [
        { id: "1", type: "SETBACK", desc: "북측 인접 대지 경계선 이격 거리 부족 (1.2m < 1.5m)", severity: "high" as const, x: 150, y: 120 },
        { id: "2", type: "STRUCTURE", desc: "슬래브 배근 간격 구조 검토 권장 (Section-A)", severity: "med" as const, x: 400, y: 300 },
        { id: "3", type: "MEP", desc: "전기실 환기 덕트 간섭 가능성 (B1F)", severity: "low" as const, x: 220, y: 450 },
      ];
      setAnalysisResult({
        score: 82,
        issues: results,
      });
      setAnalysis(false, results);
    }, 2000);
  };

  return (
    <div className="flex flex-col gap-4 rounded-3xl border border-[var(--line)] bg-[var(--surface-soft)] p-6 shadow-xl backdrop-blur-2xl">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-indigo-600 text-white shadow-lg">
             <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="m3 21 1.9-1.9"/><path d="m3 21 1.9-1.9"/><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M17 8 8 17"/><path d="M17 17H8V8"/></svg>
          </div>
          <div>
            <h3 className="text-lg font-black tracking-tight text-[var(--text-primary)]">AI 도면 정밀 분석</h3>
            <p className="text-xs font-bold text-[var(--text-tertiary)] uppercase tracking-widest">Architectural Intelligence</p>
          </div>
        </div>
        <button
          onClick={startAnalysis}
          disabled={isAnalyzing}
          className="rounded-2xl bg-black px-6 py-3 text-sm font-black text-white shadow-xl shadow-black/20 hover:scale-105 active:scale-95 transition-all disabled:opacity-50"
        >
          {isAnalyzing ? "분석 중..." : "분석 시작"}
        </button>
      </div>

      <AnimatePresence mode="wait">
        {isAnalyzing ? (
          <motion.div
            key="analyzing"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="flex flex-col items-center gap-6 py-8"
          >
            <div className="relative h-16 w-16">
               <div className="absolute inset-0 animate-ping rounded-full bg-indigo-500/20" />
               <div className="flex h-16 w-16 animate-spin items-center justify-center rounded-full border-t-2 border-indigo-600" />
            </div>
            <p className="text-sm font-bold text-slate-500 animate-pulse">CAD 레이어 기하학 데이터 추출 및 법규 대조 중...</p>
          </motion.div>
        ) : analysisResult ? (
          <motion.div
            key="result"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="flex flex-col gap-6"
          >
            <div className="grid grid-cols-3 gap-4">
               <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-4 text-center">
                  <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-tertiary)]">Design Health</p>
                  <p className={`text-2xl font-black ${analysisResult.score > 80 ? "text-emerald-600" : "text-amber-600"}`}>{analysisResult.score}%</p>
               </div>
               <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-4 text-center">
                  <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-tertiary)]">Critical Issues</p>
                  <p className="text-2xl font-black text-red-600">{analysisResult.issues.filter(i => i.severity === "high").length}</p>
               </div>
               <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-4 text-center">
                  <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-tertiary)]">AI Optimized</p>
                  <p className="text-2xl font-black text-indigo-600">YES</p>
               </div>
            </div>

            <div className="flex flex-col gap-2">
               <p className="text-xs font-black text-[var(--text-secondary)] uppercase tracking-wider px-1">Detected Non-Compliance & Risks</p>
               {analysisResult.issues.map((issue) => (
                 <div key={issue.id} className="flex items-start gap-3 rounded-2xl bg-[var(--surface)] p-4 border-l-4 border-l-indigo-500 shadow-sm transition-hover hover:shadow-md">
                    <div className={`mt-1 h-2 w-2 shrink-0 rounded-full ${
                      issue.severity === "high" ? "bg-red-500" : issue.severity === "med" ? "bg-amber-500" : "bg-blue-500"
                    }`} />
                    <div className="flex flex-col gap-0.5">
                      <p className="text-xs font-black text-[var(--text-primary)]">[{issue.type}] {issue.desc}</p>
                      <p className="text-[10px] font-bold text-[var(--text-tertiary)] leading-relaxed">
                        {issue.severity === "high" ? "⚠️ 즉시 설계 수정이 필요합니다." : "🔍 검토 및 조정이 권장됩니다."}
                      </p>
                    </div>
                 </div>
               ))}
            </div>
            
            <div className="rounded-2xl bg-indigo-600 p-4 text-white">
                <div className="flex items-center gap-3">
                   <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-white/20">
                      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="m12 3-1.912 5.813a2 2 0 0 0-1.275 1.275L3 12l5.813 1.912a2 2 0 0 0 1.275 1.275L12 21l1.912-5.813a2 2 0 0 0-1.275-1.275L21 12l-5.813-1.912a2 2 0 0 0-1.275-1.275L12 3Z"/></svg>
                   </div>
                   <p className="text-xs font-bold leading-snug">
                     AI 비서: "현재 부지의 조례(Stage 3: 법규 검토)를 대조한 결과, 일조권 사선 제한 기준이 설계에 반영되지 않았습니다. 수정을 권장합니다."
                   </p>
                </div>
            </div>
          </motion.div>
        ) : (
          <div className="flex flex-col items-center justify-center gap-4 py-12 text-center">
             <div className="h-16 w-16 opacity-20">
                <svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3v19"/><path d="M3 12h19"/><path d="M18.364 5.636 5.636 18.364"/><path d="m5.636 5.636 12.728 12.728"/></svg>
             </div>
             <p className="text-sm font-bold text-[var(--text-tertiary)]">작성된 도면 또는 업로드된 DWG/PDF를 분석하여<br/>법규 위반 및 시공 리스크를 사전에 식별합니다.</p>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
