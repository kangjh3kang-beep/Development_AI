"use client";

import { useParams } from "next/navigation";
import { motion } from "framer-motion";
import { CadEditor } from "@/components/cad/CadEditor";
import { isValidLocale } from "@/i18n/config";

export default function CadPage() {
  const { locale, id } = useParams() as { locale: string; id: string };

  if (!isValidLocale(locale)) {
    return null;
  }

  return (
    <div className="flex flex-col gap-12 pb-20">
      {/* ── Design Synergy Multi-layer Insight ── */}
      <motion.div 
        initial={{ opacity: 0, scale: 0.98 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ delay: 0.2 }}
        className="relative overflow-hidden rounded-[3rem] border border-[var(--accent-strong)]/20 bg-[var(--surface-strong)] p-12 lg:p-16 shadow-[var(--shadow-2xl)] backdrop-blur-3xl group"
      >
        <div className="absolute -left-20 -top-20 h-64 w-64 rounded-full bg-[var(--accent-strong)]/10 blur-[100px] transition-all duration-1000 group-hover:scale-150" />
        
        <div className="relative z-10 flex flex-col gap-10 lg:flex-row lg:items-center lg:gap-16">
          <div className="flex h-24 w-24 shrink-0 items-center justify-center rounded-[2rem] bg-[var(--accent-strong)] shadow-[var(--shadow-glow)]">
            <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="m18 16 4-4-4-4"/><path d="m6 8-4 4 4 4"/><path d="m14.5 4-5 16"/></svg>
          </div>
          <div className="space-y-6">
            <div className="inline-flex items-center gap-2 rounded-full border border-[var(--accent-strong)]/20 bg-[var(--accent-soft)] px-4 py-1.5 text-[10px] font-black uppercase tracking-[0.2em] text-[var(--accent-strong)]">
               Design-To-Code Pipeline Active
            </div>
            <h3 className="text-3xl font-[1000] tracking-tight text-[var(--text-primary)] sm:text-4xl">
              AI 건축 설계와 <span className="text-[var(--accent-strong)] italic underline decoration-[var(--accent-strong)]/30 underline-offset-4 font-black">CAD 엔진의 완벽한 결합.</span>
            </h3>
            <p className="max-w-3xl text-sm font-bold leading-[1.8] text-[var(--text-secondary)] italic tracking-tight underline decoration-[var(--line)] underline-offset-4">
              &quot;사통팔땅의 AI 설계 엔진은 단순히 공간을 배치하는 것을 넘어, 생성된 설계안을 즉시 <span className="text-[var(--text-primary)] font-black underline decoration-[var(--accent-strong)]/50 underline-offset-4">CAD 레이어 데이터와 동기화</span>합니다. 사용자는 웹 기반 고성능 CAD 뷰어에서 AI가 제안한 평면과 단면을 실시간으로 검토하고, 즉각적인 수정을 통해 설계의 완성도를 극대화할 수 있습니다.&quot;
            </p>
          </div>
        </div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 40 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.4 }}
        className="cc-panel cc-bracketed rounded-[4rem] p-4 lg:p-8 shadow-[var(--shadow-2xl)] overflow-hidden group"
      >
        <i className="cc-bracket cc-bracket--tl" aria-hidden /><i className="cc-bracket cc-bracket--tr" aria-hidden />
        <i className="cc-bracket cc-bracket--bl" aria-hidden /><i className="cc-bracket cc-bracket--br" aria-hidden />
        <div className="mb-6 flex items-center justify-between px-8">
            <div className="flex items-center gap-4">
              <span className="cc-meta">CAD DESIGN STUDIO · HI-FI</span>
              <span className="cc-live"><i />STAGE 2</span>
            </div>
            <div className="flex items-center gap-4">
              <span className="cc-label">Enhanced</span>
              <div className="flex gap-2">
                  <div className="h-2 w-2 rounded-full bg-[var(--status-error)]/30 group-hover:bg-[var(--status-error)] transition-colors" />
                  <div className="h-2 w-2 rounded-full bg-[var(--status-warning)]/30 group-hover:bg-[var(--status-warning)] transition-colors" />
                  <div className="h-2 w-2 rounded-full bg-[var(--status-success)]/30 group-hover:bg-[var(--status-success)] transition-colors" />
              </div>
            </div>
        </div>
        <CadEditor projectId={id} />
      </motion.div>
    </div>
  );
}
