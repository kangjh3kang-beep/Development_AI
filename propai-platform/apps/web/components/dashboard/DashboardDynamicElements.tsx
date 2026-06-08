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
    <div className="grid gap-4 md:grid-cols-3">
      {items.map((item, i) => {
        // 값이 0이면(아직 데이터 없음) 0.0 나열 대신 줄표(—)로 정직하게 표기
        const isEmpty = item.value === 0;
        return (
          <div key={i} className="db-kpi">
            <div className="flex items-center justify-between">
              <span className="db-eyebrow">{item.label}</span>
              {item.trend ? (
                <span className="db-kpi__unit text-[11px] font-semibold text-[var(--text-tertiary)]">
                  {item.trend}
                </span>
              ) : null}
            </div>

            <div className="mt-5 flex items-baseline gap-1.5">
              {isEmpty ? (
                <span className="db-kpi__placeholder">—</span>
              ) : (
                <>
                  <AnimatedCounter
                    value={item.value}
                    decimals={item.decimals}
                    duration={1400}
                    className="db-kpi__value"
                  />
                  <span className="db-kpi__unit">{item.unit}</span>
                </>
              )}
            </div>

            <p className="mt-3 db-kpi__sub">
              {isEmpty ? "프로젝트 생성 시 표시됩니다" : item.sub}
            </p>
          </div>
        );
      })}
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
