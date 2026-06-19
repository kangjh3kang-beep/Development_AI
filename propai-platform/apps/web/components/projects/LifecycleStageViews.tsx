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

  // 법규 준수 체크리스트 — 저장된 법규검토 결과(complianceData) 실값만 표시.
  // 무목업: 분석 전이면 항목을 만들지 않고(빈 배열), 화면에서 정직 CTA를 띄운다.
  const complianceData = useProjectContextStore((s) => s.complianceData);
  const complianceHasData =
    !!complianceData &&
    (complianceData.bcrCompliant != null ||
      complianceData.farCompliant != null ||
      complianceData.heightCompliant != null ||
      (complianceData.violations?.length ?? 0) > 0);
  // pass=true → 적합(체크), pass=false → 위반(미체크), null → 미판정(제외).
  const complianceChecks: { label: string; checked: boolean }[] = complianceHasData
    ? [
        { key: "건폐율 적합성", pass: complianceData!.bcrCompliant },
        { key: "용적률 적합성", pass: complianceData!.farCompliant },
        { key: "높이제한 적합성", pass: complianceData!.heightCompliant },
      ]
        .filter((c) => c.pass != null)
        .map((c) => ({ label: c.key, checked: !!c.pass }))
    : [];
  const complianceViolations = complianceData?.violations ?? [];

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
    { id: "design_ai", name: t.stageDesignAI || "AI 설계", path: "design" },
    { id: "feasibility", name: t.stageFeasibility || "사업성 분석", path: "feasibility" },
    { id: "esg_dashboard", name: t.stageESG || "ESG 컨설팅", path: "esg" },
    { id: "permit_portal", name: t.stagePermits || "인허가 포털", path: "permit" },
    { id: "construction", name: t.stageConstruction || "스마트 시공", path: "construction" },
    { id: "operations", name: t.stageOperations || "자산 관리", path: "operations" },
  ];
  // compact(보고서 동시표시): 보고서와 중복되는 입지·법규·사업성·ESG 제외.
  const REPORT_COVERED = new Set(["site_analysis", "legal_compliance", "feasibility", "esg_dashboard"]);
  const stages = compact ? allStages.filter((s) => !REPORT_COVERED.has(s.id)) : allStages;

  // 활성 스테이지 메타(없으면 안전 폴백). path가 undefined면 /projects/{id}/undefined 404가 발생하므로
  // 항상 유효한 세그먼트("site-analysis")로 폴백한다.
  const activeStageMeta = stages.find((s) => s.id === activeStage);
  const activeStageSeg = activeStageMeta?.path ?? "site-analysis";
  const activeStageName = activeStageMeta?.name ?? "입지 분석";

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
                      <h4 className="text-[10px] font-black text-[var(--text-hint)] uppercase tracking-[0.5em] px-4">법규 준수 체크리스트</h4>
                      {complianceHasData ? (
                        <div className="grid gap-4">
                          {complianceChecks.map((item, i) => (
                            <motion.div
                              key={item.label}
                              initial={{ opacity: 0, scale: 0.95 }}
                              animate={{ opacity: 1, scale: 1 }}
                              transition={{ delay: 0.5 + i * 0.05 }}
                              className="flex items-center gap-6 rounded-[2rem] bg-[var(--surface-soft)] px-8 py-5 border border-[var(--line)] transition-all hover:bg-[var(--surface-strong)] hover:translate-x-2"
                            >
                              <div className={`flex h-8 w-8 items-center justify-center rounded-xl border-2 transition-all ${
                                item.checked
                                  ? "border-[var(--status-success)] bg-[var(--status-success)]/10 text-[var(--status-success)] shadow-[0_0_15px_rgba(16,185,129,0.3)]"
                                  : "border-[var(--status-error)] bg-[var(--status-error)]/10 text-[var(--status-error)]"
                              }`}>
                                {item.checked
                                  ? <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="4"><polyline points="20 6 9 17 4 12"/></svg>
                                  : <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="4"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>}
                              </div>
                              <span className={`text-[13px] font-black tracking-tight ${item.checked ? "text-[var(--text-primary)]" : "text-[var(--status-error)]"}`}>
                                {item.label} {item.checked ? "적합" : "위반"}
                              </span>
                            </motion.div>
                          ))}
                          {complianceViolations.length > 0 && (
                            <div className="rounded-[2rem] border border-[var(--status-error)]/30 bg-[var(--status-error)]/5 px-8 py-5">
                              <p className="text-[10px] font-black uppercase tracking-[0.3em] text-[var(--status-error)] mb-3">위반 사항</p>
                              <ul className="space-y-2">
                                {complianceViolations.map((v) => (
                                  <li key={v} className="text-[13px] font-black text-[var(--text-secondary)]">· {v}</li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>
                      ) : (
                        <div className="flex flex-col items-center gap-4 rounded-[2.5rem] border border-dashed border-[var(--line-strong)] bg-[var(--surface-soft)] p-10 text-center">
                          <span className="text-4xl">📋</span>
                          <p className="text-sm font-black text-[var(--text-primary)]">법규검토 미실행</p>
                          <p className="text-xs leading-relaxed text-[var(--text-secondary)] max-w-md">아직 이 프로젝트의 법규 준수 검토 결과가 없습니다. ‘법규검토’ 모듈에서 분석을 실행하면 건폐율·용적률·높이제한 적합성과 위반 근거가 여기에 연동됩니다.</p>
                          <Link href={`/${locale}/projects/${projectId}/legal`} className="rounded-full bg-[var(--accent-strong)] px-6 py-3 text-xs font-black uppercase tracking-[0.2em] text-white">법규 분석 실행 ↗</Link>
                        </div>
                      )}
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
                        <Link href={`/${locale}/esg`} className="rounded-full bg-[var(--accent-strong)] px-6 py-3 text-xs font-black uppercase tracking-[0.2em] text-white">ESG 분석 ↗</Link>
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
                  <div className="flex min-h-[420px] flex-col items-center justify-center gap-8 rounded-[3rem] border border-dashed border-[var(--line-strong)] bg-[var(--surface-soft)] p-12 text-center">
                    <div className="flex h-16 w-16 items-center justify-center rounded-3xl bg-[var(--accent-soft)] text-[var(--accent-strong)] shadow-[var(--shadow-glow)]">
                      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="m9 15 2 2 4-4"/></svg>
                    </div>
                    <div className="space-y-3 max-w-xl">
                      <h4 className="text-2xl font-[1000] tracking-tight text-[var(--text-primary)]">인허가 분석 미실행</h4>
                      <p className="text-sm leading-relaxed text-[var(--text-secondary)]">
                        아직 이 프로젝트의 인허가 분석 결과가 없습니다. ‘인허가 포털’ 모듈에서 분석을 실행하면
                        부지·조례·상위법령을 종합한 <b className="text-[var(--text-primary)]">개발방식별 가능성·문제점·해결방안</b>이 여기에 연동됩니다.
                      </p>
                    </div>
                    <Link href={`/${locale}/projects/${projectId}/permit`}
                      className="inline-flex h-14 items-center gap-3 rounded-full bg-[var(--accent-strong)] px-9 text-xs font-black uppercase tracking-[0.2em] text-white shadow-[var(--shadow-glow)] transition-all hover:scale-105">
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>
                      인허가 분석 실행
                    </Link>
                  </div>
                )}

                {activeStage === "operations" && (
                  <div className="flex min-h-[420px] flex-col items-center justify-center gap-8 rounded-[3rem] border border-dashed border-[var(--line-strong)] bg-[var(--surface-soft)] p-12 text-center">
                    <div className="flex h-16 w-16 items-center justify-center rounded-3xl bg-[var(--surface-strong)] text-[var(--text-hint)] border border-[var(--line)]">
                      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg>
                    </div>
                    <div className="space-y-3 max-w-xl">
                      <h4 className="text-2xl font-[1000] tracking-tight text-[var(--text-primary)]">운영 분석 준비중 (데이터 없음)</h4>
                      <p className="text-sm leading-relaxed text-[var(--text-secondary)]">
                        준공 이후 자산 운영 단계의 입주율·NOI·관리비 효율·IoT 센서 지표는 운영 데이터가 연동되는 단계에서 제공됩니다.
                        현재 이 프로젝트에는 운영 실데이터가 없어 지표를 표시하지 않습니다(가짜 수치 표기 금지).
                      </p>
                    </div>
                  </div>
                )}
              </div>

              <div className="flex justify-end pt-10">
                <Link
                  href={`/${locale}/projects/${projectId}/${activeStageSeg}`}
                  className="group relative inline-flex h-20 items-center justify-center gap-6 rounded-full bg-[var(--accent-strong)] px-14 text-xs font-black text-white uppercase tracking-[0.3em] shadow-[var(--shadow-glow)] transition-all hover:scale-105 active:scale-95"
                >
                  <span className="relative z-10">{activeStageName} 정밀 분석 모듈 진입 ↗</span>
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
