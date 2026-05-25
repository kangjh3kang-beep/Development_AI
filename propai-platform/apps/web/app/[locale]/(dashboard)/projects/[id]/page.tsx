"use client";

import { useParams } from "next/navigation";
import { motion } from "framer-motion";
import { LifecycleStageViews } from "@/components/projects/LifecycleStageViews";
import { isValidLocale, type Locale } from "@/i18n/config";
import { useDictionary } from "@/hooks/use-dictionary";
import { formatCurrencyKRW } from "@/lib/formatters";

export default function ProjectDetailPage() {
  const { locale, id } = useParams() as { locale: string; id: string };
  const { dictionary, isLoading } = useDictionary(locale as Locale);

  if (isLoading || !dictionary) {
    return (
      <div className="flex h-[60vh] items-center justify-center">
        <div className="flex flex-col items-center gap-6">
          <div className="h-16 w-16 animate-spin rounded-full border-4 border-[var(--accent-strong)] border-t-transparent shadow-[var(--shadow-glow)]" />
          <p className="text-[10px] font-[1000] uppercase tracking-[0.5em] text-[var(--text-hint)] animate-pulse italic">Initializing Strategic Hub...</p>
        </div>
      </div>
    );
  }

  if (!isValidLocale(locale)) {
    return null;
  }

  const d = dictionary.pages.projectDetail;

  return (
    <div className="flex flex-col gap-16 pb-20 font-sans">
      {/* ── High-Fidelity Project Hero ── */}
      <section className="relative overflow-hidden rounded-[4rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] p-12 lg:p-20 shadow-[var(--shadow-2xl)] group">
        {/* Cinematic Background Elements */}
        <div className="absolute -right-40 -top-40 h-[500px] w-[500px] rounded-full bg-[var(--accent-strong)]/10 blur-[120px] transition-all duration-1000 group-hover:bg-[var(--accent-strong)]/15" />
        <div className="absolute -left-20 bottom-0 h-96 w-96 rounded-full bg-blue-500/5 blur-[100px]" />
        <div className="absolute inset-0 bg-[url('https://www.transparenttextures.com/patterns/carbon-fibre.png')] opacity-[0.03] dark:invert pointer-events-none" />

        <div className="relative z-10 flex flex-col justify-between gap-12 lg:flex-row lg:items-end">
          <div className="space-y-10">
            <motion.div 
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              className="flex items-center gap-4"
            >
              <span className="inline-flex h-2.5 w-2.5 rounded-full bg-[var(--accent-strong)] shadow-[var(--shadow-glow)]" />
              <p className="text-[10px] font-black uppercase tracking-[0.6em] text-[var(--accent-strong)] italic">
                {d.summary.hub} <span className="text-[var(--text-hint)] tracking-widest">{id}</span>
              </p>
            </motion.div>

            <motion.div 
              initial={{ opacity: 0, y: 30 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 }}
              className="space-y-6"
            >
              <h1 className="text-6xl font-[1000] tracking-tighter text-[var(--text-primary)] leading-[0.9] sm:text-7xl lg:text-8xl">
                {d.summary.name}<span className="text-[var(--accent-strong)]">.</span>
              </h1>
              <div className="flex flex-wrap gap-6">
                <span className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] px-6 py-2.5 text-[11px] font-black uppercase tracking-widest text-[var(--text-secondary)] backdrop-blur-md shadow-[var(--shadow-sm)]">
                  {d.summary.pnu}
                </span>
                <span className="rounded-2xl border border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] px-6 py-2.5 text-[11px] font-black uppercase tracking-widest text-[var(--accent-strong)] backdrop-blur-md shadow-[var(--shadow-sm)]">
                  {d.summary.zone}
                </span>
              </div>
            </motion.div>
          </div>

          <motion.div 
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.3 }}
            className="flex flex-wrap gap-8"
          >
            {[
              { label: d.summary.npv, value: formatCurrencyKRW(1250000000), color: "text-[var(--text-primary)]" },
              { label: d.summary.roi, value: "18.4%", color: "text-[var(--accent-strong)]" },
            ].map((stat, i) => (
              <div key={i} className="relative min-w-[240px] rounded-[3rem] border border-[var(--line-strong)] bg-[var(--surface-strong)]/50 p-10 backdrop-blur-3xl shadow-[var(--shadow-xl)] transition-all hover:-translate-y-2 hover:bg-[var(--surface-soft)] group/stat border-2 border-transparent hover:border-[var(--accent-strong)]/20">
                <p className="text-[10px] font-black uppercase tracking-[0.4em] text-[var(--text-hint)] mb-4">{stat.label}</p>
                <p className={`text-4xl font-[1000] tracking-tighter ${stat.color} group-hover/stat:scale-105 transition-transform duration-500 origin-left`}>
                  {stat.value}
                </p>
                <div className="absolute top-8 right-10 opacity-0 group-hover/stat:opacity-100 transition-opacity duration-500">
                  <svg className="h-6 w-6 text-[var(--accent-strong)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M7 17L17 7M17 7H7M17 7V17"/></svg>
                </div>
              </div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ── Deep Integration Lifecycle Hub ── */}
      <motion.div 
        initial={{ opacity: 0, y: 40 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.5 }}
      >
        <LifecycleStageViews projectId={id} dictionary={dictionary.deepIntegration} />
      </motion.div>
    </div>
  );
}
