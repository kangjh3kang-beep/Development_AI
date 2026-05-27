"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";
import {
  useProjectContextStore,
  LIFECYCLE_STAGES,
} from "@/store/useProjectContextStore";

/* ── Stage metadata ── */

interface StageDefinition {
  id: string;
  label: string;
  icon: React.ReactNode;
  route: string;
}

function getStages(locale: string, projectId: string): StageDefinition[] {
  const base = `/${locale}/projects/${projectId}`;
  return [
    { id: "site-analysis", label: "부지분석", icon: <MapPinIcon />, route: `${base}/site-analysis` },
    { id: "legal", label: "법규검토", icon: <ScaleIcon />, route: `${base}/legal` },
    { id: "design", label: "설계", icon: <PencilRulerIcon />, route: `${base}/design` },
    { id: "bim", label: "BIM", icon: <CubeIcon />, route: `${base}/bim` },
    { id: "construction", label: "시공계획", icon: <HardHatIcon />, route: `${base}/construction` },
    { id: "feasibility", label: "수지분석", icon: <TrendUpIcon />, route: `${base}/feasibility` },
    { id: "finance", label: "금융분석", icon: <BanknoteIcon />, route: `${base}/finance` },
    { id: "esg", label: "ESG", icon: <LeafIcon />, route: `${base}/esg` },
    { id: "permit", label: "인허가", icon: <FileCheckIcon />, route: `${base}/permit` },
    { id: "report", label: "보고서", icon: <FileTextIcon />, route: `${base}/report` },
  ];
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
    <div className="flex items-center gap-1.5 overflow-x-auto rounded-[var(--radius-lg)] border border-[var(--line-subtle)] bg-[var(--surface-muted)] p-1.5 scrollbar-hide">
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

function MapPinIcon() {
  return (
    <svg className="h-full w-full" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z" />
      <circle cx="12" cy="10" r="3" />
    </svg>
  );
}

function ScaleIcon() {
  return (
    <svg className="h-full w-full" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z" />
      <path d="m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z" />
      <path d="M7 21h10" />
      <path d="M12 3v18" />
      <path d="M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2" />
    </svg>
  );
}

function PencilRulerIcon() {
  return (
    <svg className="h-full w-full" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="m15 5 4 4" />
      <path d="M13 7 8.7 2.7a2.41 2.41 0 0 0-3.4 0L2.7 5.3a2.41 2.41 0 0 0 0 3.4L7 13" />
      <path d="m8 6 2-2" />
      <path d="m2 22 5.5-1.5L21.17 6.83a2.82 2.82 0 0 0-4-4L3.5 16.5Z" />
      <path d="m18 16 2-2" />
      <path d="m17 11 4.3 4.3c.94.94.94 2.46 0 3.4l-2.6 2.6c-.94.94-2.46.94-3.4 0L11 17" />
    </svg>
  );
}

function CubeIcon() {
  return (
    <svg className="h-full w-full" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
      <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
      <line x1="12" y1="22.08" x2="12" y2="12" />
    </svg>
  );
}

function HardHatIcon() {
  return (
    <svg className="h-full w-full" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2 18a1 1 0 0 0 1 1h18a1 1 0 0 0 1-1v-2a1 1 0 0 0-1-1H3a1 1 0 0 0-1 1v2z" />
      <path d="M10 15V6.5a3.5 3.5 0 0 1 7 0v0a3 3 0 0 1 3 3V15" />
      <path d="M4 15v-3a6 6 0 0 1 6-6" />
    </svg>
  );
}

function TrendUpIcon() {
  return (
    <svg className="h-full w-full" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" />
      <polyline points="16 7 22 7 22 13" />
    </svg>
  );
}

function BanknoteIcon() {
  return (
    <svg className="h-full w-full" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect width="20" height="12" x="2" y="6" rx="2" />
      <circle cx="12" cy="12" r="2" />
      <path d="M6 12h.01M18 12h.01" />
    </svg>
  );
}

function LeafIcon() {
  return (
    <svg className="h-full w-full" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M11 20A7 7 0 0 1 9.8 6.9C15.5 4.9 17 3.5 19 2c1 2 2 4.5 2 8 0 5.5-4.78 10-10 10Z" />
      <path d="M2 21c0-3 1.85-5.36 5.08-6C9.5 14.52 12 13 13 12" />
    </svg>
  );
}

function FileCheckIcon() {
  return (
    <svg className="h-full w-full" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" />
      <path d="M14 2v4a2 2 0 0 0 2 2h4" />
      <path d="m9 15 2 2 4-4" />
    </svg>
  );
}

function FileTextIcon() {
  return (
    <svg className="h-full w-full" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" />
      <path d="M14 2v4a2 2 0 0 0 2 2h4" />
      <path d="M10 9H8" />
      <path d="M16 13H8" />
      <path d="M16 17H8" />
    </svg>
  );
}

function CheckCircleIcon() {
  return (
    <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
      <polyline points="22 4 12 14.01 9 11.01" />
    </svg>
  );
}
