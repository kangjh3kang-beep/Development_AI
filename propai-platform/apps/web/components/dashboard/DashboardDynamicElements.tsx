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
    <div className="grid gap-8 md:grid-cols-3">
      {items.map((item, i) => (
        <TiltCard
          key={i}
          className={`group rounded-[2.5rem] border ${item.border} ${item.bg} p-8 shadow-[var(--shadow-lg)] hover:shadow-[var(--shadow-glow)] backdrop-blur-md`}
          maxTilt={6}
        >
          {/* Cyber Hover Glow */}
          <div className="absolute inset-0 bg-gradient-to-br from-white/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 rounded-[2.5rem]" />
          <div className="relative z-10 flex items-center justify-between">
            <span className="text-xs font-bold tracking-[0.1em] text-[var(--text-tertiary)]">
              {item.label}
            </span>
            {item.trend ? (
              <span
                className={`text-[11px] font-bold ${item.color} px-2.5 py-1 rounded-full bg-white/10 dark:bg-black/20`}
              >
                {item.trend}
              </span>
            ) : null}
          </div>
          <div className="mt-6 flex items-baseline gap-2">
            <AnimatedCounter
              value={item.value}
              decimals={item.decimals}
              duration={1400}
              className="text-5xl font-[900] tracking-tighter text-[var(--text-primary)]"
            />
            <span className="text-xl font-semibold text-[var(--text-tertiary)]">
              {item.unit}
            </span>
          </div>
          <p className="mt-4 text-[11px] font-semibold text-[var(--text-hint)] uppercase tracking-wider">
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
              <div className="flex justify-between text-[11px] font-semibold text-[var(--text-hint)]">
                <span>전체 진행률</span>
                <span>{proj.progress}%</span>
              </div>
              <div className="h-1.5 w-full rounded-full bg-[var(--line)]">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-[var(--accent)] to-blue-500 transition-all duration-1000 group-hover:w-full"
                  style={{ width: `${proj.progress}%` }}
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
