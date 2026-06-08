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
  // 모든 지표가 비어 있으면(값 0) 카드마다 안내문을 반복하지 않고
  // 묶음 하단에 한 번만 통합 안내를 보여 준다(H1: 와이어프레임 인상 제거).
  const allEmpty = items.every((it) => it.value === 0);

  return (
    <div className="space-y-3">
      <div className="grid gap-4 md:grid-cols-3">
        {items.map((item, i) => {
          // 값이 0이면(아직 데이터 없음) 회색 바 대신 흐린 줄표(—)를
          // 라벨과 같은 좌측 기준선에 정렬해 절제 있게 표기한다.
          const isEmpty = item.value === 0;
          return (
            <div key={i} className="db-kpi">
              <div className="flex items-center justify-between">
                <span className="db-eyebrow db-eyebrow--ko">{item.label}</span>
                {!isEmpty && item.trend ? (
                  <span className="db-kpi__unit text-[11px] font-semibold text-[var(--text-tertiary)]">
                    {item.trend}
                  </span>
                ) : null}
              </div>

              <div className="mt-5 flex items-baseline gap-1.5">
                {isEmpty ? (
                  <span className="db-kpi__placeholder" aria-label="데이터 없음">—</span>
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

              {/* 채워진 지표에만 부연 설명. 빈 지표는 하단 통합 안내로 대체 */}
              {!isEmpty ? <p className="mt-3 db-kpi__sub">{item.sub}</p> : null}
            </div>
          );
        })}
      </div>

      {/* 빈상태 통합 안내 — 카드별 반복 대신 한 줄로 */}
      {allEmpty ? (
        <p className="db-kpi__sub text-center text-[var(--text-tertiary)]">
          첫 프로젝트를 생성하면 지표가 채워집니다.
        </p>
      ) : null}
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
            {/* 상태 라벨 — 한글이므로 양수 트래킹 제거(C3) */}
            <p className="text-[12px] font-semibold text-[var(--accent-strong)] mb-8">
              {proj.status}
            </p>

            <div className="space-y-2">
              {/* 진행률 — 네온 시안 폐기, 단일 파랑(C2) + 한국어 라벨(C3) */}
              <div className="flex justify-between items-center">
                <span className="text-[11px] font-semibold text-[var(--text-tertiary)]">진행률</span>
                <span className="text-[12px] font-bold tabular-nums text-[var(--accent-strong)]">{proj.progress}%</span>
              </div>
              <div className="h-1.5 w-full rounded-full bg-[var(--line)] overflow-hidden">
                <div
                  className="h-full rounded-full bg-[var(--accent-strong)] transition-all duration-1000"
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
