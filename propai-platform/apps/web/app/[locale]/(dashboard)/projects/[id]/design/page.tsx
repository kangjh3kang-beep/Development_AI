"use client";

import { useParams } from "next/navigation";
import { motion } from "framer-motion";
import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { ProjectDesignWorkspaceClient } from "@/components/projects/ProjectDesignWorkspaceClient";
import { isValidLocale, type Locale } from "@/i18n/config";
import { useDictionary } from "@/hooks/use-dictionary";

export default function DesignPage() {
  const { locale, id } = useParams() as { locale: string; id: string };
  const { dictionary, isLoading } = useDictionary(locale as Locale);

  if (isLoading || !dictionary) {
    return (
      <div className="flex h-[60vh] items-center justify-center">
        <div className="h-12 w-12 animate-spin rounded-full border-4 border-[var(--accent-strong)] border-t-transparent shadow-[var(--shadow-glow)]" />
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

  const t = dictionary.modulePlaceholders["design"];

  return (
    <div className="flex flex-col gap-12 pb-20 font-sans">
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

      {/* ── Architectural Intelligence Synergy ── */}
      <motion.div 
        initial={{ opacity: 0, scale: 0.98 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ delay: 0.2 }}
        className="relative overflow-hidden rounded-[3rem] border border-[var(--line-strong)] bg-[var(--surface-strong)]/80 p-12 lg:p-16 shadow-[var(--shadow-2xl)] backdrop-blur-3xl group"
      >
        <div className="absolute -right-20 -top-20 h-64 w-64 rounded-full bg-[var(--accent-strong)]/10 blur-[100px] transition-all duration-1000 group-hover:scale-150" />
        
        <div className="relative z-10 flex flex-col gap-10 lg:flex-row lg:items-center lg:gap-16">
          <div className="flex h-24 w-24 shrink-0 items-center justify-center rounded-[2.5rem] bg-gradient-to-br from-[var(--accent-strong)] to-indigo-600 shadow-[var(--shadow-glow)]">
             <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
          </div>
          <div className="space-y-6">
            <div className="inline-flex items-center gap-2 rounded-full border border-[var(--accent-strong)]/20 bg-[var(--accent-soft)] px-4 py-1.5 text-[10px] font-black uppercase tracking-[0.2em] text-[var(--accent-strong)]">
               Generative AI Workstream Active
            </div>
            <h3 className="text-3xl font-[1000] tracking-tight text-[var(--text-primary)] sm:text-4xl">
              데이터가 빚어내는 <span className="text-[var(--accent-strong)] font-black italic underline decoration-[var(--accent-strong)]/30 underline-offset-8">최적의 공간 설계.</span>
            </h3>
            <p className="max-w-3xl text-sm font-medium leading-[1.8] text-[var(--text-secondary)] italic tracking-tight underline decoration-[var(--line-strong)] decoration-2 underline-offset-4">
              "사통팔땅의 AI 설계 솔루션은 단순한 평면 생성을 넘어 법적 상한 용적률, 일조 사선 제한, 세대별 채광 및 향을 복합 시뮬레이션합니다. 인간 건축가의 감각과 AI의 정밀한 연산이 결합되어 수익성과 주거 환경의 균형을 완벽하게 맞춘 기획 설계안을 단 몇 초 만에 도출합니다."
            </p>
          </div>
        </div>
      </motion.div>

      <motion.div 
        initial={{ opacity: 0, y: 40 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.4 }}
        className="rounded-[4rem] border border-[var(--line-strong)] bg-[var(--surface-strong)]/50 p-6 lg:p-12 shadow-[var(--shadow-2xl)] backdrop-blur-xl"
      >
        <ProjectDesignWorkspaceClient locale={locale as Locale} projectId={id} />
      </motion.div>
    </div>
  );
}
