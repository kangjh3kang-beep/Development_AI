"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import dynamic from "next/dynamic";
import { motion, AnimatePresence } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
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

const CadBimIntegrationPanel = dynamic(
  () => import("../design/CadBimIntegrationPanel").then(mod => mod.CadBimIntegrationPanel),
  { ssr: false, loading: () => <div className="h-[600px] w-full animate-pulse rounded-[2rem] bg-white/5 flex items-center justify-center"><p className="text-white/20 font-black uppercase tracking-[0.3em] text-xs text-center">BIM 3D 엔진 활성화 중...</p></div> }
);

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
}

export function LifecycleStageViews({ projectId, dictionary }: LifecycleStageViewsProps) {
  const [activeStage, setActiveStage] = useState<StageType>("design_ai");
  const params = useParams();
  const locale = params.locale as string;
  const t = dictionary.lifecycle;

  const projectQuery = useQuery({
    queryKey: ["projects", "detail", projectId],
    queryFn: () => apiClient.get<Record<string, any>>(`/projects/${projectId}`),
  });

  const p = projectQuery.data || {};

  const stages = [
    { id: "site_analysis", name: t.stageSite || "입지 분석", icon: "🗺️", path: "site-analysis" },
    { id: "legal_compliance", name: t.stageLegal || "법규 검토", icon: "⚖️", path: "legal" },
    { id: "design_ai", name: t.stageDesignAI || "AI 설계", icon: "🎨", path: "cad" },
    { id: "feasibility", name: t.stageFeasibility || "사업성 분석", icon: "📈", path: "feasibility" },
    { id: "esg_dashboard", name: t.stageESG || "ESG 컨설팅", icon: "🌿", path: "esg" },
    { id: "permit_portal", name: t.stagePermits || "인허가 포털", icon: "📝", path: "permit" },
    { id: "construction", name: t.stageConstruction || "스마트 시공", icon: "🏗️", path: "construction" },
    { id: "operations", name: t.stageOperations || "자산 관리", icon: "⚙️", path: "operations" },
  ];

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
          <div className="flex gap-2 overflow-x-auto pb-4 scrollbar-hide px-2 -mx-2">
            <div className="flex gap-2 min-w-max rounded-[2.5rem] bg-[var(--surface-strong)] p-2 border border-[var(--line-strong)] shadow-[var(--shadow-2xl)] backdrop-blur-3xl">
              {stages.map((stage) => (
                <button
                  key={stage.id}
                  onClick={() => setActiveStage(stage.id as StageType)}
                  className={`relative flex items-center gap-3 whitespace-nowrap rounded-full px-7 py-4 text-[11px] font-black uppercase tracking-[0.2em] transition-all duration-500 ${
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
                  <span className="relative z-10 text-xl">{stage.icon}</span>
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
                {activeStage === "design_ai" && <CadBimIntegrationPanel projectId={projectId} dictionary={dictionary.cadBim} />}
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
                      {[
                        { label: "필지번호 (PNU)", value: p.pnu || "1168010100100010001" },
                        { label: "면적", value: p.total_area_sqm ? `${p.total_area_sqm.toLocaleString()} m²` : "4,500 m²" },
                        { label: "공시지가", value: "12,500,000 원/m²" },
                        { label: "용도지역", value: p.status === "active" ? "일반상업지역" : "준주거지역" },
                        { label: "건폐율 / 용적률", value: "60% / 300%" },
                      ].map((item, i) => (
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
                      {[
                        { label: "건폐율", limit: "60%", current: "58.2%", progress: 97, color: "var(--success)" },
                        { label: "용적률", limit: "300%", current: "298.5%", progress: 99, color: "var(--accent-strong)" },
                        { label: "높이제한", limit: "80m", current: "75.2m", progress: 94, color: "var(--info)" },
                        { label: "일조권", limit: "적용", current: "충족", progress: 100, color: "var(--success)" },
                      ].map((item, i) => (
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
                     <div className="grid gap-10 md:grid-cols-3">
                      {[
                        { label: "Environment", score: 84, grade: "A", color: "from-emerald-500 to-teal-500" },
                        { label: "Social", score: 76, grade: "B+", color: "from-blue-500 to-indigo-500" },
                        { label: "Governance", score: 92, grade: "A+", color: "from-indigo-400 to-indigo-600" },
                      ].map((item, i) => (
                        <motion.div 
                          key={item.label} 
                          initial={{ opacity: 0, y: 20 }}
                          animate={{ opacity: 1, y: 0 }}
                          transition={{ delay: i * 0.1 }}
                          className="rounded-[3.5rem] bg-[var(--surface-soft)] p-10 border border-[var(--line)] text-center group/card transition-all hover:-translate-y-3 shadow-lg"
                        >
                          <div className={`mx-auto flex h-24 w-24 items-center justify-center rounded-[2rem] bg-gradient-to-br ${item.color} text-white shadow-2xl transition-transform group-hover/card:scale-110`}>
                            <span className="text-4xl font-[1000] italic">{item.score}</span>
                          </div>
                          <p className="mt-8 text-[11px] font-black uppercase tracking-[0.4em] text-[var(--text-hint)]">{item.label}</p>
                          <p className="mt-2 text-2xl font-[1000] text-[var(--text-primary)] underline decoration-[var(--accent-strong)] decoration-4 underline-offset-8">Rank: {item.grade}</p>
                        </motion.div>
                      ))}
                    </div>
                    <div className="grid gap-10 md:grid-cols-2">
                       <div className="rounded-[3rem] bg-[var(--surface-soft)] p-10 border border-[var(--line)] shadow-sm">
                          <h4 className="text-[10px] font-black text-[var(--text-hint)] uppercase tracking-[0.5em] mb-8">CARBON INTELLIGENCE (CO₂)</h4>
                          <div className="space-y-5">
                            {[ { label: "저감 목표 수치", value: "450 tCO₂e" }, { label: "현재 배출량 추정", value: "412 tCO₂e" }, { label: "최종 저감율", value: "8.4 %", highlight: true } ].map((item) => (
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
                            {[ { label: "에너지효율등급", value: "1++ 등급" }, { label: "녹색건축인증 (G-SEED)", value: "최우수" }, { label: "LEED 글로벌 평가", value: "Gold (예비)" } ].map((item) => (
                              <div key={item.label} className="flex items-center justify-between border-b border-[var(--line)] pb-4">
                                <span className="text-[12px] font-black text-[var(--text-secondary)] uppercase tracking-widest">{item.label}</span>
                                <span className="text-lg font-black text-[var(--text-primary)] tracking-tighter italic">{item.value}</span>
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
