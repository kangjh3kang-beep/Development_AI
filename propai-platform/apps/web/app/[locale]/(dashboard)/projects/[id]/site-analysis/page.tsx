"use client";

import React, { useState } from "react";
import { useParams } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { LandIntelligencePanel } from "@/components/projects/LandIntelligencePanel";
import { SiteInitiator } from "@/components/projects/SiteInitiator";
import { ProjectSiteAnalysisWorkspaceClient } from "@/components/projects/ProjectSiteAnalysisWorkspaceClient";
import { isValidLocale, type Locale } from "@/i18n/config";
import { useDictionary } from "@/hooks/use-dictionary";
import { apiClient } from "@/lib/api-client";

type IconProps = React.SVGAttributes<SVGElement>;

const Icons = {
  Cpu: (props: IconProps) => <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}><rect width="16" height="16" x="4" y="4" rx="2"/><rect width="6" height="6" x="9" y="9" rx="1"/><path d="M15 2v2"/><path d="M15 20v2"/><path d="M2 15h2"/><path d="M2 9h2"/><path d="M20 15h2"/><path d="M20 9h2"/><path d="M9 2v2"/><path d="M9 20v2"/></svg>,
  Brain: (props: IconProps) => <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}><path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96.44 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24 2.5 2.5 0 0 1 4.44-2.54Z"/><path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96.44 2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24 2.5 2.5 0 0 0-4.44-2.54Z"/></svg>,
  Database: (props: IconProps) => <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5V19A9 3 0 0 0 21 19V5"/><path d="M3 12A9 3 0 0 0 21 12"/></svg>,
  Map: (props: IconProps) => <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}><polygon points="3 6 9 3 15 6 21 3 21 18 15 21 9 18 3 21"/><line x1="9" x2="9" y1="3" y2="18"/><line x1="15" x2="15" y1="6" y2="21"/></svg>,
  Search: (props: IconProps) => <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>,
  Sparkles: (props: IconProps) => <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}><path d="m12 3 1.912 5.813a2 2 0 0 0 1.275 1.275L21 12l-5.813 1.912a2 2 0 0 0-1.275 1.275L12 21l-1.912-5.813a2 2 0 0 0-1.275-1.275L3 12l5.813-1.912a2 2 0 0 0 1.275-1.275L12 3Z"/><path d="M5 3v4"/><path d="M19 17v4"/><path d="M3 5h4"/><path d="M17 19h4"/></svg>,
};

export default function SiteAnalysisPage() {
  const { locale, id } = useParams() as { locale: string; id: string };
  const { dictionary, isLoading } = useDictionary(locale as Locale);
  const [stage, setStage] = useState<"init" | "analyzing" | "result">("init");
  const [siteData, setSiteData] = useState<Record<string, string | undefined> | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);

  if (isLoading || !dictionary) {
    return (
      <div className="flex h-[60vh] items-center justify-center">
        <div className="h-12 w-12 animate-spin rounded-full border-4 border-[var(--accent-strong)] border-t-transparent shadow-[var(--shadow-glow)]" />
      </div>
    );
  }

  const handleInitiate = async (data: { address?: string; file?: File | null; fileName?: string }) => {
    const address = data.address?.trim();
    if (!address) return;

    setStage("analyzing");
    setAnalysisError(null);
    setSiteData({ address });

    try {
      // 실제 용도지역 분석 API 호출
      const zoningResult = await apiClient.post<{
        address: string;
        pnu: string | null;
        zone_type: string | null;
        zone_limits: { max_bcr_pct: number; max_far_pct: number; max_height_m: number | null; zone_key: string; legal_basis: string } | null;
        land_area_sqm: number | null;
        land_category: string | null;
        official_price_per_sqm: number | null;
      }>("/zoning/analyze", {
        useMock: false,
        body: { address },
      });

      setSiteData({
        address: zoningResult.address || address,
        pnu: zoningResult.pnu ?? undefined,
        zoneType: zoningResult.zone_type ?? undefined,
        landAreaSqm: zoningResult.land_area_sqm?.toString(),
        landCategory: zoningResult.land_category ?? undefined,
      });
    } catch {
      // API 실패 시에도 주소 기반으로 결과 화면 진행 (LandIntelligencePanel이 자체 폴백 보유)
      setAnalysisError("용도지역 API 연결 실패 — 로컬 추정값으로 표시합니다.");
    } finally {
      setStage("result");
    }
  };

  const safeLocale = (isValidLocale(locale) ? locale : "ko") as Locale;

  return (
    <div className="flex flex-col gap-12 min-h-screen pb-20 font-sans">
      {/* ── High-Fidelity Project Hero ── */}
      <section className="relative overflow-hidden rounded-2xl sm:rounded-[2rem] lg:rounded-[4rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] p-6 sm:p-10 lg:p-20 shadow-[var(--shadow-2xl)] group">
        <div className="absolute -right-20 -top-20 h-80 w-80 rounded-full bg-[var(--accent-strong)]/10 blur-[100px] transition-all duration-1000 group-hover:scale-125" />
        <div className="absolute inset-0 bg-[url('https://www.transparenttextures.com/patterns/carbon-fibre.png')] opacity-[0.03] dark:invert" />

        <div className="relative z-10 flex flex-col gap-10 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-4xl space-y-8">
            <div className="flex items-center gap-4">
              <span className="inline-flex items-center gap-3 rounded-full border border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] px-6 py-2 text-[10px] font-black uppercase tracking-[0.4em] text-[var(--accent-strong)] backdrop-blur-md">
                <span className="h-2 w-2 rounded-full bg-[var(--accent-strong)] animate-ping shadow-[var(--shadow-glow)]" />
                지능형 부지분석 시스템
              </span>
            </div>

            <h1 className="text-3xl font-[1000] tracking-tighter text-[var(--text-primary)] sm:text-5xl md:text-6xl lg:text-8xl leading-[0.9]">
              부지 분석 및<br/>
              <span className="text-[var(--accent-strong)] italic">입지 전략 수집<span className="text-[var(--text-primary)]">.</span></span>
            </h1>

            <p className="max-w-2xl text-base sm:text-lg lg:text-xl font-medium leading-relaxed text-[var(--text-secondary)] italic tracking-tight underline decoration-[var(--line-strong)] decoration-2 underline-offset-8">
              "사통팔땅의 AI 엔진이 공공 빅데이터와 정밀 GIS를 실시간 결합하여, 리스크는 최소화하고 개발 가치는 극대화하는 멀티레이어 지능형 보고서를 생성합니다."
            </p>
          </div>

          <div className="hidden lg:block">
            <motion.div
              animate={{ y: [0, -20, 0] }}
              transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
              className="h-44 w-44 rounded-[3.5rem] bg-[var(--surface-soft)] border border-[var(--line-strong)] flex items-center justify-center text-[var(--accent-strong)] backdrop-blur-3xl shadow-[var(--shadow-2xl)]"
            >
               <Icons.Map width={72} height={72} strokeWidth={1} />
            </motion.div>
          </div>
        </div>
      </section>

      {/* ── Dynamic Content Stages ── */}
      <AnimatePresence mode="wait">
        {stage === "init" && (
          <motion.div
            key="init"
            initial={{ opacity: 0, scale: 0.95, y: 40 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, y: -40, filter: "blur(20px)" }}
            className="mx-auto w-full max-w-5xl"
          >
            <div className="rounded-2xl sm:rounded-[2.5rem] lg:rounded-[4.5rem] p-1.5 border border-[var(--line)] bg-[var(--surface-soft)] overflow-hidden group shadow-[var(--shadow-2xl)]">
               <div className="rounded-xl sm:rounded-[2.2rem] lg:rounded-[4.2rem] p-6 sm:p-10 lg:p-20 bg-[var(--surface-strong)]/80 backdrop-blur-3xl transition-all group-hover:bg-[var(--surface-strong)]/60 border border-[var(--line-strong)]">
                  <SiteInitiator onInitiate={handleInitiate} loading={false} />
               </div>
            </div>
          </motion.div>
        )}

        {stage === "analyzing" && (
          <motion.div
            key="analyzing"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0, filter: "blur(20px)" }}
            className="flex flex-col items-center justify-center gap-20 py-48"
          >
            <div className="relative group">
              <div className="absolute -inset-24 animate-spin-slow bg-gradient-to-r from-[var(--accent-strong)] via-blue-500 to-teal-500 rounded-full blur-[80px] opacity-10" />
              <motion.div
                animate={{ scale: [1, 1.05, 1] }}
                transition={{ duration: 2, repeat: Infinity }}
                className="relative flex h-64 w-64 items-center justify-center rounded-[4rem] bg-[var(--surface-strong)] border border-[var(--line-strong)] shadow-[var(--shadow-2xl)] backdrop-blur-3xl overflow-hidden"
              >
                 <div className="absolute inset-0 bg-[var(--accent-strong)]/5 animate-pulse" />
                 <Icons.Brain width={112} height={112} strokeWidth={1} />
              </motion.div>
            </div>

            <div className="flex flex-col items-center gap-10 text-center max-w-2xl px-6">
               <div className="space-y-4">
                  <h3 className="text-2xl sm:text-3xl lg:text-5xl font-[1000] text-[var(--text-primary)] italic tracking-tighter leading-tight">AI <span className="text-[var(--accent-strong)]">GIS 엔진</span> 분석 중...</h3>
                  <p className="text-[11px] font-black text-[var(--accent-strong)]/50 uppercase tracking-[0.6em]">사통팔땅 멀티레이어 지능형 엔진 가동 중</p>
               </div>

               <div className="flex flex-wrap justify-center gap-6">
                  {[
                    { label: "지적도 오버레이 데이터 연동", delay: 0 },
                    { label: "용도지역 지자체 조례 전수 분석", delay: 0.6 },
                    { label: "주변 개발 압력 및 시세 매핑", delay: 1.2 },
                    { label: "AI 최적 공간 모델링 추론", delay: 1.8 },
                  ].map((step, i) => (
                    <motion.div
                      key={step.label}
                      initial={{ opacity: 0, y: 20 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: step.delay }}
                      className="rounded-3xl border border-[var(--line-strong)] bg-[var(--surface-strong)] px-8 py-5 text-[11px] font-black uppercase tracking-widest text-[var(--text-secondary)] flex items-center gap-4 backdrop-blur-md hover:bg-[var(--surface-soft)] hover:text-[var(--text-primary)] transition-all cursor-default shadow-[var(--shadow-sm)]"
                    >
                       <div className="h-2 w-2 rounded-full bg-[var(--accent-strong)] shadow-[var(--shadow-glow)] animate-pulse" />
                       {step.label}
                    </motion.div>
                  ))}
               </div>
            </div>
          </motion.div>
        )}

        {stage === "result" && siteData && (
          <motion.div
            key="result"
            initial={{ opacity: 0, y: 40 }}
            animate={{ opacity: 1, y: 0 }}
            className="w-full flex flex-col gap-16"
          >
            {/* Context Summary Bar */}
            <div className="flex flex-col lg:flex-row lg:items-center justify-between rounded-2xl sm:rounded-[2rem] lg:rounded-[4rem] bg-[var(--surface-strong)] p-6 sm:p-8 lg:p-10 lg:px-14 border border-[var(--line-strong)] backdrop-blur-3xl shadow-[var(--shadow-2xl)] gap-6 sm:gap-8">
               <div className="flex items-center gap-8">
                  <div className="flex h-20 w-20 items-center justify-center rounded-[2rem] bg-[var(--accent-strong)]/10 text-[var(--accent-strong)] border border-[var(--accent-strong)]/20 shadow-[var(--shadow-glow)]">
                    <Icons.Map width={40} height={40} strokeWidth={1.5} />
                  </div>
                  <div className="space-y-1">
                    <p className="text-[10px] font-black uppercase tracking-[0.4em] text-[var(--text-hint)]">분석 대상 부지</p>
                    <p className="text-xl sm:text-2xl lg:text-3xl font-[1000] text-[var(--text-primary)] tracking-tighter italic">
                      {siteData.address || "분석 대상 주소를 입력하세요"}
                    </p>
                    {siteData.zoneType && (
                      <p className="text-sm font-bold text-[var(--accent-strong)]">
                        {siteData.zoneType}
                        {siteData.landAreaSqm && ` · ${Number(siteData.landAreaSqm).toLocaleString()}m²`}
                        {siteData.landCategory && ` · ${siteData.landCategory}`}
                      </p>
                    )}
                  </div>
               </div>
               <button
                onClick={() => { setStage("init"); setSiteData(null); setAnalysisError(null); }}
                className="group flex h-16 items-center justify-center gap-4 rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] px-10 text-[11px] font-black text-[var(--text-primary)] hover:text-white uppercase tracking-[0.3em] transition-all hover:bg-[var(--accent-strong)] hover:border-[var(--accent-strong)] active:scale-95 shadow-[var(--shadow-lg)]"
               >
                 <span>새 분석</span>
                 <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" className="transition-transform group-hover:rotate-180"><path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/><path d="M16 16h5v5"/></svg>
               </button>
            </div>

            {/* API 연결 실패 안내 */}
            {analysisError && (
              <div className="rounded-2xl border border-amber-500/20 bg-amber-500/5 p-5 text-sm text-amber-600 dark:text-amber-400 font-medium">
                {analysisError}
              </div>
            )}

            <motion.div
              initial={{ opacity: 0, y: 40 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
              className="rounded-2xl sm:rounded-[2.5rem] lg:rounded-[4.5rem] border border-[var(--line-strong)] bg-[var(--surface-strong)]/50 p-4 sm:p-8 lg:p-14 shadow-[var(--shadow-2xl)] backdrop-blur-xl"
            >
              <LandIntelligencePanel projectId={id} data={siteData} />
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Live Workspace Client ── */}
      <ProjectSiteAnalysisWorkspaceClient locale={safeLocale} projectId={id} />
    </div>
  );
}
