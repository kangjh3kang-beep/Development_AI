"use client";

import dynamic from "next/dynamic";
import { useParams } from "next/navigation";
import { motion } from "framer-motion";
import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { isValidLocale, type Locale } from "@/i18n/config";
import { useDictionary } from "@/hooks/use-dictionary";
import { ContractorIntelligence } from "@/components/construction/ContractorIntelligence";
import { ProjectConstructionWorkspaceClient } from "@/components/projects/ProjectConstructionWorkspaceClient";
import { NextStageCta } from "@/components/projects/NextStageCta";

const CostAndQuantityDashboard = dynamic(
  () => import("@/components/construction/CostAndQuantityDashboard").then(mod => mod.CostAndQuantityDashboard)
);

const ScheduleSupervisionPanel = dynamic(
  () => import("@/components/construction/ScheduleSupervisionPanel").then(mod => mod.ScheduleSupervisionPanel)
);

export default function ConstructionPage() {
  const { locale, id } = useParams() as { locale: string; id: string };
  const { dictionary, isLoading } = useDictionary(locale as Locale);

  if (isLoading || !dictionary) {
    return (
      <div className="flex h-[60vh] items-center justify-center">
        <div className="h-12 w-12 animate-spin rounded-full border-4 border-[var(--data-accent)] border-t-transparent" />
      </div>
    );
  }

  if (!isValidLocale(locale)) {
    return null;
  }

  const runtimeMode =
    process.env.NEXT_PUBLIC_USE_MOCKS === "false"
      ? dictionary.workspace.modeLive
      : dictionary.workspace.modeMock;

  const t = dictionary.modulePlaceholders["construction"];

  return (
    <div className="flex flex-col gap-12 pb-20">
      <motion.div
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <ModulePlaceholder
          eyebrow={t.eyebrow}
          title={t.title}
          description={t.description}
          statusLabel={runtimeMode}
          localeLabel={locale}
          items={t.items}
        />
      </motion.div>

      {/* ── Cinematic Insight Box ── */}
      <motion.div
        initial={{ opacity: 0, scale: 0.98 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ delay: 0.2 }}
        className="cc-panel cc-bracketed relative overflow-hidden rounded-[2.5rem] p-10 shadow-xl group"
      >
        <i className="cc-bracket cc-bracket--tl" aria-hidden /><i className="cc-bracket cc-bracket--tr" aria-hidden />
        <i className="cc-bracket cc-bracket--bl" aria-hidden /><i className="cc-bracket cc-bracket--br" aria-hidden />
        <div className="cc-grid-bg" aria-hidden />
        <div className="absolute -right-20 -top-20 h-40 w-40 rounded-full bg-[var(--data-accent-soft)] blur-3xl transition-all duration-1000 group-hover:scale-150" />

        <div className="relative z-10 flex flex-col gap-6 lg:flex-row lg:items-center lg:gap-12">
          <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl bg-[var(--data-accent)] shadow-[var(--data-glow)]">
            <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
          </div>
          <div className="space-y-4">
            <span className="cc-meta">CONSTRUCTION SYNERGY · AI</span>
            <h3 className="text-xl font-black tracking-tight text-[var(--text-primary)]">
              시공감리 vs 협력사 추천의 지능형 시너지
            </h3>
            <p className="max-w-4xl text-sm font-medium leading-relaxed text-[var(--text-secondary)] italic tracking-tight">
              사통팔땅의 <span className="text-[var(--data-accent)] font-black">최적 협력사 추천</span> 엔진은 과거 <span className="text-[var(--chart-2)] font-black">시공감리 빅데이터</span>를 정밀 분석합니다. 공정 준수율, 실사 하자 발생률, 자재 매핑 정합성 등의 핵심 피치를 AI가 학습하여, 현재 프로젝트의 BIM 설계 도면과 가장 부합하는 고숙련 파트너를 정교하게 매칭합니다.
            </p>
          </div>
        </div>
      </motion.div>

      {/* ── Live Workspace: Cost, Checklist, Risk ── */}
      <motion.div
        initial={{ opacity: 0, y: 40 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.25 }}
      >
        <ProjectConstructionWorkspaceClient locale={locale as Locale} projectId={id} />
      </motion.div>

      <div className="space-y-16">
        <motion.div
          initial={{ opacity: 0, y: 40 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="cc-panel rounded-[3rem] p-6 lg:p-12 shadow-2xl"
        >
          <ContractorIntelligence locale={locale as Locale} />
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 40 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="cc-panel rounded-[3rem] p-6 lg:p-12 shadow-2xl"
        >
          <CostAndQuantityDashboard projectId={id} dictionary={(dictionary as any).cost ?? {}} />
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 40 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="cc-panel rounded-[3rem] p-6 lg:p-12 shadow-2xl"
        >
          <ScheduleSupervisionPanel projectId={id} dictionary={(dictionary as any).schedule ?? {}} />
        </motion.div>
      </div>

      <NextStageCta locale={locale} currentStage="construction" />
    </div>
  );
}
