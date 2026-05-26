import React from "react";

type ModulePlaceholderProps = {
  eyebrow: string;
  title: string;
  description: string;
  localeLabel: string;
  statusLabel: string;
  items: string[];
};

export function ModulePlaceholder({
  eyebrow,
  title,
  description,
  localeLabel,
  statusLabel,
  items,
}: ModulePlaceholderProps) {
  return (
    <div className="relative overflow-hidden rounded-[var(--radius-2xl)] bg-[var(--surface-strong)] p-12 lg:p-20 shadow-[var(--shadow-2xl)] border border-[var(--line-strong)] group transition-colors duration-500">
      {/* 애니메이션 글로우 배경 */}
      <div className="absolute -right-20 -top-20 h-96 w-96 rounded-full bg-[var(--accent-strong)] opacity-[0.05] dark:opacity-10 blur-[100px] group-hover:opacity-20 transition-all duration-1000" />
      <div className="absolute -left-20 -bottom-20 h-96 w-96 rounded-full bg-indigo-500 opacity-[0.05] dark:opacity-10 blur-[100px] group-hover:opacity-20 transition-all duration-1000" />
      
      <div className="relative z-10 grid gap-12 lg:grid-cols-[1.2fr_0.8fr] items-center">
        <div className="space-y-8">
          <div className="flex flex-wrap items-center gap-3">
            <span className="inline-flex items-center gap-2 rounded-xl border border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] px-5 py-2 text-[11px] font-bold tracking-[0.15em] text-[var(--accent-strong)] backdrop-blur-md">
              <span className="h-2.5 w-2.5 rounded-full bg-[var(--accent-strong)] animate-pulse" />
              {eyebrow}
            </span>
            <span className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-2 text-[11px] font-bold tracking-wider text-[var(--text-hint)] backdrop-blur-md">
              {localeLabel}
            </span>
            <span className="rounded-xl border border-indigo-500/30 bg-indigo-500/10 px-4 py-2 text-[11px] font-bold tracking-wider text-indigo-500 dark:text-indigo-400 backdrop-blur-md">
              {statusLabel}
            </span>
          </div>

          <div className="space-y-4">
            <h2 className="text-4xl font-[900] text-[var(--text-primary)] tracking-tighter sm:text-5xl lg:text-6xl leading-[1.1]">
              {title}<span className="text-[var(--accent-strong)]">.</span>
            </h2>
            <p className="max-w-2xl text-lg font-medium leading-relaxed text-[var(--text-secondary)] tracking-tight">
              &quot;{description}&quot;
            </p>
          </div>
        </div>

        <div className="relative">
          <div className="absolute -inset-4 rounded-[var(--radius-2xl)] bg-gradient-to-tr from-[var(--accent-strong)]/10 via-transparent to-indigo-500/10 blur-3xl opacity-50" />
          <div className="relative rounded-[2rem] border border-[var(--line-strong)] bg-[var(--surface)] p-10 backdrop-blur-3xl shadow-[var(--shadow-xl)]">
            <div className="flex items-center gap-4 mb-8">
              <div className="h-10 w-10 rounded-2xl bg-[var(--accent-strong)]/10 flex items-center justify-center text-[var(--accent-strong)] ring-1 ring-[var(--accent-strong)]/20 shadow-inner">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="m12 3-1.912 5.813a2 2 0 0 0 1.275 1.275L21 12l-5.813 1.912a2 2 0 0 0-1.275 1.275L12 21l-1.912-5.813a2 2 0 0 0-1.275-1.275L3 12l5.813-1.912a2 2 0 0 0 1.275-1.275L12 3Z"/></svg>
              </div>
              <p className="text-[11px] font-bold tracking-[0.3em] text-[var(--text-hint)]">범위 및 준비 상태</p>
            </div>
            
            <ul className="space-y-5">
              {items.map((item, i) => (
                <li key={i} className="flex items-start gap-4 text-sm font-medium text-[var(--text-secondary)] leading-relaxed group/item">
                  <span className="mt-1.5 h-2 w-2 rounded-full bg-[var(--accent-strong)] shadow-[var(--shadow-glow)] opacity-40 group-hover/item:opacity-100 group-hover/item:scale-125 transition-all shrink-0" />
                  {item}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
