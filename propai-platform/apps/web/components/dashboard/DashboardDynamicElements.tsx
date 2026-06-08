"use client";

import { AnimatedCounter } from "@/components/ui/AnimatedCounter";
import { TiltCard } from "@/components/ui/TiltCard";
import { GridBackground } from "@/components/ui/GridBackground";
import Link from "next/link";
import type { ReactNode } from "react";

/* ── KPI Card with AnimatedCounter ── */

interface KpiItem {
  label: string;
  value: number;
  decimals: number;
  unit: string;
  trend: string;
  sub: string;
  color: string;
  bg: string;
  border: string;
}

export function KpiGrid({ items }: { items: KpiItem[] }) {
  return (
    <div className="grid gap-6 md:grid-cols-3">
      {items.map((item, i) => (
        <TiltCard
          key={i}
          className={`cc-bracketed cc-interactive group rounded-[var(--radius-md)] border ${item.border} ${item.bg} p-7 shadow-[var(--shadow-md)] overflow-hidden`}
          maxTilt={4}
        >
          {/* HUD 정밀 그리드 배경 + 코너 브래킷(계기판 디테일) */}
          <div className="cc-grid-bg opacity-50" />
          <i className="cc-bracket cc-bracket--tl" />
          <i className="cc-bracket cc-bracket--tr" />
          <i className="cc-bracket cc-bracket--bl" />
          <i className="cc-bracket cc-bracket--br" />

          <div className="relative z-10 flex items-center justify-between">
            <span className="cc-label">{item.label}</span>
            {item.trend ? (
              <span className={`cc-num text-[11px] font-bold ${item.color} px-2.5 py-1 rounded-md bg-white/10 dark:bg-black/20`}>
                {item.trend}
              </span>
            ) : null}
          </div>

          <div className="mt-6 flex items-baseline gap-2">
            <AnimatedCounter
              value={item.value}
              decimals={item.decimals}
              duration={1400}
              className="cc-num text-5xl font-[900]"
            />
            <span className="cc-num text-lg font-semibold text-[var(--text-tertiary)]">
              {item.unit}
            </span>
          </div>

          <p className="mt-4 cc-label text-[10px] text-[var(--text-hint)]">
            {item.sub}
          </p>
        </TiltCard>
      ))}
    </div>
  );
}

/* ── Project Card with TiltCard ── */

interface ProjectItem {
  id: string;
  name: string;
  status: string;
  value: string;
  tag: string;
  progress: number;
}

export function ProjectCardGrid({
  projects,
  locale,
}: {
  projects: readonly ProjectItem[];
  locale: string;
}) {
  return (
    <div className="grid gap-6 sm:grid-cols-2">
      {projects.map((proj) => (
        <TiltCard
          key={proj.id}
          className="group rounded-[2rem] border border-[var(--line-strong)] bg-[var(--surface-soft)] shadow-[var(--shadow-md)] hover:shadow-[var(--shadow-glow)] backdrop-blur-lg"
          maxTilt={5}
        >
          <Link
            href={`/${locale}/projects/${proj.id}`}
            className="relative block p-8 overflow-hidden"
          >
            <div className="absolute inset-0 bg-[var(--accent-soft)] opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
            <div className="relative z-10 flex items-center justify-between mb-6">
              <span className="rounded-lg bg-[var(--surface-muted)] px-3 py-1 text-[11px] font-bold text-[var(--text-tertiary)]">
                {proj.tag}
              </span>
              <div className="h-8 w-8 rounded-full border border-[var(--line)] flex items-center justify-center transition-all group-hover:bg-[var(--accent)] group-hover:border-[var(--accent)]">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="3"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="text-[var(--text-primary)] group-hover:text-white transition-colors"
                >
                  <path d="m9 18 6-6-6-6" />
                </svg>
              </div>
            </div>
            <h4 className="text-lg font-bold text-[var(--text-primary)] leading-tight mb-2">
              {proj.name}
            </h4>
            <p className="text-[11px] font-bold text-[var(--accent-strong)] tracking-wider mb-8">
              {proj.status}
            </p>

            <div className="space-y-2">
              <div className="flex justify-between items-center">
                <span className="cc-label text-[10px]">PROGRESS</span>
                <span className="cc-num text-[12px] font-bold text-[var(--data-accent)]">{proj.progress}%</span>
              </div>
              <div className="h-1.5 w-full rounded-full bg-[var(--line)] overflow-hidden">
                <div
                  className="h-full rounded-full bg-[var(--data-accent)] transition-all duration-1000"
                  style={{ width: `${proj.progress}%`, boxShadow: "var(--data-glow)" }}
                />
              </div>
            </div>
          </Link>
        </TiltCard>
      ))}
    </div>
  );
}

/* ── Hero Grid Background wrapper ── */

export function HeroGridBackground() {
  return <GridBackground className="z-[1]" />;
}
