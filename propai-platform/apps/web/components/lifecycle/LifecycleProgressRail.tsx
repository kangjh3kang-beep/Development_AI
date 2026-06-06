"use client";

/**
 * 라이프사이클 진행 레일 — 10단계 여정 가시화(스토어 단일 source).
 *
 * useProjectContextStore에 이미 존재하는 LIFECYCLE_STAGES·completedStages·
 * currentStage·getNextRecommendedStage 자산을 시각화하는 "뷰"다.
 *   - 완료(채움) / 현재(강조·링) / 다음추천(펄스·점선) / 미시작(흐림)
 *   - 각 단계 클릭 → 해당 프로젝트 상세 탭으로 이동(기존 네비 경로 재사용)
 *   - 활성 프로젝트가 없으면 렌더하지 않음(대시보드 무파괴)
 *
 * 디자인 토큰만 사용(하드코딩 hex 없음). 가로/세로 방향 지원.
 */

import Link from "next/link";
import { motion } from "framer-motion";
import {
  useProjectContextStore,
  LIFECYCLE_STAGES,
  type LifecycleStage,
} from "@/store/useProjectContextStore";
import { StageIcon } from "@/components/common/StageIcon";

type StageStatus = "completed" | "current" | "next" | "pending";

/** 스토어 단계 id → 프로젝트 상세 라우트 세그먼트 + StageIcon 아이콘 키 + 라벨 */
const STAGE_META: Record<LifecycleStage, { route: string; icon: string; label: string }> = {
  "site-analysis": { route: "site-analysis", icon: "site_analysis", label: "부지분석" },
  legal: { route: "legal", icon: "legal_compliance", label: "법규검토" },
  design: { route: "design", icon: "design_ai", label: "설계" },
  bim: { route: "bim", icon: "design_ai", label: "BIM" },
  construction: { route: "construction", icon: "construction", label: "시공계획" },
  feasibility: { route: "feasibility", icon: "feasibility", label: "수지분석" },
  finance: { route: "finance", icon: "feasibility", label: "금융분석" },
  esg: { route: "esg", icon: "esg_dashboard", label: "ESG" },
  permit: { route: "permit", icon: "permit_portal", label: "인허가" },
  report: { route: "report", icon: "permit_portal", label: "보고서" },
};

const STATUS_NODE: Record<StageStatus, string> = {
  completed:
    "bg-[var(--accent-strong)]/10 text-[var(--accent-strong)] hover:bg-[var(--accent-strong)]/20",
  current:
    "bg-[var(--accent-strong)]/15 text-[var(--accent-strong)] ring-2 ring-[var(--accent-strong)]/40 shadow-[var(--shadow-glow)]",
  next:
    "bg-[var(--surface-muted)] text-[var(--text-secondary)] border border-dashed border-[var(--accent-strong)]/40 hover:text-[var(--accent-strong)]",
  pending: "bg-[var(--surface-muted)] text-[var(--text-hint)] opacity-60",
};

export function LifecycleProgressRail({
  locale,
  orientation = "horizontal",
  className = "",
}: {
  locale: string;
  orientation?: "horizontal" | "vertical";
  className?: string;
}) {
  const projectId = useProjectContextStore((s) => s.projectId);
  const projectName = useProjectContextStore((s) => s.projectName);
  const completedStages = useProjectContextStore((s) => s.completedStages);
  const currentStage = useProjectContextStore((s) => s.currentStage);
  const getNextRecommendedStage = useProjectContextStore((s) => s.getNextRecommendedStage);

  // 활성 프로젝트가 없으면 표시하지 않는다(대시보드/레이아웃 무파괴).
  if (!projectId) return null;

  const nextStage = getNextRecommendedStage();
  const completedCount = LIFECYCLE_STAGES.filter((id) => completedStages.includes(id)).length;
  const pct = Math.round((completedCount / LIFECYCLE_STAGES.length) * 100);

  function statusOf(id: LifecycleStage): StageStatus {
    if (completedStages.includes(id)) return "completed";
    if (currentStage === id) return "current";
    if (nextStage === id) return "next";
    return "pending";
  }

  const isVertical = orientation === "vertical";

  return (
    <section
      className={`rounded-[var(--radius-2xl)] border border-[var(--line)] bg-[var(--surface-soft)] p-4 shadow-[var(--shadow-lg)] ${className}`}
      aria-label="프로젝트 라이프사이클 진행 현황"
    >
      <header className="mb-3 flex items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="text-[10px] font-black uppercase tracking-[0.25em] text-[var(--accent-strong)]">
            라이프사이클 진행
          </p>
          {projectName && (
            <p className="truncate text-[13px] font-bold text-[var(--text-primary)]">{projectName}</p>
          )}
        </div>
        <span className="shrink-0 rounded-full border border-[var(--line)] bg-[var(--surface-muted)] px-3 py-1 text-[11px] font-bold text-[var(--text-secondary)]">
          {completedCount}/{LIFECYCLE_STAGES.length} · {pct}%
        </span>
      </header>

      {/* 진행 바 */}
      <div className="mb-4 h-1.5 w-full overflow-hidden rounded-full bg-[var(--surface-muted)]">
        <div
          className="h-full rounded-full bg-[var(--accent-strong)] transition-[width] duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>

      <ol
        className={
          isVertical
            ? "flex flex-col gap-1.5"
            : // 10단계를 모두 보이게 — 잘림(scrollbar-hide+overflow) 대신 wrap 어포던스.
              "flex flex-wrap items-center gap-y-2 gap-x-1"
        }
      >
        {LIFECYCLE_STAGES.map((id, index) => {
          const meta = STAGE_META[id];
          const status = statusOf(id);
          const navigable = status !== "pending";

          const node = (
            <motion.div
              initial={{ opacity: 0, y: isVertical ? 0 : 8, x: isVertical ? -8 : 0 }}
              animate={{ opacity: 1, y: 0, x: 0 }}
              transition={{ delay: index * 0.04, duration: 0.25 }}
              className={`relative flex items-center gap-2 rounded-[var(--radius-xl)] px-3 py-2 transition-all duration-300 ${
                isVertical ? "w-full" : "min-w-[88px] flex-col text-center"
              } ${STATUS_NODE[status]} ${navigable ? "cursor-pointer" : ""}`}
              title={meta.label}
            >
              {status === "current" && (
                <span className="absolute -right-1 -top-1 flex h-3 w-3" aria-hidden="true">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[var(--accent-strong)] opacity-50" />
                  <span className="relative inline-flex h-3 w-3 rounded-full bg-[var(--accent-strong)]" />
                </span>
              )}
              {status === "next" && (
                <span className="absolute -right-1 -top-1 flex h-2.5 w-2.5" aria-hidden="true">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[var(--accent-strong)] opacity-40" />
                  <span className="relative inline-flex h-2.5 w-2.5 rounded-full border border-[var(--accent-strong)] bg-[var(--surface)]" />
                </span>
              )}
              <span className="flex h-6 w-6 items-center justify-center">
                {status === "completed" ? (
                  <svg
                    width={18}
                    height={18}
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  >
                    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                    <polyline points="22 4 12 14.01 9 11.01" />
                  </svg>
                ) : (
                  <StageIcon id={meta.icon} size={18} />
                )}
              </span>
              <span className="text-[10px] font-bold uppercase leading-tight tracking-[0.08em]">
                {meta.label}
              </span>
            </motion.div>
          );

          const cell = navigable ? (
            <Link href={`/${locale}/projects/${projectId}/${meta.route}`} className="block">
              {node}
            </Link>
          ) : (
            node
          );

          return (
            <li key={id} className={isVertical ? "" : "flex items-center"}>
              {cell}
              {!isVertical && index < LIFECYCLE_STAGES.length - 1 && (
                <span
                  aria-hidden="true"
                  className={`mx-0.5 h-0.5 w-3 shrink-0 rounded-full ${
                    completedStages.includes(id)
                      ? "bg-[var(--accent-strong)]"
                      : "bg-[var(--line)]"
                  }`}
                />
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
