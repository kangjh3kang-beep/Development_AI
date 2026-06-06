"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { LIFECYCLE_STAGES, STAGE_META } from "@/lib/lifecycle-stages";
import { StageIcon } from "@/components/common/StageIcon";

/* ── Stage metadata (SSOT: lib/lifecycle-stages) ── */

interface StageDefinition {
  id: string;
  label: string;
  icon: React.ReactNode;
  route: string;
}

function getStages(locale: string, projectId: string): StageDefinition[] {
  const base = `/${locale}/projects/${projectId}`;
  return LIFECYCLE_STAGES.map((id) => {
    const meta = STAGE_META[id];
    return {
      id,
      label: meta.label,
      icon: <StageIcon id={meta.icon} size={20} />,
      route: `${base}/${meta.route}`,
    };
  });
}

/* ── Pipeline Component ── */

export function ProjectLifecyclePipeline({
  locale,
  projectId,
  compact = false,
}: {
  locale: string;
  projectId: string;
  compact?: boolean;
}) {
  const pathname = usePathname();
  const completedStages = useProjectContextStore((s) => s.completedStages);
  const currentStage = useProjectContextStore((s) => s.currentStage);
  const getNextRecommendedStage = useProjectContextStore(
    (s) => s.getNextRecommendedStage,
  );

  const stages = getStages(locale, projectId);
  const nextStage = getNextRecommendedStage();

  // Determine active stage from current route
  const activeRouteStage = stages.find((s) => pathname.startsWith(s.route));

  function getStageStatus(stageId: string): "completed" | "current" | "next" | "pending" {
    if (completedStages.includes(stageId)) return "completed";
    if (activeRouteStage?.id === stageId || currentStage === stageId) return "current";
    if (nextStage === stageId) return "next";
    return "pending";
  }

  if (compact) {
    return (
      <CompactPipeline
        stages={stages}
        getStageStatus={getStageStatus}
        nextStage={nextStage}
      />
    );
  }

  return (
    <div className="w-full">
      {/* Desktop: horizontal pipeline */}
      <div className="hidden md:block">
        <div className="relative flex items-center gap-0 overflow-x-auto rounded-[var(--radius-2xl)] border border-[var(--line)] bg-[var(--surface-soft)] p-3 shadow-[var(--shadow-lg)] backdrop-blur-3xl scrollbar-hide">
          {stages.map((stage, index) => {
            const status = getStageStatus(stage.id);
            return (
              <div key={stage.id} className="flex items-center">
                <StageNode
                  stage={stage}
                  status={status}
                  index={index}
                  isNext={stage.id === nextStage}
                />
                {index < stages.length - 1 && (
                  <StageConnector
                    completed={completedStages.includes(stage.id)}
                  />
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Mobile: vertical pipeline */}
      <div className="block md:hidden">
        <div className="grid gap-2 rounded-[var(--radius-2xl)] border border-[var(--line)] bg-[var(--surface-soft)] p-4 shadow-[var(--shadow-lg)]">
          {stages.map((stage, index) => {
            const status = getStageStatus(stage.id);
            return (
              <div key={stage.id}>
                <MobileStageRow
                  stage={stage}
                  status={status}
                  index={index}
                  isNext={stage.id === nextStage}
                  isLast={index === stages.length - 1}
                />
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

/* ── Desktop Stage Node ── */

function StageNode({
  stage,
  status,
  index,
  isNext,
}: {
  stage: StageDefinition;
  status: "completed" | "current" | "next" | "pending";
  index: number;
  isNext: boolean;
}) {
  const baseClasses =
    "relative flex flex-col items-center gap-2 rounded-[var(--radius-xl)] px-4 py-3 transition-all duration-300 min-w-[90px]";

  const statusClasses = {
    completed:
      "bg-[var(--accent-strong)]/10 text-[var(--accent-strong)] cursor-pointer hover:bg-[var(--accent-strong)]/20 hover:scale-105",
    current:
      "bg-[var(--accent-strong)]/15 text-[var(--accent-strong)] ring-2 ring-[var(--accent-strong)]/40 shadow-[var(--shadow-glow)]",
    next: "bg-[var(--surface-muted)] text-[var(--text-secondary)] cursor-pointer hover:bg-[var(--surface-strong)] hover:text-[var(--accent-strong)] border border-dashed border-[var(--accent-strong)]/30",
    pending:
      "bg-[var(--surface-muted)] text-[var(--text-hint)] opacity-60",
  };

  const content = (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05, duration: 0.3 }}
      className={`${baseClasses} ${statusClasses[status]}`}
    >
      {/* Pulsing ring for current stage */}
      {status === "current" && (
        <span className="absolute -right-1 -top-1 flex h-3 w-3">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[var(--accent-strong)] opacity-50" />
          <span className="relative inline-flex h-3 w-3 rounded-full bg-[var(--accent-strong)]" />
        </span>
      )}

      {/* Icon */}
      <div className="relative flex h-8 w-8 items-center justify-center">
        {status === "completed" ? (
          <CheckCircleIcon />
        ) : (
          <span className="h-5 w-5">{stage.icon}</span>
        )}
      </div>

      {/* Label */}
      <span className="text-[10px] font-bold uppercase tracking-[0.1em] leading-tight text-center whitespace-nowrap">
        {stage.label}
      </span>
    </motion.div>
  );

  if (status === "completed" || status === "next" || status === "current") {
    return <Link href={stage.route}>{content}</Link>;
  }

  return content;
}

/* ── Desktop Connector ── */

function StageConnector({ completed }: { completed: boolean }) {
  return (
    <div className="flex items-center px-0.5">
      <div
        className={`h-0.5 w-4 transition-colors duration-500 ${
          completed
            ? "bg-[var(--accent-strong)]"
            : "bg-[var(--line)]"
        }`}
      />
      <svg
        className={`h-3 w-3 -ml-1 transition-colors duration-500 ${
          completed
            ? "text-[var(--accent-strong)]"
            : "text-[var(--line)]"
        }`}
        viewBox="0 0 12 12"
        fill="currentColor"
      >
        <path d="M4 2l4 4-4 4" />
      </svg>
    </div>
  );
}

/* ── Mobile Stage Row ── */

function MobileStageRow({
  stage,
  status,
  index,
  isNext,
  isLast,
}: {
  stage: StageDefinition;
  status: "completed" | "current" | "next" | "pending";
  index: number;
  isNext: boolean;
  isLast: boolean;
}) {
  const statusColors = {
    completed: "border-[var(--accent-strong)]/40 bg-[var(--accent-strong)]/10",
    current: "border-[var(--accent-strong)] bg-[var(--accent-strong)]/15 shadow-[var(--shadow-glow)]",
    next: "border-dashed border-[var(--accent-strong)]/30 bg-[var(--surface-muted)]",
    pending: "border-[var(--line)] bg-[var(--surface-muted)] opacity-60",
  };

  const textColors = {
    completed: "text-[var(--accent-strong)]",
    current: "text-[var(--accent-strong)]",
    next: "text-[var(--text-secondary)]",
    pending: "text-[var(--text-hint)]",
  };

  const inner = (
    <motion.div
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.04, duration: 0.25 }}
      className={`flex items-center gap-3 rounded-[var(--radius-xl)] border px-4 py-3 transition-all duration-300 ${statusColors[status]}`}
    >
      {/* Status indicator */}
      <div className={`flex h-7 w-7 shrink-0 items-center justify-center ${textColors[status]}`}>
        {status === "completed" ? (
          <CheckCircleIcon />
        ) : (
          <span className="h-4 w-4">{stage.icon}</span>
        )}
      </div>

      {/* Label */}
      <span className={`text-xs font-bold tracking-wide ${textColors[status]}`}>
        {stage.label}
      </span>

      {/* Current pulse */}
      {status === "current" && (
        <span className="ml-auto flex h-2.5 w-2.5">
          <span className="absolute inline-flex h-2.5 w-2.5 animate-ping rounded-full bg-[var(--accent-strong)] opacity-50" />
          <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-[var(--accent-strong)]" />
        </span>
      )}
    </motion.div>
  );

  if (status === "completed" || status === "next" || status === "current") {
    return <Link href={stage.route}>{inner}</Link>;
  }

  return inner;
}

/* ── Compact Pipeline (for layout breadcrumb) ── */

function CompactPipeline({
  stages,
  getStageStatus,
  nextStage,
}: {
  stages: StageDefinition[];
  getStageStatus: (id: string) => "completed" | "current" | "next" | "pending";
  nextStage: string | null;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1.5 rounded-[var(--radius-lg)] border border-[var(--line-subtle)] bg-[var(--surface-muted)] p-1.5">
      {stages.map((stage, index) => {
        const status = getStageStatus(stage.id);

        const dotColors = {
          completed: "bg-[var(--accent-strong)]",
          current: "bg-[var(--accent-strong)] ring-2 ring-[var(--accent-strong)]/30",
          next: "bg-[var(--text-hint)] ring-1 ring-dashed ring-[var(--accent-strong)]/30",
          pending: "bg-[var(--line)]",
        };

        const canNavigate = status === "completed" || status === "current" || status === "next";

        const dot = (
          <div
            className="group relative flex items-center"
            title={stage.label}
          >
            <div
              className={`h-2.5 w-2.5 rounded-full transition-all duration-300 ${dotColors[status]} ${
                canNavigate ? "cursor-pointer hover:scale-150" : ""
              }`}
            />
            {/* Tooltip */}
            <div className="pointer-events-none absolute -top-8 left-1/2 -translate-x-1/2 rounded-lg bg-[var(--surface-strong)] px-2.5 py-1 text-[10px] font-bold text-[var(--text-primary)] opacity-0 shadow-[var(--shadow-lg)] transition-opacity group-hover:opacity-100 whitespace-nowrap border border-[var(--line)]">
              {stage.label}
            </div>
            {/* Connector */}
            {index < stages.length - 1 && (
              <div
                className={`mx-0.5 h-px w-3 ${
                  status === "completed"
                    ? "bg-[var(--accent-strong)]"
                    : "bg-[var(--line)]"
                }`}
              />
            )}
          </div>
        );

        if (canNavigate) {
          return (
            <Link key={stage.id} href={stage.route} className="flex items-center">
              {dot}
            </Link>
          );
        }

        return <div key={stage.id} className="flex items-center">{dot}</div>;
      })}
    </div>
  );
}

/* ── SVG Icons (inline, no external deps) ── */

function CheckCircleIcon() {
  return (
    <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
      <polyline points="22 4 12 14.01 9 11.01" />
    </svg>
  );
}
