"use client";

import { useParams } from "next/navigation";
import { motion } from "framer-motion";
import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { isValidLocale, type Locale } from "@/i18n/config";
import { useDictionary } from "@/hooks/use-dictionary";

export default function ESGPage() {
  const { locale, id } = useParams() as { locale: string; id: string };
  const { dictionary, isLoading } = useDictionary(locale as Locale);

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

  const runtimeMode =
    process.env.NEXT_PUBLIC_USE_MOCKS === "false"
      ? dictionary.workspace.modeLive
      : dictionary.workspace.modeMock;

  const t = dictionary.modulePlaceholders["esg"];

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
            <h3 className="text-[10px] font-black text-[var(--text-tertiary)] uppercase tracking-[0.4em]">ESG Risk Matrix</h3>
          </div>

          <div className="grid gap-6">
            {[
              { label: "Environmental (E)", score: 88, grade: "A+", desc: "Net Zero Readiness" },
              { label: "Social (S)", score: 74, grade: "A", desc: "Community Impact" },
              { label: "Governance (G)", score: 92, grade: "S", desc: "Transparency" },
              { label: "Overall Rating", score: 85, grade: "A+", desc: "Premium Standard" },
            ].map((item, i) => (
              <div key={item.label} className="relative rounded-[2rem] border border-[var(--line)] bg-[var(--surface-soft)] p-6 transition-all hover:bg-[var(--surface)] group/card">
                <div className="flex items-center justify-between">
                  <div className="space-y-1">
                    <span className="text-[11px] font-black uppercase tracking-widest text-[var(--text-secondary)]">{item.label}</span>
                    <p className="text-[9px] font-bold text-[var(--accent-strong)]/60 uppercase">{item.desc}</p>
                  </div>
                  <div className="text-right">
                    <span className="block text-2xl font-[1000] text-[var(--text-primary)] leading-none mb-1 tracking-tighter">{item.score}<span className="text-xs text-[var(--text-hint)] tracking-normal">/100</span></span>
                    <span className="inline-block rounded-lg bg-[var(--accent-soft)] px-3 py-1 text-[10px] font-black text-[var(--accent-strong)]">{item.grade}</span>
                  </div>
                </div>
                <div className="mt-4 h-1.5 w-full rounded-full bg-[var(--line)] overflow-hidden">
                  <motion.div 
                    initial={{ width: 0 }}
                    animate={{ width: `${item.score}%` }}
                    transition={{ delay: 0.5 + i * 0.1, duration: 1 }}
                    className="h-full bg-gradient-to-r from-[var(--accent-strong)] to-[var(--info)] shadow-[0_0_15px_var(--accent-strong)]/20"
                  />
                </div>
              </div>
            ))}
          </div>
        </motion.div>

        {/* Carbon Emission Intelligence */}
        <motion.div 
          initial={{ opacity: 0, x: 30 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.3 }}
          className="rounded-[3.5rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] p-12 shadow-[var(--shadow-2xl)] backdrop-blur-3xl overflow-hidden relative"
        >
          <div className="absolute top-0 right-0 p-12 opacity-5 translate-x-1/4 -translate-y-1/4 text-[var(--text-primary)]">
             <svg width="200" height="200" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1"><path d="M11 20A7 7 0 0 1 4 13a7 7 0 0 1 7-7 7 7 0 0 1 7 7c0 3.87-3.13 7-7 7z"/><path d="M17.5 19.5L22 24"/><path d="M22 17l-4.5 4.5"/></svg>
          </div>

           <div className="flex items-center gap-4 mb-10">
            <div className="h-10 w-10 rounded-2xl bg-[var(--info-soft)] flex items-center justify-center text-[var(--info)]">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/></svg>
            </div>
            <h3 className="text-[10px] font-black text-[var(--text-tertiary)] uppercase tracking-[0.4em]">Carbon Life-Cycle Analysis</h3>
          </div>

          <div className="grid gap-4">
            {[
              { label: "전과정 탄소 배출 목표", value: "2,450", unit: "tCO2e", color: "text-[var(--text-primary)]" },
              { label: "예상 건축 배출량", value: "3,120", unit: "tCO2e", color: "text-[var(--error)]" },
              { label: "AI 기반 저감 대상량", value: "-670", unit: "tCO2e", color: "text-[var(--accent-strong)]" },
              { label: "에너지 효율 등급", value: "1+++", unit: "Grade", color: "text-[var(--info)]" },
            ].map((item) => (
              <div key={item.label} className="flex items-center justify-between gap-6 rounded-[2rem] bg-[var(--surface-soft)] px-10 py-8 border border-[var(--line)] transition-all hover:bg-[var(--surface)] group/stat shadow-[var(--shadow-sm)]">
                <span className="text-[11px] font-black uppercase tracking-widest text-[var(--text-tertiary)] group-hover/stat:text-[var(--text-secondary)] transition-colors max-w-[150px]">{item.label}</span>
                <div className="text-right">
                  <span className={`text-4xl font-[1000] tracking-[0.02em] ${item.color} leading-none block`}>{item.value}</span>
                  <span className="text-[9px] font-black uppercase tracking-widest text-[var(--text-hint)]">{item.unit}</span>
                </div>
              </div>
            ))}
          </div>

          <div className="mt-8 rounded-3xl bg-[var(--accent-soft)] p-6 border border-[var(--accent-strong)]/10">
            <p className="text-[10px] font-black text-[var(--accent-strong)] uppercase tracking-widest mb-2 italic">AI Insight</p>
            <p className="text-xs font-bold text-[var(--text-secondary)] leading-relaxed italic">
              &quot;고효율 단열재 및 BIPV 시스템 적용 시 저감 목표치의 82%를 달성할 수 있습니다.&quot;
            </p>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
