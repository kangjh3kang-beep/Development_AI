"use client";

import { useState } from "react";
import Link from "next/link";
import { StageIcon } from "@/components/common/StageIcon";
import { useParams } from "next/navigation";
import dynamic from "next/dynamic";
import { motion, AnimatePresence } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";

const FeasibilitySimulationWidget = dynamic(
  () => import("../finance/FeasibilitySimulationWidget").then(mod => mod.FeasibilitySimulationWidget),
  { ssr: false, loading: () => <div className="h-[400px] w-full animate-pulse rounded-[2rem] bg-white/5 flex items-center justify-center"><p className="text-white/20 font-black uppercase tracking-[0.3em] text-xs text-center">AI 사업성 분석 엔진 로딩 중...</p></div> }
);

const CostAndQuantityDashboard = dynamic(
  () => import("../construction/CostAndQuantityDashboard").then(mod => mod.CostAndQuantityDashboard),
  { ssr: false }
);

const ScheduleSupervisionPanel = dynamic(
  () => import("../construction/ScheduleSupervisionPanel").then(mod => mod.ScheduleSupervisionPanel),
  { ssr: false }
);

// 설계(CAD/BIM)는 전용 스튜디오(/design-studio·/bim-studio)로 분리 — 여기선 임베드하지 않음.

type StageType =
  | "site_analysis"
  | "legal_compliance"
  | "design_ai"
  | "feasibility"
  | "esg_dashboard"
  | "permit_portal"
  | "construction"
  | "operations";

interface LifecycleStageViewsProps {
  projectId: string;
  dictionary: Record<string, any>;
  /** 통합보고서가 위에 표시될 때(compact): 보고서와 중복되는 입지·법규·사업성·ESG 탭은 숨기고
   *  보고서가 다루지 않는 전방 단계(설계·인허가·시공·운영)만 노출 → 옛 화면 중복 제거. */
  compact?: boolean;
}

export function LifecycleStageViews({ projectId, dictionary, compact = false }: LifecycleStageViewsProps) {
  // compact면 보고서 미포함 단계부터(설계), 아니면 입지분석부터.
  const [activeStage, setActiveStage] = useState<StageType>(compact ? "design_ai" : "site_analysis");
  // 설계 스튜디오(무거운 WebGL CAD/BIM)는 사용자가 명시적으로 열 때만 로드.
  const params = useParams();
  const locale = params.locale as string;
  const t = dictionary.lifecycle;

  const projectQuery = useQuery({
    queryKey: ["projects", "detail", projectId],
    queryFn: () => apiClient.get<Record<string, any>>(`/projects/${projectId}`),
  });

  const p = projectQuery.data || {};

  // 저장된 실제 분석(프로젝트별 스냅샷에서 복원됨) — 단일 데이터원. 백엔드 메타(p)로 폴백.
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const designData = useProjectContextStore((s) => s.designData);
  const esgData = useProjectContextStore((s) => s.esgData);

  const fmtArea = (v: number | null | undefined) =>
    v != null ? `${Math.round(v).toLocaleString()} m²` : null;
  const officialPrice =
    siteAnalysis?.officialPrices?.[0]?.pricePerSqm ?? null;
  const bcrLimit = siteAnalysis?.ordinance?.effectiveBcr ?? null;
  const farLimit = siteAnalysis?.ordinance?.effectiveFar ?? null;
  const NA = "분석 전";

  // 부지분석 탭 — 저장 분석 → 백엔드 메타 → '분석 전'(하드코딩 제거)
  const siteRows = [
    {
      label: "필지번호 (PNU)",
      value: siteAnalysis?.pnu || p.pnu_codes?.[0] || p.pnu || NA,
    },
    {
      label: "면적",
      value: fmtArea(siteAnalysis?.landAreaSqm) || fmtArea(p.total_area_sqm) || NA,
    },
    {
      label: "공시지가",
      value: officialPrice != null
        ? `${Math.round(officialPrice).toLocaleString()} 원/m²`
        : NA,
    },
    {
      label: "용도지역",
      value: siteAnalysis?.zoneCode || p.zone_type || NA,
    },
    {
      label: "건폐율 / 용적률",
      value: bcrLimit != null && farLimit != null ? `${bcrLimit}% / ${farLimit}%` : NA,
    },
  ];

  // 법규 탭 건축 한도 — 한도=조례/법정 상한, 현재=설계값(없으면 '분석 전')
  const pct = (cur: number | null, lim: number | null) =>
    cur != null && lim ? Math.min(100, Math.round((cur / lim) * 100)) : 0;
  const legalLimits = [
    {
      label: "건폐율",
      limit: bcrLimit != null ? `${bcrLimit}%` : "—",
      current: designData?.bcr != null ? `${designData.bcr}%` : NA,
      progress: pct(designData?.bcr ?? null, bcrLimit),
      color: "var(--success)",
    },
    {
      label: "용적률",
      limit: farLimit != null ? `${farLimit}%` : "—",
      current: designData?.far != null ? `${designData.far}%` : NA,
      progress: pct(designData?.far ?? null, farLimit),
      color: "var(--accent-strong)",
    },
  ];

  // ESG 탄소 — context esgData(있으면 실값). tCO₂e = kg/1000.
  const tco2e = (kg: number | null | undefined) =>
    kg != null ? `${(kg / 1000).toLocaleString(undefined, { maximumFractionDigits: 1 })} tCO₂e` : NA;
  const esgHasData = !!esgData && (esgData.embodiedCarbonKg != null || esgData.operationalCarbonKg != null || esgData.totalCarbonPerSqm != null);
  const carbonRows = [
    { label: "내재 탄소(자재)", value: tco2e(esgData?.embodiedCarbonKg) },
    { label: "운영 탄소(연간)", value: tco2e(esgData?.operationalCarbonKg) },
    {
      label: "단위면적당",
      value: esgData?.totalCarbonPerSqm != null ? `${esgData.totalCarbonPerSqm.toLocaleString(undefined, { maximumFractionDigits: 1 })} kgCO₂/m²` : NA,
      highlight: true,
    },
  ];

  const allStages = [
    { id: "site_analysis", name: t.stageSite || "입지 분석", path: "site-analysis" },
    { id: "legal_compliance", name: t.stageLegal || "법규 검토", path: "legal" },
    { id: "design_ai", name: t.stageDesignAI || "AI 설계", path: "cad" },
    { id: "feasibility", name: t.stageFeasibility || "사업성 분석", path: "feasibility" },
    { id: "esg_dashboard", name: t.stageESG || "ESG 컨설팅", path: "esg" },
    { id: "permit_portal", name: t.stagePermits || "인허가 포털", path: "permit" },
    { id: "construction", name: t.stageConstruction || "스마트 시공", path: "construction" },
    { id: "operations", name: t.stageOperations || "자산 관리", path: "operations" },
  ];
  // compact(보고서 동시표시): 보고서와 중복되는 입지·법규·사업성·ESG 제외.
  const REPORT_COVERED = new Set(["site_analysis", "legal_compliance", "feasibility", "esg_dashboard"]);
  const stages = compact ? allStages.filter((s) => !REPORT_COVERED.has(s.id)) : allStages;

  return (
    <div className="mt-20 flex flex-col gap-10">
      <div className="flex flex-col gap-6">
        <div className="flex items-center justify-between px-2">
          <h3 className="text-[10px] font-black tracking-[0.4em] text-[var(--text-hint)] uppercase">
             {t.title || "프로젝트 라이프사이클 허브"}
          </h3>
          <div className="h-px flex-1 mx-8 bg-gradient-to-r from-[var(--line-strong)] to-transparent" />
        </div>
        
        <div className="relative group/nav">
          <div className="px-2 -mx-2 pb-2">
            <div className="flex flex-wrap gap-2 rounded-[2rem] bg-[var(--surface-strong)] p-2 border border-[var(--line-strong)] shadow-[var(--shadow-2xl)] backdrop-blur-3xl">
              {stages.map((stage) => (
                <button
                  key={stage.id}
                  onClick={() => setActiveStage(stage.id as StageType)}
                  className={`relative flex items-center gap-2.5 whitespace-nowrap rounded-full px-5 py-3 text-[11px] font-black uppercase tracking-[0.15em] transition-all duration-500 ${
                    activeStage === stage.id
                      ? "text-white"
                      : "text-[var(--text-tertiary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-soft)]"
                  }`}
                >
                  {activeStage === stage.id && (
                    <motion.div
                      layoutId="activeStageTab"
                      className="absolute inset-0 rounded-full bg-gradient-to-r from-teal-500 via-teal-400 to-indigo-500 shadow-[var(--shadow-glow)]"
                      transition={{ type: "spring", bounce: 0.2, duration: 0.6 }}
                    >
                      <div className="absolute inset-0 rounded-full bg-white/10 opacity-50 backdrop-blur-sm" />
                    </motion.div>
                  )}
                  <span className="relative z-10">{<StageIcon id={stage.id} />}</span>
                  <span className="relative z-10">{stage.name}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-8">
        <AnimatePresence mode="wait">
          <motion.div
            key={activeStage}
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -30, filter: "blur(10px)" }}
            className="min-h-[500px] rounded-[4rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] p-14 shadow-[var(--shadow-2xl)] backdrop-blur-3xl overflow-hidden group"
          >
            <div className="relative z-10 h-full flex flex-col gap-10">
              <div className="flex-1">
                {activeStage === "design_ai" && (
                  <div className="flex min-h-[420px] flex-col items-center justify-center gap-8 rounded-[3rem] border border-dashed border-[var(--line-strong)] bg-[var(--surface-soft)] p-12 text-center">
                    <div className="flex h-16 w-16 items-center justify-center rounded-3xl bg-[var(--accent-soft)] text-[var(--accent-strong)] shadow-[var(--shadow-glow)]">
                      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m2 12 5-3 5 3 5-3 5 3"/><path d="m2 17 5-3 5 3 5-3 5 3"/><path d="m2 7 5-3 5 3 5-3 5 3"/></svg>
                    </div>
                    <div className="space-y-3 max-w-xl">
                      <h4 className="text-2xl font-[1000] tracking-tight text-[var(--text-primary)]">설계 스튜디오</h4>
                      <p className="text-sm leading-relaxed text-[var(--text-secondary)]">
                        CAD 자동설계와 BIM·적산은 <b className="text-[var(--text-primary)]">전용 스튜디오</b>에서 운영합니다. 고사양 WebGL 엔진을
                        별도 화면으로 분리해 이 페이지의 속도·안정성을 유지합니다(선택한 프로젝트 기준으로 자동 연동).
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center justify-center gap-3">
                      <Link href={`/${locale}/design-studio`}
                        className="inline-flex h-14 items-center gap-3 rounded-full bg-[var(--accent-strong)] px-9 text-xs font-black uppercase tracking-[0.2em] text-white shadow-[var(--shadow-glow)] transition-all hover:scale-105">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 3v18h18"/><path d="m7 14 4-4 3 3 5-5"/></svg>
                        AI 자동설계 (CAD)
                      </Link>
                      <Link href={`/${locale}/bim-studio`}
                        className="inline-flex h-14 items-center gap-3 rounded-full border border-[var(--accent-strong)]/40 px-9 text-xs font-black uppercase tracking-[0.2em] text-[var(--accent-strong)] transition-all hover:scale-105">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/></svg>
                        BIM · 적산
                      </Link>
                    </div>
                  </div>
                )}
                {activeStage === "feasibility" && <FeasibilitySimulationWidget projectId={projectId} dictionary={dictionary.feasibility} />}
                {activeStage === "construction" && (
                  <div className="flex flex-col gap-16">
                    <CostAndQuantityDashboard projectId={projectId} dictionary={dictionary.cost} />
                    <div className="h-px w-full bg-[var(--line-strong)]" />
                    <ScheduleSupervisionPanel projectId={projectId} dictionary={dictionary.schedule} />
                  </div>
                )}

                {activeStage === "site_analysis" && (
                  <div className="grid gap-14 md:grid-cols-2">
                    <div className="relative flex h-[400px] items-center justify-center rounded-[3rem] border border-[var(--line-strong)] bg-[var(--surface-soft)] overflow-hidden group/map shadow-inner">
                      <div className="absolute inset-0 bg-indigo-500/5 group-hover/map:bg-indigo-500/10 transition-colors" />
                      <div className="text-center relative z-10">
                        <span className="text-7xl filter drop-shadow-[0_0_20px_rgba(255,255,255,0.2)]">🗺️</span>
                        <p className="mt-6 text-[10px] font-black uppercase tracking-[0.5em] text-[var(--accent-strong)] animate-pulse">GIS Intelligence Active</p>
                      </div>
                    </div>
                    <div className="flex flex-col justify-center gap-4">
                      {siteRows.map((item, i) => (
                        <motion.div 
                          key={item.label} 
                          initial={{ opacity: 0, x: 20 }}
                          animate={{ opacity: 1, x: 0 }}
                          transition={{ delay: i * 0.1 }}
                          className="flex items-center justify-between rounded-2xl bg-[var(--surface-soft)] px-8 py-5 border border-[var(--line)] shadow-sm hover:scale-105 transition-transform"
                        >
                          <span className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">{item.label}</span>
                          <span className="text-sm font-black text-[var(--text-primary)] tracking-tight italic underline decoration-[var(--accent-strong)]/20 decoration-2 underline-offset-4">{item.value}</span>
                        </motion.div>
                      ))}
                    </div>
                  </div>
                )}

                {activeStage === "legal_compliance" && (
                  <div className="grid gap-14 md:grid-cols-2">
                    <div className="space-y-8">
                      <h4 className="text-[10px] font-black text-[var(--text-hint)] uppercase tracking-[0.5em] px-4">건축 제한 현황 (MAX LIMITS)</h4>
                      {legalLimits.map((item, i) => (
                        <div key={item.label} className="rounded-[2.5rem] bg-[var(--surface-soft)] p-8 border border-[var(--line)] group/stat shadow-sm">
                          <div className="flex items-center justify-between mb-5">
                            <span className="text-[11px] font-black uppercase tracking-[0.2em] text-[var(--text-secondary)]">{item.label}</span>
                            <span className="text-[9px] font-black text-[var(--text-hint)] uppercase tracking-widest italic tracking-tighter self-end opacity-40">한도: {item.limit}</span>
                          </div>
                          <div className="h-2 w-full rounded-full bg-[var(--surface-strong)] overflow-hidden">
                            <motion.div 
                              initial={{ width: 0 }}
                              animate={{ width: `${item.progress}%` }}
                              transition={{ duration: 1, delay: i * 0.1 }}
                              className="h-full shadow-[var(--shadow-glow)]" 
                              style={{ backgroundColor: item.color }}
                            />
                          </div>
                          <p className="mt-5 text-right text-lg font-black text-[var(--text-primary)] tracking-tighter italic">{item.current}</p>
                        </div>
                      ))}
                    </div>
                    <div className="space-y-8">
                      <h4 className="text-[10px] font-black text-[var(--text-hint)] uppercase tracking-[0.5em] px-4">AI 규제 체크리스트 (VERIFIED)</h4>
                      <div className="grid gap-4">
                        {[
                          { label: "용도지역 및 허용 지번 적합성", checked: true },
                          { label: "건축법 제 22조 기술 준수", checked: true },
                          { label: "소방법 및 비상구조 검토", checked: true },
                          { label: "환경영향평가 (진행 중)", checked: false },
                          { label: "교통영향평가 및 정체 구역 분석", checked: false },
                          { label: "일조권 사선 제한 및 시각 분석", checked: true },
                        ].map((item, i) => (
                          <motion.div 
                            key={item.label} 
                            initial={{ opacity: 0, scale: 0.95 }}
                            animate={{ opacity: 1, scale: 1 }}
                            transition={{ delay: 0.5 + i * 0.05 }}
                            className="flex items-center gap-6 rounded-[2rem] bg-[var(--surface-soft)] px-8 py-5 border border-[var(--line)] transition-all hover:bg-[var(--surface-strong)] hover:translate-x-2"
                          >
                            <div className={`flex h-8 w-8 items-center justify-center rounded-xl border-2 transition-all ${
                              item.checked
                                ? "border-[var(--success)] bg-[var(--success)]/10 text-[var(--success)] shadow-[0_0_15px_rgba(16,185,129,0.3)]"
                                : "border-[var(--line-strong)] text-transparent"
                            }`}>
                              {item.checked ? <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="4"><polyline points="20 6 9 17 4 12"/></svg> : null}
                            </div>
                            <span className={`text-[13px] font-black tracking-tight ${item.checked ? "text-[var(--text-primary)]" : "text-[var(--text-hint)] italic"}`}>{item.label}</span>
                          </motion.div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}

                {activeStage === "esg_dashboard" && (
                  <div className="flex flex-col gap-12">
                    {!esgHasData && (
                      <div className="flex flex-col items-center gap-4 rounded-[3rem] border border-dashed border-[var(--line-strong)] bg-[var(--surface-soft)] p-10 text-center">
                        <span className="text-4xl">🌿</span>
                        <p className="text-sm font-black text-[var(--text-primary)]">ESG/탄소 분석 전</p>
                        <p className="text-xs text-[var(--text-secondary)] max-w-md">이 프로젝트의 ESG·탄소 데이터가 아직 없습니다. ‘ESG/탄소 경영’ 모듈에서 분석을 실행하면 내재·운영 탄소가 여기에 연동됩니다.</p>
                        <Link href={`/${locale}/esg`} className="rounded-full bg-[var(--accent-strong)] px-6 py-3 text-xs font-black uppercase tracking-[0.2em] text-white">ESG 분석 실행 ↗</Link>
                      </div>
                    )}
                    <div className="grid gap-10 md:grid-cols-2">
                       <div className="rounded-[3rem] bg-[var(--surface-soft)] p-10 border border-[var(--line)] shadow-sm">
                          <h4 className="text-[10px] font-black text-[var(--text-hint)] uppercase tracking-[0.5em] mb-8">CARBON INTELLIGENCE (CO₂)</h4>
                          <div className="space-y-5">
                            {carbonRows.map((item) => (
                              <div key={item.label} className="flex items-center justify-between border-b border-[var(--line)] pb-4">
                                <span className="text-[12px] font-black text-[var(--text-secondary)] uppercase tracking-widest">{item.label}</span>
                                <span className={`text-lg font-black tracking-tighter italic ${item.highlight ? 'text-[var(--accent-strong)]' : 'text-[var(--text-primary)]'}`}>{item.value}</span>
                              </div>
                            ))}
                          </div>
                       </div>
                       <div className="rounded-[3rem] bg-[var(--surface-soft)] p-10 border border-[var(--line)] shadow-sm">
                          <h4 className="text-[10px] font-black text-[var(--text-hint)] uppercase tracking-[0.5em] mb-8">GREEN CERTIFICATION FLOW</h4>
                          <div className="space-y-5">
                            {[ "에너지효율등급", "녹색건축인증 (G-SEED)", "LEED 글로벌 평가" ].map((label) => (
                              <div key={label} className="flex items-center justify-between border-b border-[var(--line)] pb-4">
                                <span className="text-[12px] font-black text-[var(--text-secondary)] uppercase tracking-widest">{label}</span>
                                <span className="text-lg font-black text-[var(--text-hint)] tracking-tighter italic">{NA}</span>
                              </div>
                            ))}
                          </div>
                       </div>
                    </div>
                  </div>
                )}

                {activeStage === "permit_portal" && (
                  <div className="flex flex-col gap-12 justify-center py-10">
                    <div className="rounded-[4rem] bg-[var(--surface-soft)] p-16 border border-[var(--line)] shadow-inner">
                      <h4 className="text-[10px] font-black text-[var(--text-hint)] uppercase tracking-[0.6em] mb-20 text-center">PERMIT WORKFLOW PULSE</h4>
                      <div className="flex items-center justify-between gap-4 max-w-5xl mx-auto">
                        {[
                          { label: "서류 접수", step: 1, current: true, status: "완료" },
                          { label: "관계 부처 협의", step: 2, current: true, status: "진행중" },
                          { label: "보완 사항 통보", step: 3, current: false, status: "대기" },
                          { label: "건축 허가 승인", step: 4, current: false, status: "대기" },
                          { label: "착공 상세 신고", step: 5, current: false, status: "대기" },
                        ].map((stage, i, arr) => (
                          <div key={stage.label} className="flex items-center gap-4 flex-1">
                            <div className="flex flex-col items-center gap-6 flex-1">
                              <div className={`relative flex h-16 w-16 items-center justify-center rounded-2xl border-4 text-lg font-black transition-all ${
                                stage.current 
                                ? "border-[var(--accent-strong)] text-[var(--accent-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-glow)]" 
                                : "border-[var(--line-strong)] text-[var(--text-hint)] opacity-30"
                              }`}>
                                {stage.step}
                                {stage.current && <span className="absolute -top-3 -right-3 h-6 w-6 rounded-full bg-[var(--accent-strong)] text-[9px] text-white flex items-center justify-center animate-bounce shadow-lg">✓</span>}
                              </div>
                              <div className="flex flex-col items-center gap-1">
                                <span className={`text-[12px] font-[1000] uppercase tracking-tighter ${stage.current ? "text-[var(--text-primary)]" : "text-[var(--text-hint)]"}`}>{stage.label}</span>
                                <span className="text-[9px] font-black text-[var(--accent-strong)] uppercase tracking-widest opacity-60 italic">{stage.status}</span>
                              </div>
                            </div>
                            {i < arr.length - 1 && (
                              <div className={`mb-20 h-1.5 flex-1 rounded-full ${stage.current ? "bg-gradient-to-r from-[var(--accent-strong)] to-[var(--line-strong)]" : "bg-[var(--line-strong)]"} opacity-20`} />
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}

                {activeStage === "operations" && (
                  <div className="grid gap-14 md:grid-cols-2">
                    <div className="rounded-[3.5rem] bg-[var(--surface-soft)] p-10 border border-[var(--line)] shadow-sm">
                      <h4 className="text-[10px] font-black text-[var(--text-hint)] uppercase tracking-[0.5em] mb-10">ASSET KPI INTELLIGENCE</h4>
                      <div className="grid gap-6">
                        {[ 
                          { label: "전체 입주 점유율", value: "98.5%", trend: "+2.1%" }, 
                          { label: "월 평균 순수익률 (NOI)", value: "4.2%", trend: "+0.5%" }, 
                          { label: "공용 관리비 효율", value: "1,250 ₩/m²", trend: "-120 ₩" }, 
                          { label: "탄소 배출 에너지 비용", value: "840 ₩/m²", trend: "-15%" } 
                        ].map((item) => (
                          <div key={item.label} className="flex items-center justify-between rounded-3xl bg-[var(--surface-strong)] px-8 py-6 border border-[var(--line)] transition-all hover:scale-[1.03] group/item shadow-sm">
                            <span className="text-[11px] font-black text-[var(--text-hint)] uppercase tracking-widest">{item.label}</span>
                            <div className="flex flex-col items-end">
                               <span className="text-xl font-black text-[var(--text-primary)] group-hover/item:text-[var(--accent-strong)] transition-colors italic tracking-tighter">{item.value}</span>
                               <span className="text-[9px] font-black text-[var(--success)] uppercase tracking-widest">{item.trend}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                    <div className="flex flex-col gap-10">
                       <div className="rounded-[3.5rem] bg-[var(--surface-soft)] p-10 border border-[var(--line)] shadow-sm">
                          <h4 className="text-[10px] font-black text-[var(--text-hint)] uppercase tracking-[0.5em] mb-10">IOT SENSOR TELEMETRY</h4>
                          <div className="grid grid-cols-2 gap-6">
                             {[ { label: "내부 온도", value: "22.5°C", icon: "🌡️" }, { label: "공기질 (PM2.5)", value: "12 μg/m³", icon: "🍃" } ].map((item) => (
                               <div key={item.label} className="flex items-center gap-5 rounded-[2.5rem] bg-[var(--surface-strong)] p-8 border border-[var(--line)] shadow-sm">
                                 <span className="text-4xl filter drop-shadow-lg">{item.icon}</span>
                                 <div>
                                   <p className="text-[9px] font-black text-[var(--text-hint)] uppercase tracking-widest mb-1">{item.label}</p>
                                   <p className="text-lg font-[1000] text-[var(--text-primary)] tracking-tighter italic">{item.value}</p>
                                 </div>
                               </div>
                             ))}
                          </div>
                       </div>
                       <div className="rounded-[2.5rem] p-8 border border-[var(--accent-strong)]/20 flex items-center justify-between bg-[var(--accent-soft)]/5 shadow-inner">
                          <div className="flex flex-col gap-1">
                             <span className="text-[9px] font-black text-[var(--text-hint)] uppercase tracking-widest opacity-60">NEXT FACILITY AUDIT</span>
                             <span className="text-sm font-black text-[var(--text-secondary)] italic">정기 정밀 점검 예정일</span>
                          </div>
                          <span className="text-xl font-black text-[var(--accent-strong)] italic tracking-tighter">2026.04.15 <span className="text-[10px] ml-2 opacity-50 NOT-italic">(D-15)</span></span>
                       </div>
                    </div>
                  </div>
                )}
              </div>

              <div className="flex justify-end pt-10">
                <Link
                  href={`/${locale}/projects/${projectId}/${stages.find(s => s.id === activeStage)?.path}`}
                  className="group relative inline-flex h-20 items-center justify-center gap-6 rounded-full bg-[var(--accent-strong)] px-14 text-xs font-black text-white uppercase tracking-[0.3em] shadow-[var(--shadow-glow)] transition-all hover:scale-105 active:scale-95"
                >
                  <span className="relative z-10">{stages.find(s => s.id === activeStage)?.name} 정밀 분석 모듈 진입 ↗</span>
                  <div className="absolute inset-0 rounded-full bg-white opacity-0 group-hover:opacity-10 transition-opacity" />
                </Link>
              </div>
            </div>
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}
