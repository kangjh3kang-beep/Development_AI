"use client";

import { useParams } from "next/navigation";
import { motion } from "framer-motion";
import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { ModuleCommandStrip } from "@/components/layout/ModuleCommandStrip";
import { isValidLocale, type Locale } from "@/i18n/config";
import { isMockMode } from "@/lib/runtime-mode";
import { useDictionary } from "@/hooks/use-dictionary";
import { ProjectEsgWorkspaceClient } from "@/components/projects/ProjectEsgWorkspaceClient";
import { NextStageCta } from "@/components/projects/NextStageCta";
import GresbScoreCard from "@/components/esg/GresbScoreCard";
import { useProjectContextStore } from "@/store/useProjectContextStore";

export default function ESGPage() {
  const { locale, id } = useParams() as { locale: string; id: string };
  const { dictionary, isLoading } = useDictionary(locale as Locale);
  const esgData = useProjectContextStore((s) => s.esgData);

  if (isLoading || !dictionary) {
    return (
      <div className="flex h-[60vh] items-center justify-center">
        <div className="h-12 w-12 animate-spin rounded-full border-4 border-teal-500 border-t-transparent" />
      </div>
    );
  }

  if (!isValidLocale(locale)) {
    return null;
  }

  const runtimeMode = isMockMode()
    ? dictionary.workspace.modeMock
    : dictionary.workspace.modeLive;

  const t = dictionary.modulePlaceholders["esg"];

  return (
    <div className="flex flex-col gap-12 pb-20">
      <ModuleCommandStrip label="ESG · 환경·사회·지배구조" meta={runtimeMode} />
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

      <div className="grid gap-10 md:grid-cols-2">
        {/* ESG Score Matrix */}
        <motion.div
          initial={{ opacity: 0, x: -30 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.2 }}
          className="rounded-[3.5rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] p-12 shadow-[var(--shadow-2xl)] backdrop-blur-3xl"
        >
          <div className="flex items-center gap-4 mb-10">
            <div className="h-10 w-10 rounded-2xl bg-[var(--accent-soft)] flex items-center justify-center text-[var(--accent-strong)]">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
            </div>
            <h3 className="cc-label tracking-[0.4em]">ESG Risk Matrix</h3>
          </div>

          {(() => {
            const hasCarbon = esgData?.totalCarbonPerSqm != null;
            // E(환경)만 실제 LCA 탄소 원단위(kgCO2e/㎡)에서 산출. S/G는 정량 평가 데이터가
            // 없으므로 가짜 점수를 만들지 않고 정성 평가(GRESB 카드 참조)로 안내한다.
            const eScore = hasCarbon
              ? Math.max(0, Math.min(100, 100 - (esgData!.totalCarbonPerSqm ?? 0) / 10))
              : null;
            const grade = (s: number) =>
              s >= 90 ? "S" : s >= 80 ? "A+" : s >= 70 ? "A" : s >= 60 ? "B" : "C";
            return (
              <div className="grid grid-cols-1 gap-6 min-w-0">
                {/* E — 실 LCA 탄소 기반 */}
                <div className="relative rounded-[2rem] border border-[var(--line)] bg-[var(--surface-soft)] p-6 transition-all hover:bg-[var(--surface)]">
                  <div className="flex items-center justify-between">
                    <div className="space-y-1">
                      <span className="text-[11px] font-black uppercase tracking-widest text-[var(--text-secondary)]">Environmental (E)</span>
                      <p className="text-[9px] font-bold text-[var(--accent-strong)]/60 uppercase">
                        {hasCarbon ? "LCA 탄소 원단위 기반" : "LCA 분석 대기"}
                      </p>
                    </div>
                    <div className="text-right">
                      <span className="block cc-num text-2xl font-[1000] leading-none mb-1">
                        {eScore != null ? Math.round(eScore) : "—"}
                        <span className="text-xs text-[var(--text-hint)] tracking-normal">/100</span>
                      </span>
                      {eScore != null && (
                        <span className="inline-block rounded-lg bg-[var(--accent-soft)] px-3 py-1 text-[10px] font-black text-[var(--accent-strong)]">{grade(eScore)}</span>
                      )}
                    </div>
                  </div>
                  <div className="mt-4 h-1.5 w-full rounded-full bg-[var(--line)] overflow-hidden">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${eScore ?? 0}%` }}
                      transition={{ delay: 0.5, duration: 1 }}
                      className="h-full bg-gradient-to-r from-[var(--accent-strong)] to-[var(--status-info)]"
                    />
                  </div>
                </div>

                {/* S / G — 정량 데이터 없음(가짜 점수 금지). GRESB 스코어링으로 안내 */}
                <div className="rounded-[2rem] border border-dashed border-[var(--line)] bg-[var(--surface-soft)] p-6">
                  <span className="text-[11px] font-black uppercase tracking-widest text-[var(--text-secondary)]">Social (S) · Governance (G)</span>
                  <p className="mt-2 text-xs font-medium text-[var(--text-tertiary)] leading-relaxed">
                    본 단계는 LCA 탄소(E) 중심입니다. S/G는 정량 평가 데이터가 없어 점수를 표기하지 않습니다.
                    아래 GRESB 스코어링에서 경영(G)·성과·개발 항목을 정량 산출하세요.
                  </p>
                </div>
              </div>
            );
          })()}
        </motion.div>

        {/* GRESB ESG 스코어링 — 백엔드 /api/v1/gresb/score 실산식 */}
        <motion.div
          initial={{ opacity: 0, x: 30 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.3 }}
        >
          <GresbScoreCard />
        </motion.div>
      </div>

      {/* ── Live Workspace: LCA, EPD, Low-Carbon Alternatives ── */}
      <motion.div
        initial={{ opacity: 0, y: 40 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.4 }}
      >
        <ProjectEsgWorkspaceClient locale={locale as Locale} projectId={id} />
      </motion.div>

      <NextStageCta locale={locale} currentStage="esg" />
    </div>
  );
}
